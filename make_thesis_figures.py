"""Figures for the LaTeX thesis in Thesis_latex/, sized for the LTHthesis text
width (117 mm) so fonts stay legible without scaling.

Run: MPLBACKEND=Agg python make_thesis_figures.py   (no API calls)
Writes Thesis_latex/figures/architecture.pdf and
Thesis_latex/figures/four_tank_reasoning_comparison.pdf.
"""

import json
import os

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from plot_reasoning_comparison import RUNS, oracle_score, trajectory
from supervisor_security import safe_exec_supervisor
from train_supervisor_four_tank import (
    SCENARIO_BATTERY, VALIDATION_SCENARIO_BATTERY, SEED_SUPERVISOR_PATH, score_supervisor,
)

FIGURES_DIR = os.path.join("Thesis_latex", "figures")
TEXT_WIDTH_IN = 117 / 25.4

plt.rcParams.update({"font.size": 7.5, "font.family": "serif", "axes.titlesize": 8, "legend.fontsize": 6.5})


def architecture_figure():
    fig, ax = plt.subplots(figsize=(TEXT_WIDTH_IN, 2.35))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis("off")

    def box(x, y, w, h, title, body, colour):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05,rounding_size=0.12",
                                    facecolor=colour, edgecolor="black", linewidth=0.7))
        ax.text(x + w / 2, y + h - 0.28, title, ha="center", va="top", fontsize=7.5, fontweight="bold")
        ax.text(x + w / 2, y + h - 0.72, body, ha="center", va="top", fontsize=6.0, linespacing=1.25)

    def arrow(x0, y0, x1, y1, text="", text_xy=None):
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="-|>", linewidth=0.8, color="black", shrinkA=0, shrinkB=0))
        if text:
            tx, ty = text_xy
            ax.text(tx, ty, text, ha="center", va="center", fontsize=6, style="italic")

    box(0.05, 2.75, 2.8, 2.15, "Layer 3: LLM learner",
        "offline, run manually;\nreads champion code,\nscores, traces, lessons;\nproposes candidates", "#dbe8f5")
    box(3.6, 2.75, 2.8, 2.15, "Gate",
        "AST security check,\nrestricted built-ins,\ntimeout; scored on fault\nbattery; promoted if better", "#f5ecd6")
    box(7.15, 2.75, 2.8, 2.15, "Layer 2: supervisor",
        "deterministic Python;\nevery decision interval:\nanomaly flags and\nadjusted setpoints", "#dcefdc")
    box(7.15, 0.1, 2.8, 1.9, "Layer 1: PI/PID",
        "fixed, never generated;\ntracks active setpoints,\ndrives the pumps", "#eeeeee")
    box(3.6, 0.1, 2.8, 1.9, "Plant",
        "tank levels and pumps;\ninjected leak faults", "#ffffff")

    arrow(2.85, 3.85, 3.6, 3.85)
    arrow(6.4, 3.85, 7.15, 3.85)
    arrow(8.55, 2.75, 8.55, 2.0, "setpoints", (9.3, 2.38))
    arrow(7.15, 1.05, 6.4, 1.05)
    # Offline path: logged plant telemetry back to the learner (one arrowhead).
    ax.plot([3.6, 1.45, 1.45], [0.6, 0.6, 2.2], color="black", linewidth=0.8)
    ax.annotate("", xy=(1.45, 2.75), xytext=(1.45, 2.2),
                arrowprops=dict(arrowstyle="-|>", linewidth=0.8, color="black", shrinkA=0, shrinkB=0))
    ax.text(0.7, 1.55, "logged\ntelemetry\n(offline)", ha="center", va="center", fontsize=6, style="italic")
    arrow(5.0, 2.0, 7.6, 2.75)
    ax.text(6.05, 2.58, "telemetry", ha="center", va="center", fontsize=6, style="italic", rotation=15)

    fig.tight_layout(pad=0.1)
    fig.savefig(os.path.join(FIGURES_DIR, "architecture.pdf"))
    plt.close(fig)


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
    architecture_figure()
    reasoning_figure()
    print(f"[SUCCESS] wrote figures to {FIGURES_DIR}")


if __name__ == "__main__":
    main()
