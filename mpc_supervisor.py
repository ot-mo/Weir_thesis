"""Model-based predictive supervisor for the four-tank coordination test bed:
the stand-in for the goal document's model-based predictive benchmark (RQ1).

Every decision it simulates candidate setpoint pairs over a prediction horizon
with an internal model of plant + PI loops, and applies the pair with the
lowest predicted cost (production error, h2-band and upper-level violations,
pump headroom, setpoint moves). Candidates are evaluated in parallel as numpy
arrays: a coarse grid around the current setpoints, then a finer grid around
the best one.

Variants:
- MPCSupervisor(): nominal model plus an online disturbance estimate. After
  each decision the measured state is compared with the model's prediction,
  and the difference is folded into an additive inflow per tank (the
  bias-update idea used in industrial MPC). It does not know the true
  disturbance. With no arguments it is the original, untuned controller
  ("mpc_untuned" in the benchmark).
- MPCSupervisor(**tuned_params()): the same controller with the parameters
  tune_mpc.py found on the development battery ("mpc_tuned"), including the
  choice of cost form.
- MPCSupervisor(oracle_scenario=s, ...): uses the true current plant
  parameters and disturbance of scenario s, held constant over the horizon
  ("mpc_known_disturbance"). It is not an upper bound: knowing the current
  disturbance does not make its model or its cost match the score, and it
  lost to the estimating MPC on 30 of 120 scenarios with the quadratic cost.

Cost forms:
- "quadratic" (original): weighted squared production error and squared
  constraint-violation size, averaged over the horizon. A 1 mm violation
  costs almost nothing, while the score counts every second of it.
- "score": the score's own terms over the horizon - absolute production
  error (L), seconds with h2 within `margin` of the band edges, seconds with
  an upper level within `margin` of its limit, the score's weights, and the
  score's price on setpoint travel times `move_scale` - plus the pump
  headroom term.

Unlike the generated supervisors, this controller is stateful, so create a
new instance per episode.
"""

import json
import os

import numpy as np

import four_tank_coordination as C

# Cost weights, applied to horizon-averaged quantities. Relative production
# error of 2% costs 4; a 0.02 m constraint violation costs 40; a 0.05 m
# setpoint move costs 2.5.
W_PRODUCTION = 1e4
W_BAND = 1e5
W_UPPER = 1e5
W_HEADROOM = 10.0       # per V^2 outside [1.5, 11.5] V
W_MOVE = 50.0           # per metre of setpoint change
PUMP_HEADROOM = (1.5, 11.5)
COARSE_STEPS = (-0.10, -0.05, -0.02, -0.01, 0.0, 0.01, 0.02, 0.05, 0.10)
FINE_STEPS = (-0.006, -0.003, 0.0, 0.003, 0.006)
ESTIMATE_GAIN = 0.5


TUNED_PARAMS_PATH = os.path.join("results", "coordination", "mpc_tuned_params.json")


