"""Layer 3 for the PC-Gym four-tank MIMO testbed: offline DeepSeek-driven
heuristic learner for the four-tank supervisor.

Run manually: python train_supervisor_four_tank.py [num_trials]

Mirrors train_supervisor_two_tank.py's structure (elitist hill-climb,
security-check gate, fixed scenario battery, held-out validation, context
report, generalization-gap prompt) exactly, pointed at pcgym_four_tank.py's
plant instead. Reuses the identical MIMO signature
supervise(telemetry_window, active_setpoints, nominal_targets) - the
two-tank supervisor's current_supervisor.py loads and runs here unmodified,
though it transplants poorly (see pcgym_four_tank.py's __main__ block and
the README): its thresholds were calibrated for a completely different
plant's units/scale and don't zero-shot-transfer, which is exactly why this
system gets its own from-scratch trainer rather than reusing the two-tank
champion directly.
"""

import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

from openai import OpenAI
from dotenv import load_dotenv

from supervisor_security import check_source, safe_exec_supervisor
from two_tank_sim import MIMO_REQUIRED_ARGS
from pcgym_four_tank import FourTankScenarioConfig, run_episode, build_log_report, pid_only_supervisor

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

SUPERVISORS_DIR = "generated_supervisors_four_tank"
CURRENT_SUPERVISOR_PATH = os.path.join(SUPERVISORS_DIR, "current_supervisor.py")
RESULTS_DIR = "results"
FAILURE_POINTS_PATH = os.path.join(RESULTS_DIR, "failure_points_four_tank.jsonl")
TRIALS_PATH = os.path.join(RESULTS_DIR, "supervisor_training_trials_four_tank.jsonl")
CONTEXT_REPORT_PATH = os.path.join(RESULTS_DIR, "context_report_four_tank.jsonl")
MAX_CONTEXT_RELATIONS = 25
SUMMARY_CSV_PATH = os.path.join(RESULTS_DIR, "summary_four_tank.csv")
FINAL_REPORT_PATH = os.path.join(RESULTS_DIR, "final_report_four_tank.md")

VIOLATION_PENALTY = 500
MISSED_ANOMALY_PENALTY = 300
FALSE_POSITIVE_PENALTY = 160
NO_FAULT_FALSE_POSITIVE_PENALTY = 250  # lowered from 800: this plant's real background
# oscillation was pushing every candidate's false-positive rate on baseline_no_fault to
# 400-900+ events, and at 800/event the resulting scores (150k-700k) swamped the search's
# ability to distinguish "somewhat better" candidates from "much worse" ones. Still kept
# above FALSE_POSITIVE_PENALTY (160) to preserve the "no excuse to ever trigger here"
# asymmetry, just not so extreme it collapses the search's signal.
EXCEPTION_PENALTY = 10000
RESTORE_GAP_PENALTY = 200

NO_FAULT_REGRESSION_ABS_TOLERANCE = 5.0
FAULT_REGRESSION_ABS_TOLERANCE = 100.0
FAULT_REGRESSION_REL_TOLERANCE = 0.15

# Fault timing: episode is 600s, natural settling time is ~100-300s (an order
# of magnitude slower than our own tank_sim.py), so onsets/offsets/durations
# are scaled up accordingly - a 10-30s fault window here would be gone before
# the supervisor could plausibly notice at a reasonable macro-cycle length.
SCENARIO_BATTERY = [
    FourTankScenarioConfig(name="baseline_no_fault"),
    FourTankScenarioConfig(name="tank1_leak", leak1_onset_s=150.0, leak1_multiplier=2.5, leak1_offset_s=400.0),
    FourTankScenarioConfig(name="tank2_leak", leak2_onset_s=150.0, leak2_multiplier=2.5, leak2_offset_s=400.0),
    FourTankScenarioConfig(name="both_leaks", leak1_onset_s=150.0, leak1_multiplier=2.0, leak1_offset_s=350.0,
                            leak2_onset_s=200.0, leak2_multiplier=2.0, leak2_offset_s=400.0),
    FourTankScenarioConfig(name="tank1_severe_persistent", leak1_onset_s=400.0, leak1_multiplier=4.0, leak1_offset_s=None),
    FourTankScenarioConfig(name="tank2_severe_persistent", leak2_onset_s=400.0, leak2_multiplier=4.0, leak2_offset_s=None),
]

