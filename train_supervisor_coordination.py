"""Layer 3 for the four-tank setpoint-coordination test bed: the LLM
meta-supervisor writes a deterministic supervise() function that only moves
the PI setpoints, as in the goal document's grinding-circuit experiment.

Run manually: python train_supervisor_coordination.py [num_generations] --run NAME [--from RUN] [--model NAME] [--effort LEVEL]
  --run: required; every run has its own folders, generated_supervisors_coordination/NAME/ (candidates,
         champion) and results/coordination/NAME/ (trial log, evaluations, lessons, run log, report).
         An existing run continues where it stopped.
  --from: seed a NEW run with RUN's champion instead of the fixed recipe (generation numbers restart at 1);
         the new run also inherits RUN's measured record of the changes already tried on that champion
  --model: deepseek-flash (default), gpt-6-luna or gpt-6.1-sol (OPENAI_API_KEY in .env)
  --effort: reasoning effort, default low (DeepSeek: none|low|high|max; Luna: none|low|medium|high|xhigh|max;
            Sol: low|medium|high|xhigh|max)
Report only, no API calls: python train_supervisor_coordination.py --report --run NAME
Index of all runs: results/coordination/README.md

A copy of train_supervisor_four_tank.py (which stays as it is for the leak
task) with the same loop - parallel candidates, security gate, elitist
promotion with a per-disturbance-type regression guard that tightens over the
generations, decision traces (the champion's worst scenarios and where
non-promoted candidates failed), one targeted change per candidate (with the
share of the champion's code it kept logged), previous attempts, lessons
learned, stop switch, token logging - pointed at
four_tank_coordination.py:
- Interface: supervise(telemetry_window, active_setpoints, objectives) ->
  {"diagnosis": str, "adjusted_setpoints": {"h1": float, "h2": float}}.
- Score: four_tank_coordination.score() - production off target, band and
  upper-limit violations, safety, setpoint travel, exceptions.
- Batteries: DEV (drives promotion), VALIDATION (held-out, same ranges, new
  seeds; its score is shown to the LLM only as a generalization gap) and
  BEYOND (disturbances beyond the development range; never shown to the
  LLM, only reported - the frozen-policy test for RQ2).
"""

import csv
import difflib
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np
from openai import OpenAI
from dotenv import load_dotenv

import four_tank_coordination as C
from supervisor_security import check_source, safe_exec_supervisor, SAFE_BUILTINS

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)
_openai_client = None


