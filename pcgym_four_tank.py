"""PC-Gym quadruple-tank benchmark: PID-only vs our two-tank supervisor.

Uses PC-Gym's built-in `four_tank` model (Johansson's classic quadruple-tank
process: 2 pumps, 4 coupled tank levels) as a richer, better-established MIMO
benchmark than our own two-tank cascade. Each pump feeds its own tank
directly AND the *other* loop's tank indirectly through a delayed
cross-coupling path (v1 -> h1 direct, v1 -> h4 -> h2 delayed; v2 -> h2 direct,
v2 -> h3 -> h1 delayed) - a harder, more circuit-like interaction than our
direct cascade.

Reuses our existing two-tank MIMO supervisor interface unchanged:
    supervise(telemetry_window, active_setpoints, nominal_targets)
where "tank1"/"tank2" are the h1/h2 level loops. Each telemetry entry's
pump_effort is the output of the loop regulating that tank - under the
default cross pairing that is pump 2 for tank1 and pump 1 for tank2.

Setup notes (found empirically - see conversation, not in the PC-Gym docs):
- dt=1.0s; the plant's natural settling time is ~100-300s, an order of
  magnitude slower than our own tank_sim.py.
- Default gamma_1=gamma_2=0.2 puts this in the "non-minimum-phase" regime
  (gamma_1+gamma_2 < 1): most pump flow is routed through the cross-coupling
  path, so each level is mainly driven by the OTHER pump through the upper
  tank. The level loops are therefore paired off-diagonally (see
  FourTankScenarioConfig.pid_pairing); pairing them diagonally made the loops
  fight each other during faults.
- Max achievable steady state at full 12V on both pumps is h1~=0.50,
  h2~=0.61 - setpoints must stay comfortably below that.

CRITICAL HISTORY - why this file bypasses pcgym.make_env entirely and
integrates the model directly instead: the original version used
`pcgym.make_env(...)` with `integration_method='jax'` (the default 'casadi'
path fails on Windows - its native CVODES plugin DLL won't load here) and
injected faults by mutating `env.model.a1`/`a2` at runtime. This silently
had ZERO effect on the actual simulated dynamics for two independent
reasons, discovered only after ~20 training trials never once produced a
real detection: (1) `make_env.reset()` builds a brand-new
`integration_engine`, whose own `__init__` calls `make_env(env_params)`
AGAIN internally, so `env.int_eng.env` is a second, separate model instance
from `env` itself (`env.int_eng.env is env` is False) - the real stepping
code reads `env.int_eng.env.model`, not `env.model`. (2) Even after fixing
that, PC-Gym's JAX integration path still showed no effect - confirmed via
direct testing that PC-Gym's JAX/diffrax stepping caches/traces the dynamics
function in a way that doesn't pick up later Python-level attribute
mutations on the model object. Every "fault" scenario in every four-tank
experiment before this fix was therefore actually running completely
fault-free the whole time, which is the real reason detection never worked -
not a threshold-tuning or window-size problem, though those were real,
separately-fixed issues too. The permanent fix: instantiate
`pcgym.model_classes.four_tank(int_method="numpy")` directly (confirmed
mutating `.a1`/`.a2` on this object takes effect immediately, since it's
plain numpy with no tracing/caching) and integrate it ourselves with simple
explicit Euler steps, exactly like tank_sim.py and two_tank_sim.py already
do. This also incidentally eliminates the earlier CasADi DLL issue and a
pump-output-floor workaround that was needed for PC-Gym's adaptive JAX
integrator (whose sqrt(h) singularity at h=0 doesn't affect a fixed-step
Euler loop the same way).
"""

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
from pcgym.model_classes import four_tank

from PID import PIDController
from supervisor_security import call_with_timeout

A1_NOMINAL = 0.0035  # four_tank's default outlet area for tank 1
A2_NOMINAL = 0.0030  # four_tank's default outlet area for tank 2