# Held-out validation battery: same categories, different fault parameters,
# never used to decide promotion.
VALIDATION_SCENARIO_BATTERY = [
    FourTankScenarioConfig(name="val_baseline_no_fault"),
    FourTankScenarioConfig(name="val_tank1_leak", leak1_onset_s=180.0, leak1_multiplier=2.2, leak1_offset_s=420.0),
    FourTankScenarioConfig(name="val_tank2_leak", leak2_onset_s=180.0, leak2_multiplier=2.2, leak2_offset_s=420.0),
    FourTankScenarioConfig(name="val_both_leaks", leak1_onset_s=130.0, leak1_multiplier=1.8, leak1_offset_s=330.0,
                            leak2_onset_s=220.0, leak2_multiplier=2.4, leak2_offset_s=430.0),
    FourTankScenarioConfig(name="val_tank1_severe_persistent", leak1_onset_s=350.0, leak1_multiplier=3.4, leak1_offset_s=None),
    FourTankScenarioConfig(name="val_tank2_severe_persistent", leak2_onset_s=350.0, leak2_multiplier=3.4, leak2_offset_s=None),
]


def score_supervisor(supervisor_fn, battery=None):
    battery = SCENARIO_BATTERY if battery is None else battery
    traces = []
    total = 0.0
    for scenario in battery:
        result = run_episode(supervisor_fn, scenario)
        m = result["metrics"]
        tank1_never_faults = scenario.leak1_onset_s is None
        tank2_never_faults = scenario.leak2_onset_s is None
        tank1_fp = sum(1 for f in result["failure_points"] if f["type"] == "false_positive" and f["tank"] == "tank1")
        tank2_fp = sum(1 for f in result["failure_points"] if f["type"] == "false_positive" and f["tank"] == "tank2")
        fp_cost = (
            tank1_fp * (NO_FAULT_FALSE_POSITIVE_PENALTY if tank1_never_faults else FALSE_POSITIVE_PENALTY)
            + tank2_fp * (NO_FAULT_FALSE_POSITIVE_PENALTY if tank2_never_faults else FALSE_POSITIVE_PENALTY)
        )
        scenario_score = (
            m["iae"]
            + m["violation_count"] * VIOLATION_PENALTY
            + m["missed_anomaly_count"] * MISSED_ANOMALY_PENALTY
            + fp_cost
            + m["exception_count"] * EXCEPTION_PENALTY
            + m["restore_gap"] * RESTORE_GAP_PENALTY
        )
        total += scenario_score
        traces.append({"scenario": scenario.name, "score": round(scenario_score, 3), "log_report": build_log_report(result)})
    return total / len(battery), traces


def validate_supervisor(supervisor_fn):
    return score_supervisor(supervisor_fn, battery=VALIDATION_SCENARIO_BATTERY)


def load_failure_catalog(max_examples_per_category=3):
    if not os.path.exists(FAILURE_POINTS_PATH):
        return {"counts": {}, "examples": {}}
    counts, examples = {}, {}
    with open(FAILURE_POINTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            key = f"{entry.get('tank', '?')}:{entry.get('type', 'unknown')}"
            counts[key] = counts.get(key, 0) + 1
            examples.setdefault(key, [])
            if len(examples[key]) < max_examples_per_category:
                examples[key].append(entry)
    return {"counts": counts, "examples": examples}


def load_context_report(max_relations=MAX_CONTEXT_RELATIONS):
    if not os.path.exists(CONTEXT_REPORT_PATH):
        return []
    relations = []
    with open(CONTEXT_REPORT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            for relation in entry.get("relations", []):
                relations.append(relation)
    return relations[-max_relations:]


def append_context_report(trial_idx, relations):
    if not relations:
        return
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(CONTEXT_REPORT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"trial": trial_idx, "relations": relations}) + "\n")


