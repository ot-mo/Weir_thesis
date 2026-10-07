"""Evaluate controllers on the sealed test battery (no API calls).

Run: python evaluate_sealed_test.py --unseal "REASON" [--runs RUN1 RUN2 ...] [--baselines]

This is the only script that opens coordination_test_battery.py. The protocol
(results/coordination/PROTOCOL.md) allows one evaluation, after all protocol
runs are finished. Every access is appended to
results/coordination/sealed_test/access_log.jsonl - commit it, so each look is
visible in the history - and the trainer code must be committed first, so the
evaluated code is a known version.

--runs: LLM policies, each the final champion of a run
        (generated_supervisors_coordination/RUN/current_supervisor.py).
--baselines: also evaluate the fixed recipe, the untuned MPC, the tuned MPC
        and the tuned MPC with known current disturbance.
Writes results/coordination/sealed_test/scores_<timestamp>.csv (one row per
controller and scenario, every metric) and prints means per battery part.
"""

import argparse
import csv
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

import numpy as np

import coordination_test_battery as B
import four_tank_coordination as C
from mpc_supervisor import MPCSupervisor, tuned_params
from supervisor_security import check_source, safe_exec_supervisor

OUT_DIR = os.path.join("results", "coordination", "sealed_test")
ACCESS_LOG = os.path.join(OUT_DIR, "access_log.jsonl")
SUPERVISORS_DIR = "generated_supervisors_coordination"
BASELINES = ("fixed_recipe", "mpc_untuned", "mpc_tuned", "mpc_known_disturbance")
REQUIRED_ARGS = ("telemetry_window", "active_setpoints", "objectives")


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()


def _controller(name, scenario, sources):
    if name == "fixed_recipe":
        return C.fixed_recipe_supervisor
    if name == "mpc_untuned":
        return MPCSupervisor()
    if name == "mpc_tuned":
        return MPCSupervisor(**tuned_params())
    if name == "mpc_known_disturbance":
        return MPCSupervisor(oracle_scenario=scenario, **tuned_params())
    fn, err = safe_exec_supervisor(sources[name])
    if err:
        raise RuntimeError(f"{name}: {err}")
    return fn


def _run(job):
    name, scenario, sources = job
    scenario = dataclasses.replace(scenario, supervisor_timeout_s=10.0 if name.startswith("mpc") else scenario.supervisor_timeout_s)
    m = C.run_episode(_controller(name, scenario, sources), scenario)["metrics"]
    return {"controller": name, "scenario": scenario.name, "part": scenario.range_label, "kind": scenario.kind_label,
            "pattern": scenario.pattern_label, **m, "score": C.score(m)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unseal", required=True, help="why the sealed battery is opened (logged)")
    ap.add_argument("--runs", nargs="*", default=[])
    ap.add_argument("--baselines", action="store_true")
    args = ap.parse_args()
    if not args.runs and not args.baselines:
        sys.exit("nothing to evaluate: give --runs and/or --baselines")
    if _git("status", "--porcelain", "--untracked-files=no", "--", "*.py"):
        sys.exit("commit the code first: the evaluated version must be a known commit")

    sources = {}
    for run in args.runs:
        path = os.path.join(SUPERVISORS_DIR, run, "current_supervisor.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        ok, reason = check_source(src, required_args=REQUIRED_ARGS)
        if not ok:
            sys.exit(f"{run}: fails the security check: {reason}")
        sources[run] = src
    controllers = list(args.runs) + (list(BASELINES) if args.baselines else [])

    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    entry = {"time": stamp, "git_commit": _git("rev-parse", "--short", "HEAD"), "reason": args.unseal,
             "controllers": controllers, "fingerprint": B.EXPECTED_FINGERPRINT,
             "policy_sha256": {r: hashlib.sha256(s.encode("utf-8")).hexdigest()[:16] for r, s in sources.items()},
             "mpc_tuned_params": tuned_params() if args.baselines else None}
    with open(ACCESS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[UNSEALED] logged to {ACCESS_LOG}: {args.unseal}")

    battery = B.make_test_battery(unseal=True)
    jobs = [(name, sc, sources) for name in controllers for sc in battery]
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as pool:
        rows = list(pool.map(_run, jobs, chunksize=2))

    out = os.path.join(OUT_DIR, f"scores_{stamp}.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    parts = list(dict.fromkeys(r["part"] for r in rows))
    print(f"{len(rows)} episodes -> {out}\n")
    print(f"{'controller':26s}" + "".join(f"{p:>20s}" for p in parts))
    for name in controllers:
        cells = [np.mean([r["score"] for r in rows if r["controller"] == name and r["part"] == p]) for p in parts]
        print(f"{name:26s}" + "".join(f"{c:20.1f}" for c in cells))


if __name__ == "__main__":
    main()