def get_openai_client():
    """Created on first use, so DeepSeek-only runs don't need OPENAI_API_KEY."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


MODEL_DEFAULT = "deepseek-flash"
# OpenAI model ids, from OpenAI's model pages (checked 2026-10-01): both allow
# 128,000 output tokens; Sol does not accept reasoning effort "none".
OPENAI_REASONING_EFFORTS = {
    "gpt-6-luna": ("none", "low", "medium", "high", "xhigh", "max"),
    "gpt-6.1-sol": ("low", "medium", "high", "xhigh", "max"),
}
OPENAI_MAX_OUTPUT_TOKENS = 128000
# Standard USD per 1M tokens (uncached input, cached input, output), for the
# cost estimate in the logs and report. DeepSeek at its off-peak rate; peak
# hours cost twice as much.
PRICES_PER_MILLION = {
    "deepseek-flash": (0.15, 0.003, 0.60),
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-6.1-sol": (2.00, 0.10, 10.00),
}


def provider_of(model):
    return "openai" if model.startswith("gpt-") else "deepseek"


REQUIRED_ARGS = ("telemetry_window", "active_setpoints", "objectives")

BASE_SUPERVISORS_DIR = "generated_supervisors_coordination"
SEED_SUPERVISOR_PATH = os.path.join(BASE_SUPERVISORS_DIR, "supervisor_gen_0.py")
BASE_RESULTS_DIR = os.path.join("results", "coordination")
BASELINES_CSV_PATH = os.path.join(BASE_RESULTS_DIR, "baselines.csv")
# Per-run paths, set by _use_run().
SUPERVISORS_DIR = CURRENT_SUPERVISOR_PATH = RESULTS_DIR = None
EVALUATIONS_PATH = TRIALS_PATH = CONTEXT_REPORT_PATH = SUMMARY_CSV_PATH = FINAL_REPORT_PATH = None
RUN_LOG_PATH = INVOCATIONS_PATH = INHERITED_TRIALS_PATH = None
MAX_CONTEXT_RELATIONS = 12
# Lessons (relations_learned) are kept only from promoted candidates. The model
# writes them in the same reply as its code, before it is scored; until
# 2026-10-05 the best non-promoted candidate's lessons were also kept when
# nothing was promoted, and in window600_onechange those lessons pointed at the
# change that had just failed (averaging the feed-load estimate). What failed
# is now recorded by the trainer instead: one measured line per candidate, all
# generations of the run (see _history_block), at most MAX_HISTORY_ENTRIES.
MAX_HISTORY_ENTRIES = 30
MAX_RELATIONS_PER_GENERATION = 2
MAX_RELATION_WORDS = 30

CANDIDATES_PER_GENERATION = 3  # was 4; 3 since 2026-10-05 to cut cost per generation
REASONING_EFFORT_DEFAULT = "low"  # see train_supervisor_four_tank.py for the measurements behind this
# Cap on output tokens per reply, reasoning included ("low" effort is only a
# preference). DeepSeek's default is 65,536. On this task the replies that
# succeeded used 33k-54k tokens (the leak task: 14k-33k), and 3 of 7 replies in
# the first run were cut off at exactly the default with nothing returned -
# most likely the long tail of the same distribution, not endless loops. Lower
# caps (32k, 48k) would have cut off successful replies too, so the cap is set
# above the default instead, to let long replies finish while still bounding a
# genuine runaway. DeepSeek allows up to 384k.
MAX_OUTPUT_TOKENS = 131072
# Higher efforts write longer replies: at "low" one reply already reached 101k
# tokens (window600_fixedguard), so "high" and "max" get twice the room.
MAX_OUTPUT_TOKENS_BY_EFFORT = {"high": 262144, "max": 262144}
NON_THINKING_TEMPERATURE = 1.0
STOP_FILE = "STOP_TRAINING"
TRACE_SCENARIOS = 2
# Non-promoted candidates of the previous generation whose worst scenario's
# decision trace goes into the prompt (rejected-by-guard first, then best
# average), each cut to at most FAILURE_TRACE_MAX_ROWS rows. Without these the
# model only saw a one-line rejection reason and never how its oscillation
# handling actually failed.
FAILURE_TRACE_CANDIDATES = 2
FAILURE_TRACE_MAX_ROWS = 30

# Regression guard, by disturbance type rather than by single scenario. A
# per-scenario guard (one scenario per cell) blocked almost every candidate
# after the first generation in the window-50 runs - e.g. a 150.3 average
# against the champion's 196 - because a single oscillation or target-change
# scenario got worse, even when the rest of that disturbance type improved.
# Now: the mean score of each disturbance type (nominal, feed, pump, split,
# combined) may get worse by at most the larger of an absolute and a relative
# tolerance of the champion's mean for that type, and no single scenario may
# get worse by more than the larger of an absolute and a relative cap of its
# score (to stop one scenario being wrecked).
#
# The tolerances follow a schedule over the generations. In the first 600 s
# run every candidate that beat the seed's average (best 258 against 533) was
# rejected by the scenario cap or the nominal group, so nothing was promoted
# and the model kept seeing only the seed's traces. Loose early means a
# candidate that is much better overall but worse on one scenario still gets
# promoted; that scenario then shows up in the next prompt's worst-scenario
# traces and has to be fixed. Stricter later protects what has been gained.
# The battery average must improve in every tier.
# Each tier: (from generation, group abs, group rel, scenario cap abs, scenario cap rel).
GUARD_SCHEDULE = (
    (1, 10.0, 0.25, 300.0, 1.50),
    (3, 10.0, 0.15, 200.0, 1.00),
    (5, 10.0, 0.10, 100.0, 0.50),
)


def guard_tolerances(gen_idx):
    """(group abs, group rel, scenario cap abs, scenario cap rel) for this generation."""
    tiers = [t for t in GUARD_SCHEDULE if gen_idx >= t[0]] or GUARD_SCHEDULE[:1]
    return tiers[-1][1:]

# Same seeds and scenarios per cell as benchmark_coordination.py, so the
# baseline CSV has these exact scenarios. Three scenarios per cell instead of
# one, so a single noisy scenario weighs less in both the score and the guard.
SCENARIOS_PER_CELL = 3
DEV_BATTERY = C.make_battery("dev", per_cell=SCENARIOS_PER_CELL, seed=1)
VALIDATION_BATTERY = C.make_battery("dev", per_cell=SCENARIOS_PER_CELL, seed=2)
BEYOND_BATTERY = C.make_battery("beyond", per_cell=SCENARIOS_PER_CELL, seed=3)
_KIND_BY_NAME = {s.name: s.kind_label for s in DEV_BATTERY}


def _disturbance_text(scenario, t):
    parts = [f"{d.kind}:{d.value(t):+.2f}" for d in scenario.disturbances if abs(d.value(t)) > 1e-9]
    return ",".join(parts) or "none"


TRACE_SAMPLE_EVERY = 6  # inside a long unchanged stretch, one row per minute (6 decisions)


def _format_decision_trace(result, scenario):
    """Decision rows where the situation changes - production leaves or
    re-enters the 2% band, a constraint starts or stops being violated, the
    setpoints start or stop moving - with one row either side, plus one row per
    minute inside long stretches where something stays wrong. A first version
    kept every off-target row: 160 rows and ~10k prompt tokens for the seed."""
    h = result["hist"]
    rows, status = [], []
    prev_sp = None
    for d in result["decisions"]:
        i = int(round(d["time_s"] / scenario.dt))
        q, target = h["q"][i], d["target"]
        sp = (d["setpoints"]["h1"], d["setpoints"]["h2"])
        off = abs(q - target) > C.RECOVERY_TOLERANCE * target
        violated = not (C.H2_BAND[0] <= h["h2"][i] <= C.H2_BAND[1]) or max(h["h3"][i], h["h4"][i]) > C.UPPER_LEVEL_LIMIT
        moved = prev_sp is not None and max(abs(sp[0] - prev_sp[0]), abs(sp[1] - prev_sp[1])) > 1e-4
        prev_sp = sp
        status.append((off, violated, moved))
        rows.append(f"t={d['time_s']:.0f}s target={target:.2f} Q={q:.2f} h=[{h['h1'][i]:.3f},{h['h2'][i]:.3f},"
                    f"{h['h3'][i]:.3f},{h['h4'][i]:.3f}] v=[{h['v1'][i]:.1f},{h['v2'][i]:.1f}] "
                    f"sp=[{sp[0]:.3f},{sp[1]:.3f}] disturbance={_disturbance_text(scenario, d['time_s'])}")
    keep = {0, len(rows) - 1}
    for idx in range(1, len(rows)):
        if status[idx] != status[idx - 1]:
            keep.update((idx - 1, idx, idx + 1))
        elif any(status[idx]) and idx % TRACE_SAMPLE_EVERY == 0:
            keep.add(idx)
    lines, last = [], -1
    for idx in sorted(k for k in keep if 0 <= k < len(rows)):
        if idx > last + 1:
            lines.append(f"  ... {idx - last - 1} rows omitted (same situation as the row before)")
        lines.append(rows[idx])
        last = idx
    if last < len(rows) - 1:
        lines.append(f"  ... {len(rows) - 1 - last} rows omitted (same situation as the row before)")
    return lines


def score_supervisor(supervisor_fn, battery=None):
    battery = DEV_BATTERY if battery is None else battery
    traces = []
    for scenario in battery:
        result = C.run_episode(supervisor_fn, scenario)
        traces.append({
            "scenario": scenario.name,
            "score": round(C.score(result["metrics"]), 3),
            "metrics": result["metrics"],
            "decision_trace": _format_decision_trace(result, scenario),
        })
    return float(np.mean([t["score"] for t in traces])), traces


def validate_supervisor(supervisor_fn):
    return score_supervisor(supervisor_fn, battery=VALIDATION_BATTERY)


def beyond_supervisor(supervisor_fn):
    return score_supervisor(supervisor_fn, battery=BEYOND_BATTERY)


def load_context_report(max_relations=MAX_CONTEXT_RELATIONS):
    if not os.path.exists(CONTEXT_REPORT_PATH):
        return []
    relations = []
    with open(CONTEXT_REPORT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                relations.extend(json.loads(line).get("relations", []))
    return relations[-max_relations:]


def append_context_report(trial_idx, relations, candidate=None):
    if not relations:
        return
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(CONTEXT_REPORT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"trial": trial_idx, "candidate": candidate, "relations": relations}) + "\n")


def append_evaluation(traces, run_label):
    """Per-scenario metrics of every evaluated program, for later analysis
    (e.g. variance between independently generated policies)."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(EVALUATIONS_PATH, "a", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps({"run": run_label, "scenario": t["scenario"], "score": t["score"], **t["metrics"]}) + "\n")


