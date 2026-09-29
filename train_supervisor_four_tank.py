"""Layer 3 for the PC-Gym four-tank MIMO testbed: offline DeepSeek-driven
heuristic learner for the four-tank supervisor.

Run manually: python train_supervisor_four_tank.py [num_generations]

Mirrors train_supervisor_two_tank.py's structure (elitist hill-climb,
security-check gate, fixed scenario battery, held-out validation, context
report, generalization-gap prompt), pointed at pcgym_four_tank.py's plant,
with three additions taken from the program-search literature (Eureka,
FunSearch, AlphaEvolve, Learning Beyond Gradients):
- Each generation samples CANDIDATES_PER_GENERATION programs in parallel from
  the same prompt at a non-zero temperature, and the best eligible one is
  promoted. At temperature 0 the same prompt returned near-identical code
  trial after trial.
- The prompt describes the plant the way a process engineer on this unit
  would know it (layout, mass balances, parameters, loop pairing, operating
  point, fault mode), rather than only its measured statistics.
- The prompt shows a per-decision trace of the champion on its worst
  scenarios (true fault state vs its flags over time), plus a summary of the
  previous generation's non-promoted attempts.
"""

import csv
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from openai import OpenAI
from dotenv import load_dotenv

from supervisor_security import check_source, safe_exec_supervisor
from two_tank_sim import MIMO_REQUIRED_ARGS
from pcgym_four_tank import (
    FourTankScenarioConfig, run_episode, build_log_report, pid_only_supervisor,
    plant_parameters, nominal_operating_point,
)

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

CANDIDATES_PER_GENERATION = 4
SAMPLING_TEMPERATURE = 1.0
TRACE_SCENARIOS = 2  # champion's worst-scoring scenarios shown as decision traces

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
# Onsets/offsets deliberately sit OFF the 10s decision grid (e.g. 153, not
# 150): when every dev fault landed exactly on a decision boundary, dev and
# val were structurally different and the detection lag was a fixed artefact
# of the grid rather than of the detector.
SCENARIO_BATTERY = [
    FourTankScenarioConfig(name="baseline_no_fault"),
    FourTankScenarioConfig(name="tank1_leak", leak1_onset_s=153.0, leak1_multiplier=2.5, leak1_offset_s=404.0),
    FourTankScenarioConfig(name="tank2_leak", leak2_onset_s=147.0, leak2_multiplier=2.5, leak2_offset_s=396.0),
    FourTankScenarioConfig(name="both_leaks", leak1_onset_s=153.0, leak1_multiplier=2.0, leak1_offset_s=352.0,
                            leak2_onset_s=207.0, leak2_multiplier=2.0, leak2_offset_s=405.0),
    FourTankScenarioConfig(name="tank1_severe_persistent", leak1_onset_s=403.0, leak1_multiplier=4.0, leak1_offset_s=None),
    FourTankScenarioConfig(name="tank2_severe_persistent", leak2_onset_s=397.0, leak2_multiplier=4.0, leak2_offset_s=None),
]

# Held-out validation battery: same categories, different fault parameters,
# never used to decide promotion.
VALIDATION_SCENARIO_BATTERY = [
    FourTankScenarioConfig(name="val_baseline_no_fault"),
    FourTankScenarioConfig(name="val_tank1_leak", leak1_onset_s=183.0, leak1_multiplier=2.2, leak1_offset_s=424.0),
    FourTankScenarioConfig(name="val_tank2_leak", leak2_onset_s=176.0, leak2_multiplier=2.2, leak2_offset_s=418.0),
    FourTankScenarioConfig(name="val_both_leaks", leak1_onset_s=134.0, leak1_multiplier=1.8, leak1_offset_s=331.0,
                            leak2_onset_s=226.0, leak2_multiplier=2.4, leak2_offset_s=437.0),
    FourTankScenarioConfig(name="val_tank1_severe_persistent", leak1_onset_s=356.0, leak1_multiplier=3.4, leak1_offset_s=None),
    FourTankScenarioConfig(name="val_tank2_severe_persistent", leak2_onset_s=344.0, leak2_multiplier=3.4, leak2_offset_s=None),
]


