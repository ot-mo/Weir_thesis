"""Pre-registered analysis of the coordination protocol (no API calls).

Final analysis, on the sealed test battery's scores:
    python analyze_protocol.py --scores results/coordination/sealed_test/scores_<stamp>.csv --runs RUN1 RUN2 ...
Dry run of the same code on the validation batteries (held-out as the
development-range part, beyond as the single beyond level), to check the code
before the protocol runs - its numbers are not results:
    python analyze_protocol.py --dry-run --runs window50_run1 window50_run2 window50_run3

Statistics (fixed in results/coordination/PROTOCOL.md):
- H0,1 / RQ1: mean paired difference LLM - tuned MPC over policies and
  development-range scenarios, 95 % CI from a hierarchical bootstrap
  (resample policies, then scenarios). H0,1 is rejected if the CI excludes 0.
  Equivalence: the 90 % CI lies inside +-10 % of the tuned MPC's mean (TOST).
- H0,2 / RQ2: slope of mean log(1 + score) against amplitude level (1 =
  development range, 1.25, 1.5, 2; disturbance scenarios only), LLM (mean
  over policies) minus tuned MPC, 95 % CI from the same bootstrap with
  scenarios resampled within each level. H0,2 is rejected if the CI excludes 0.
- C3: per-policy mean scores (median, IQR, range), their SD with a bootstrap
  CI, and the number of runs with no promotion.
- Secondary: per-metric paired differences on the development range,
  bootstrap p-values, Holm-adjusted; unseen periods and combinations as
  LLM/MPC score ratios with CIs.
"""

import argparse
import csv
import dataclasses
import json
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import four_tank_coordination as C
from mpc_supervisor import MPCSupervisor, tuned_params
from supervisor_security import safe_exec_supervisor

B = 10000
SEED = 7
COMPARATOR = "mpc_tuned"
EQUIVALENCE_MARGIN = 0.10
DEV_PARTS = ("dev", "nominal")
LEVELS = {"dev": 1.0, "x1.25": 1.25, "x1.5": 1.5, "x2": 2.0}
METRICS = ("production_iae_l", "band_violation_s", "upper_violation_s", "safety_violation_s", "setpoint_tv_m",
           "saturation_s", "recovery_s", "wrapper_interventions")
SUPERVISORS_DIR = "generated_supervisors_coordination"
RESULTS_DIR = os.path.join("results", "coordination")


# -- data ----------------------------------------------------------------------
def _dry_run_job(job):
    name, part, scenario, source = job
    if name == "fixed_recipe":
        fn = C.fixed_recipe_supervisor
    elif name == "mpc_untuned":
        fn = MPCSupervisor()
    elif name == "mpc_tuned":
        fn = MPCSupervisor(**tuned_params())
    else:
        fn, _ = safe_exec_supervisor(source)
    if name.startswith("mpc"):
        scenario = dataclasses.replace(scenario, supervisor_timeout_s=10.0)
    m = C.run_episode(fn, scenario)["metrics"]
    if part == "dev" and scenario.range_label == "nominal":
        part = "nominal"
    return {"controller": name, "scenario": scenario.name, "part": part, "kind": scenario.kind_label,
            "pattern": scenario.pattern_label, **m, "score": C.score(m)}


def dry_run_scores(runs):
    """Validation batteries standing in for the test battery: held-out as the
    development-range part and beyond as level 'x2' (the only beyond level)."""
    sources = {r: open(os.path.join(SUPERVISORS_DIR, r, "current_supervisor.py"), encoding="utf-8").read() for r in runs}
    parts = {"dev": C.make_battery("dev", 3, 2), "x2": C.make_battery("beyond", 3, 3)}
    controllers = list(runs) + ["fixed_recipe", "mpc_untuned", COMPARATOR]
    jobs = [(n, part, sc, sources.get(n)) for n in controllers for part, scen in parts.items() for sc in scen]
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as pool:
        return list(pool.map(_dry_run_job, jobs, chunksize=4))


def load_scores(path):
    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in METRICS + ("score",):
            r[k] = float(r[k])
    return rows


def _matrix(rows, controllers, parts, key="score"):
    """controllers x scenarios array over the given parts (same scenario order for all)."""
    scen = sorted({r["scenario"] for r in rows if r["part"] in parts})
    idx = {(r["controller"], r["scenario"]): r[key] for r in rows if r["part"] in parts}
    return np.array([[idx[(c, s)] for s in scen] for c in controllers]), scen


