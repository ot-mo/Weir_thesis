"""Layer 3 for the four-tank setpoint-coordination test bed: the LLM
meta-supervisor writes a deterministic supervise() function that only moves
the PI setpoints, as in the goal document's grinding-circuit experiment.

Run manually: python train_supervisor_coordination.py [num_generations] [--effort none|low|high|max] [--run NAME]
Report only, no API calls: python train_supervisor_coordination.py --report [--run NAME]

A copy of train_supervisor_four_tank.py (which stays as it is for the leak
task) with the same loop - parallel candidates, security gate, elitist
promotion with a per-scenario regression guard, decision traces, previous
attempts, lessons learned, stop switch, token logging - pointed at
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
import hashlib
import json
import os
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

REQUIRED_ARGS = ("telemetry_window", "active_setpoints", "objectives")

BASE_SUPERVISORS_DIR = "generated_supervisors_coordination"
SEED_SUPERVISOR_PATH = os.path.join(BASE_SUPERVISORS_DIR, "supervisor_gen_0.py")
SUPERVISORS_DIR = BASE_SUPERVISORS_DIR
CURRENT_SUPERVISOR_PATH = os.path.join(SUPERVISORS_DIR, "current_supervisor.py")
RESULTS_DIR = "results"
EVALUATIONS_PATH = os.path.join(RESULTS_DIR, "evaluations_coordination.jsonl")
TRIALS_PATH = os.path.join(RESULTS_DIR, "supervisor_training_trials_coordination.jsonl")
CONTEXT_REPORT_PATH = os.path.join(RESULTS_DIR, "context_report_coordination.jsonl")
SUMMARY_CSV_PATH = os.path.join(RESULTS_DIR, "summary_coordination.csv")
FINAL_REPORT_PATH = os.path.join(RESULTS_DIR, "final_report_coordination.md")
BASELINES_CSV_PATH = os.path.join(RESULTS_DIR, "coordination_baselines.csv")
MAX_CONTEXT_RELATIONS = 12
MAX_RELATIONS_PER_GENERATION = 2
MAX_RELATION_WORDS = 30

CANDIDATES_PER_GENERATION = 4
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
NON_THINKING_TEMPERATURE = 1.0
STOP_FILE = "STOP_TRAINING"
TRACE_SCENARIOS = 2

REGRESSION_ABS_TOLERANCE = 20.0
REGRESSION_REL_TOLERANCE = 0.15

# Same seeds as benchmark_coordination.py, one scenario per cell, so these are
# the "_0" scenarios of the baseline CSV and the numbers are directly comparable.
DEV_BATTERY = C.make_battery("dev", per_cell=1, seed=1)
VALIDATION_BATTERY = C.make_battery("dev", per_cell=1, seed=2)
BEYOND_BATTERY = C.make_battery("beyond", per_cell=1, seed=3)


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


def append_context_report(trial_idx, relations):
    if not relations:
        return
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(CONTEXT_REPORT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"trial": trial_idx, "relations": relations}) + "\n")


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
setpoints for h1 and h2; you never drive the pumps directly.

Production: Q = a1*sqrt(2g*h1) + a2*sqrt(2g*h2), reported in L/s. With the loops holding h1 and h2
at their setpoints, Q at steady state depends only on the two setpoints, while the pump voltages
and upper levels needed to hold them depend on the disturbances. Your code may evaluate these
relations itself (the constants above and `math` are available), e.g. to find the setpoint pair
that gives the target production.

Design operating point: setpoints h1={C.NOMINAL_SETPOINTS['h1']}, h2={C.NOMINAL_SETPOINTS['h2']} give Q={C.NOMINAL_PRODUCTION:.2f} L/s with
v1={op['v1']:.2f} V, v2={op['v2']:.2f} V, h3={op['h3']:.3f} m, h4={op['h4']:.3f} m. Every run starts in steady
operation at this point. Measurements are noise-free (rounded to 0.1 mm).

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
        per_scenario = ", ".join(f"{t['scenario']}={t['score']:.0f}" for t in a["traces"]) if a.get("traces") else "not scored"
        entries.append(f"- candidate {a['candidate']}: {a['decision']}"
                       + (f" ({a['reason']})" if a.get("reason") else "")
                       + (f", avg {a['score']:.1f}" if a.get("score") is not None else "")
                       + f"; per-scenario: {per_scenario}"
                       + f"\n  changed: {str(a.get('proposed_change') or '')[:300]}")
    return ("\nPREVIOUS GENERATION'S NON-PROMOTED ATTEMPTS (sampled independently; learn from what "
            "they tried and how it scored):\n" + "\n".join(entries) + "\n")


def _results_block(traces):
    lines = []
    for t in traces:
        m = t["metrics"]
        lines.append(f"- {t['scenario']}: score {t['score']:.1f} | production off target {m['production_iae_l']:.0f} L | "
                     f"h2 band violated {m['band_violation_s']:.0f} s | upper limit violated {m['upper_violation_s']:.0f} s | "
                     f"safety {m['safety_violation_s']:.0f} s | setpoint travel {m['setpoint_tv_m']:.3f} m | "
                     f"recovery {m['recovery_s']:.0f} s | pump saturated {m['saturation_s']:.0f} s | exceptions {m['exceptions']}")
    return "\n".join(lines)


def build_prompt(current_code, best_score, traces, context_relations, best_val_score=None, previous_attempts=None):
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
- Every {sample.decision_interval_steps} s (from t = {sample.window_steps} s on), with the most recent {sample.window_steps} one-second
  samples: len(telemetry_window) is ALWAYS exactly {sample.window_steps}. Consecutive windows overlap by
  {sample.window_steps - sample.decision_interval_steps} samples.
- "time" in each sample is seconds since the window's first sample (0, 1, ..., {sample.window_steps - 1}), not
  absolute time.
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
{{"time": float, "h1": float, "h2": float, "h3": float, "h4": float, "v1": float, "v2": float, "production": float}}
(levels in m, pump voltages in V, production in L/s). active_setpoints is {{"h1": float, "h2": float}}.
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
Promotion requires a better average AND no single scenario worse than the champion by more than
the larger of {REGRESSION_ABS_TOLERANCE:g} points or {REGRESSION_REL_TOLERANCE:.0%}.

TASK:
1. Diagnose what causes the worst-scoring scenarios, using the traces and the plant description: how does each disturbance move the pump voltages and upper levels, and which objective is violated?
2. Write an improved `supervise` that keeps production on target and the constraints satisfied, using the free degree of freedom, without moving the setpoints more than needed.
3. In "self_check", state in 2-4 sentences how your logic keeps production on target and the constraints satisfied when a disturbance pushes an upper level toward its limit or a pump toward saturation. Do not solve the mass balances by hand; if your logic needs steady-state relations, compute them in the code.
4. Add at most {MAX_RELATIONS_PER_GENERATION} NEW generalizable cause-effect relations this result reveals, each ONE sentence of at most {MAX_RELATION_WORDS} words. Do not repeat a listed one.

OUTPUT FORMAT - strictly this JSON:
{{
  "failure_analysis": {{
    "what_failed": "string",
    "failing_scenarios": ["scenario_name", ...],
    "change_type": "structural | scalar/config | bug_fix",
    "next_recommendation": "string"
  }},
  "self_check": "string, 2-4 sentences: how your logic handles an upper level near its limit or a saturating pump",
  "proposed_change": "string, at most 2 sentences",
  "code": "full source of the new supervise function as a string",
  "relations_learned": ["one sentence, at most {MAX_RELATION_WORDS} words", ...]
}}

========== CURRENT STATE (changes every generation) ==========

Current supervisor source:
```python
{current_code}
```

Current battery score: {best_score:.1f}. {gen_check}

Per-scenario results:
{_results_block(traces)}

DECISION TRACES of the current supervisor on its {TRACE_SCENARIOS} worst-scoring scenarios, one row per call where
the situation changes (production leaves or re-enters the {C.RECOVERY_TOLERANCE:.0%} band around the target, a constraint
starts or stops being violated, the setpoints start or stop moving) with one row either side, plus
one row per minute while something stays wrong. t = absolute simulation time (your function never sees it); Q = production
(L/s); h = [h1, h2, h3, h4] (m); v = [v1, v2] (V); sp = setpoints returned; disturbance = the TRUE
active disturbance (shown here only for diagnosis; your function cannot see it).
{trace_block}
{_attempts_block(previous_attempts)}
LESSONS LEARNED by earlier attempts. HARD CONSTRAINT: do not repeat a change a lesson says
failed, and do not reintroduce a bug pattern a lesson identifies:
{chr(10).join('- ' + r for r in context_relations) if context_relations else "(none recorded yet)"}

Respond with the JSON object described under OUTPUT FORMAT.
"""