def _format_decision_trace(result):
    yn = lambda flags: f"[{'Y' if flags['tank1'] else '-'},{'Y' if flags['tank2'] else '-'}]"
    lines = []
    for d in result["supervisor_decisions"]:
        lines.append(
            f"t={d['time_s']:.0f}s fault={yn(d['fault_active'])} flag={yn(d['anomaly_flags'])} "
            f"mean|e|=[{d['mean_abs_error']['tank1']:.3f},{d['mean_abs_error']['tank2']:.3f}] "
            f"effort=[{d['mean_effort']['tank1']:.1f},{d['mean_effort']['tank2']:.1f}] "
            f"level=[{d['tank1_level']:.3f},{d['tank2_level']:.3f}] "
            f"sp=[{d['adjusted_setpoints']['tank1']:.3f},{d['adjusted_setpoints']['tank2']:.3f}]"
        )
    return lines


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
        traces.append({
            "scenario": scenario.name,
            "score": round(scenario_score, 3),
            "log_report": build_log_report(result),
            "decision_trace": _format_decision_trace(result),
        })
    return total / len(battery), traces


def validate_supervisor(supervisor_fn):
    return score_supervisor(supervisor_fn, battery=VALIDATION_SCENARIO_BATTERY)


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
    and returns measured per-loop effort/error statistics for a genuinely
    healthy episode, split into the start-up transient (t < 200s: every
    episode starts below the operating point) and the settled remainder.
    """
    import numpy as np
    scenario = FourTankScenarioConfig(name="baseline_no_fault")
    result = run_episode(pid_only_supervisor, scenario)
    t = np.array(result["time_hist"])
    stats = {}
    for phase, mask in (("startup", (t >= 1) & (t < 200)), ("settled", t >= 200)):
        stats[phase] = {}
        for tank, h_key, effort_key, target in (
            ("tank1", "h1_hist", "effort1_hist", scenario.nominal_setpoint1),
            ("tank2", "h2_hist", "effort2_hist", scenario.nominal_setpoint2),
        ):
            err = target - np.array(result[h_key])[mask]
            effort = np.array(result[effort_key])[mask]
            stats[phase][tank] = {
                "err_mean_abs": float(np.abs(err).mean()), "err_min": float(err.min()), "err_max": float(err.max()),
                "effort_mean": float(effort.mean()), "effort_min": float(effort.min()), "effort_max": float(effort.max()),
            }
    return stats


def _plant_block():
    s = FourTankScenarioConfig(name="reference")
    p = plant_parameters()
    op = nominal_operating_point(s.nominal_setpoint1, s.nominal_setpoint2)
    return f"""
PLANT DESCRIPTION (process knowledge a plant engineer on this unit has):
Quadruple-tank process (Johansson, 2000): four tanks, two pumps, two three-way
split valves.
- Lower tanks: tank1 (level h1) and tank2 (level h2). Upper tanks: tank3 (h3)
  and tank4 (h4). Tank3 drains by gravity into tank1, tank4 drains into tank2,
  and tank1/tank2 drain to the sump.
- Pump 1 (voltage v1): its split valve sends gamma1={p['gamma_1']:.2f} of the flow to
  tank1 and {1 - p['gamma_1']:.2f} to tank4 (which then drains into tank2).
- Pump 2 (voltage v2): its split valve sends gamma2={p['gamma_2']:.2f} of the flow to
  tank2 and {1 - p['gamma_2']:.2f} to tank3 (which then drains into tank1).
- So each lower tank gets most of its inflow from the OTHER pump, delayed by
  passing through an upper tank. This is the non-minimum-phase configuration
  (gamma1 + gamma2 < 1).