def _compute_reference_stats():
    """Runs the plain PID-only controller (no supervisor) on baseline_no_fault
    and returns real measured effort/error statistics for a genuinely healthy
    episode. Used to give the LLM hard numbers instead of qualitative
    "this plant oscillates" language - the actual healthy envelope turned out
    to be much wider than that phrasing implies (errors up to +/-0.19 on
    targets of only 0.30/0.35, pump effort routinely saturating near 12V),
    which is almost certainly why early candidates kept false-triggering.
    """
    import numpy as np
    scenario = FourTankScenarioConfig(name="baseline_no_fault")
    result = run_episode(pid_only_supervisor, scenario)
    v1 = np.array(result["v1_hist"])[5:]
    v2 = np.array(result["v2_hist"])[5:]
    h1 = np.array(result["h1_hist"])[5:]
    h2 = np.array(result["h2_hist"])[5:]
    err1 = scenario.nominal_setpoint1 - h1
    err2 = scenario.nominal_setpoint2 - h2
    return {
        "v1": {"mean": float(v1.mean()), "std": float(v1.std()), "min": float(v1.min()), "max": float(v1.max())},
        "v2": {"mean": float(v2.mean()), "std": float(v2.std()), "min": float(v2.min()), "max": float(v2.max())},
        "error1": {"mean_abs": float(np.abs(err1).mean()), "min": float(err1.min()), "max": float(err1.max())},
        "error2": {"mean_abs": float(np.abs(err2).mean()), "min": float(err2.min()), "max": float(err2.max())},
    }


