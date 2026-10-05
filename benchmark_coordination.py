"""Baselines on the four-tank coordination test bed (no API calls).

Run: python benchmark_coordination.py [per_cell]   (default 3, as in the trainer)

Evaluates the fixed recipe (PID only), the MPC supervisor with an estimated
disturbance, and the oracle MPC on three seeded batteries - development,
held-out development (same ranges, new seeds) and beyond the development
range - and writes per-episode metrics to results/coordination/baselines.csv.
"""

import csv
import dataclasses
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import four_tank_coordination as C
from mpc_supervisor import MPCSupervisor

OUTPUT_PATH = os.path.join("results", "coordination", "baselines.csv")
CONTROLLERS = ("fixed_recipe", "mpc_estimated", "mpc_oracle")
BATTERY_SEEDS = {"dev": 1, "heldout": 2, "beyond": 3}
METRICS = ("production_iae_l", "band_violation_s", "upper_violation_s", "safety_violation_s",
           "setpoint_tv_m", "recovery_s", "saturation_s", "exceptions")


def _run(job):
    controller, battery_name, scenario = job
    scenario = dataclasses.replace(scenario, supervisor_timeout_s=10.0)  # MPC needs ~50 ms per decision
    if controller == "fixed_recipe":
        fn = C.fixed_recipe_supervisor
    elif controller == "mpc_estimated":
        fn = MPCSupervisor()
    else:
        fn = MPCSupervisor(oracle_scenario=scenario)
    m = C.run_episode(fn, scenario)["metrics"]
    return {"controller": controller, "battery": battery_name, "scenario": scenario.name,
            "range": scenario.range_label, "kind": scenario.kind_label, "pattern": scenario.pattern_label,
            **m, "score": C.score(m)}


def main():
    # 3 matches train_supervisor_coordination.SCENARIOS_PER_CELL, so the trainer's
    # report finds baselines for exactly its scenarios.
    per_cell = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    batteries = {"dev": C.make_battery("dev", per_cell, BATTERY_SEEDS["dev"]),
                 "heldout": C.make_battery("dev", per_cell, BATTERY_SEEDS["heldout"]),
                 "beyond": C.make_battery("beyond", per_cell, BATTERY_SEEDS["beyond"])}
    jobs = [(c, name, sc) for name, bat in batteries.items() for sc in bat for c in CONTROLLERS]
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as pool:
        rows = list(pool.map(_run, jobs))

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} episodes -> {OUTPUT_PATH}\n")
    header = f"{'battery':8s} {'controller':14s} {'score':>8s} {'IAE L':>7s} {'band s':>7s} {'upper s':>8s} {'TV m':>6s} {'recov s':>8s} {'sat s':>6s}"
    print(header)
    for name in batteries:
        for c in CONTROLLERS:
            sel = [r for r in rows if r["battery"] == name and r["controller"] == c]
            mean = lambda k: np.mean([r[k] for r in sel])
            print(f"{name:8s} {c:14s} {mean('score'):8.0f} {mean('production_iae_l'):7.0f} {mean('band_violation_s'):7.0f} "
                  f"{mean('upper_violation_s'):8.0f} {mean('setpoint_tv_m'):6.2f} {mean('recovery_s'):8.0f} {mean('saturation_s'):6.0f}")
        print()

    print("Mean score by disturbance kind (dev | beyond):")
    for kind in ("nominal", "feed", "pump", "split", "combined"):
        cells = []
        for c in CONTROLLERS:
            vals = [np.mean([r["score"] for r in rows if r["battery"] == b and r["controller"] == c and r["kind"] == kind] or [np.nan])
                    for b in ("dev", "beyond")]
            cells.append(f"{c} {vals[0]:6.0f} | {vals[1]:6.0f}")
        print(f"  {kind:9s} " + "   ".join(cells))


if __name__ == "__main__":
    main()