Mass balances (Torricelli outflow; all tank cross-sections A1..A4 = {p['A1']:g} m^2, g = {p['g']} m/s^2):
  dh1/dt = -a1*sqrt(2g*h1) + a3*sqrt(2g*h3) + gamma1*k1*v1
  dh2/dt = -a2*sqrt(2g*h2) + a4*sqrt(2g*h4) + gamma2*k2*v2
  dh3/dt = -a3*sqrt(2g*h3) + (1-gamma2)*k2*v2
  dh4/dt = -a4*sqrt(2g*h4) + (1-gamma1)*k1*v1
with outlet areas a1={p['a1']}, a2={p['a2']}, a3={p['a3']}, a4={p['a4']} m^2 and pump
gains k1={p['k1']}, k2={p['k2']} m^3/(V*s). Pumps are limited to {s.pump_output_limits[0]:g}-{s.pump_output_limits[1]:g} V.
Only h1 and h2 are measured; h3 and h4 are NOT measured.

Base layer: two PI level loops at a 1 s sample time (Kp={s.pid_kp:g} V/m, Ki={s.pid_ki:g} V/(m*s)),
paired off-diagonally, which is the correct pairing for this configuration:
the tank1 loop drives PUMP 2 and the tank2 loop drives PUMP 1. In telemetry,
tankN.pump_effort is the output voltage of the loop regulating tankN - so
tank1.pump_effort is pump 2's voltage and tank2.pump_effort is pump 1's.
error = setpoint - level.

Design operating point at the nominal setpoints (h1={s.nominal_setpoint1}, h2={s.nominal_setpoint2}; steady state of
the fault-free mass balances): tank1 loop (pump 2) = {op['v2']:.2f} V, tank2 loop
(pump 1) = {op['v1']:.2f} V, h3 = {op['h3']:.3f} m, h4 = {op['h4']:.3f} m.

Operation: every run starts with all four tanks at 0.20 m, below the operating
point, so the first ~200 s are a start-up transient even when nothing is wrong.
Faults can begin during or after it. Level measurements are noise-free
(rounded to 0.1 mm).

Known fault mode: an outlet leak in tank1 and/or tank2, i.e. the effective
outlet area a1 and/or a2 increases, anywhere from mild (~1.5x) to severe
(~4x). A leak can start and stop at any time and can be transient or
persistent; both tanks can leak at the same time with overlapping intervals.
Safety limits: h1 and h2 must stay within [{s.safety_bounds[0]}, {s.safety_bounds[1]}] m.

Supervisor authority: you can only move the two level setpoints (clamped to
[{s.setpoint_clamp[0]}, {s.setpoint_clamp[1]}] m) and raise the two anomaly flags. You cannot drive the pumps
directly.
"""


def _reference_block(r):
    lines = ["MEASURED REFERENCE STATISTICS (an actual fault-free episode under the PI loops alone,",
             "no supervisor action; hard numbers, not estimates):"]
    for phase, label in (("startup", "Start-up transient (t = 1-199 s)"), ("settled", "Settled operation (t >= 200 s)")):
        lines.append(f"- {label}:")
        for tank in ("tank1", "tank2"):
            s = r[phase][tank]
            lines.append(
                f"    {tank}: error range [{s['err_min']:.4f}, {s['err_max']:.4f}], mean|error|={s['err_mean_abs']:.4f}; "
                f"loop effort mean={s['effort_mean']:.2f} V, range [{s['effort_min']:.2f}, {s['effort_max']:.2f}] V"
            )
    lines.append("Any anomaly condition that healthy values in these ranges can satisfy will false-positive.")
    return "\n".join(lines)


def _attempts_block(previous_attempts):
    if not previous_attempts:
        return ""
    entries = []
    for a in previous_attempts:
        per_scenario = ", ".join(f"{t['scenario']}={t['score']:.0f}" for t in a["traces"]) if a.get("traces") else "not scored"
        entries.append(f"- candidate {a['candidate']}: outcome={a['decision']}"
                       + (f" ({a['reason']})" if a.get("reason") else "")
                       + (f", avg score={a['score']:.1f}" if a.get("score") is not None else "")
                       + f"\n  per-scenario: {per_scenario}"
                       + f"\n  what it changed: {str(a.get('proposed_change') or '')[:500]}")
    return ("\nATTEMPTS FROM THE PREVIOUS GENERATION THAT WERE NOT PROMOTED (sampled independently "
            "from the same kind of prompt; learn from what they tried and how it scored):\n" + "\n".join(entries) + "\n")


def build_prompt(current_code, best_score, traces, context_relations, best_val_score=None,
                 reference_stats=None, previous_attempts=None):
    scenario_names = ", ".join(s.name for s in SCENARIO_BATTERY)
    sample = FourTankScenarioConfig(name="reference")
    ref_block = _reference_block(reference_stats) if reference_stats is not None else ""
    results = [{k: v for k, v in t.items() if k != "decision_trace"} for t in traces]
    worst = sorted(traces, key=lambda t: -t["score"])[:TRACE_SCENARIOS]
    trace_block = "\n\n".join(f"{t['scenario']} (score {t['score']:.1f}):\n" + "\n".join(t["decision_trace"]) for t in worst)

    return f"""