def _plant_block():
    p = C.plant_params()
    op = C.steady_state(C.NOMINAL_SETPOINTS["h1"], C.NOMINAL_SETPOINTS["h2"])
    feed = [c for c in C.DISTURBANCE_CHANNELS["feed"]]
    max_feed = max(rng[1] for _, _, rng, _ in feed)
    max_pump = max(rng[1] for _, _, rng, _ in C.DISTURBANCE_CHANNELS["pump"])
    max_split = max(rng[1] for _, _, rng, _ in C.DISTURBANCE_CHANNELS["split"])
    return f"""
PLANT DESCRIPTION (process knowledge a plant engineer on this unit has):
Quadruple-tank process (Johansson, 2000): four tanks, two pumps, two three-way
split valves.
- Lower tanks: tank1 (level h1) and tank2 (level h2). Upper tanks: tank3 (h3)
  and tank4 (h4). Tank3 drains by gravity into tank1, tank4 drains into tank2,
  and tank1/tank2 drain to the product line.
- Pump 1 (voltage v1): its split valve sends gamma1={p['gamma_1']:.2f} of the flow to
  tank1 and {1 - p['gamma_1']:.2f} to tank4 (which then drains into tank2).
- Pump 2 (voltage v2): its split valve sends gamma2={p['gamma_2']:.2f} of the flow to
  tank2 and {1 - p['gamma_2']:.2f} to tank3 (which then drains into tank1).
- So each lower tank gets most of its inflow from the OTHER pump, delayed by
  passing through an upper tank (non-minimum-phase configuration).
Mass balances (Torricelli outflow; all tank cross-sections A1..A4 = {p['A1']:g} m^2, g = {p['g']} m/s^2):
  dh1/dt = -a1*sqrt(2g*h1) + a3*sqrt(2g*h3) + gamma1*k1*v1 + d1
  dh2/dt = -a2*sqrt(2g*h2) + a4*sqrt(2g*h4) + gamma2*k2*v2 + d2
  dh3/dt = -a3*sqrt(2g*h3) + (1-gamma2)*k2*v2
  dh4/dt = -a4*sqrt(2g*h4) + (1-gamma1)*k1*v1
with outlet areas a1={p['a1']}, a2={p['a2']}, a3={p['a3']}, a4={p['a4']} m^2, nominal pump gains
k1={p['k1']}, k2={p['k2']} m^3/(V*s), and d1, d2 = unmeasured extra in/outflow (0 nominally).
Pumps are limited to {C.PUMP_LIMITS[0]:g}-{C.PUMP_LIMITS[1]:g} V. All four levels and both pump voltages are measured.

Base layer: two PI level loops at a 1 s sample time (Kp={C.PID_KP:g} V/m, Ki={C.PID_KI:g} V/(m*s)), paired
off-diagonally: the h1 loop drives PUMP 2 and the h2 loop drives PUMP 1. They track your
setpoints for h1 and h2; you never drive the pumps directly. After a setpoint change the loops
need about 1.5-2 minutes to settle (production within 2% after ~70 s, within 0.5% after ~115 s),
and meanwhile the pump voltages overshoot their new steady values by about 1-1.5 V: levels,
slopes and voltages measured during that transient reflect the setpoint change, not a disturbance.

Production: Q = a1*sqrt(2g*h1) + a2*sqrt(2g*h2), reported in L/s. With the loops holding h1 and h2
at their setpoints, Q at steady state depends only on the two setpoints, while the pump voltages
and upper levels needed to hold them depend on the disturbances. Your code may evaluate these
relations itself (the constants above and `math` are available), e.g. to find the setpoint pair
that gives the target production.

Design operating point: setpoints h1={C.NOMINAL_SETPOINTS['h1']}, h2={C.NOMINAL_SETPOINTS['h2']} give Q={C.NOMINAL_PRODUCTION:.2f} L/s with
v1={op['v1']:.2f} V, v2={op['v2']:.2f} V, h3={op['h3']:.3f} m, h4={op['h4']:.3f} m. The plant has been in
steady operation at this point since long before t = 0. Measurements are noise-free (rounded to 0.1 mm).

Operating objectives (the objectives argument carries the current values):
- keep production Q at the production target (normally {C.NOMINAL_PRODUCTION:.2f} L/s; the target can change
  during a run);
- keep h2 inside the band {list(C.H2_BAND)} m;
- keep both upper levels h3 and h4 below {C.UPPER_LEVEL_LIMIT} m;
- keep h1 and h2 within the safety limits {list(C.SAFETY_BOUNDS)} m;
- move the setpoints no more than needed (every metre of setpoint travel is penalized).

Disturbances (development range; one or two at a time, as a step, a ramp over a few minutes, or
an oscillation with a period of a few minutes):
- feed: extra outflow (draw-off) from tank1 or tank2, or extra inflow to tank2, up to about {max_feed:g} L/s;
- pump: loss of pump gain k1 or k2 of up to about {max_pump * 100:.0f}%;
- split: shift of gamma1 or gamma2 by up to about {max_split:g}.
Two setpoints and one production target leave one degree of freedom: as a disturbance moves the
pump voltages and upper levels, a good supervisor shifts production between tank1 and tank2 so the
constraints keep holding while Q stays on target. Large disturbances can make some objectives
impossible to meet at the same time.
"""


def _builtins_rule():
    is_exception = lambda v: isinstance(v, type) and issubclass(v, BaseException)
    names = [n for n, v in SAFE_BUILTINS.items() if not is_exception(v) and n not in ("True", "False", "None")]
    exceptions = [n for n, v in SAFE_BUILTINS.items() if is_exception(v)]
    return (f"The ONLY built-in names available are: {', '.join(names)}. Exception types for try/except: "
            f"{', '.join(exceptions)}. Any other built-in raises NameError at runtime, which counts as an "
            f"exception on every call. The `math` and `statistics` modules are already available; do not import them.")


def _attempts_block(previous_attempts):
    attempts = [a for a in previous_attempts or [] if a["decision"] != "SKIPPED"]
    if not attempts:
        return ""
    entries = []
    for a in attempts:
        per_type = (", ".join(f"{kind} {mean:.0f}" for kind, mean in _group_means(a["traces"]).items())
                    if a.get("traces") else "not scored")
        entries.append(f"- candidate {a['candidate']}: {a['decision']}"
                       + (f" ({a['reason']})" if a.get("reason") else "")
                       + (f", avg {a['score']:.1f}" if a.get("score") is not None else "")
                       + f"; mean per type: {per_type}"
                       + f"\n  changed: {str(a.get('proposed_change') or '')[:300]}")
    block = ("\nPREVIOUS GENERATION'S NON-PROMOTED ATTEMPTS (sampled independently; learn from what "
             "they tried and how it scored):\n" + "\n".join(entries) + "\n")
    return block + _failure_traces_block(attempts)


def _failure_traces_block(attempts):
    """Decision trace of the scenario that sank each of up to
    FAILURE_TRACE_CANDIDATES non-promoted candidates."""
    failed = [a for a in attempts if a.get("traces") and a.get("failed_scenario")]
    failed.sort(key=lambda a: (a["decision"] != "REJECTED_REGRESSION", a["score"]))
    parts = []
    for a in failed[:FAILURE_TRACE_CANDIDATES]:
        name = a["failed_scenario"]
        trace = next(t for t in a["traces"] if t["scenario"] == name)
        rows = trace["decision_trace"]
        if len(rows) > FAILURE_TRACE_MAX_ROWS:
            # Head and tail: the tail shows whether an oscillation dies out or grows.
            head, tail = FAILURE_TRACE_MAX_ROWS * 2 // 3, FAILURE_TRACE_MAX_ROWS // 3
            rows = rows[:head] + [f"  ... {len(rows) - head - tail} rows cut"] + rows[-tail:]
        parts.append(f"candidate {a['candidate']} on {name} (score {trace['score']:.1f}; the champion it was "
                     f"compared with scored {a['champion_scores'][name]:.1f}):\n" + "\n".join(rows))
    if not parts:
        return ""
    return ("\nWHERE THOSE ATTEMPTS FAILED: decision traces (same format as above) of the scenario each one lost "
            "most on against the champion. Find the mechanism in its logic that produced this behaviour before "
            "reusing its idea.\n" + "\n\n".join(parts) + "\n")


def _history_block():
    """One measured line per earlier candidate of this run, from the trial log
    (preceded by what a run seeded with --from inherited): its change, its
    average against the champion it was compared with, and the scenario it
    gained and lost most on."""
    lines = []
    inherited = _read_jsonl(INHERITED_TRIALS_PATH) if INHERITED_TRIALS_PATH else []
    for t in (inherited + _read_trials())[-MAX_HISTORY_ENTRIES:]:
        change = str(t.get("proposed_change") or "")[:300]
        origin = f"run {t['run']} " if t.get("run") else ""
        line = f"- {origin}gen {t['trial']} c{t.get('candidate')} {t['decision']}: {change}"
        if t.get("score") is None:
            line += f" | {str(t.get('reason') or '')[:120]}"
        else:
            line += (f" | avg {t['champion_score']:.1f} -> {t['score']:.1f}" if t.get("champion_score") is not None
                     else f" | avg {t['score']:.1f}")
            for key, label in (("biggest_gain", "gained most"), ("biggest_loss", "lost most")):
                d = t.get(key)
                if d:
                    line += f" | {label} {d['scenario']} {d['champion']:.0f} -> {d['candidate']:.0f}"
        lines.append(line)
    if not lines:
        return ""
    return ("\nCHANGES TRIED SO FAR (measured by the trainer, oldest first; lines marked with a run name were tried on "
            "this champion in an earlier run; avg = battery score of the champion it was compared with -> the candidate's). HARD CONSTRAINT: do not resubmit a change listed as not "
            "PROMOTED; build on one only if your change removes the loss it caused, and say how in proposed_change.\n"
            + "\n".join(lines) + "\n")


