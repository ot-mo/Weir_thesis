"""Four-tank setpoint-coordination test bed: a scaled-down rehearsal of the
grinding-circuit experiment in the goal document (Måldokument-1.pdf).

The leak-detection test bed (pcgym_four_tank.py) asks the supervisor to flag
faults. The thesis instead asks it to coordinate the setpoints of existing PID
loops so that a product variable stays on target while operating constraints
hold, under disturbances inside and beyond the development range. This module
maps that problem onto the quadruple-tank process:

  grinding circuit                 four-tank analog
  -----------------------------    ---------------------------------------------
  P80 on target                    production rate Q = tank1 + tank2 outflow, L/s
  sump level stable                h2 inside H2_BAND
  circulating load within limits   upper tanks h3, h4 below UPPER_LEVEL_LIMIT
  fresh feed flow variation        "feed": extra in/outflow at tank 1 or 2
  ore density variation            "pump": pump gain k1 or k2 changes
  percentage solids variation      "split": valve split gamma1 or gamma2 changes
  setpoint smoothness              total variation of the supervisor's setpoints

The supervisor only moves the two PI setpoints (h1, h2). Two setpoints and one
production target leave one degree of freedom, which the supervisor must use
to keep the constraints satisfied as disturbances move the operating point.
Every episode starts at the steady operating point, as a running plant would.

Supervisor interface (no anomaly flags):
    supervise(telemetry_window, active_setpoints, objectives) ->
        {"diagnosis": str, "adjusted_setpoints": {"h1": float, "h2": float}}
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
from pcgym.model_classes import four_tank

from PID import PIDController
from supervisor_security import call_with_timeout

NOMINAL_SETPOINTS = {"h1": 0.30, "h2": 0.35}
H2_BAND = (0.25, 0.45)          # sump-level analog, m
UPPER_LEVEL_LIMIT = 0.75        # circulating-load analog for h3 and h4, m
SAFETY_BOUNDS = (0.02, 1.5)     # lower-tank levels, m
SETPOINT_LIMITS = (0.05, 0.48)
PUMP_LIMITS = (1.0, 12.0)
PID_KP, PID_KI = 40.0, 0.3      # cross-paired PI loops, as in pcgym_four_tank.py
RECOVERY_TOLERANCE = 0.02       # settled once |Q - Q*| <= 2% of Q* for good


def plant_params():
    m = four_tank(int_method="numpy")
    return {k: getattr(m, k) for k in ("g", "gamma_1", "gamma_2", "k1", "k2", "a1", "a2", "a3", "a4", "A1", "A2", "A3", "A4")}


def production_lps(h1, h2, p=None):
    p = p or plant_params()
    return 1000.0 * (p["a1"] * np.sqrt(2 * p["g"] * max(h1, 0.0)) + p["a2"] * np.sqrt(2 * p["g"] * max(h2, 0.0)))


def steady_state(sp1, sp2, k1_mult=1.0, k2_mult=1.0, gamma1_shift=0.0, gamma2_shift=0.0, d1_lps=0.0, d2_lps=0.0):
    """Steady state of the plant with h1/h2 held at (sp1, sp2) by the loops:
    pump voltages and upper-tank levels. Voltages outside PUMP_LIMITS mean the
    loops cannot actually hold that operating point."""
    p = plant_params()
    k1, k2 = p["k1"] * k1_mult, p["k2"] * k2_mult
    g1, g2 = p["gamma_1"] + gamma1_shift, p["gamma_2"] + gamma2_shift
    q1 = p["a1"] * np.sqrt(2 * p["g"] * sp1) - d1_lps / 1000.0
    q2 = p["a2"] * np.sqrt(2 * p["g"] * sp2) - d2_lps / 1000.0
    v1, v2 = np.linalg.solve(np.array([[g1 * k1, (1 - g2) * k2], [(1 - g1) * k1, g2 * k2]]), np.array([q1, q2]))
    h3 = ((1 - g2) * k2 * v2 / p["a3"]) ** 2 / (2 * p["g"]) if v2 > 0 else 0.0
    h4 = ((1 - g1) * k1 * v1 / p["a4"]) ** 2 / (2 * p["g"]) if v1 > 0 else 0.0
    return {"v1": float(v1), "v2": float(v2), "h3": float(h3), "h4": float(h4)}


NOMINAL_PRODUCTION = production_lps(NOMINAL_SETPOINTS["h1"], NOMINAL_SETPOINTS["h2"])


@dataclass(frozen=True)
class Disturbance:
    kind: str            # feed1, feed2 (L/s); pump1, pump2 (relative gain change); split1, split2 (gamma shift)
    pattern: str         # step, ramp, sine
    amplitude: float
    onset_s: float
    ramp_s: float = 300.0
    period_s: float = 300.0

    def value(self, t):
        if t < self.onset_s:
            return 0.0
        if self.pattern == "step":
            return self.amplitude
        if self.pattern == "ramp":
            return self.amplitude * min(1.0, (t - self.onset_s) / self.ramp_s)
        if self.pattern == "sine":
            return self.amplitude * np.sin(2 * np.pi * (t - self.onset_s) / self.period_s)
        raise ValueError(self.pattern)


@dataclass
class CoordinationScenario:
    name: str
    disturbances: tuple = ()
    target_changes: tuple = ()      # ((time_s, production_target_lps), ...)
    range_label: str = "dev"        # dev | beyond | nominal
    kind_label: str = "nominal"
    pattern_label: str = "none"
    sim_time: float = 1200.0
    dt: float = 1.0
    window_steps: int = 50
    decision_interval_steps: int = 10
    supervisor_timeout_s: float = 0.5
    sensor_noise_std: float = 0.0
    seed: int = 0
    events: tuple = field(default=())  # times used for recovery_time; filled by the battery builder


# Disturbance channels: (kind, sign, development amplitude range, beyond range).
# Calibrated with steady_state(): development amplitudes stay solvable, i.e.
# some setpoint pair still meets the production target with every constraint
# satisfied, while the upper part of each range breaks the fixed recipe; the
# beyond ranges start past the edge of solvability.
DISTURBANCE_CHANNELS = {
    "feed": [("feed1", -1, (0.75, 1.75), (2.0, 3.0)),      # draw-off at tank 1, L/s
             ("feed2", -1, (1.5, 2.75), (3.0, 4.0)),       # draw-off at tank 2
             ("feed2", +1, (1.5, 3.0), (4.0, 6.0))],       # extra inflow at tank 2
    "pump": [("pump1", -1, (0.10, 0.28), (0.32, 0.45)),    # relative pump-gain loss
             ("pump2", -1, (0.10, 0.30), (0.38, 0.50))],
    "split": [("split1", -1, (0.05, 0.12), (0.15, 0.20)),  # valve split shift
              ("split1", +1, (0.08, 0.20), (0.26, 0.32)),
              ("split2", +1, (0.08, 0.18), (0.22, 0.28))],
}
PATTERNS = ("step", "ramp", "sine")


def _sample_disturbance(rng, kind_label, pattern, range_label, scale=1.0):
    kind, sign, dev, beyond = DISTURBANCE_CHANNELS[kind_label][rng.integers(len(DISTURBANCE_CHANNELS[kind_label]))]
    lo, hi = dev if range_label == "dev" else beyond
    return Disturbance(kind=kind, pattern=pattern, amplitude=float(sign * rng.uniform(lo, hi) * scale),
                       onset_s=float(rng.uniform(150, 300)), ramp_s=float(rng.uniform(200, 400)),
                       period_s=float(rng.uniform(200, 500)))


def make_battery(range_label, per_cell=1, seed=0):
    """Seeded scenario battery over the goal document's factors: disturbance
    kind (feed, pump, split, combined) x temporal pattern (step, ramp, sine),
    plus nominal scenarios with production-target changes ("dev" only)."""
    rng = np.random.default_rng(seed)
    battery = []
    for i in range(per_cell):
        if range_label == "dev":
            for j in range(2):
                t1 = float(rng.uniform(150, 300))
                t2 = float(t1 + rng.uniform(400, 550))
                step = float(rng.uniform(0.05, 0.10)) * (1 if j == 0 else -1)
                battery.append(CoordinationScenario(
                    name=f"nominal_target_{'up' if step > 0 else 'down'}_{i}", range_label="nominal",
                    target_changes=((t1, NOMINAL_PRODUCTION * (1 + step)), (t2, NOMINAL_PRODUCTION)),
                    events=(t1, t2), seed=seed + 1000 * i + j))
        for kind_label in ("feed", "pump", "split", "combined"):
            for pattern in PATTERNS:
                if kind_label == "combined":
                    first, second = rng.choice(["feed", "pump", "split"], size=2, replace=False)
                    dists = (_sample_disturbance(rng, first, pattern, range_label, 0.75),
                             _sample_disturbance(rng, second, pattern, range_label, 0.75))
                else:
                    dists = (_sample_disturbance(rng, kind_label, pattern, range_label),)
                battery.append(CoordinationScenario(
                    name=f"{range_label}_{kind_label}_{pattern}_{i}", disturbances=dists, range_label=range_label,
                    kind_label=kind_label, pattern_label=pattern, events=tuple(sorted(d.onset_s for d in dists)),
                    seed=seed + 1000 * i + len(battery)))
    return battery


def fixed_recipe_supervisor(telemetry_window, active_setpoints, objectives):
    """PID-only baseline: the loops keep a fixed operating recipe. When the
    production target changes, both setpoints are scaled with the nominal
    square-root relation (Q ~ sqrt(h)); disturbances are not handled."""
    scale = (objectives["production_target"] / NOMINAL_PRODUCTION) ** 2
    return {
        "diagnosis": "fixed recipe",
        "adjusted_setpoints": {"h1": NOMINAL_SETPOINTS["h1"] * scale, "h2": NOMINAL_SETPOINTS["h2"] * scale},
    }


def _apply_disturbances(model, p, scenario, t):
    k1, k2 = p["k1"], p["k2"]
    g1, g2 = p["gamma_1"], p["gamma_2"]
    d1 = d2 = 0.0
    for dist in scenario.disturbances:
        v = dist.value(t)
        if dist.kind == "feed1":
            d1 += v / 1000.0
        elif dist.kind == "feed2":
            d2 += v / 1000.0
        elif dist.kind == "pump1":
            k1 *= 1.0 + v
        elif dist.kind == "pump2":
            k2 *= 1.0 + v
        elif dist.kind == "split1":
            g1 += v
        elif dist.kind == "split2":
            g2 += v
        else:
            raise ValueError(dist.kind)
    model.k1, model.k2, model.gamma_1, model.gamma_2 = k1, k2, g1, g2
    return d1, d2


def _make_pid(setpoint, steady_voltage, dt):
    pid = PIDController(Kp=PID_KP, Ki=PID_KI, Kd=0.0, setpoint=setpoint, output_limits=PUMP_LIMITS)
    # Start in steady operation: integral pre-loaded so the first output is
    # the steady-state voltage (PID.py returns 0 V on its very first call).
    pid._integral = steady_voltage / PID_KI
    pid._last_time = -dt
    return pid


def run_episode(supervisor_fn: Callable, scenario: CoordinationScenario) -> dict:
    p = plant_params()
    model = four_tank(int_method="numpy")
    rng = np.random.default_rng(scenario.seed)
    sp = dict(NOMINAL_SETPOINTS)
    ss = steady_state(sp["h1"], sp["h2"])
    x = np.array([sp["h1"], sp["h2"], ss["h3"], ss["h4"]], dtype=float)
    # Cross pairing: the h1 loop drives pump 2, the h2 loop drives pump 1.
    loop_h1 = _make_pid(sp["h1"], ss["v2"], scenario.dt)
    loop_h2 = _make_pid(sp["h2"], ss["v1"], scenario.dt)
    target = NOMINAL_PRODUCTION
    changes = sorted(scenario.target_changes)

    nsteps = int(scenario.sim_time / scenario.dt)
    hist = {k: [] for k in ("t", "h1", "h2", "h3", "h4", "v1", "v2", "q", "target", "sp1", "sp2")}
    telemetry, decisions, exceptions = [], [], 0

    for k in range(nsteps):
        t = k * scenario.dt
        while changes and t >= changes[0][0]:
            target = changes.pop(0)[1]
        d1, d2 = _apply_disturbances(model, p, scenario, t)
        noise = rng.normal(0.0, scenario.sensor_noise_std, 4) if scenario.sensor_noise_std else np.zeros(4)
        meas = x + noise

        loop_h1.setpoint, loop_h2.setpoint = sp["h1"], sp["h2"]
        v2 = float(loop_h1.update(measurement=meas[0], current_time=t))
        v1 = float(loop_h2.update(measurement=meas[1], current_time=t))
        dxdt = np.array(model(x, np.array([v1, v2])), dtype=float)
        dxdt[0] += d1 / p["A1"]
        dxdt[1] += d2 / p["A2"]
        x = np.maximum(x + dxdt * scenario.dt, 0.0)

        q = production_lps(x[0], x[1], p)
        for key, val in (("t", t), ("h1", x[0]), ("h2", x[1]), ("h3", x[2]), ("h4", x[3]), ("v1", v1), ("v2", v2),
                         ("q", q), ("target", target), ("sp1", sp["h1"]), ("sp2", sp["h2"])):
            hist[key].append(float(val))
        mq = production_lps(max(meas[0], 0.0), max(meas[1], 0.0), p)
        telemetry.append({"time": t, "h1": round(float(meas[0]), 4), "h2": round(float(meas[1]), 4),
                          "h3": round(float(meas[2]), 4), "h4": round(float(meas[3]), 4),
                          "v1": round(v1, 3), "v2": round(v2, 3), "production": round(float(mq), 3)})

        if k >= scenario.window_steps and k % scenario.decision_interval_steps == 0:
            recent = telemetry[-scenario.window_steps:]
            t0 = recent[0]["time"]
            window = [dict(s, time=s["time"] - t0) for s in recent]
            objectives = {"production_target": target, "h2_band": list(H2_BAND),
                          "upper_level_limit": UPPER_LEVEL_LIMIT, "setpoint_limits": list(SETPOINT_LIMITS)}
            decision, err = call_with_timeout(supervisor_fn, (window, dict(sp), objectives),
                                              timeout_s=scenario.supervisor_timeout_s)
            if err is not None:
                exceptions += 1
                decision = {"diagnosis": f"SUPERVISOR_FAILURE: {err}", "adjusted_setpoints": dict(sp)}
            proposed = decision.get("adjusted_setpoints", {}) or {}
            for name in ("h1", "h2"):
                value = float(proposed.get(name, sp[name]))
                sp[name] = min(SETPOINT_LIMITS[1], max(SETPOINT_LIMITS[0], value))
            decisions.append({"time_s": t, "setpoints": dict(sp), "target": target,
                              "diagnosis": str(decision.get("diagnosis", ""))})

    return {"scenario": scenario.name, "hist": hist, "decisions": decisions,
            "metrics": compute_metrics(hist, scenario, exceptions)}


# Provisional weights for a single score (lower is better), needed later to
# rank LLM candidates. The goal document fixes exact definitions before the
# real tests, so these are a starting point: 1 L off target = 1, one second of
# band or upper-limit violation = 2, one metre of setpoint travel = 100.
SCORE_WEIGHTS = {"production_iae_l": 1.0, "band_violation_s": 2.0, "upper_violation_s": 2.0,
                 "safety_violation_s": 10.0, "setpoint_tv_m": 100.0, "exceptions": 1000.0}


def score(metrics):
    return float(sum(w * metrics[k] for k, w in SCORE_WEIGHTS.items()))


def compute_metrics(hist, scenario, exceptions=0):
    dt = scenario.dt
    q, target = np.array(hist["q"]), np.array(hist["target"])
    h2, h3, h4 = np.array(hist["h2"]), np.array(hist["h3"]), np.array(hist["h4"])
    h1 = np.array(hist["h1"])
    v1, v2 = np.array(hist["v1"]), np.array(hist["v2"])
    sp1, sp2 = np.array(hist["sp1"]), np.array(hist["sp2"])
    t = np.array(hist["t"])

    # Recovery = settling time: from each event until production enters the
    # tolerance band and stays there until the next event. If it is still
    # outside at the end of the segment, the whole segment counts (censored).
    within = np.abs(q - target) <= RECOVERY_TOLERANCE * target
    events = sorted(scenario.events)
    recoveries = []
    for i, event in enumerate(events):
        end = events[i + 1] if i + 1 < len(events) else t[-1] + dt
        seg = np.where((t >= event) & (t < end))[0]
        outside = seg[~within[seg]]
        recoveries.append(float(t[outside[-1]] + dt - event) if len(outside) else 0.0)

    return {
        "production_iae_l": float(np.sum(np.abs(q - target)) * dt),
        "band_violation_s": float(np.sum((h2 < H2_BAND[0]) | (h2 > H2_BAND[1])) * dt),
        "upper_violation_s": float(np.sum((h3 > UPPER_LEVEL_LIMIT) | (h4 > UPPER_LEVEL_LIMIT)) * dt),
        "safety_violation_s": float(np.sum((h1 < SAFETY_BOUNDS[0]) | (h1 > SAFETY_BOUNDS[1])
                                           | (h2 < SAFETY_BOUNDS[0]) | (h2 > SAFETY_BOUNDS[1])) * dt),
        "setpoint_tv_m": float(np.sum(np.abs(np.diff(sp1))) + np.sum(np.abs(np.diff(sp2)))),
        "saturation_s": float(np.sum((np.minimum(v1, v2) <= PUMP_LIMITS[0] + 1e-6)
                                     | (np.maximum(v1, v2) >= PUMP_LIMITS[1] - 1e-6)) * dt),
        "recovery_s": float(np.mean(recoveries)) if recoveries else 0.0,
        "exceptions": int(exceptions),
    }
