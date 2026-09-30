"""Figures for the LaTeX thesis in Thesis_latex/, sized for the LTHthesis text
width (117 mm) so fonts stay legible without scaling.

Run: MPLBACKEND=Agg python make_thesis_figures.py   (no API calls)
Writes Thesis_latex/figures/four_tank_reasoning_comparison.pdf. The
architecture figure (three_layer_architecture.png) comes from the goal document.
"""

import json
import os

import matplotlib.pyplot as plt

from plot_reasoning_comparison import RUNS, oracle_score, trajectory
from supervisor_security import safe_exec_supervisor
from train_supervisor_four_tank import (
    SCENARIO_BATTERY, VALIDATION_SCENARIO_BATTERY, SEED_SUPERVISOR_PATH, score_supervisor,
)

FIGURES_DIR = os.path.join("Thesis_latex", "figures")
TEXT_WIDTH_IN = 117 / 25.4

# Times-like fonts to match the thesis body text (mathptmx).
plt.rcParams.update({"font.size": 7.5, "font.family": "serif",
                     "font.serif": ["Times New Roman", "Times", "STIXGeneral", "DejaVu Serif"],
                     "mathtext.fontset": "stix", "axes.titlesize": 8, "legend.fontsize": 6.5})


def reasoning_figure():
    with open(SEED_SUPERVISOR_PATH, "r", encoding="utf-8") as f:
        seed_fn, _ = safe_exec_supervisor(f.read())
    gen0_dev, _ = score_supervisor(seed_fn)
    gen0_val, _ = score_supervisor(seed_fn, battery=VALIDATION_SCENARIO_BATTERY)
    oracle_dev, oracle_val = oracle_score(SCENARIO_BATTERY), oracle_score(VALIDATION_SCENARIO_BATTERY)

    fig, (ax_dev, ax_val) = plt.subplots(2, 1, figsize=(TEXT_WIDTH_IN, 4.3), sharex=True)
    max_gen = 1
    for offset, (label, path, colour) in zip((-0.1, 0.0, 0.1), RUNS):
        with open(path, "r", encoding="utf-8") as f:
            trials = [json.loads(line) for line in f if line.strip()]
        dev, val, candidates = trajectory(trials, gen0_dev, gen0_val)
        gens = list(range(len(dev)))
        max_gen = max(max_gen, gens[-1])
        ax_dev.scatter([g + offset for g, _ in candidates], [s for _, s in candidates],
                       color=colour, alpha=0.3, s=9, linewidths=0)
        ax_dev.plot(gens, dev, marker="o", markersize=3.5, linewidth=1.1, color=colour, label=label)
        ax_val.plot(gens, val, marker="o", markersize=3.5, linewidth=1.1, color=colour, label=label)

    for ax, oracle, title in ((ax_dev, oracle_dev, "Development battery"),
                              (ax_val, oracle_val, "Held-out battery")):
        ax.axhline(oracle, color="black", linestyle="--", linewidth=0.9, label="Oracle")
        ax.set_yscale("log")
        ax.set_ylabel("Average score")
        ax.set_title(title, pad=3)
        ax.grid(True, which="both", alpha=0.3, linewidth=0.5)
    ax_val.set_xticks(range(max_gen + 1))
    ax_val.set_xlabel("Generation")
    # The held-out panel's upper right is empty; in the development panel a
    # legend would hide the crashed candidates at the top.
    ax_val.legend(loc="upper right", ncol=2, frameon=True)
    fig.tight_layout(pad=0.3, h_pad=0.6)
    fig.savefig(os.path.join(FIGURES_DIR, "four_tank_reasoning_comparison.pdf"))
    plt.close(fig)


def main():
    os.makedirs(FIGURES_DIR, exist_ok=True)
    reasoning_figure()
    print(f"[SUCCESS] wrote figures to {FIGURES_DIR}")


if __name__ == "__main__":
    main()