You are improving a deterministic supervisory function that sits above the
PI level loops of a quadruple-tank water process. It watches the loops'
telemetry, raises an anomaly flag per tank while that tank has a fault, and
may adjust the level setpoints to mitigate a fault and restore them after it.
{_plant_block()}
{ref_block}

HOW YOUR FUNCTION IS CALLED:
- Every {sample.decision_interval_steps} s (from t = {sample.window_steps} s on), with the most recent {sample.window_steps} one-second
  samples: len(telemetry_window) is ALWAYS exactly {sample.window_steps}. Consecutive windows
  overlap by {sample.window_steps - sample.decision_interval_steps} samples.
- "time" in each sample is seconds since the window's first sample (0, 1, ..., {sample.window_steps - 1}),
  not absolute time.
- The function is stateless: it is re-loaded fresh and keeps no memory between
  calls; everything it knows comes from the current window and its arguments.
- The flags you return are held until the next call {sample.decision_interval_steps} s later. Every second a
  tank's held flag disagrees with that tank's true fault state counts as one
  missed-anomaly or one false-positive event for that tank.

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
active_setpoints and nominal_targets are dicts with keys "tank1" (h1 target) and "tank2" (h2 target).

Rules for the code you write:
- No imports, no exec/eval, no file/network/os access, no access to dunder attributes.
- Only use: arithmetic, comparisons, built-in functions (abs, min, max, len, round, sum, sorted, range, all, any, isinstance, etc.), and the `math`/`statistics` modules (already available, do not import them).
- The function must be a pure function of its three arguments plus module-level constants.

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
{json.dumps(results, indent=2)}