def build_prompt(current_code, best_score, traces, failure_catalog, context_relations, best_val_score=None, reference_stats=None):
    scenario_names = ", ".join(s.name for s in SCENARIO_BATTERY)
    ref_block = ""
    if reference_stats is not None:
        r = reference_stats
        ref_block = f"""
MEASURED REFERENCE STATISTICS (from an actual healthy, fault-free episode with
plain PID control, no supervisor action at all - these are hard numbers, not
estimates):
- Pump 1 (v1) effort: mean={r['v1']['mean']:.2f}V, std={r['v1']['std']:.2f}, range [{r['v1']['min']:.2f}, {r['v1']['max']:.2f}]V
- Pump 2 (v2) effort: mean={r['v2']['mean']:.2f}V, std={r['v2']['std']:.2f}, range [{r['v2']['min']:.2f}, {r['v2']['max']:.2f}]V
- Tank1 error: mean|error|={r['error1']['mean_abs']:.4f}, range [{r['error1']['min']:.4f}, {r['error1']['max']:.4f}] (on a target of ~0.30)
- Tank2 error: mean|error|={r['error2']['mean_abs']:.4f}, range [{r['error2']['min']:.4f}, {r['error2']['max']:.4f}] (on a target of ~0.35)

This means: pump effort ROUTINELY SATURATES NEAR THE 1-12V RAIL and tracking
error swings as large as +/-0.19 (roughly 25-60% of the setpoint) EVEN WHEN
NOTHING IS WRONG. If your detection threshold would flag anything within
these ranges, it WILL false-positive constantly. Your threshold must sit
clearly outside this measured healthy envelope, not just "a bit above average".
"""

    return f"""
You are improving a deterministic supervisory control function for a
quadruple-tank (four-tank) water system - the classic Johansson benchmark.
Two pumps (v1, v2) each feed TWO tanks: v1 feeds tank1 (h1) directly AND
tank4 (h4) via a split valve, and h4 then drains into tank2 (h2) - so v1
affects h1 immediately and h2 with a delay. Symmetrically, v2 feeds tank2 (h2)
directly AND tank3 (h3), which drains into tank1 (h1) - so v2 affects h2
immediately and h1 with a delay. Only h1 and h2 are controlled/measured here
(mapped to "tank1"/"tank2" in the telemetry below); h3/h4 are not directly
observed. This cross-coupling is stronger and more delayed than a simple
cascade, and the default configuration is deliberately in the
"non-minimum-phase" regime, where most pump flow is routed through the
delayed cross-path rather than direct - so BOTH tanks show real, sustained
effort/error oscillation even with NO fault present at all, just from
control-loop interaction. Do not treat all oscillation as anomalous; a
healthy tank here still varies over time.
{ref_block}
PRIMARY OBJECTIVE - READ THIS BEFORE ANYTHING ELSE: every candidate proposed so
far has failed by triggering false anomaly flags on baseline_no_fault far more
than it ever correctly caught a real fault (400-900+ false-flag events out of
~600 possible steps, versus at most a few hundred missed-fault events even in
the worst fault scenario). At the current scoring weights, a supervisor that
NEVER flags anything at all scores BETTER than every candidate tried so far.
Staying silent is the safe default; only flag an anomaly when you have strong,
specific evidence clearly outside the measured healthy envelope above. Getting
baseline_no_fault to (near) zero false positives is more valuable right now
than improving fault detection - do not sacrifice the former for the latter.

IMPORTANT UNITS/SCALE (this plant is NOT the same as any other tank system
you may have seen): pump effort (v1, v2) ranges roughly 1-12 (volts), tank
levels range roughly 0.05-0.48 (meters), and the natural settling time is
~100-300 seconds - an order of magnitude slower than a typical small tank
model. Do not reuse absolute threshold constants from a different plant;
derive thresholds relative to this plant's own observed statistics (e.g. a
ratio of recent-to-baseline effort within the telemetry window, or relative
to nominal_target) so they remain meaningful at this specific scale.

The function signature MUST remain exactly:
def supervise(telemetry_window, active_setpoints, nominal_targets):
    ...
    return {{
        "diagnosis": str,
        "adjusted_setpoints": {{"tank1": float, "tank2": float}},
        "anomaly_flags": {{"tank1": bool, "tank2": bool}},
    }}

telemetry_window is a list of dicts shaped like:
{{"time": float, "tank1": {{"level": float, "pump_effort": float, "error": float}}, "tank2": {{...same keys...}}}}
active_setpoints and nominal_targets are dicts with keys "tank1" (h1, actuated by v1) and "tank2" (h2, actuated by v2).

Rules for the code you write:
- No imports, no exec/eval, no file/network/os access, no access to dunder attributes.
- Only use: arithmetic, comparisons, built-in functions (abs, min, max, len, round, sum, sorted, range, all, any, isinstance, etc.), and the `math`/`statistics` modules (already available, do not import them).
- The function must be a pure function of its three arguments plus module-level constants; it will be re-loaded fresh each run, so no persistent state across calls.

Current supervisor source:
```python
{current_code}
```

Current average score across the fixed scenario battery ({scenario_names}): {best_score}
(Lower score is better. Score = IAE(both tanks combined) + violation_count*{VIOLATION_PENALTY} + missed_anomaly_count*{MISSED_ANOMALY_PENALTY} + false_positive_count*FP_PENALTY + exception_count*{EXCEPTION_PENALTY} + restore_gap*{RESTORE_GAP_PENALTY})
(missed_anomaly/false_positive/restore_gap are evaluated PER TANK and summed. restore_gap is |final_setpoint - nominal_target| per tank, counted only when that tank's own fault has fully cleared by episode end.)
(FP_PENALTY is {NO_FAULT_FALSE_POSITIVE_PENALTY} for a tank in a scenario where THAT TANK never faults at all - there is zero excuse to ever flag it there - and {FALSE_POSITIVE_PENALTY} otherwise.)
(IMPORTANT: a candidate is only promoted if it improves the average score AND does not regress any individual scenario beyond tolerance versus the current champion, even if the average improves. Tolerance is asymmetric: for baseline_no_fault (no fault ever), tolerance is ~0 - any regression there is rejected outright. For a scenario with a genuine fault, up to ~15% (or 100 points, whichever is larger) of regression is allowed.)
{f'''(GENERALIZATION CHECK: the current champion also scores {best_val_score:.1f} on a separate held-out battery of scenarios you never see (different fault onset times/magnitudes/durations than the ones shown to you, same categories). Its dev score is {best_score:.1f}, so the dev-vs-held-out gap is {best_val_score - best_score:+.1f}. You cannot see or optimize against the held-out battery directly, so a growing gap here is a signal that recent changes are fitting the exact numeric parameters of the visible scenarios rather than the underlying physical pattern.)''' if best_val_score is not None else ''}

Per-scenario results with the current supervisor (failure_point_counts keys are "tank_name:failure_type"):
{json.dumps(traces, indent=2)}

Aggregate failure-point catalog from past runs (counts and worst examples, keyed "tank_name:failure_type"):
{json.dumps(failure_catalog, indent=2)}

Lessons learned from previous trials - cause-effect relationships already discovered
by earlier attempts (durable observations, not tied to any one candidate's code).
REQUIRED: your code must not repeat a change that a relation below already says
failed for a specific reason. If a relation identifies a specific bug pattern
(e.g. "comparing a window against its own contaminated baseline"), your code must
not contain that pattern - this is a hard constraint, not a suggestion:
{json.dumps(context_relations, indent=2) if context_relations else "(none recorded yet - this is an early trial)"}

Task:
1. Diagnose what is causing the worst-scoring scenarios and/or the most common failure-point categories, keeping the non-minimum-phase cross-coupling and this plant's own scale in mind.
2. Propose an improved `supervise` function that reduces missed anomalies and false positives on both tanks without introducing new safety violations, and that restores both setpoints back toward nominal once their respective faults have genuinely cleared.
3. Before finalizing, trace through what your code would do on baseline_no_fault using the measured reference statistics above: for each of tank1 and tank2, confirm that typical healthy effort/error values (including the extremes in the measured ranges) do NOT cross your anomaly condition. State this reasoning explicitly in "self_check" below - not just "it should work", but the actual numbers compared against your actual threshold.
4. Separately, identify any NEW generalizable cause-effect relationship this trial's result reveals, whether or not this candidate gets promoted. Only include a relation if it is genuinely new - do not repeat one already listed above.

You must output strictly JSON matching this structure:
{{
  "failure_analysis": {{
    "what_failed": "string",
    "failing_scenarios": ["scenario_name", ...],
    "change_type": "structural | scalar/config | bug_fix",
    "next_recommendation": "string"
  }},
  "self_check": "string: your threshold(s) vs. the measured healthy ranges above, numerically, for both tanks",
  "proposed_change": "string",
  "code": "full source of the new supervise function as a string",
  "relations_learned": ["short generalizable cause-effect statement", ...]
}}
"""