@dataclass
class FourTankScenarioConfig:
    name: str
    sim_time: float = 600.0
    dt: float = 1.0
    nominal_setpoint1: float = 0.30  # h1 target
    nominal_setpoint2: float = 0.35  # h2 target
    leak1_onset_s: Optional[float] = None
    leak1_multiplier: float = 1.0  # outlet-area multiplier while the leak is active
    leak1_offset_s: Optional[float] = None
    leak2_onset_s: Optional[float] = None
    leak2_multiplier: float = 1.0
    leak2_offset_s: Optional[float] = None
    initial_levels: tuple = (0.2, 0.2, 0.2, 0.2)
    safety_bounds: tuple = (0.02, 1.5)
    # "cross": the tank1 loop drives pump 2 and the tank2 loop drives pump 1.
    # With gamma_1 = gamma_2 = 0.2 the relative gain for the diagonal pairing is
    # gamma1*gamma2/(gamma1+gamma2-1) = -0.07, so Johansson (2000) pairs
    # off-diagonally. Under the old "diagonal" pairing a tank1 leak made loop 1
    # saturate pump 1, which overfed tank2 via tank4, so loop 2 cut pump 2 and
    # drained tank3 - tank1's main feed - leaving 171 unavoidable safety
    # violations in tank1_severe_persistent that no setpoint policy could fix.
    pid_pairing: str = "cross"
    # PI retuned for the cross pairing (grid search: best 600s IAE among tunings
    # that converge; the old 15/0.4/2.0 limit-cycles at +/-0.05 on this pairing).
    pid_kp: float = 40.0
    pid_ki: float = 0.3
    pid_kd: float = 0.0
    pump_output_limits: tuple = (1.0, 12.0)
    # Decision cadence and window length are deliberately separate: flags can
    # only change at a decision, so a 50s cadence alone forced >=51 missed and
    # >=51 false-positive steps per fault event no matter how good the
    # detector was. Deciding every 10s on overlapping 50s windows removes that
    # floor while keeping the same amount of history per decision.
    window_steps: int = 50  # len(telemetry_window), always exactly this long
    decision_interval_steps: int = 10  # supervisor decides every 10s
    setpoint_clamp: tuple = (0.05, 0.48)
    supervisor_timeout_s: float = 0.5


def _make_plant():
    """Direct instantiation of PC-Gym's validated four_tank physics, bypassing
    pcgym.make_env's gym.Env/integration-engine wrapper entirely (see the
    CRITICAL note in the module docstring for why: both the JAX and CasADi
    integration paths through that wrapper broke fault injection or crashed
    on this machine). int_method='numpy' selects the model's plain
    numpy/np.sqrt code path instead of jax.numpy, so a plain explicit-Euler
    loop - the same pattern tank_sim.py and two_tank_sim.py already use -
    integrates it directly and reliably.
    """
    return four_tank(int_method="numpy")


def plant_parameters() -> dict:
    m = _make_plant()
    return {k: getattr(m, k) for k in ("g", "gamma_1", "gamma_2", "k1", "k2", "a1", "a2", "a3", "a4", "A1", "A2", "A3", "A4")}


def nominal_operating_point(h1_target: float, h2_target: float) -> dict:
    """Steady state of the fault-free mass balances with h1/h2 held at their
    targets: solves the two lower-tank balances for the pump voltages, then
    the upper-tank balances for h3/h4."""
    p = plant_parameters()
    root = lambda h: np.sqrt(2 * p["g"] * h)
    q1 = p["a1"] * root(h1_target)  # tank1 outflow = total tank1 inflow
    q2 = p["a2"] * root(h2_target)
    # q1 = g1*k1*v1 + (1-g2)*k2*v2 ;  q2 = (1-g1)*k1*v1 + g2*k2*v2
    coeffs = np.array([[p["gamma_1"] * p["k1"], (1 - p["gamma_2"]) * p["k2"]],
                       [(1 - p["gamma_1"]) * p["k1"], p["gamma_2"] * p["k2"]]])
    v1, v2 = np.linalg.solve(coeffs, np.array([q1, q2]))
    h3 = ((1 - p["gamma_2"]) * p["k2"] * v2 / p["a3"]) ** 2 / (2 * p["g"])
    h4 = ((1 - p["gamma_1"]) * p["k1"] * v1 / p["a4"]) ** 2 / (2 * p["g"])
    return {"v1": float(v1), "v2": float(v2), "h3": float(h3), "h4": float(h4)}


def pid_only_supervisor(telemetry_window, active_setpoints, nominal_targets):
    return {
        "diagnosis": "PID-only baseline: no supervisory action.",
        "adjusted_setpoints": dict(nominal_targets),
        "anomaly_flags": {"tank1": False, "tank2": False},
    }


def build_log_report(episode_result: dict) -> dict:
    return {
        "scenario": episode_result["scenario"],
        "metrics": episode_result["metrics"],
        "failure_point_counts": _count_failure_points(episode_result["failure_points"]),
    }