def tuned_params(path=TUNED_PARAMS_PATH):
    """Parameters chosen by tune_mpc.py (keyword arguments for MPCSupervisor)."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["params"]


class MPCSupervisor:
    def __init__(self, horizon_s=300, oracle_scenario=None, dt=1.0, cost="quadratic",
                 w_production=W_PRODUCTION, w_band=W_BAND, w_upper=W_UPPER, w_headroom=W_HEADROOM,
                 w_move=W_MOVE, estimate_gain=ESTIMATE_GAIN, margin=0.0, move_scale=1.0):
        if cost not in ("quadratic", "score"):
            raise ValueError(cost)
        self.horizon = int(horizon_s / dt)
        self.dt = dt
        self.oracle_scenario = oracle_scenario
        self.cost_form = cost
        self.w_production, self.w_band, self.w_upper = w_production, w_band, w_upper
        self.w_headroom, self.w_move, self.estimate_gain = w_headroom, w_move, estimate_gain
        self.margin, self.move_scale = margin, move_scale
        self.p = C.plant_params()
        self.d_hat = np.zeros(4)           # estimated additive inflow per tank, m/s
        self.pending = None                # (predicted state, interval steps) from last decision
        self.calls = 0

    # -- model ---------------------------------------------------------------
    def _params_now(self):
        p = dict(self.p)
        extra = np.zeros(4)
        if self.oracle_scenario is not None:
            s = self.oracle_scenario
            # Decisions happen at t = interval, 2*interval, ... (see run_episode).
            t = s.decision_interval_steps * self.calls * s.dt
            model = type("M", (), {})()
            d1, d2 = C._apply_disturbances(model, self.p, s, t)
            p.update(k1=model.k1, k2=model.k2, gamma_1=model.gamma_1, gamma_2=model.gamma_2)
            extra[0], extra[1] = d1 / p["A1"], d2 / p["A2"]
        else:
            extra = self.d_hat
        return p, extra

    def _simulate(self, x0, integ0, sp, steps, p, extra):
        """Closed loop (plant + cross-paired PI loops) for every candidate row
        of sp (n, 2). Returns per-step trajectories needed by the cost."""
        n = sp.shape[0]
        x = np.repeat(x0[None, :], n, axis=0)
        integ = np.repeat(integ0[None, :], n, axis=0)   # [loop_h1 (pump 2), loop_h2 (pump 1)]
        g2 = 2 * p["g"]
        traj = {"q": np.empty((steps, n)), "h2": np.empty((steps, n)), "upper": np.empty((steps, n)),
                "v1": np.empty((steps, n)), "v2": np.empty((steps, n))}
        lo, hi = C.PUMP_LIMITS
        kp = np.array([C.PI_GAINS["h1"][0], C.PI_GAINS["h2"][0]])
        ki = np.array([C.PI_GAINS["h1"][1], C.PI_GAINS["h2"][1]])
        for k in range(steps):
            e = sp - x[:, :2]
            integ = integ + e * self.dt
            out = kp * e + ki * integ
            sat = (out > hi) | (out < lo)
            integ = np.where(sat, integ - e * self.dt, integ)    # same anti-windup back-off as PID.py
            out = np.clip(out, lo, hi)
            v2, v1 = out[:, 0], out[:, 1]
            r = np.sqrt(g2 * np.maximum(x, 0.0))
            dx = np.empty_like(x)
            dx[:, 0] = (-p["a1"] * r[:, 0] + p["a3"] * r[:, 2] + p["gamma_1"] * p["k1"] * v1) / p["A1"]
            dx[:, 1] = (-p["a2"] * r[:, 1] + p["a4"] * r[:, 3] + p["gamma_2"] * p["k2"] * v2) / p["A2"]
            dx[:, 2] = (-p["a3"] * r[:, 2] + (1 - p["gamma_2"]) * p["k2"] * v2) / p["A3"]
            dx[:, 3] = (-p["a4"] * r[:, 3] + (1 - p["gamma_1"]) * p["k1"] * v1) / p["A4"]
            x = np.maximum(x + (dx + extra) * self.dt, 0.0)
            traj["q"][k] = 1000.0 * (p["a1"] * np.sqrt(g2 * x[:, 0]) + p["a2"] * np.sqrt(g2 * x[:, 1]))
            traj["h2"][k] = x[:, 1]
            traj["upper"][k] = np.maximum(x[:, 2], x[:, 3])
            traj["v1"][k], traj["v2"][k] = v1, v2
        return traj, x

    def _cost(self, traj, sp, current, objectives):
        target = objectives["production_target"]
        band_lo, band_hi = objectives["h2_band"]
        limit = objectives["upper_level_limit"]
        head = sum(np.maximum(PUMP_HEADROOM[0] - traj[v], 0.0) ** 2 + np.maximum(traj[v] - PUMP_HEADROOM[1], 0.0) ** 2
                   for v in ("v1", "v2"))
        move = np.abs(sp - current).sum(axis=1)
        if self.cost_form == "score":
            w = C.SCORE_WEIGHTS
            m = self.margin
            prod = np.abs(traj["q"] - target).sum(axis=0) * self.dt
            band = ((traj["h2"] < band_lo + m) | (traj["h2"] > band_hi - m)).sum(axis=0) * self.dt
            upper = (traj["upper"] > limit - m).sum(axis=0) * self.dt
            return (w["production_iae_l"] * prod + w["band_violation_s"] * band + w["upper_violation_s"] * upper
                    + self.w_headroom * head.mean(axis=0) + w["setpoint_tv_m"] * self.move_scale * move)
        prod = ((traj["q"] - target) / target) ** 2
        band = np.maximum(band_lo - traj["h2"], 0.0) ** 2 + np.maximum(traj["h2"] - band_hi, 0.0) ** 2
        upper = np.maximum(traj["upper"] - limit, 0.0) ** 2
        return (self.w_production * prod.mean(axis=0) + self.w_band * band.mean(axis=0)
                + self.w_upper * upper.mean(axis=0) + self.w_headroom * head.mean(axis=0) + self.w_move * move)

    # -- supervisor interface -----------------------------------------------
    def __call__(self, telemetry_window, active_setpoints, objectives):
        self.calls += 1
        s = telemetry_window[-1]
        x0 = np.array([s["h1"], s["h2"], s["h3"], s["h4"]], dtype=float)
        current = np.array([active_setpoints["h1"], active_setpoints["h2"]], dtype=float)

        if self.oracle_scenario is None and self.pending is not None:
            predicted, steps = self.pending
            residual = (x0 - predicted) / (steps * self.dt)
            self.d_hat = self.d_hat + self.estimate_gain * residual

        # PI integrator states reconstructed from the measured voltages:
        # output = Kp * e + Ki * integral (exact unless the loop is saturated).
        e = current - x0[:2]
        (kp1, ki1), (kp2, ki2) = C.PI_GAINS["h1"], C.PI_GAINS["h2"]
        integ0 = np.array([(s["v2"] - kp1 * e[0]) / ki1, (s["v1"] - kp2 * e[1]) / ki2])

        p, extra = self._params_now()
        lo, hi = objectives["setpoint_limits"]
        best = current
        for steps in (COARSE_STEPS, FINE_STEPS):
            grid = np.array([[best[0] + a, best[1] + b] for a in steps for b in steps])
            grid = np.unique(np.clip(grid, lo, hi), axis=0)
            traj, _ = self._simulate(x0, integ0, grid, self.horizon, p, extra)
            best = grid[int(np.argmin(self._cost(traj, grid, current, objectives)))]

        interval = 10  # matches CoordinationScenario.decision_interval_steps
        _, x_next = self._simulate(x0, integ0, best[None, :], interval, p, extra)
        self.pending = (x_next[0], interval)
        return {
            "diagnosis": f"MPC: setpoints ({best[0]:.3f}, {best[1]:.3f}), disturbance estimate "
                         f"{np.round(self.d_hat * 1000, 3).tolist()} L/s per tank",
            "adjusted_setpoints": {"h1": float(best[0]), "h2": float(best[1])},
        }