def _biggest_changes(best_traces, cand_traces):
    """(scenario gained most, scenario lost most) against the champion, None if there is none."""
    diffs = [(c["score"] - b["score"], b["scenario"], b["score"], c["score"]) for b, c in zip(best_traces, cand_traces)]
    as_dict = lambda d: {"scenario": d[1], "champion": round(d[2], 1), "candidate": round(d[3], 1)}
    gain, loss = min(diffs), max(diffs)
    return (as_dict(gain) if gain[0] < 0 else None), (as_dict(loss) if loss[0] > 0 else None)


def _results_block(traces):
    """Means per disturbance type, then one compact line per scenario:
    score | litres off target | seconds h2 outside band | seconds upper level
    above limit | setpoint travel (m) | recovery (s) [| safety s, exceptions if any]."""
    lines = ["Mean score per disturbance type: "
             + ", ".join(f"{kind} {mean:.1f}" for kind, mean in _group_means(traces).items()), ""]
    for t in traces:
        m = t["metrics"]
        extra = (f" | safety {m['safety_violation_s']:.0f}s" if m["safety_violation_s"] else "") + \
                (f" | EXCEPTIONS {m['exceptions']}" if m["exceptions"] else "")
        lines.append(f"- {t['scenario']}: {t['score']:.1f} | {m['production_iae_l']:.0f} L | band {m['band_violation_s']:.0f}s | "
                     f"upper {m['upper_violation_s']:.0f}s | travel {m['setpoint_tv_m']:.3f} m | recovery {m['recovery_s']:.0f}s{extra}")
    return "\n".join(lines)


def _guard_schedule_text():
    lines = []
    for i, (start, group_abs, group_rel, cap_abs, cap_rel) in enumerate(GUARD_SCHEDULE):
        end = GUARD_SCHEDULE[i + 1][0] - 1 if i + 1 < len(GUARD_SCHEDULE) else None
        gens = (f"generation {start} on" if end is None else
                f"generations {start}-{end}" if end > start else f"generation {start}")
        lines.append(f"- {gens}: type mean +max({group_abs:g} points, {group_rel:.0%}), "
                     f"single scenario +max({cap_abs:g} points, {cap_rel:.0%})")
    return "\n".join(lines)


def _guard_rule_text(gen_idx):
    if gen_idx is None:
        return ""
    group_abs, group_rel, cap_abs, cap_rel = guard_tolerances(gen_idx)
    return (f"This is generation {gen_idx}: a type mean may get worse by at most the larger of {group_abs:g} points "
            f"or {group_rel:.0%}, a single scenario by at most the larger of {cap_abs:g} points or {cap_rel:.0%}.")


def build_prompt(current_code, best_score, traces, context_relations, best_val_score=None, previous_attempts=None,
                 gen_idx=None):
    """Run-invariant content first (cached by DeepSeek's prefix cache), the
    per-generation state last."""
    sample = DEV_BATTERY[0]
    w = C.SCORE_WEIGHTS
    worst = sorted(traces, key=lambda t: -t["score"])[:TRACE_SCENARIOS]
    trace_block = "\n\n".join(f"{t['scenario']} (score {t['score']:.1f}):\n" + "\n".join(t["decision_trace"]) for t in worst)
    gen_check = (f"Held-out check: the champion scores {best_val_score:.1f} on a separate battery you never see "
                 f"(same disturbance types and ranges, different timing and amplitudes), a dev-vs-held-out gap of "
                 f"{best_val_score - best_score:+.1f}. A growing gap means recent changes fit the visible "
                 f"scenarios' exact numbers rather than the physics.") if best_val_score is not None else ""

    return f"""
You are improving a deterministic supervisory function that sits above the
PI level loops of a quadruple-tank process. It reads the recent telemetry and
returns new setpoints for the two PI loops, so that production stays on
target and the operating constraints hold while disturbances act on the plant.
Your output is Python code that runs online without you.
{_plant_block()}
HOW YOUR FUNCTION IS CALLED:
- Every {sample.decision_interval_steps} s (from t = {sample.decision_interval_steps} s on), with the most recent {sample.window_steps} one-second samples
  ({sample.window_steps // 60} minutes): len(telemetry_window) is ALWAYS exactly {sample.window_steps}. The history before t = 0 is
  steady operation. Consecutive windows overlap by {sample.window_steps - sample.decision_interval_steps} samples.
- "time" in each sample is seconds since the window's first sample (0, 1, ..., {sample.window_steps - 1}), not
  absolute time.
- Each sample also records the setpoints (sp_h1, sp_h2) and production target that were active
  at that time, so you can see your own recent setpoint changes and any target change in the window.
- The function is stateless: it is re-loaded fresh and keeps no memory between calls; everything
  it knows comes from the current window and its arguments.
- The setpoints you return are clamped to setpoint_limits and held until the next call.

The function signature MUST remain exactly:
def supervise(telemetry_window, active_setpoints, objectives):
    ...
    return {{
        "diagnosis": str,
        "adjusted_setpoints": {{"h1": float, "h2": float}},
    }}

telemetry_window is a list of dicts shaped like:
{{"time": float, "h1": float, "h2": float, "h3": float, "h4": float, "v1": float, "v2": float, "production": float,
 "sp_h1": float, "sp_h2": float, "production_target": float}}
(levels and setpoints in m, pump voltages in V, production and target in L/s). active_setpoints is
{{"h1": float, "h2": float}}.
objectives is {{"production_target": float (L/s), "h2_band": [low, high], "upper_level_limit": float,
"setpoint_limits": [low, high]}}. "diagnosis" is a short human-readable explanation of the decision.

Rules for the code you write:
- No imports, no exec/eval, no file/network/os access, no access to dunder attributes.
- {_builtins_rule()}
- The function must be a pure function of its three arguments plus module-level constants.

SCORING (per scenario, lower is better; the battery score is the average over the scenarios):
Score = {w['production_iae_l']:g} * production off target (integral of |Q - target|, litres)
      + {w['band_violation_s']:g} * seconds with h2 outside the band
      + {w['upper_violation_s']:g} * seconds with h3 or h4 above the limit
      + {w['safety_violation_s']:g} * seconds with h1 or h2 outside the safety limits
      + {w['setpoint_tv_m']:g} * total setpoint travel (sum of |change| of both setpoints, m)
      + {w['exceptions']:g} * exceptions or timeouts of your function
The scenarios are grouped by disturbance type (nominal = production-target changes only; feed;
pump; split; combined). Promotion requires a better battery average, AND for every type a mean
score no worse than the champion's by more than a tolerance, AND no single scenario worse than the
champion's by more than a cap. Both start loose and tighten over the generations:
{_guard_schedule_text()}

TASK:
1. Diagnose what causes the worst-scoring scenarios, using the traces and the plant description: how does each disturbance move the pump voltages and upper levels, and which objective is violated?
2. Make ONE targeted change to the current supervisor that addresses what your diagnosis found, so that production stays on target and the constraints hold, using the free degree of freedom, without moving the setpoints more than needed. One change = one mechanism (for example how a disturbance is estimated, how oscillations are handled, how the setpoint pair is chosen, a filter or a threshold); it may span several lines. Keep the rest of the current code as it is - its structure, helper functions and constants - unless the change has to touch them. Do not rewrite the function from scratch: rewrites tend to fix one scenario and break others, as the previous attempts below show, and one change at a time shows which change caused a score difference.
3. In "self_check", state in 2-4 sentences how your logic keeps production on target and the constraints satisfied when a disturbance pushes an upper level toward its limit or a pump toward saturation. Do not solve the mass balances by hand; if your logic needs steady-state relations, compute them in the code.
4. Add at most {MAX_RELATIONS_PER_GENERATION} NEW generalizable cause-effect relations your change relies on, each ONE sentence of at most {MAX_RELATION_WORDS} words. They are kept as lessons for later generations only if your change is promoted. Do not repeat a listed one.

OUTPUT FORMAT - strictly this JSON:
{{
  "failure_analysis": {{
    "what_failed": "string",
    "failing_scenarios": ["scenario_name", ...],
    "change_type": "structural | scalar/config | bug_fix",
    "next_recommendation": "string"
  }},
  "self_check": "string, 2-4 sentences: how your logic handles an upper level near its limit or a saturating pump",
  "proposed_change": "string, ONE sentence naming the single change you made",
  "code": "full source of the new supervise function as a string",
  "relations_learned": ["one sentence, at most {MAX_RELATION_WORDS} words", ...]
}}

========== CURRENT STATE (changes every generation) ==========

Current supervisor source:
```python
{current_code}
```

Current battery score: {best_score:.1f}. {gen_check}
{_guard_rule_text(gen_idx)}

Per-scenario results (score | litres off target | seconds h2 outside band | seconds upper level above
limit | setpoint travel | recovery time):
{_results_block(traces)}

DECISION TRACES of the current supervisor on its {TRACE_SCENARIOS} worst-scoring scenarios, one row per call where
the situation changes (production leaves or re-enters the {C.RECOVERY_TOLERANCE:.0%} band around the target, a constraint
starts or stops being violated, the setpoints start or stop moving) with one row either side, plus
one row per minute while something stays wrong. t = absolute simulation time (your function never sees it); Q = production
(L/s); h = [h1, h2, h3, h4] (m); v = [v1, v2] (V); sp = setpoints returned; disturbance = the TRUE
active disturbance (shown here only for diagnosis; your function cannot see it).
{trace_block}
{_history_block()}{_attempts_block(previous_attempts)}
LESSONS LEARNED: cause-effect relations written by the model behind each PROMOTED change. They are
consistent with a measured improvement but not proven; where a measured result above contradicts
one, trust the measurement:
{chr(10).join('- ' + r for r in context_relations) if context_relations else "(none recorded yet)"}

Respond with the JSON object described under OUTPUT FORMAT.
"""


