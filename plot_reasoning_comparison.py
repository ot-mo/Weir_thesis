"""Four-tank reasoning ablation: champion score per generation for each
DeepSeek reasoning level, against gen_0 and the perfect-detection oracle.

Run: MPLBACKEND=Agg python plot_reasoning_comparison.py
Writes results/four_tank_reasoning_comparison.png (no API calls).
"""

import json
import os

import matplotlib.pyplot as plt

from supervisor_security import safe_exec_supervisor
from train_supervisor_four_tank import (
    SCENARIO_BATTERY, VALIDATION_SCENARIO_BATTERY, SEED_SUPERVISOR_PATH, score_supervisor,
)

OUTPUT_PATH = os.path.join("results", "four_tank_reasoning_comparison.png")

# (label, trial log, colour). The "high" run is the default run: gen_1-2 at
# high effort with the pre-trim prompt, gen_3 at low effort after the trim.
RUNS = [
    ("High reasoning", os.path.join("results", "supervisor_training_trials_four_tank.jsonl"), "#1f77b4"),
    ("Low reasoning", os.path.join("results", "supervisor_training_trials_four_tank_low_reasoning.jsonl"), "#2ca02c"),
    ("No reasoning", os.path.join("results", "supervisor_training_trials_four_tank_no_thinking.jsonl"), "#d62728"),
]


def oracle_for(scenario):
    """Flags exactly the true fault state at each decision - the best any
    supervisor can do at a 10s decision interval - with nominal setpoints."""
    calls = {"n": 0}

    def supervise(telemetry_window, active_setpoints, nominal_targets):
        calls["n"] += 1
        t = scenario.window_steps + scenario.decision_interval_steps * (calls["n"] - 1)
        active = lambda on, off: on is not None and t >= on and (off is None or t < off)
        return {
            "diagnosis": "oracle",
            "adjusted_setpoints": dict(nominal_targets),
            "anomaly_flags": {"tank1": active(scenario.leak1_onset_s, scenario.leak1_offset_s),
                              "tank2": active(scenario.leak2_onset_s, scenario.leak2_offset_s)},
        }
    return supervise


def oracle_score(battery):
    return sum(score_supervisor(oracle_for(s), battery=[s])[0] for s in battery) / len(battery)


def trajectory(trials, gen0_dev, gen0_val):
    """Champion dev/held-out score after each generation (carried forward when
    nothing is promoted) and every scored candidate's dev score."""
    last_gen = max((t["trial"] for t in trials), default=0)
    dev, val, candidates = [gen0_dev], [gen0_val], []
    for g in range(1, last_gen + 1):
        in_gen = [t for t in trials if t["trial"] == g]
        promoted = [t for t in in_gen if t["decision"] == "PROMOTED"]
        dev.append(promoted[0]["score"] if promoted else dev[-1])
        val.append(promoted[0]["validation_score"] if promoted else val[-1])
        candidates += [(g, t["score"]) for t in in_gen if t.get("score") is not None]
    return dev, val, candidates


def main():
    with open(SEED_SUPERVISOR_PATH, "r", encoding="utf-8") as f:
        seed_fn, _ = safe_exec_supervisor(f.read())
    gen0_dev, _ = score_supervisor(seed_fn)
    gen0_val, _ = score_supervisor(seed_fn, battery=VALIDATION_SCENARIO_BATTERY)
    oracle_dev, oracle_val = oracle_score(SCENARIO_BATTERY), oracle_score(VALIDATION_SCENARIO_BATTERY)

    fig, (ax_dev, ax_val) = plt.subplots(1, 2, figsize=(13, 5.2), sharey=True)
    max_gen = 1
    for offset, (label, path, colour) in zip((-0.12, 0.0, 0.12), RUNS):
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            trials = [json.loads(line) for line in f if line.strip()]
        dev, val, candidates = trajectory(trials, gen0_dev, gen0_val)
        gens = list(range(len(dev)))
        max_gen = max(max_gen, gens[-1])
        ax_dev.scatter([g + offset for g, _ in candidates], [s for _, s in candidates],
                       color=colour, alpha=0.25, s=18, linewidths=0)
        ax_dev.plot(gens, dev, marker="o", color=colour, label=label, drawstyle="default")
        ax_val.plot(gens, val, marker="o", color=colour, label=label)
        print(f"{label:15s} dev: " + " -> ".join(f"{s:.0f}" for s in dev)
              + " | held-out: " + " -> ".join(f"{s:.0f}" for s in val))

    for ax, oracle, title in ((ax_dev, oracle_dev, "Dev battery (drives promotion)"),
                              (ax_val, oracle_val, "Held-out battery (never shown to the LLM)")):
        ax.axhline(oracle, color="black", linestyle="--", linewidth=1.2, label=f"Oracle ({oracle:.0f})")
        ax.set_yscale("log")
        ax.set_xticks(range(max_gen + 1))
        ax.set_xlabel("Generation (4 candidates each)")
        ax.set_title(title)
        ax.grid(True, which="both", alpha=0.3)
    ax_dev.set_ylabel("Average score (log scale, lower is better)")
    ax_dev.legend(loc="upper right")
    fig.suptitle("Four-tank supervisor: effect of LLM reasoning on search progress")
    fig.text(0.5, 0.005,
             "Lines: champion after each generation. Dots: every scored candidate (dev). Gen 0 = seed supervisor. "
             "High run's gen 3 used low effort; no-reasoning run used the older built-ins prompt wording.",
             ha="center", fontsize=8, color="#444444")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(OUTPUT_PATH, dpi=150)
    print(f"oracle dev {oracle_dev:.1f} / held-out {oracle_val:.1f}")
    print(f"[SUCCESS] wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
