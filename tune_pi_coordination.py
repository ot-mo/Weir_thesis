"""Tune the coordination test bed's PI level loops (no API calls).

Run: python tune_pi_coordination.py [ms_bound]   (default 1.6)

The real plant's regulatory loops can be assumed to be well tuned, so the test
bed's should be too. For every pair of per-loop PI settings on a grid, this
script computes
- the maximum sensitivity Ms of the coupled loops: the peak over frequency of
  the largest singular value of S = (I + G K)^-1, with G the plant linearised
  at the nominal operating point (h1 0.30 m, h2 0.35 m) and K the cross-paired
  PI controllers (h1 loop -> pump 2, h2 loop -> pump 1), and
- the load-disturbance IAE: the integral of |h1 - 0.30| + |h2 - 0.35| (m s)
  over 800 s after a 1 L/s draw-off step on tank 1, plus the same for tank 2,
  in the nonlinear test bed with the setpoints held,
and keeps the setting with the lowest IAE among those with Ms <= ms_bound
(Astrom and Hagglund's constrained IAE optimisation of PI controllers; Ms of
1.4-2.0 is the usual range, 1.6 a common compromise). It also reports the
setpoint-step overshoot of the result.

Writes results/coordination/pi_tuning.csv (every setting with Ms <= 2 and its
IAE). The chosen gains are set by hand in four_tank_coordination.PI_GAINS.
"""

import csv
import itertools
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import four_tank_coordination as C

KPS = (5, 10, 15, 20, 30, 40, 60, 80, 120, 160)          # V/m
TIS = (20, 30, 45, 60, 90, 133, 200, 300, 400, 600)      # s
OUT_CSV = os.path.join("results", "coordination", "pi_tuning.csv")
WS = np.logspace(-4, 0, 600)


def linear_model():
    """Linearisation at the nominal operating point: dx = A x + B u, y = (h1, h2), u = (v1, v2)."""
    p = C.plant_params()
    ss = C.steady_state(C.NOMINAL_SETPOINTS["h1"], C.NOMINAL_SETPOINTS["h2"])
    h = np.array([C.NOMINAL_SETPOINTS["h1"], C.NOMINAL_SETPOINTS["h2"], ss["h3"], ss["h4"]])
    area = np.array([p["A1"], p["A2"], p["A3"], p["A4"]])
    outlet = np.array([p["a1"], p["a2"], p["a3"], p["a4"]])
    tau = area / outlet * np.sqrt(2 * h / p["g"])
    a = np.diag(-1 / tau)
    a[0, 2] = area[2] / (area[0] * tau[2])
    a[1, 3] = area[3] / (area[1] * tau[3])
    g1, g2, k1, k2 = p["gamma_1"], p["gamma_2"], p["k1"], p["k2"]
    b = np.array([[g1 * k1 / area[0], 0], [0, g2 * k2 / area[1]], [0, (1 - g2) * k2 / area[2]], [(1 - g1) * k1 / area[3], 0]])
    c = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
    return a, b, c


A, B, CM = linear_model()
# Frequency responses with the inputs reordered to the cross pairing (v2 for h1, v1 for h2).
G = np.array([(CM @ np.linalg.solve(1j * w * np.eye(4) - A, B))[:, ::-1] for w in WS])


def max_sensitivity(kp1, ti1, kp2, ti2):
    k = np.stack([kp1 * (1 + 1 / (1j * WS * ti1)), kp2 * (1 + 1 / (1j * WS * ti2))], axis=-1)
    s = np.linalg.inv(np.eye(2)[None] + G * k[:, None, :])
    return float(np.linalg.svd(s, compute_uv=False)[:, 0].max())


def _episode(gains, supervisor, scenario):
    kp1, ti1, kp2, ti2 = gains
    saved = C.PI_GAINS
    C.PI_GAINS = {"h1": (kp1, kp1 / ti1), "h2": (kp2, kp2 / ti2)}
    try:
        return C.run_episode(supervisor, scenario)
    finally:
        C.PI_GAINS = saved


def load_iae(gains):
    total = 0.0
    for kind in ("feed1", "feed2"):
        d = C.Disturbance(kind=kind, pattern="step", amplitude=-1.0, onset_s=10.0)
        r = _episode(gains, lambda w, s, o: {"diagnosis": "", "adjusted_setpoints": dict(s)},
                     C.CoordinationScenario(name="load", sim_time=800.0, disturbances=(d,), events=(10.0,)))
        h = r["hist"]
        total += float(np.sum(np.abs(np.array(h["h1"]) - C.NOMINAL_SETPOINTS["h1"]))
                       + np.sum(np.abs(np.array(h["h2"]) - C.NOMINAL_SETPOINTS["h2"])))
    return total


def overshoot(gains):
    """Percent overshoot of h1 and h2 after 3 cm setpoint steps (one loop at a time)."""
    out = []
    for idx, sp in ((0, (0.33, 0.35)), (1, (0.30, 0.38))):
        r = _episode(gains, lambda w, s, o, sp=sp: {"diagnosis": "", "adjusted_setpoints": {"h1": sp[0], "h2": sp[1]}},
                     C.CoordinationScenario(name="step", sim_time=800.0))
        y = np.array(r["hist"]["h1" if idx == 0 else "h2"])
        start = (C.NOMINAL_SETPOINTS["h1"], C.NOMINAL_SETPOINTS["h2"])[idx]
        out.append(100 * (y.max() - sp[idx]) / (sp[idx] - start))
    return out


def main():
    bound = float(sys.argv[1]) if len(sys.argv) > 1 else 1.6
    grid = list(itertools.product(KPS, TIS, KPS, TIS))
    ms = {g: max_sensitivity(*g) for g in grid}
    feasible = [g for g in grid if ms[g] <= 2.0]
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as pool:
        iae = dict(zip(feasible, pool.map(load_iae, feasible, chunksize=8)))
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["kp_h1", "ti_h1", "kp_h2", "ti_h2", "ms", "load_iae"])
        for g in sorted(feasible, key=iae.get):
            writer.writerow([*g, round(ms[g], 3), round(iae[g], 3)])
    best = min((g for g in feasible if ms[g] <= bound), key=iae.get)
    previous = (40, 133.3, 40, 133.3)
    for label, g in (("previous gains", previous), (f"best with Ms <= {bound}", best)):
        o = overshoot(g)
        print(f"{label}: h1 loop Kp {g[0]}, Ti {g[1]} s | h2 loop Kp {g[2]}, Ti {g[3]} s | Ms {max_sensitivity(*g):.2f} | "
              f"load IAE {load_iae(g):.2f} | overshoot {o[0]:.0f} % / {o[1]:.0f} %")
    print(f"{len(feasible)} of {len(grid)} settings have Ms <= 2 -> {OUT_CSV}")


if __name__ == "__main__":
    main()