# -- statistics ----------------------------------------------------------------
def hier_bootstrap(llm, ref, stat, rng, b=B):
    """llm: policies x scenarios, ref: scenarios. Resample policies, then scenarios."""
    p, s = llm.shape
    out = np.empty(b)
    for i in range(b):
        pi, si = rng.integers(p, size=p), rng.integers(s, size=s)
        out[i] = stat(llm[np.ix_(pi, si)], ref[si])
    return out


def h01(rows, runs, rng):
    llm, _ = _matrix(rows, runs, DEV_PARTS)
    ref, _ = _matrix(rows, [COMPARATOR], DEV_PARTS)
    ref = ref[0]
    diff = lambda a, r: float(a.mean() - r.mean())
    boot = hier_bootstrap(llm, ref, diff, rng)
    est, margin = diff(llm, ref), EQUIVALENCE_MARGIN * ref.mean()
    ci95, ci90 = np.percentile(boot, [2.5, 97.5]), np.percentile(boot, [5, 95])
    return {"llm_mean": float(llm.mean()), "mpc_mean": float(ref.mean()), "difference": est,
            "ci95": ci95.tolist(), "ci90": ci90.tolist(), "margin": float(margin),
            "reject_h01": bool(ci95[0] > 0 or ci95[1] < 0),
            "equivalent": bool(ci90[0] > -margin and ci90[1] < margin)}


def h02(rows, runs, rng):
    levels = [lv for lv in LEVELS if any(r["part"] == lv for r in rows)]
    x = np.array([LEVELS[lv] for lv in levels])
    data = []
    for lv in levels:
        sc = sorted({r["scenario"] for r in rows if r["part"] == lv and r["kind"] != "nominal"})
        idx = {(r["controller"], r["scenario"]): r["score"] for r in rows if r["part"] == lv}
        llm = np.log1p(np.array([[idx[(c, s)] for s in sc] for c in runs]))
        ref = np.log1p(np.array([idx[(COMPARATOR, s)] for s in sc]))
        data.append((llm, ref))
    slope = lambda ys: float(np.polyfit(x, ys, 1)[0]) if len(x) > 1 else float("nan")

    def stat(sel_p, sel_s):
        llm_means = [d[0][np.ix_(sel_p, s)].mean() for d, s in zip(data, sel_s)]
        ref_means = [d[1][s].mean() for d, s in zip(data, sel_s)]
        return slope(llm_means) - slope(ref_means), llm_means, ref_means

    p = len(runs)
    est, llm_means, ref_means = stat(np.arange(p), [np.arange(d[1].size) for d in data])
    boot = np.empty(B)
    for i in range(B):
        boot[i] = stat(rng.integers(p, size=p), [rng.integers(d[1].size, size=d[1].size) for d in data])[0]
    ci = np.percentile(boot, [2.5, 97.5])
    return {"levels": levels, "llm_mean_log": [float(v) for v in llm_means], "mpc_mean_log": [float(v) for v in ref_means],
            "slope_difference": est, "ci95": ci.tolist(), "reject_h02": bool(ci[0] > 0 or ci[1] < 0)}


def c3(rows, runs, rng):
    llm, _ = _matrix(rows, runs, DEV_PARTS)
    per_policy = llm.mean(axis=1)
    boot = np.array([np.std(per_policy[rng.integers(len(runs), size=len(runs))], ddof=1) for _ in range(B)])
    promotions = {}
    for r in runs:
        path = os.path.join(RESULTS_DIR, r, "trials.jsonl")
        trials = [json.loads(l) for l in open(path, encoding="utf-8")] if os.path.exists(path) else []
        promotions[r] = sum(t["decision"] == "PROMOTED" for t in trials)
    q1, med, q3 = np.percentile(per_policy, [25, 50, 75])
    return {"per_policy": dict(zip(runs, per_policy.round(2).tolist())), "median": float(med), "iqr": [float(q1), float(q3)],
            "range": [float(per_policy.min()), float(per_policy.max())], "sd": float(np.std(per_policy, ddof=1)),
            "sd_ci95": np.percentile(boot, [2.5, 97.5]).tolist(), "promotions": promotions,
            "runs_without_promotion": sum(v == 0 for v in promotions.values())}


def per_metric(rows, runs, rng):
    out = {}
    for m in METRICS:
        llm, _ = _matrix(rows, runs, DEV_PARTS, key=m)
        ref, _ = _matrix(rows, [COMPARATOR], DEV_PARTS, key=m)
        boot = hier_bootstrap(llm, ref[0], lambda a, r: float(a.mean() - r.mean()), rng, b=2000)
        p = min(1.0, 2 * min(np.mean(boot <= 0), np.mean(boot >= 0)))
        out[m] = {"llm": float(llm.mean()), "mpc": float(ref.mean()), "p": float(p)}
    order = sorted(out, key=lambda k: out[k]["p"])
    running = 0.0
    for i, m in enumerate(order):
        running = max(running, min(1.0, (len(order) - i) * out[m]["p"]))
        out[m]["p_holm"] = running
    return out