def call_deepseek(prompt, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(0.3)
            response = client.chat.completions.create(
                model="deepseek-flash",
                messages=[
                    {"role": "system", "content": "You are a control-systems engineer. Respond ONLY with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[DEEPSEEK API ERROR - Attempt {attempt}/{max_retries}]: {e}")
            time.sleep(1.0 * attempt)
    print(f"[CRITICAL] All {max_retries} retries failed for this trial.")
    return None


def promote(candidate_code, trial_idx):
    gen_path = os.path.join(SUPERVISORS_DIR, f"supervisor_gen_{trial_idx}.py")
    best_path = os.path.join(SUPERVISORS_DIR, f"best_supervisor_gen_{trial_idx}.py")
    with open(gen_path, "w", encoding="utf-8") as f:
        f.write(candidate_code)
    with open(best_path, "w", encoding="utf-8") as f:
        f.write(candidate_code)
    with open(CURRENT_SUPERVISOR_PATH, "w", encoding="utf-8") as f:
        f.write(candidate_code)
    print(f"[PROMOTED] Trial {trial_idx} is the new current_supervisor.py")


def save_candidate_only(candidate_code, trial_idx):
    gen_path = os.path.join(SUPERVISORS_DIR, f"supervisor_gen_{trial_idx}.py")
    with open(gen_path, "w", encoding="utf-8") as f:
        f.write(candidate_code)


def log_trial(trial_idx, decision, score, failure_analysis, proposed_change, reason=None, validation_score=None, self_check=None):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(TRIALS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "trial": trial_idx,
            "decision": decision,
            "score": score,
            "validation_score": validation_score,
            "failure_analysis": failure_analysis,
            "self_check": self_check,
            "proposed_change": proposed_change,
            "reason": reason,
        }) + "\n")


def append_failure_points(traces, run_label):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(FAILURE_POINTS_PATH, "a", encoding="utf-8") as f:
        for trace in traces:
            for key, count in trace["log_report"]["failure_point_counts"].items():
                tank, fp_type = key.split(":", 1)
                f.write(json.dumps({
                    "run": run_label,
                    "scenario": trace["scenario"],
                    "tank": tank,
                    "type": fp_type,
                    "detail": f"count={count} in this evaluation",
                }) + "\n")


_SCENARIO_BY_NAME = {s.name: s for s in SCENARIO_BATTERY}


def find_scenario_regression(best_traces, cand_traces):
    for b, c in zip(best_traces, cand_traces):
        scenario = _SCENARIO_BY_NAME[b["scenario"]]
        no_fault_scenario = scenario.leak1_onset_s is None and scenario.leak2_onset_s is None
        if no_fault_scenario:
            allowed = NO_FAULT_REGRESSION_ABS_TOLERANCE
        else:
            allowed = max(FAULT_REGRESSION_ABS_TOLERANCE, FAULT_REGRESSION_REL_TOLERANCE * b["score"])
        if c["score"] > b["score"] + allowed:
            return b["scenario"], b["score"], c["score"]
    return None


def _next_trial_start():
    existing = [f for f in os.listdir(SUPERVISORS_DIR) if f.startswith("supervisor_gen_") and f.endswith(".py")]
    max_n = 0
    for f in existing:
        try:
            n = int(f[len("supervisor_gen_"):-len(".py")])
            max_n = max(max_n, n)
        except ValueError:
            continue
    return max_n + 1


def _read_trials():
    if not os.path.exists(TRIALS_PATH):
        return []
    with open(TRIALS_PATH, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def generate_report():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    trials = _read_trials()

    with open(SUMMARY_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["trial", "decision", "score", "validation_score", "reason"])
        for t in trials:
            writer.writerow([t.get("trial"), t.get("decision"), t.get("score"), t.get("validation_score"), t.get("reason")])

    decision_counts = {}
    for t in trials:
        decision_counts[t["decision"]] = decision_counts.get(t["decision"], 0) + 1
    promoted = [t for t in trials if t["decision"] == "PROMOTED"]

    champion_hash = None
    champion_score = None
    champion_val_score = None
    if os.path.exists(CURRENT_SUPERVISOR_PATH):
        with open(CURRENT_SUPERVISOR_PATH, "r", encoding="utf-8") as f:
            champion_code = f.read()
        champion_hash = hashlib.sha256(champion_code.encode("utf-8")).hexdigest()[:12]
        ok, _ = check_source(champion_code, required_args=MIMO_REQUIRED_ARGS)
        if ok:
            fn, err = safe_exec_supervisor(champion_code)
            if not err:
                champion_score, _ = score_supervisor(fn)
                champion_val_score, _ = validate_supervisor(fn)

    relations = load_context_report(max_relations=MAX_CONTEXT_RELATIONS)

    lines = [
        "# Four-Tank MIMO Supervisor Training Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "## Current champion",
        "",
        f"- Source hash: `{champion_hash}`" if champion_hash else "- No current_supervisor.py found",
    ]
    if champion_score is not None:
        gap = champion_val_score - champion_score
        lines += [
            f"- Dev battery score: {champion_score:.2f}",
            f"- Held-out validation battery score: {champion_val_score:.2f}",
            f"- Dev/validation gap: {gap:+.2f} ({'worse on held-out - possible overfitting' if gap > 0.15 * abs(champion_score) + 5 else 'consistent with dev performance'})",
        ]

    lines += ["", "## Trial history", "", f"- Total trials logged: {len(trials)}"]
    for decision, count in sorted(decision_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"  - {decision}: {count}")

    lines += ["", "## Score trajectory (promoted trials only)", "", "| Trial | Dev score | Validation score |", "|---|---|---|"]
    for t in promoted:
        val = t.get("validation_score")
        lines.append(f"| gen_{t['trial']} | {t['score']:.2f} | {val:.2f} |" if val is not None else f"| gen_{t['trial']} | {t['score']:.2f} | - |")

    lines += ["", "## Known open issues / lessons learned so far", ""]
    if relations:
        for r in relations:
            lines.append(f"- {r}")
    else:
        lines.append("(none recorded yet)")

    with open(FINAL_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[SUCCESS] Report written to {FINAL_REPORT_PATH} and {SUMMARY_CSV_PATH}")


def main():
    if "--report" in sys.argv:
        generate_report()
        return

    num_trials = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    start_trial = _next_trial_start()

    with open(CURRENT_SUPERVISOR_PATH, "r", encoding="utf-8") as f:
        current_code = f.read()

    ok, reason = check_source(current_code, required_args=MIMO_REQUIRED_ARGS)
    if not ok:
        print(f"[CRITICAL] current_supervisor.py fails its own security check: {reason}")
        sys.exit(1)
    current_fn, err = safe_exec_supervisor(current_code)
    if err:
        print(f"[CRITICAL] current_supervisor.py failed to load: {err}")
        sys.exit(1)

    best_score, best_traces = score_supervisor(current_fn)
    best_val_score, _ = validate_supervisor(current_fn)
    append_failure_points(best_traces, "trainer_baseline")
    print(f"[BASELINE] current_supervisor.py avg score: {best_score:.3f} (held-out: {best_val_score:.3f})")

    reference_stats = _compute_reference_stats()
    print(f"[REFERENCE] healthy v1={reference_stats['v1']['mean']:.2f}V (std {reference_stats['v1']['std']:.2f}), "
          f"v2={reference_stats['v2']['mean']:.2f}V (std {reference_stats['v2']['std']:.2f}), "
          f"|err1| up to {reference_stats['error1']['max']:.3f}, |err2| up to {reference_stats['error2']['max']:.3f}")

    for i in range(num_trials):
        trial_idx = start_trial + i
        print(f"\n=== Trial {i + 1}/{num_trials} (gen_{trial_idx}) ===")
        failure_catalog = load_failure_catalog()
        context_relations = load_context_report()
        prompt = build_prompt(current_code, best_score, best_traces, failure_catalog, context_relations,
                               best_val_score=best_val_score, reference_stats=reference_stats)
        response = call_deepseek(prompt)

        if response is None:
            log_trial(trial_idx, "SKIPPED", None, None, None, reason="DeepSeek call failed")
            continue

        candidate_code = response.get("code", "")
        failure_analysis = response.get("failure_analysis")
        proposed_change = response.get("proposed_change")
        self_check = response.get("self_check")
        if self_check:
            print(f"[SELF-CHECK] {self_check}")
        new_relations = response.get("relations_learned") or []
        if new_relations:
            print(f"[LEARNED] {new_relations}")
        append_context_report(trial_idx, new_relations)

        ok, reason = check_source(candidate_code, required_args=MIMO_REQUIRED_ARGS)
        if not ok:
            print(f"[REJECTED - SECURITY] {reason}")
            log_trial(trial_idx, "REJECTED_SECURITY", None, failure_analysis, proposed_change, reason=reason, self_check=self_check)
            continue

        candidate_fn, err = safe_exec_supervisor(candidate_code)
        if err:
            print(f"[REJECTED - LOAD] {err}")
            log_trial(trial_idx, "REJECTED_LOAD", None, failure_analysis, proposed_change, reason=err, self_check=self_check)
            continue

        cand_score, cand_traces = score_supervisor(candidate_fn)
        append_failure_points(cand_traces, f"trainer_trial_{trial_idx}")
        print(f"Candidate score: {cand_score:.3f} (current best: {best_score:.3f})")

        if cand_score < best_score:
            regression = find_scenario_regression(best_traces, cand_traces)
            if regression:
                scen_name, old_s, new_s = regression
                print(f"[REJECTED - REGRESSION] '{scen_name}' regressed {old_s:.1f} -> {new_s:.1f} despite a better aggregate score")
                save_candidate_only(candidate_code, trial_idx)
                log_trial(trial_idx, "REJECTED_REGRESSION", cand_score, failure_analysis, proposed_change,
                          reason=f"{scen_name} regressed {old_s:.1f} -> {new_s:.1f}", self_check=self_check)
                continue
            promote(candidate_code, trial_idx)
            best_score, current_code, best_traces = cand_score, candidate_code, cand_traces
            best_val_score, _ = validate_supervisor(candidate_fn)
            print(f"[VALIDATION] held-out score: {best_val_score:.3f} (dev score: {cand_score:.3f})")
            log_trial(trial_idx, "PROMOTED", cand_score, failure_analysis, proposed_change, validation_score=best_val_score, self_check=self_check)
        else:
            save_candidate_only(candidate_code, trial_idx)
            log_trial(trial_idx, "ROLLBACK", cand_score, failure_analysis, proposed_change, self_check=self_check)

    print(f"\n[DONE] Final best score: {best_score:.3f}. current_supervisor.py reflects the best candidate found.")
    generate_report()


if __name__ == "__main__":
    main()