def call_deepseek(prompt, reasoning_effort=REASONING_EFFORT_DEFAULT, max_retries=3):
    """Returns (parsed JSON or None, token usage of every attempt that got a
    response, including unparseable ones, since those are billed too)."""
    usage_per_attempt = []
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
                max_tokens=MAX_OUTPUT_TOKENS,
                **_thinking_kwargs(reasoning_effort),
            )
        except Exception as e:
            print(f"[DEEPSEEK API ERROR - Attempt {attempt}/{max_retries}]: {e}")
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
            print(f"[DEEPSEEK API ERROR - Attempt {attempt}/{max_retries}]: unparseable response ({e}); "
                  f"finish_reason={choice.finish_reason}, content_chars={len(content)}, reasoning_chars={len(reasoning)}, "
                  f"prompt_tokens={usage['prompt']}, completion_tokens={usage['completion']}, "
                  f"reasoning_tokens={usage['reasoning']}")
            time.sleep(1.0 * attempt)
    print(f"[CRITICAL] All {max_retries} retries failed for this call.")
    return None, usage_per_attempt


def _thinking_kwargs(reasoning_effort):
    if reasoning_effort == "none":
        return {"extra_body": {"thinking": {"type": "disabled"}}, "temperature": NON_THINKING_TEMPERATURE}
    return {"reasoning_effort": reasoning_effort}


