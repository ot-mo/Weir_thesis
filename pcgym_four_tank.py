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
- `integration_method: 'jax'` is required on Windows; the default 'casadi'
  integrator fails to load its native CVODES plugin DLL here.
- dt=1.0s; the plant's natural settling time is ~100-300s, an order of
  magnitude slower than our own tank_sim.py.
- Default gamma_1=gamma_2=0.2 puts this in the "non-minimum-phase" regime
  (gamma_1+gamma_2 < 1): most pump flow is routed through the cross-coupling
  path, which is deliberately harder for decentralized PID and is why the
  PID-only baseline below is slow/oscillatory rather than badly tuned.
- A pump output floor (>= 1.0, not 0.0) is necessary: letting either pump
  hit exactly zero drains its tank toward 0, and the sqrt(h) term in the
  plant's dynamics has a singular derivative there, which crashes PC-Gym's
  adaptive-step JAX integrator (EquinoxRuntimeError).
- Max achievable steady state at full 12V on both pumps is h1~=0.50,
  h2~=0.61 - setpoints must stay comfortably below that.
"""

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import pcgym

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
    macro_cycle_steps: int = 30  # 30s per supervisor decision
    setpoint_clamp: tuple = (0.05, 0.48)
    supervisor_timeout_s: float = 0.5


def _build_env(scenario: FourTankScenarioConfig):
    nsteps = int(scenario.sim_time / scenario.dt)
    sp1 = [scenario.nominal_setpoint1] * nsteps
    sp2 = [scenario.nominal_setpoint2] * nsteps
    action_space = {"low": np.array([0.0, 0.0]), "high": np.array([12.0, 12.0])}
    observation_space = {"low": np.array([0.0] * 6), "high": np.array([2.0] * 6)}
    env_params = {
        "N": nsteps,
        "tsim": scenario.sim_time,
        "SP": {"h1": sp1, "h2": sp2},
        "o_space": observation_space,
        "a_space": action_space,
        "x0": np.array(list(scenario.initial_levels) + [scenario.nominal_setpoint1, scenario.nominal_setpoint2]),
        "model": "four_tank",
        "integration_method": "jax",
        "normalise_a": False,
        "normalise_o": False,
    }
    return pcgym.make_env(env_params), nsteps


def pid_only_supervisor(telemetry_window, active_setpoints, nominal_targets):
    return {
        "diagnosis": "PID-only baseline: no supervisory action.",
        "adjusted_setpoints": dict(nominal_targets),
        "anomaly_flags": {"tank1": False, "tank2": False},
    }


def run_episode(supervisor_fn: Callable, scenario: FourTankScenarioConfig) -> dict:
    env, nsteps = _build_env(scenario)
    obs, _ = env.reset()

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
            env.model.a1 = A1_NOMINAL * scenario.leak1_multiplier
        if scenario.leak1_offset_s is not None and t == scenario.leak1_offset_s:
            env.model.a1 = A1_NOMINAL
        if scenario.leak2_onset_s is not None and t == scenario.leak2_onset_s:
            env.model.a2 = A2_NOMINAL * scenario.leak2_multiplier
        if scenario.leak2_offset_s is not None and t == scenario.leak2_offset_s:
            env.model.a2 = A2_NOMINAL

        fault_active = {
            "tank1": abs(env.model.a1 - A1_NOMINAL) > 1e-9,
            "tank2": abs(env.model.a2 - A2_NOMINAL) > 1e-9,
        }

        pid1.setpoint = active_setpoints["tank1"]
        pid2.setpoint = active_setpoints["tank2"]
        h1, h2 = float(obs[0]), float(obs[1])
        v1 = float(pid1.update(measurement=h1, current_time=t))
        v2 = float(pid2.update(measurement=h2, current_time=t))

        obs, _, done, _, _ = env.step(np.array([v1, v2]))
        h1n, h2n, h3n, h4n = (float(x) for x in obs[:4])

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

        if done:
            break

    violation_count = sum(1 for f in failure_points if f["type"] == "safety_violation")
    missed_anomaly_count = sum(1 for f in failure_points if f["type"] == "missed_anomaly")
    false_positive_count = sum(1 for f in failure_points if f["type"] == "false_positive")
    exception_count = sum(1 for f in failure_points if f["type"] in ("exception", "timeout"))

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