DECISION TRACES of the current supervisor on its {TRACE_SCENARIOS} worst-scoring scenarios, one line
per call. t = absolute simulation time of the call (shown here only so you can
line decisions up with the fault; your function never sees absolute time).
fault = the TRUE fault state at that moment for [tank1, tank2] (Y = leaking).
flag = the flags your function returned (held for the next {sample.decision_interval_steps} s). mean|e| and
effort = per-loop means over the {sample.decision_interval_steps} s since the previous call. level = level at
the call; sp = the setpoints your function returned.
{trace_block}
{_attempts_block(previous_attempts)}
Lessons learned from previous trials - cause-effect relationships already discovered
by earlier attempts (durable observations, not tied to any one candidate's code).
REQUIRED: your code must not repeat a change that a relation below already says
failed for a specific reason. If a relation identifies a specific bug pattern,
your code must not contain that pattern - this is a hard constraint, not a suggestion:
{json.dumps(context_relations, indent=2) if context_relations else "(none recorded yet - this is an early trial)"}

Task:
1. Diagnose what is causing the worst-scoring scenarios, using the traces and the plant description: how does each fault actually show up in the telemetry of both loops, given the cross-coupling and the off-diagonal pairing?
2. Propose an improved `supervise` function that reduces missed anomalies and false positives on both tanks without introducing new safety violations, and that restores both setpoints back toward nominal once their respective faults have genuinely cleared.
3. Before finalizing, check your anomaly conditions against the measured reference statistics for BOTH the start-up transient and settled operation: confirm numerically that healthy values in those ranges do not satisfy them. Put the actual numbers compared against your actual thresholds in "self_check".
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


def call_deepseek(prompt, temperature=SAMPLING_TEMPERATURE, max_retries=3):
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
                temperature=temperature,
            )
        except Exception as e:
            print(f"[DEEPSEEK API ERROR - Attempt {attempt}/{max_retries}]: {e}")
            time.sleep(1.0 * attempt)
            continue
        choice = response.choices[0]
        content = choice.message.content or ""
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            # Empty/truncated bodies are billed like any other response, so log
            # enough to tell a token-limit cutoff (finish_reason="length") from
            # JSON-mode returning nothing (finish_reason="stop").
            usage = response.usage
            details = getattr(usage, "completion_tokens_details", None)
            reasoning = getattr(choice.message, "reasoning_content", None) or ""
            print(f"[DEEPSEEK API ERROR - Attempt {attempt}/{max_retries}]: unparseable response ({e}); "
                  f"finish_reason={choice.finish_reason}, content_chars={len(content)}, reasoning_chars={len(reasoning)}, "
                  f"prompt_tokens={getattr(usage, 'prompt_tokens', None)}, "
                  f"completion_tokens={getattr(usage, 'completion_tokens', None)}, "
                  f"reasoning_tokens={getattr(details, 'reasoning_tokens', None)}")
            time.sleep(1.0 * attempt)
    print(f"[CRITICAL] All {max_retries} retries failed for this call.")
    return None


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