def call_llm(prompt, model=MODEL_DEFAULT, reasoning_effort=REASONING_EFFORT_DEFAULT, max_retries=3):
    """Returns (parsed JSON or None, token usage of every attempt that got a
    response, including unparseable ones, since those are billed too)."""
    usage_per_attempt = []
    api = get_openai_client() if provider_of(model) == "openai" else client
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(0.3)
            response = api.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a control-systems engineer. Respond ONLY with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                **_request_kwargs(model, reasoning_effort),
            )
        except Exception as e:
            print(f"[LLM API ERROR - Attempt {attempt}/{max_retries}]: {e}")
            time.sleep(1.0 * attempt)
            continue
        choice = response.choices[0]
        content = choice.message.content or ""
        usage = _usage(response)
        usage_per_attempt.append(usage)
        try:
            return json.loads(content), usage_per_attempt
        except json.JSONDecodeError as e:
            reasoning = getattr(choice.message, "reasoning_content", None) or ""
            print(f"[LLM API ERROR - Attempt {attempt}/{max_retries}]: unparseable response ({e}); "
                  f"finish_reason={choice.finish_reason}, content_chars={len(content)}, reasoning_chars={len(reasoning)}, "
                  f"prompt_tokens={usage['prompt']}, completion_tokens={usage['completion']}, "
                  f"reasoning_tokens={usage['reasoning']}")
            time.sleep(1.0 * attempt)
    print(f"[CRITICAL] All {max_retries} retries failed for this call.")
    return None, usage_per_attempt


def _request_kwargs(model, reasoning_effort):
    """Provider-specific request parameters. OpenAI's reasoning models take
    max_completion_tokens and reasoning_effort (including "none" on Luna) and
    no temperature; DeepSeek takes max_tokens, and switches thinking off
    through extra_body, where temperature then matters."""
    if provider_of(model) == "openai":
        return {"max_completion_tokens": OPENAI_MAX_OUTPUT_TOKENS, "reasoning_effort": reasoning_effort}
    if reasoning_effort == "none":
        return {"max_tokens": MAX_OUTPUT_TOKENS, "extra_body": {"thinking": {"type": "disabled"}},
                "temperature": NON_THINKING_TEMPERATURE}
    return {"max_tokens": MAX_OUTPUT_TOKENS_BY_EFFORT.get(reasoning_effort, MAX_OUTPUT_TOKENS),
            "reasoning_effort": reasoning_effort}


def _usage(response):
    u = response.usage
    details = getattr(u, "completion_tokens_details", None)
    # DeepSeek reports cache hits as prompt_cache_hit_tokens, OpenAI as
    # prompt_tokens_details.cached_tokens.
    cache_hit = getattr(u, "prompt_cache_hit_tokens", None)
    if cache_hit is None:
        cache_hit = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", None)
    return {
        "prompt": getattr(u, "prompt_tokens", None),
        "cache_hit": cache_hit,
        "completion": getattr(u, "completion_tokens", None),
        "reasoning": getattr(details, "reasoning_tokens", None),
    }


def estimate_cost(usages, model):
    """USD at standard (DeepSeek: off-peak) rates; None for an unknown model."""
    if model not in PRICES_PER_MILLION:
        return None
    price_in, price_cached, price_out = PRICES_PER_MILLION[model]
    s = _sum_usage(usages)
    return ((s["prompt"] - s["cache_hit"]) * price_in + s["cache_hit"] * price_cached
            + s["completion"] * price_out) / 1e6


def _sum_usage(usages):
    total = {"requests": len(usages), "prompt": 0, "cache_hit": 0, "completion": 0, "reasoning": 0}
    for u in usages:
        for key in ("prompt", "cache_hit", "completion", "reasoning"):
            total[key] += u.get(key) or 0
    return total


def _candidate_path(gen_idx, candidate):
    return os.path.join(SUPERVISORS_DIR, f"supervisor_gen_{gen_idx}_c{candidate}.py")


def promote(candidate_code, gen_idx, candidate):
    best_path = os.path.join(SUPERVISORS_DIR, f"best_supervisor_gen_{gen_idx}.py")
    for path in (_candidate_path(gen_idx, candidate), best_path, CURRENT_SUPERVISOR_PATH):
        with open(path, "w", encoding="utf-8") as f:
            f.write(candidate_code)
    print(f"[PROMOTED] gen_{gen_idx} candidate {candidate} is the new current_supervisor.py")


def save_candidate_only(candidate_code, gen_idx, candidate):
    with open(_candidate_path(gen_idx, candidate), "w", encoding="utf-8") as f:
        f.write(candidate_code)