def _usage(response):
    u = response.usage
    details = getattr(u, "completion_tokens_details", None)
    return {
        "prompt": getattr(u, "prompt_tokens", None),
        "cache_hit": getattr(u, "prompt_cache_hit_tokens", None),
        "completion": getattr(u, "completion_tokens", None),
        "reasoning": getattr(details, "reasoning_tokens", None),
    }


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


def log_trial(trial_idx, decision, score, failure_analysis, proposed_change, reason=None, validation_score=None,
              self_check=None, candidate=None, reasoning_effort=None, usage=None):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(TRIALS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "trial": trial_idx, "candidate": candidate, "reasoning_effort": reasoning_effort, "usage": usage,
            "decision": decision, "score": score, "validation_score": validation_score,
            "failure_analysis": failure_analysis, "self_check": self_check,
            "proposed_change": proposed_change, "reason": reason,
        }) + "\n")


def find_scenario_regression(best_traces, cand_traces):
    for b, c in zip(best_traces, cand_traces):
        allowed = max(REGRESSION_ABS_TOLERANCE, REGRESSION_REL_TOLERANCE * b["score"])
        if c["score"] > b["score"] + allowed:
            return b["scenario"], b["score"], c["score"]
    return None


def _use_run(run_name):
    """Separate named experiment (own candidates, lessons and logs), seeded
    with gen_0 the first time - e.g. for independent repeated runs (C3)."""
    global SUPERVISORS_DIR, CURRENT_SUPERVISOR_PATH, EVALUATIONS_PATH, TRIALS_PATH
    global CONTEXT_REPORT_PATH, SUMMARY_CSV_PATH, FINAL_REPORT_PATH
    SUPERVISORS_DIR = os.path.join(BASE_SUPERVISORS_DIR, run_name)
    CURRENT_SUPERVISOR_PATH = os.path.join(SUPERVISORS_DIR, "current_supervisor.py")
    suffix = f"coordination_{run_name}"
    EVALUATIONS_PATH = os.path.join(RESULTS_DIR, f"evaluations_{suffix}.jsonl")
    TRIALS_PATH = os.path.join(RESULTS_DIR, f"supervisor_training_trials_{suffix}.jsonl")
    CONTEXT_REPORT_PATH = os.path.join(RESULTS_DIR, f"context_report_{suffix}.jsonl")
    SUMMARY_CSV_PATH = os.path.join(RESULTS_DIR, f"summary_{suffix}.csv")
    FINAL_REPORT_PATH = os.path.join(RESULTS_DIR, f"final_report_{suffix}.md")
    os.makedirs(SUPERVISORS_DIR, exist_ok=True)
    if not os.path.exists(CURRENT_SUPERVISOR_PATH):
        with open(SEED_SUPERVISOR_PATH, "r", encoding="utf-8") as src, \
                open(CURRENT_SUPERVISOR_PATH, "w", encoding="utf-8") as dst:
            dst.write(src.read())
        print(f"[RUN] new run '{run_name}' seeded with {SEED_SUPERVISOR_PATH}")


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
        writer.writerow(["trial", "candidate", "reasoning_effort", "decision", "score", "validation_score", "reason"])
        for t in trials:
            writer.writerow([t.get("trial"), t.get("candidate"), t.get("reasoning_effort"), t.get("decision"),
                             t.get("score"), t.get("validation_score"), t.get("reason")])

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

    usage_by_effort = {}
    for t in trials:
        if t.get("usage"):
            usage_by_effort.setdefault(t.get("reasoning_effort") or "?", []).extend(t["usage"])
    if usage_by_effort:
        lines += ["", "## Token usage per API request, by reasoning effort", "",
                  "| Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning |",
                  "|---|---|---|---|---|---|"]
        for effort_level, usages in usage_by_effort.items():
            s = _sum_usage(usages)
            n = s["requests"]
            lines.append(f"| {effort_level} | {n} | {s['prompt'] / n:.0f} | {s['cache_hit'] / n:.0f} | "
                         f"{s['completion'] / n:.0f} | {s['reasoning'] / n:.0f} |")

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
    if run_name:
        _use_run(run_name)
    elif not os.path.exists(CURRENT_SUPERVISOR_PATH):
        with open(SEED_SUPERVISOR_PATH, "r", encoding="utf-8") as src, \
                open(CURRENT_SUPERVISOR_PATH, "w", encoding="utf-8") as dst:
            dst.write(src.read())
    if "--report" in sys.argv:
        generate_report()
        return

    num_generations = next((int(a) for a in sys.argv[1:] if a.isdigit()), 4)
    effort = option("--effort", REASONING_EFFORT_DEFAULT)
    start_gen = _next_trial_start()

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
            os.remove(STOP_FILE)
            print(f"\n[STOP] {STOP_FILE} found - stopping before generation {g + 1}/{num_generations}; "
                  f"no requests were sent for it")
            break
        gen_idx = start_gen + g
        print(f"\n=== Generation {g + 1}/{num_generations} (gen_{gen_idx}): sampling {CANDIDATES_PER_GENERATION} candidates "
              f"at reasoning effort {effort} ===")
        prompt = build_prompt(current_code, best_score, best_traces, load_context_report(),
                              best_val_score=best_val_score, previous_attempts=previous_attempts)
        with ThreadPoolExecutor(max_workers=CANDIDATES_PER_GENERATION) as pool:
            responses = list(pool.map(lambda _: call_deepseek(prompt, reasoning_effort=effort),
                                      range(CANDIDATES_PER_GENERATION)))

        records = [_evaluate_candidate(resp, usage, k, gen_idx) for k, (resp, usage) in enumerate(responses, start=1)]
        tokens = _sum_usage([u for r in records for u in r["usage"]])
        print(f"[TOKENS] {tokens['requests']} requests: prompt {tokens['prompt']} (cache hit {tokens['cache_hit']}), "
              f"completion {tokens['completion']} (reasoning {tokens['reasoning']})")

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
                      reasoning_effort=effort, usage=r["usage"])

        if winner is not None:
            promote(winner["code"], gen_idx, winner["candidate"])
            best_score, current_code, best_traces = winner["score"], winner["code"], winner["traces"]
            best_val_score, _ = validate_supervisor(winner["fn"])
            print(f"[VALIDATION] held-out score: {best_val_score:.3f} (dev score: {best_score:.3f})")
            winner["decision"] = "PROMOTED"
            log_trial(gen_idx, "PROMOTED", winner["score"], winner["failure_analysis"], winner["proposed_change"],
                      validation_score=best_val_score, self_check=winner["self_check"], candidate=winner["candidate"],
                      reasoning_effort=effort, usage=winner["usage"])
        else:
            print(f"[NO PROMOTION] champion stays at {best_score:.3f}")

        scored = [r for r in records if r.get("score") is not None]
        source = winner or (min(scored, key=lambda r: r["score"]) if scored else None)
        if source is not None and source.get("relations"):
            relations = source["relations"][:MAX_RELATIONS_PER_GENERATION]
            print(f"[LEARNED] {relations}")
            append_context_report(gen_idx, relations)

        previous_attempts = [r for r in records if r is not winner]

    print(f"\n[DONE] Final best score: {best_score:.3f}. current_supervisor.py reflects the best candidate found.")
    generate_report()


if __name__ == "__main__":
    main()