def log_trial(trial_idx, decision, score, failure_analysis, proposed_change, reason=None, validation_score=None,
              self_check=None, candidate=None, temperature=None):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(TRIALS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "trial": trial_idx,
            "candidate": candidate,
            "temperature": temperature,
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
    """Next generation number, from supervisor_gen_<N>.py (one candidate per
    trial, older runs) and supervisor_gen_<N>_c<k>.py (several per generation)."""
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


def generate_report():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    trials = _read_trials()

    with open(SUMMARY_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["trial", "candidate", "decision", "score", "validation_score", "reason"])
        for t in trials:
            writer.writerow([t.get("trial"), t.get("candidate"), t.get("decision"), t.get("score"), t.get("validation_score"), t.get("reason")])

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

    lines += ["", "## Trial history", "", f"- Total candidates logged: {len(trials)}"]
    for decision, count in sorted(decision_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"  - {decision}: {count}")

    lines += ["", "## Score trajectory (promoted candidates only)", "", "| Generation | Candidate | Dev score | Validation score |", "|---|---|---|---|"]
    for t in promoted:
        val = t.get("validation_score")
        val_str = f"{val:.2f}" if val is not None else "-"
        lines.append(f"| gen_{t['trial']} | {t.get('candidate') or '-'} | {t['score']:.2f} | {val_str} |")

    lines += ["", "## Known open issues / lessons learned so far", ""]
    if relations:
        for r in relations:
            lines.append(f"- {r}")
    else:
        lines.append("(none recorded yet)")

    with open(FINAL_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[SUCCESS] Report written to {FINAL_REPORT_PATH} and {SUMMARY_CSV_PATH}")


def _evaluate_candidate(response, candidate, gen_idx):
    """Security-check, load and score one sampled response. Returns a record;
    record["decision"] is provisional until the generation's winner is picked."""
    if response is None:
        return {"candidate": candidate, "decision": "SKIPPED", "reason": "DeepSeek call failed", "score": None}
    record = {
        "candidate": candidate,
        "code": response.get("code", ""),
        "failure_analysis": response.get("failure_analysis"),
        "proposed_change": response.get("proposed_change"),
        "self_check": response.get("self_check"),
        "relations": response.get("relations_learned") or [],
        "score": None,
        "reason": None,
    }
    ok, reason = check_source(record["code"], required_args=MIMO_REQUIRED_ARGS)
    if not ok:
        record.update(decision="REJECTED_SECURITY", reason=reason)
        return record
    fn, err = safe_exec_supervisor(record["code"])
    if err:
        record.update(decision="REJECTED_LOAD", reason=err)
        return record
    record["fn"] = fn
    record["score"], record["traces"] = score_supervisor(fn)
    append_failure_points(record["traces"], f"trainer_gen_{gen_idx}_c{candidate}")
    record["decision"] = "SCORED"
    return record


def main():
    if "--report" in sys.argv:
        generate_report()
        return

    num_generations = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    start_gen = _next_trial_start()

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
    print(f"[REFERENCE] healthy settled |err1| up to {max(abs(reference_stats['settled']['tank1']['err_min']), abs(reference_stats['settled']['tank1']['err_max'])):.4f}, "
          f"|err2| up to {max(abs(reference_stats['settled']['tank2']['err_min']), abs(reference_stats['settled']['tank2']['err_max'])):.4f}")

    previous_attempts = []
    for g in range(num_generations):
        gen_idx = start_gen + g
        print(f"\n=== Generation {g + 1}/{num_generations} (gen_{gen_idx}): sampling {CANDIDATES_PER_GENERATION} candidates "
              f"at temperature {SAMPLING_TEMPERATURE} ===")
        prompt = build_prompt(current_code, best_score, best_traces, load_context_report(),
                              best_val_score=best_val_score, reference_stats=reference_stats,
                              previous_attempts=previous_attempts)
        with ThreadPoolExecutor(max_workers=CANDIDATES_PER_GENERATION) as pool:
            responses = list(pool.map(lambda _: call_deepseek(prompt), range(CANDIDATES_PER_GENERATION)))

        records = [_evaluate_candidate(resp, k, gen_idx) for k, resp in enumerate(responses, start=1)]

        winner = None
        for r in records:
            if r["decision"] != "SCORED":
                print(f"  c{r['candidate']}: [{r['decision']}] {r.get('reason')}")
                continue
            if r["score"] >= best_score:
                r["decision"] = "ROLLBACK"
            else:
                regression = find_scenario_regression(best_traces, r["traces"])
                if regression:
                    scen_name, old_s, new_s = regression
                    r["decision"] = "REJECTED_REGRESSION"
                    r["reason"] = f"{scen_name} regressed {old_s:.1f} -> {new_s:.1f}"
                else:
                    r["decision"] = "ELIGIBLE"
                    if winner is None or r["score"] < winner["score"]:
                        winner = r
            print(f"  c{r['candidate']}: score {r['score']:.3f} (champion {best_score:.3f}) -> {r['decision']}"
                  + (f" ({r['reason']})" if r.get("reason") else ""))

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
                      temperature=SAMPLING_TEMPERATURE)

        if winner is not None:
            promote(winner["code"], gen_idx, winner["candidate"])
            best_score, current_code, best_traces = winner["score"], winner["code"], winner["traces"]
            best_val_score, _ = validate_supervisor(winner["fn"])
            print(f"[VALIDATION] held-out score: {best_val_score:.3f} (dev score: {best_score:.3f})")
            winner["decision"] = "PROMOTED"
            log_trial(gen_idx, "PROMOTED", winner["score"], winner["failure_analysis"], winner["proposed_change"],
                      validation_score=best_val_score, self_check=winner["self_check"], candidate=winner["candidate"],
                      temperature=SAMPLING_TEMPERATURE)
        else:
            print(f"[NO PROMOTION] champion stays at {best_score:.3f}")

        # One set of relations per generation, from the promoted candidate (or
        # the best-scoring one), so four near-duplicate lists don't crowd the
        # context report.
        scored = [r for r in records if r.get("score") is not None]
        source = winner or (min(scored, key=lambda r: r["score"]) if scored else None)
        if source is not None and source.get("relations"):
            print(f"[LEARNED] {source['relations']}")
            append_context_report(gen_idx, source["relations"])

        previous_attempts = [r for r in records if r is not winner]

    print(f"\n[DONE] Final best score: {best_score:.3f}. current_supervisor.py reflects the best candidate found.")
    generate_report()


if __name__ == "__main__":
    main()