def code_change(old, new):
    """How much of the champion a candidate kept: share of the champion's lines
    unchanged in the candidate, and lines added/removed. Logged to check that
    candidates make one targeted change rather than a rewrite."""
    old_lines = [l.rstrip() for l in old.strip().splitlines()]
    new_lines = [l.rstrip() for l in new.strip().splitlines()]
    kept = sum(b.size for b in difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_matching_blocks())
    return {"kept_fraction": round(kept / max(len(old_lines), 1), 3),
            "lines_added": len(new_lines) - kept, "lines_removed": len(old_lines) - kept}


def log_trial(trial_idx, decision, score, failure_analysis, proposed_change, reason=None, validation_score=None,
              self_check=None, candidate=None, reasoning_effort=None, usage=None, model=None, code_change=None,
              measured=None):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(TRIALS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "trial": trial_idx, "candidate": candidate, "model": model, "reasoning_effort": reasoning_effort,
            "usage": usage,
            "decision": decision, "score": score, "validation_score": validation_score,
            "failure_analysis": failure_analysis, "self_check": self_check,
            "proposed_change": proposed_change, "reason": reason, "code_change": code_change,
            **(measured or {}),
        }) + "\n")


def _group_means(traces):
    groups = {}
    for t in traces:
        groups.setdefault(_KIND_BY_NAME.get(t["scenario"], "other"), []).append(t["score"])
    return {kind: float(np.mean(scores)) for kind, scores in groups.items()}


def find_regression(best_traces, cand_traces, gen_idx):
    """(reason, scenario) if the candidate regresses a disturbance type's mean
    or wrecks a single scenario under this generation's tolerances (see
    GUARD_SCHEDULE), else (None, None). The scenario is the one whose trace is
    shown in the next prompt: the capped scenario, or the scenario of the
    regressed type that got worst."""
    group_abs, group_rel, cap_abs, cap_rel = guard_tolerances(gen_idx)
    best_groups, cand_groups = _group_means(best_traces), _group_means(cand_traces)
    for kind, best_mean in best_groups.items():
        allowed = max(group_abs, group_rel * best_mean)
        if cand_groups[kind] > best_mean + allowed:
            pairs = [(b, c) for b, c in zip(best_traces, cand_traces) if _KIND_BY_NAME.get(b["scenario"], "other") == kind]
            worst = max(pairs, key=lambda bc: bc[1]["score"] - bc[0]["score"])[0]["scenario"]
            return (f"'{kind}' disturbances got worse on average: {best_mean:.1f} -> {cand_groups[kind]:.1f}, "
                    f"allowed +{allowed:.0f}"), worst
    for b, c in zip(best_traces, cand_traces):
        allowed = max(cap_abs, cap_rel * b["score"])
        if c["score"] > b["score"] + allowed:
            return f"{b['scenario']} got much worse: {b['score']:.1f} -> {c['score']:.1f}, allowed +{allowed:.0f}", b["scenario"]
    return None, None


def worst_regression(best_traces, cand_traces):
    """Scenario where the candidate lost most against the champion, or None if it lost nowhere."""
    b, c = max(zip(best_traces, cand_traces), key=lambda bc: bc[1]["score"] - bc[0]["score"])
    return b["scenario"] if c["score"] > b["score"] else None


def _existing_runs():
    return sorted(d for d in os.listdir(BASE_SUPERVISORS_DIR) if os.path.isdir(os.path.join(BASE_SUPERVISORS_DIR, d)))


def _use_run(run_name, seed_from=None):
    """Point every path at the run's own folders. A new run is seeded with the
    fixed recipe (gen_0), or with another run's champion if seed_from is given.
    Returns the seed's path for a new run, None for an existing one."""
    global SUPERVISORS_DIR, CURRENT_SUPERVISOR_PATH, RESULTS_DIR, EVALUATIONS_PATH, TRIALS_PATH
    global CONTEXT_REPORT_PATH, SUMMARY_CSV_PATH, FINAL_REPORT_PATH, RUN_LOG_PATH, INVOCATIONS_PATH, INHERITED_TRIALS_PATH
    SUPERVISORS_DIR = os.path.join(BASE_SUPERVISORS_DIR, run_name)
    CURRENT_SUPERVISOR_PATH = os.path.join(SUPERVISORS_DIR, "current_supervisor.py")
    RESULTS_DIR = os.path.join(BASE_RESULTS_DIR, run_name)
    EVALUATIONS_PATH = os.path.join(RESULTS_DIR, "evaluations.jsonl")
    TRIALS_PATH = os.path.join(RESULTS_DIR, "trials.jsonl")
    CONTEXT_REPORT_PATH = os.path.join(RESULTS_DIR, "context_report.jsonl")
    SUMMARY_CSV_PATH = os.path.join(RESULTS_DIR, "summary.csv")
    FINAL_REPORT_PATH = os.path.join(RESULTS_DIR, "final_report.md")
    RUN_LOG_PATH = os.path.join(RESULTS_DIR, "run_log.txt")
    INVOCATIONS_PATH = os.path.join(RESULTS_DIR, "invocations.jsonl")
    INHERITED_TRIALS_PATH = os.path.join(RESULTS_DIR, "inherited_trials.jsonl")
    os.makedirs(SUPERVISORS_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    if os.path.exists(CURRENT_SUPERVISOR_PATH):
        if seed_from:
            print(f"[CRITICAL] run '{run_name}' already exists; --from only seeds a new run")
            sys.exit(1)
        return None
    seed_path = os.path.join(BASE_SUPERVISORS_DIR, seed_from, "current_supervisor.py") if seed_from else SEED_SUPERVISOR_PATH
    if not os.path.exists(seed_path):
        print(f"[CRITICAL] no champion to seed from at {seed_path}")
        sys.exit(1)
    with open(seed_path, "r", encoding="utf-8") as src, open(CURRENT_SUPERVISOR_PATH, "w", encoding="utf-8") as dst:
        dst.write(src.read())
    if seed_from:
        with open(INHERITED_TRIALS_PATH, "w", encoding="utf-8") as f:
            for t in _champion_history(seed_from):
                f.write(json.dumps(t) + "\n")
    return seed_path


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _champion_history(run):
    """Trials of `run` measured against its current champion: everything after
    its last promotion (plus that promotion), or, if it never promoted, all its
    trials plus what it inherited itself. Each is labelled with its run.
    window600_measured, for example, started without this and repeated in its
    first generation the change that had failed six times in window600_onechange."""
    folder = os.path.join(BASE_RESULTS_DIR, run)
    own = [dict(t, run=t.get("run", run)) for t in _read_jsonl(os.path.join(folder, "trials.jsonl"))]
    promoted = [t["trial"] for t in own if t["decision"] == "PROMOTED"]
    if promoted:
        last = max(promoted)
        return [t for t in own if t["trial"] > last or (t["trial"] == last and t["decision"] == "PROMOTED")]
    return _read_jsonl(os.path.join(folder, "inherited_trials.jsonl")) + own


class _Tee:
    """Console output also goes to the run's run_log.txt."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            stream.write(text)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def _git_commit():
    """Commit the run's code came from, marked if trainer code had uncommitted changes."""
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", "*.py"],
                               capture_output=True, text=True).stdout.strip()
    except OSError:
        return None
    return (commit + ("+uncommitted" if dirty else "")) if commit else None


