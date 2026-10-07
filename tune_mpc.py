"""Tune the MPC baseline on the development battery (no API calls).

Run: python tune_mpc.py [budget]   (default 40)

The LLM side is optimised directly against the score on the development
battery; the champion of window600_high comes from a lineage of about 40
candidates. To give the model-based baseline a comparable chance, this script
evaluates `budget` MPC configurations on the same development battery
(seeded random search, configuration 0 = the original untuned MPC) and keeps
the one with the lowest mean score. The held-out, beyond and sealed test
batteries are not used.

Search space:
- cost form: "quadratic" (original) or "score" (the score's own terms over the
  horizon, see mpc_supervisor.py);
- prediction horizon, disturbance-estimator gain, pump-headroom weight;
- quadratic form: production, band, upper-limit and move weights (x0.25-4
  around the original values);
- score form: constraint margin and the multiplier on the score's price of
  setpoint travel.

Writes results/coordination/mpc_tuning.csv (every configuration and its dev
score) and results/coordination/mpc_tuned_params.json (the best one).
"""

import csv
import dataclasses
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

import numpy as np

import four_tank_coordination as C
import mpc_supervisor as M

SEED = 2026
DEV_SEED, PER_CELL = 1, 3          # the trainer's development battery
OUT_DIR = os.path.join("results", "coordination")
TUNING_CSV = os.path.join(OUT_DIR, "mpc_tuning.csv")


def sample_configs(budget, seed=SEED):
    rng = np.random.default_rng(seed)
    log_u = lambda lo, hi: float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
    configs = [{"cost": "quadratic"},                     # 0: the original controller
               {"cost": "score"}]                         # 1: score cost, other settings as the original
    while len(configs) < budget:
        cfg = {"cost": str(rng.choice(["quadratic", "score"])),
               "horizon_s": int(rng.choice([150, 200, 300, 400, 500])),
               "estimate_gain": round(float(rng.uniform(0.2, 1.0)), 3),
               "w_headroom": round(log_u(1.0, 100.0), 3)}
        if cfg["cost"] == "quadratic":
            cfg.update(w_production=round(M.W_PRODUCTION * log_u(0.25, 4.0), 1),
                       w_band=round(M.W_BAND * log_u(0.25, 4.0), 1),
                       w_upper=round(M.W_UPPER * log_u(0.25, 4.0), 1),
                       w_move=round(M.W_MOVE * log_u(0.25, 4.0), 2))
        else:
            cfg.update(margin=round(float(rng.uniform(0.0, 0.015)), 4),
                       move_scale=round(log_u(0.25, 4.0), 3))
        configs.append(cfg)
    return configs[:budget]


def _run(job):
    idx, cfg, scenario = job
    scenario = dataclasses.replace(scenario, supervisor_timeout_s=10.0)
    m = C.run_episode(M.MPCSupervisor(**cfg), scenario)["metrics"]
    return idx, scenario.name, C.score(m)


def _git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip() or None
    except OSError:
        return None


def main():
    budget = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    configs = sample_configs(budget)
    battery = C.make_battery("dev", PER_CELL, DEV_SEED)
    jobs = [(i, cfg, sc) for i, cfg in enumerate(configs) for sc in battery]
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as pool:
        results = list(pool.map(_run, jobs, chunksize=4))

    scores = {i: [] for i in range(len(configs))}
    for i, _, value in results:
        scores[i].append(value)
    means = {i: float(np.mean(v)) for i, v in scores.items()}

    os.makedirs(OUT_DIR, exist_ok=True)
    keys = sorted({k for cfg in configs for k in cfg})
    with open(TUNING_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["config", "dev_score"] + keys)
        for i, cfg in enumerate(configs):
            writer.writerow([i, round(means[i], 3)] + [cfg.get(k, "") for k in keys])

    best = min(means, key=means.get)
    record = {"params": configs[best], "config": best, "dev_score": round(means[best], 3),
              "untuned_dev_score": round(means[0], 3), "budget": budget, "seed": SEED,
              "battery": {"range": "dev", "per_cell": PER_CELL, "seed": DEV_SEED},
              "tuned": datetime.now(timezone.utc).isoformat(timespec="seconds"), "git_commit": _git_commit()}
    with open(M.TUNED_PARAMS_PATH, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=1)

    print(f"{len(configs)} configurations x {len(battery)} dev scenarios")
    for i in sorted(means, key=means.get)[:8]:
        print(f"  config {i:2d}: dev {means[i]:7.1f}  {configs[i]}")
    print(f"untuned (config 0): {means[0]:.1f}; best: config {best}, {means[best]:.1f} -> {M.TUNED_PARAMS_PATH}")


if __name__ == "__main__":
    main()
