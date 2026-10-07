"""Re-score every coordination run's champion with the current test bed (no API calls).

Run: python rescore_champions_coordination.py

The runs index (results/coordination/README.md) compares champions from runs
made with different versions of the test bed (window length, PI tuning). This
script scores each run's final champion (current_supervisor.py) on the
development, held-out and beyond batteries with the current test bed, so the
rows are comparable, and writes results/coordination/champion_rescores.csv.
"""
import csv
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import four_tank_coordination as C
from supervisor_security import safe_exec_supervisor

BATTERIES = {"dev": ("dev", 1), "heldout": ("dev", 2), "beyond": ("beyond", 3)}


def job(args):
    run, battery, scenario = args
    with open(os.path.join("generated_supervisors_coordination", run, "current_supervisor.py"), encoding="utf-8") as f:
        fn, err = safe_exec_supervisor(f.read())
    m = C.run_episode(fn, scenario)["metrics"]
    return run, battery, scenario.name, C.score(m)


if __name__ == "__main__":
    runs = sorted(d for d in os.listdir("generated_supervisors_coordination")
                  if os.path.isdir(os.path.join("generated_supervisors_coordination", d)))
    scen = {b: C.make_battery(r, 3, s) for b, (r, s) in BATTERIES.items()}
    jobs = [(run, b, sc) for run in runs for b, ss in scen.items() for sc in ss]
    with ProcessPoolExecutor(max_workers=11) as pool:
        rows = list(pool.map(job, jobs, chunksize=8))
    out = os.path.join("results", "coordination", "champion_rescores.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["run", "battery", "scenario", "score"])
        w.writerows(rows)
    for run in runs:
        means = [np.mean([s for r, b, _, s in rows if r == run and b == bat]) for bat in BATTERIES]
        print(f"{run:28s} " + " / ".join(f"{m:.1f}" for m in means))