def _next_trial_start():
    max_n = 0
    for f in os.listdir(SUPERVISORS_DIR):
        if not (f.startswith("supervisor_gen_") and f.endswith(".py")):
            continue
        stem = f[len("supervisor_gen_"):-len(".py")].split("_c")[0]
        try:
            max_n = max(max_n, int(stem))
        except ValueError:
            continue
    return max_n + 1


def _read_trials():
    if not os.path.exists(TRIALS_PATH):
        return []
    with open(TRIALS_PATH, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _baseline_scores():
    """Mean baseline scores on exactly the trainer's batteries (the '_0'
    scenarios of benchmark_coordination.py's CSV), if that CSV exists."""
    if not os.path.exists(BASELINES_CSV_PATH):
        return {}
    wanted = {"dev": {s.name for s in DEV_BATTERY}, "heldout": {s.name for s in VALIDATION_BATTERY},
              "beyond": {s.name for s in BEYOND_BATTERY}}
    sums = {}
    with open(BASELINES_CSV_PATH, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["scenario"] in wanted.get(row["battery"], ()):
                sums.setdefault((row["controller"], row["battery"]), []).append(float(row["score"]))
    return {k: float(np.mean(v)) for k, v in sums.items()}


def generate_report():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    trials = _read_trials()

    with open(SUMMARY_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["trial", "candidate", "reasoning_effort", "decision", "score", "validation_score", "reason",
                         "kept_fraction"])
        for t in trials:
            writer.writerow([t.get("trial"), t.get("candidate"), t.get("reasoning_effort"), t.get("decision"),
                             t.get("score"), t.get("validation_score"), t.get("reason"),
                             (t.get("code_change") or {}).get("kept_fraction")])

    decision_counts = {}
    for t in trials:
        decision_counts[t["decision"]] = decision_counts.get(t["decision"], 0) + 1
    promoted = [t for t in trials if t["decision"] == "PROMOTED"]

    champion = {}
    if os.path.exists(CURRENT_SUPERVISOR_PATH):
        with open(CURRENT_SUPERVISOR_PATH, "r", encoding="utf-8") as f:
            champion_code = f.read()
        champion["hash"] = hashlib.sha256(champion_code.encode("utf-8")).hexdigest()[:12]
        ok, _ = check_source(champion_code, required_args=REQUIRED_ARGS)
        if ok:
            fn, err = safe_exec_supervisor(champion_code)
            if not err:
                champion["dev"], _ = score_supervisor(fn)
                champion["heldout"], _ = validate_supervisor(fn)
                champion["beyond"], _ = beyond_supervisor(fn)

    baselines = _baseline_scores()
    lines = ["# Four-Tank Setpoint-Coordination Supervisor Training Report", "",
             f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}", "",
             "## Current champion vs baselines", "",
             f"Source hash: `{champion.get('hash')}`", "",
             "| Battery | LLM champion | Fixed recipe | MPC (estimated) | MPC (oracle) |", "|---|---|---|---|---|"]
    for battery, label in (("dev", "Development (drives promotion)"), ("heldout", "Held-out development"),
                           ("beyond", "Beyond development range (never shown to the LLM)")):
        cells = [f"{champion[battery]:.1f}" if battery in champion else "-"]
        for c in ("fixed_recipe", "mpc_estimated", "mpc_oracle"):
            cells.append(f"{baselines[(c, battery)]:.1f}" if (c, battery) in baselines else "-")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    if not baselines:
        lines.append("\n(Baselines missing: run `python benchmark_coordination.py` to fill them in.)")

    lines += ["", "## Trial history", "", f"- Total candidates logged: {len(trials)}"]
    for decision, count in sorted(decision_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"  - {decision}: {count}")

    usage_by_setting = {}
    for t in trials:
        if t.get("usage"):
            key = (t.get("model") or MODEL_DEFAULT, t.get("reasoning_effort") or "?")
            usage_by_setting.setdefault(key, []).extend(t["usage"])
    if usage_by_setting:
        lines += ["", "## Token usage per API request, by model and reasoning effort", "",
                  "| Model | Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning | Est. cost total |",
                  "|---|---|---|---|---|---|---|---|"]
        for (model, effort_level), usages in usage_by_setting.items():
            s = _sum_usage(usages)
            n = s["requests"]
            cost = estimate_cost(usages, model)
            lines.append(f"| {model} | {effort_level} | {n} | {s['prompt'] / n:.0f} | {s['cache_hit'] / n:.0f} | "
                         f"{s['completion'] / n:.0f} | {s['reasoning'] / n:.0f} | "
                         f"{f'${cost:.2f}' if cost is not None else '-'} |")

    measured = [t for t in trials if t.get("code_change")]
    if measured:
        kept = [t["code_change"]["kept_fraction"] for t in measured]
        lines.append(f"- Share of the champion's lines kept by a candidate: median {np.median(kept):.0%} "
                     f"(range {min(kept):.0%}-{max(kept):.0%}, {len(kept)} candidates)")

    lines += ["", "## Score trajectory (promoted candidates only)", "",
              "| Generation | Candidate | Dev score | Held-out score |", "|---|---|---|---|"]
    for t in promoted:
        val = t.get("validation_score")
        lines.append(f"| gen_{t['trial']} | {t.get('candidate') or '-'} | {t['score']:.2f} | "
                     f"{f'{val:.2f}' if val is not None else '-'} |")

    relations = load_context_report()
    lines += ["", "## Lessons learned so far", ""] + ([f"- {r}" for r in relations] or ["(none recorded yet)"])

    with open(FINAL_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[SUCCESS] Report written to {FINAL_REPORT_PATH} and {SUMMARY_CSV_PATH}")


def _evaluate_candidate(response, usage, candidate, gen_idx):
    if response is None:
        return {"candidate": candidate, "decision": "SKIPPED", "reason": "DeepSeek call failed", "score": None,
                "usage": usage}
    record = {
        "candidate": candidate, "usage": usage, "code": response.get("code", ""),
        "failure_analysis": response.get("failure_analysis"), "proposed_change": response.get("proposed_change"),
        "self_check": response.get("self_check"), "relations": response.get("relations_learned") or [],
        "score": None, "reason": None,
    }
    ok, reason = check_source(record["code"], required_args=REQUIRED_ARGS)
    if not ok:
        record.update(decision="REJECTED_SECURITY", reason=reason)
        return record
    fn, err = safe_exec_supervisor(record["code"])
    if err:
        record.update(decision="REJECTED_LOAD", reason=err)
        return record
    record["fn"] = fn
    record["score"], record["traces"] = score_supervisor(fn)
    append_evaluation(record["traces"], f"gen_{gen_idx}_c{candidate}")
    record["decision"] = "SCORED"
    return record


def main():
    option = lambda name, default: sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default
    run_name = option("--run", None)
    if not run_name:
        print("[CRITICAL] name the run with --run NAME (a new name starts a new run, an existing one continues). "
              f"Existing runs: {', '.join(_existing_runs()) or 'none'}")
        sys.exit(1)
    if "--report" in sys.argv:
        if not os.path.isdir(os.path.join(BASE_SUPERVISORS_DIR, run_name)):
            print(f"[CRITICAL] no run named '{run_name}'. Existing runs: {', '.join(_existing_runs())}")
            sys.exit(1)
        _use_run(run_name)
        generate_report()
        return
    seeded_from = _use_run(run_name, seed_from=option("--from", None))
    sys.stdout = _Tee(sys.__stdout__, open(RUN_LOG_PATH, "a", encoding="utf-8", buffering=1))
    print(f"\n##### {datetime.now().isoformat(timespec='seconds')} run '{run_name}' #####")
    if seeded_from:
        print(f"[RUN] new run, seeded with {seeded_from}")

    num_generations = next((int(a) for a in sys.argv[1:] if a.isdigit()), 4)
    model = option("--model", MODEL_DEFAULT)
    effort = option("--effort", REASONING_EFFORT_DEFAULT)
    if provider_of(model) == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            print("[CRITICAL] OPENAI_API_KEY is not set (expected in .env)")
            sys.exit(1)
        allowed = OPENAI_REASONING_EFFORTS.get(model)
        if allowed and effort not in allowed:
            print(f"[CRITICAL] {model} does not accept reasoning effort '{effort}'; use one of {', '.join(allowed)}")
            sys.exit(1)
    start_gen = _next_trial_start()
    with open(INVOCATIONS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "git_commit": _git_commit(), "model": model, "reasoning_effort": effort,
                            "generations": num_generations, "candidates_per_generation": CANDIDATES_PER_GENERATION,
                            "start_gen": start_gen,
                            "seeded_from": seeded_from.replace(os.sep, "/") if seeded_from else None}) + "\n")

    with open(CURRENT_SUPERVISOR_PATH, "r", encoding="utf-8") as f:
        current_code = f.read()
    ok, reason = check_source(current_code, required_args=REQUIRED_ARGS)
    if not ok:
        print(f"[CRITICAL] current_supervisor.py fails its own security check: {reason}")
        sys.exit(1)
    current_fn, err = safe_exec_supervisor(current_code)
    if err:
        print(f"[CRITICAL] current_supervisor.py failed to load: {err}")
        sys.exit(1)

    best_score, best_traces = score_supervisor(current_fn)
    best_val_score, _ = validate_supervisor(current_fn)
    append_evaluation(best_traces, "baseline")
    print(f"[BASELINE] current_supervisor.py avg score: {best_score:.3f} (held-out: {best_val_score:.3f})")

    if os.path.exists(STOP_FILE):
        os.remove(STOP_FILE)
        print(f"[STOP] removed a stale {STOP_FILE} left over from an earlier run")

    previous_attempts = []
    for g in range(num_generations):
        if os.path.exists(STOP_FILE):
            # Left in place so parallel runs (--run run1/run2/...) all see it;
            # it is cleared when the trainer is started next time.
            print(f"\n[STOP] {STOP_FILE} found - stopping before generation {g + 1}/{num_generations}; "
                  f"no requests were sent for it")
            break
        gen_idx = start_gen + g
        print(f"\n=== Generation {g + 1}/{num_generations} (gen_{gen_idx}): sampling {CANDIDATES_PER_GENERATION} candidates "
              f"from {model} at reasoning effort {effort} ===")
        group_abs, group_rel, cap_abs, cap_rel = guard_tolerances(gen_idx)
        print(f"[GUARD] gen_{gen_idx}: type mean +max({group_abs:g}, {group_rel:.0%}), "
              f"single scenario +max({cap_abs:g}, {cap_rel:.0%})")
        prompt = build_prompt(current_code, best_score, best_traces, load_context_report(),
                              best_val_score=best_val_score, previous_attempts=previous_attempts, gen_idx=gen_idx)
        with ThreadPoolExecutor(max_workers=CANDIDATES_PER_GENERATION) as pool:
            responses = list(pool.map(lambda _: call_llm(prompt, model=model, reasoning_effort=effort),
                                      range(CANDIDATES_PER_GENERATION)))

        records = [_evaluate_candidate(resp, usage, k, gen_idx) for k, (resp, usage) in enumerate(responses, start=1)]
        all_usage = [u for r in records for u in r["usage"]]
        tokens = _sum_usage(all_usage)
        cost = estimate_cost(all_usage, model)
        print(f"[TOKENS] {tokens['requests']} requests: prompt {tokens['prompt']} (cache hit {tokens['cache_hit']}), "
              f"completion {tokens['completion']} (reasoning {tokens['reasoning']})"
              + (f", est. ${cost:.3f}" if cost is not None else ""))

        for r in records:
            if r.get("code"):
                r["code_change"] = code_change(current_code, r["code"])

        winner = None
        for r in records:
            if r["decision"] != "SCORED":
                print(f"  c{r['candidate']}: [{r['decision']}] {r.get('reason')}")
                continue
            # Champion score on every scenario, so the next prompt can put a
            # non-promoted candidate's worst scenario next to the champion's.
            r["champion_scores"] = {t["scenario"]: t["score"] for t in best_traces}
            gain, loss = _biggest_changes(best_traces, r["traces"])
            r["measured"] = {"champion_score": round(best_score, 3), "biggest_gain": gain, "biggest_loss": loss}
            if r["score"] >= best_score:
                r["decision"] = "ROLLBACK"
                r["failed_scenario"] = worst_regression(best_traces, r["traces"])
            else:
                regression, r["failed_scenario"] = find_regression(best_traces, r["traces"], gen_idx)
                if regression:
                    r["decision"] = "REJECTED_REGRESSION"
                    r["reason"] = regression
                else:
                    r["decision"] = "ELIGIBLE"
                    if winner is None or r["score"] < winner["score"]:
                        winner = r
            cc = r["code_change"]
            print(f"  c{r['candidate']}: score {r['score']:.3f} (champion {best_score:.3f}) -> {r['decision']}"
                  + (f" ({r['reason']})" if r.get("reason") else "")
                  + f" [kept {cc['kept_fraction']:.0%} of the champion's lines, +{cc['lines_added']}/-{cc['lines_removed']}]")

        for r in records:
            if r is winner:
                continue
            if r["decision"] == "ELIGIBLE":
                r["decision"] = "NOT_SELECTED"
                r["reason"] = f"beat the champion but candidate {winner['candidate']} scored lower"
            if r.get("code"):
                save_candidate_only(r["code"], gen_idx, r["candidate"])
            log_trial(gen_idx, r["decision"], r["score"], r.get("failure_analysis"), r.get("proposed_change"),
                      reason=r.get("reason"), self_check=r.get("self_check"), candidate=r["candidate"],
                      reasoning_effort=effort, usage=r["usage"], model=model, code_change=r.get("code_change"),
                      measured=r.get("measured"))

        if winner is not None:
            promote(winner["code"], gen_idx, winner["candidate"])
            best_score, current_code, best_traces = winner["score"], winner["code"], winner["traces"]
            best_val_score, _ = validate_supervisor(winner["fn"])
            print(f"[VALIDATION] held-out score: {best_val_score:.3f} (dev score: {best_score:.3f})")
            winner["decision"] = "PROMOTED"
            log_trial(gen_idx, "PROMOTED", winner["score"], winner["failure_analysis"], winner["proposed_change"],
                      validation_score=best_val_score, self_check=winner["self_check"], candidate=winner["candidate"],
                      reasoning_effort=effort, usage=winner["usage"], model=model,
                      code_change=winner.get("code_change"), measured=winner.get("measured"))
        else:
            print(f"[NO PROMOTION] champion stays at {best_score:.3f}")

        if winner is not None and winner.get("relations"):
            relations = winner["relations"][:MAX_RELATIONS_PER_GENERATION]
            print(f"[LEARNED] {relations}")
            append_context_report(gen_idx, relations, candidate=winner["candidate"])

        previous_attempts = [r for r in records if r is not winner]

    print(f"\n[DONE] Final best score: {best_score:.3f}. current_supervisor.py reflects the best candidate found.")
    generate_report()


if __name__ == "__main__":
    main()
