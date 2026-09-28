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
by mapping tank1 <-> (h1, v1) and tank2 <-> (h2, v2). Our already-trained
generated_supervisors_two_tank/current_supervisor.py can run against this
plant with zero code changes.

Setup notes (found empirically - see conversation, not in the PC-Gym docs):
- dt=1.0s; the plant's natural settling time is ~100-300s, an order of
  magnitude slower than our own tank_sim.py.
- Default gamma_1=gamma_2=0.2 puts this in the "non-minimum-phase" regime
  (gamma_1+gamma_2 < 1): most pump flow is routed through the cross-coupling
  path, which is deliberately harder for decentralized PID and is why the
  PID-only baseline below is slow/oscillatory rather than badly tuned.
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
    pid_kp: float = 15.0
    pid_ki: float = 0.4
    pid_kd: float = 2.0
    pump_output_limits: tuple = (1.0, 12.0)
    macro_cycle_steps: int = 50  # 50s per supervisor decision, and len(telemetry_window)
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

        pid1.setpoint = active_setpoints["tank1"]
        pid2.setpoint = active_setpoints["tank2"]
        h1, h2 = float(x[0]), float(x[1])
        v1 = float(pid1.update(measurement=h1, current_time=t))
        v2 = float(pid2.update(measurement=h2, current_time=t))

        dxdt = np.array(model(x, np.array([v1, v2])), dtype=float)
        x = np.maximum(x + dxdt * scenario.dt, 0.0)
        h1n, h2n, h3n, h4n = float(x[0]), float(x[1]), float(x[2]), float(x[3])

        error1 = active_setpoints["tank1"] - h1n
        error2 = active_setpoints["tank2"] - h2n
        iae_accum += (abs(error1) + abs(error2)) * scenario.dt

        time_hist.append(t); h1_hist.append(h1n); h2_hist.append(h2n)
        h3_hist.append(h3n); h4_hist.append(h4n); v1_hist.append(v1); v2_hist.append(v2)

        telemetry_buffer.append({
            "time": t,
            "tank1": {"level": round(h1n, 4), "pump_effort": round(v1, 3), "error": round(error1, 4)},
            "tank2": {"level": round(h2n, 4), "pump_effort": round(v2, 3), "error": round(error2, 4)},
        })

        for tank_name, level in (("tank1", h1n), ("tank2", h2n)):
            if level < scenario.safety_bounds[0] or level > scenario.safety_bounds[1]:
                failure_points.append({"time_s": t, "type": "safety_violation", "tank": tank_name, "detail": f"level={level:.4f}"})

        for tank_name in ("tank1", "tank2"):
            if fault_active[tank_name] and not last_anomaly_flags[tank_name]:
                failure_points.append({"time_s": t, "type": "missed_anomaly", "tank": tank_name, "detail": "fault active, last anomaly_flag=False"})
            elif not fault_active[tank_name] and last_anomaly_flags[tank_name]:
                failure_points.append({"time_s": t, "type": "false_positive", "tank": tank_name, "detail": "no fault, last anomaly_flag=True"})

        if t_step > 0 and t_step % scenario.macro_cycle_steps == 0:
            window = telemetry_buffer[-scenario.macro_cycle_steps:]
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

            supervisor_decisions.append({
                "time_s": t,
                "tank1_level": round(h1n, 4),
                "tank2_level": round(h2n, 4),
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