def _count_failure_points(failure_points: list) -> dict:
    counts = {}
    for fp in failure_points:
        key = f"{fp['tank']}:{fp['type']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def run_episode(supervisor_fn: Callable, scenario: FourTankScenarioConfig) -> dict:
    model = _make_plant()
    x = np.array(scenario.initial_levels, dtype=float)  # [h1, h2, h3, h4]
    nsteps = int(scenario.sim_time / scenario.dt)

    pid1 = PIDController(Kp=scenario.pid_kp, Ki=scenario.pid_ki, Kd=scenario.pid_kd,
                          setpoint=scenario.nominal_setpoint1, output_limits=scenario.pump_output_limits)
    pid2 = PIDController(Kp=scenario.pid_kp, Ki=scenario.pid_ki, Kd=scenario.pid_kd,
                          setpoint=scenario.nominal_setpoint2, output_limits=scenario.pump_output_limits)

    active_setpoints = {"tank1": scenario.nominal_setpoint1, "tank2": scenario.nominal_setpoint2}
    time_hist, h1_hist, h2_hist, h3_hist, h4_hist = [], [], [], [], []
    v1_hist, v2_hist = [], []
    effort1_hist, effort2_hist = [], []
    telemetry_buffer = []
    supervisor_decisions = []
    failure_points = []

    iae_accum = 0.0
    last_anomaly_flags = {"tank1": False, "tank2": False}

    for t_step in range(nsteps - 1):
        t = t_step * scenario.dt

        if scenario.leak1_onset_s is not None and t == scenario.leak1_onset_s:
            model.a1 = A1_NOMINAL * scenario.leak1_multiplier
        if scenario.leak1_offset_s is not None and t == scenario.leak1_offset_s:
            model.a1 = A1_NOMINAL
        if scenario.leak2_onset_s is not None and t == scenario.leak2_onset_s:
            model.a2 = A2_NOMINAL * scenario.leak2_multiplier
        if scenario.leak2_offset_s is not None and t == scenario.leak2_offset_s:
            model.a2 = A2_NOMINAL

        fault_active = {
            "tank1": abs(model.a1 - A1_NOMINAL) > 1e-9,
            "tank2": abs(model.a2 - A2_NOMINAL) > 1e-9,
        }

        # pid1/pid2 are the tank1/tank2 level loops; which pump each one
        # drives depends on the pairing.
        pid1.setpoint = active_setpoints["tank1"]
        pid2.setpoint = active_setpoints["tank2"]
        h1, h2 = float(x[0]), float(x[1])
        effort1 = float(pid1.update(measurement=h1, current_time=t))
        effort2 = float(pid2.update(measurement=h2, current_time=t))
        if scenario.pid_pairing == "cross":
            v1, v2 = effort2, effort1
        else:
            v1, v2 = effort1, effort2

        dxdt = np.array(model(x, np.array([v1, v2])), dtype=float)
        x = np.maximum(x + dxdt * scenario.dt, 0.0)
        h1n, h2n, h3n, h4n = float(x[0]), float(x[1]), float(x[2]), float(x[3])

        error1 = active_setpoints["tank1"] - h1n
        error2 = active_setpoints["tank2"] - h2n
        iae_accum += (abs(error1) + abs(error2)) * scenario.dt

        time_hist.append(t); h1_hist.append(h1n); h2_hist.append(h2n)
        h3_hist.append(h3n); h4_hist.append(h4n); v1_hist.append(v1); v2_hist.append(v2)
        effort1_hist.append(effort1); effort2_hist.append(effort2)

        # Telemetry is per level loop: tankN's pump_effort is the output of the
        # loop regulating tankN (pump 2 for tank1 under the cross pairing).
        telemetry_buffer.append({
            "time": t,
            "tank1": {"level": round(h1n, 4), "pump_effort": round(effort1, 3), "error": round(error1, 4)},
            "tank2": {"level": round(h2n, 4), "pump_effort": round(effort2, 3), "error": round(error2, 4)},
        })

        for tank_name, level in (("tank1", h1n), ("tank2", h2n)):
            if level < scenario.safety_bounds[0] or level > scenario.safety_bounds[1]:
                failure_points.append({"time_s": t, "type": "safety_violation", "tank": tank_name, "detail": f"level={level:.4f}"})

        for tank_name in ("tank1", "tank2"):
            if fault_active[tank_name] and not last_anomaly_flags[tank_name]:
                failure_points.append({"time_s": t, "type": "missed_anomaly", "tank": tank_name, "detail": "fault active, last anomaly_flag=False"})
            elif not fault_active[tank_name] and last_anomaly_flags[tank_name]:
                failure_points.append({"time_s": t, "type": "false_positive", "tank": tank_name, "detail": "no fault, last anomaly_flag=True"})

        if t_step >= scenario.window_steps and t_step % scenario.decision_interval_steps == 0:
            # "time" is re-based to seconds since the window's first sample, so a
            # supervisor can't key its flags off the scenarios' absolute fault times.
            recent = telemetry_buffer[-scenario.window_steps:]
            t0 = recent[0]["time"]
            window = [{"time": s["time"] - t0, "tank1": s["tank1"], "tank2": s["tank2"]} for s in recent]
            nominal_targets = {"tank1": scenario.nominal_setpoint1, "tank2": scenario.nominal_setpoint2}
            (decision, err) = call_with_timeout(
                supervisor_fn, (window, dict(active_setpoints), nominal_targets),
                timeout_s=scenario.supervisor_timeout_s,
            )
            if err is not None:
                fp_type = "timeout" if err == "timeout" else "exception"
                failure_points.append({"time_s": t, "type": fp_type, "tank": "both", "detail": err})
                decision = {
                    "diagnosis": f"SUPERVISOR_FAILURE: {err}. Preserving setpoints.",
                    "adjusted_setpoints": dict(active_setpoints),
                    "anomaly_flags": {"tank1": True, "tank2": True},
                }

            adjusted = decision.get("adjusted_setpoints", {}) or {}
            flags = decision.get("anomaly_flags", {}) or {}
            new_setpoints, new_flags = {}, {}
            for tank_name in ("tank1", "tank2"):
                proposed = float(adjusted.get(tank_name, active_setpoints[tank_name]))
                new_setpoints[tank_name] = max(scenario.setpoint_clamp[0], min(scenario.setpoint_clamp[1], proposed))
                new_flags[tank_name] = bool(flags.get(tank_name, False))

            since_last = telemetry_buffer[-scenario.decision_interval_steps:]
            supervisor_decisions.append({
                "time_s": t,
                "tank1_level": round(h1n, 4),
                "tank2_level": round(h2n, 4),
                "fault_active": dict(fault_active),
                "mean_abs_error": {tn: round(sum(abs(s[tn]["error"]) for s in since_last) / len(since_last), 4)
                                   for tn in ("tank1", "tank2")},
                "mean_effort": {tn: round(sum(s[tn]["pump_effort"] for s in since_last) / len(since_last), 2)
                                for tn in ("tank1", "tank2")},
                "adjusted_setpoints": new_setpoints,
                "anomaly_flags": new_flags,
                "diagnosis": str(decision.get("diagnosis", "")),
            })
            active_setpoints = new_setpoints
            last_anomaly_flags = new_flags

    violation_count = sum(1 for f in failure_points if f["type"] == "safety_violation")
    missed_anomaly_count = sum(1 for f in failure_points if f["type"] == "missed_anomaly")
    false_positive_count = sum(1 for f in failure_points if f["type"] == "false_positive")
    exception_count = sum(1 for f in failure_points if f["type"] in ("exception", "timeout"))

    fault1_active_at_end = abs(model.a1 - A1_NOMINAL) > 1e-9
    fault2_active_at_end = abs(model.a2 - A2_NOMINAL) > 1e-9
    restore_gap = 0.0
    if not fault1_active_at_end:
        restore_gap += abs(active_setpoints["tank1"] - scenario.nominal_setpoint1)
    if not fault2_active_at_end:
        restore_gap += abs(active_setpoints["tank2"] - scenario.nominal_setpoint2)

    return {
        "scenario": scenario.name,
        "time_hist": time_hist, "h1_hist": h1_hist, "h2_hist": h2_hist,
        "h3_hist": h3_hist, "h4_hist": h4_hist, "v1_hist": v1_hist, "v2_hist": v2_hist,
        "effort1_hist": effort1_hist, "effort2_hist": effort2_hist,
        "supervisor_decisions": supervisor_decisions,
        "failure_points": failure_points,
        "metrics": {
            "iae": round(iae_accum, 3),
            "violation_count": violation_count,
            "missed_anomaly_count": missed_anomaly_count,
            "false_positive_count": false_positive_count,
            "exception_count": exception_count,
            "restore_gap": round(restore_gap, 4),
        },
    }


if __name__ == "__main__":
    from supervisor_security import safe_exec_supervisor

    scenario = FourTankScenarioConfig(
        name="tank1_leak",
        leak1_onset_s=150.0, leak1_multiplier=2.5, leak1_offset_s=400.0,
    )

    print("=== PID-only (no supervisor) ===")
    result = run_episode(pid_only_supervisor, scenario)
    print("metrics:", result["metrics"])

    print("\n=== Our trained two-tank supervisor (unmodified) ===")
    with open("generated_supervisors_two_tank/current_supervisor.py", "r", encoding="utf-8") as f:
        code = f.read()
    fn, err = safe_exec_supervisor(code)
    if err:
        print("load error:", err)
    else:
        result2 = run_episode(fn, scenario)
        print("metrics:", result2["metrics"])
        for d in result2["supervisor_decisions"]:
            print(d["time_s"], d["adjusted_setpoints"], d["anomaly_flags"])