def ratios(rows, runs, part, rng):
    if not any(r["part"] == part for r in rows):
        return None
    llm, _ = _matrix(rows, runs, (part,))
    ref, _ = _matrix(rows, [COMPARATOR], (part,))
    boot = hier_bootstrap(llm, ref[0], lambda a, r: float(a.mean() / r.mean()), rng, b=2000)
    return {"ratio": float(llm.mean() / ref[0].mean()), "ci95": np.percentile(boot, [2.5, 97.5]).tolist()}


# -- report --------------------------------------------------------------------
def report(rows, runs, label):
    rng = np.random.default_rng(SEED)
    a, b2, c, pm = h01(rows, runs, rng), h02(rows, runs, rng), c3(rows, runs, rng), per_metric(rows, runs, rng)
    f = lambda v: f"{v:.1f}"
    lines = [f"# Coordination protocol analysis ({label})", "",
             f"Policies: {', '.join(runs)} (n = {len(runs)}); comparator: `{COMPARATOR}`; bootstrap B = {B}, seed {SEED}.", "",
             "## H0,1 / RQ1 (development range)", "",
             f"- LLM mean {f(a['llm_mean'])}, tuned MPC mean {f(a['mpc_mean'])}, difference {a['difference']:+.1f} "
             f"(95 % CI {a['ci95'][0]:+.1f} to {a['ci95'][1]:+.1f}; 90 % CI {a['ci90'][0]:+.1f} to {a['ci90'][1]:+.1f}).",
             f"- H0,1 rejected: {a['reject_h01']}. Equivalent within +-{f(a['margin'])} (10 % of MPC): {a['equivalent']}.", "",
             "## H0,2 / RQ2 (degradation with amplitude)", "",
             "| Level | " + " | ".join(b2["levels"]) + " |", "|---|" + "---|" * len(b2["levels"]),
             "| LLM mean log(1+score) | " + " | ".join(f"{v:.3f}" for v in b2["llm_mean_log"]) + " |",
             "| MPC mean log(1+score) | " + " | ".join(f"{v:.3f}" for v in b2["mpc_mean_log"]) + " |", "",
             f"- Slope difference (LLM - MPC) {b2['slope_difference']:+.3f} per unit amplitude "
             f"(95 % CI {b2['ci95'][0]:+.3f} to {b2['ci95'][1]:+.3f}); H0,2 rejected: {b2['reject_h02']}.", "",
             "## C3 (variance between independently generated policies)", "",
             f"- Per-policy mean (development range): {c['per_policy']}",
             f"- Median {f(c['median'])}, IQR {f(c['iqr'][0])}-{f(c['iqr'][1])}, range {f(c['range'][0])}-{f(c['range'][1])}, "
             f"SD {f(c['sd'])} (95 % CI {f(c['sd_ci95'][0])}-{f(c['sd_ci95'][1])}).",
             f"- Promotions per run: {c['promotions']}; runs without a promotion: {c['runs_without_promotion']}.", "",
             "## Secondary: per-metric differences (development range, Holm-adjusted)", "",
             "| Metric | LLM | MPC | p | p (Holm) |", "|---|---|---|---|---|"]
    for m, v in pm.items():
        lines.append(f"| {m} | {v['llm']:.2f} | {v['mpc']:.2f} | {v['p']:.3f} | {v['p_holm']:.3f} |")
    for part in ("unseen_period", "unseen_combination"):
        r = ratios(rows, runs, part, rng)
        if r:
            lines.append(f"\n- {part}: LLM/MPC score ratio {r['ratio']:.2f} (95 % CI {r['ci95'][0]:.2f}-{r['ci95'][1]:.2f})")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--scores")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if bool(args.scores) == args.dry_run:
        raise SystemExit("give exactly one of --scores CSV or --dry-run")
    rows = dry_run_scores(args.runs) if args.dry_run else load_scores(args.scores)
    label = "DRY RUN on validation batteries - not results" if args.dry_run else f"sealed test, {os.path.basename(args.scores)}"
    text = report(rows, args.runs, label)
    name = "protocol_analysis_dry_run.md" if args.dry_run else "protocol_analysis.md"
    out = os.path.join(RESULTS_DIR, "sealed_test" if not args.dry_run else "", name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    print(f"-> {out}")


if __name__ == "__main__":
    main()
