"""
Print-size figures for the paper, from the held-out experiment run.

    python paper/make_figures.py [backend/experiments/results/main]

Writes paper/figures/profit.pdf (full text width) and paper/figures/weights.pdf
(single column).  Colours/tokens follow backend/experiments/analyze.py.
"""

import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.experiments.analyze import (  # noqa: E402
    load, build_frame, summarise, INK, INK_2, MUTED, GRID, BASELINE, SERIES,
)

WHITE = "#ffffff"
SCENARIOS = [("baseline", "Baseline"), ("tight_budget", "Tight budget"), ("volatile", "Volatile")]
METHODS = [
    ("newsvendor", "Newsvendor"),
    ("base_stock", "Base-stock (95%)"),
    ("agent_procurement", "Procurement agent"),
    ("agent_finance", "Finance agent"),
    ("agent_inventory", "Inventory agent"),
    ("agent_sales", "Sales agent"),
    ("ensemble_mean", "Agent mean"),
    ("ensemble_median", "Agent median"),
    ("amdie", "AMDIE"),
]

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 7, "axes.labelsize": 7, "xtick.labelsize": 6.5, "ytick.labelsize": 6.5,
    "text.color": INK, "axes.labelcolor": INK_2, "figure.facecolor": WHITE, "savefig.facecolor": WHITE,
    "pdf.fonttype": 42,
})


def style(ax, grid_axis="x"):
    ax.set_facecolor(WHITE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(colors=INK_2, length=0, pad=2)
    ax.grid(True, axis=grid_axis, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def main(results_dir: Path):
    out = ROOT / "paper" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    rows = load(results_dir)
    idx, rel = build_frame(rows)
    S = {(r["scenario"], r["policy"]): r for r in summarise(idx, rel)}

    # Profit relative to base-stock, one panel per scenario
    fig, axes = plt.subplots(1, 3, figsize=(7.16, 2.05), sharey=True, gridspec_kw={"wspace": 0.08})
    ys = np.arange(len(METHODS))[::-1]
    for ax, (sc, title) in zip(axes, SCENARIOS):
        for y, (p, _) in zip(ys, METHODS):
            r = S[(sc, p)]
            color = SERIES[0] if p == "amdie" else MUTED
            ax.plot([r["rel_profit_lo"], r["rel_profit_hi"]], [y, y], color=color, linewidth=1.6, solid_capstyle="round")
            ax.plot(r["rel_profit"], y, "o", color=color, markersize=4.2, markeredgecolor=WHITE, markeredgewidth=1.0)
        ax.axvline(0, color=BASELINE, linewidth=0.8)
        ax.set_title(title, fontsize=7.5, loc="left", color=INK, pad=3)
        ax.set_xlabel(r"$\Delta$ profit vs. base-stock (%)")
        ax.set_xlim(-16, 7)
        style(ax)
    axes[0].set_yticks(ys)
    axes[0].set_yticklabels([m[1] for m in METHODS])
    fig.savefig(out / "profit.pdf", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)

    # AMDIE weight evolution, baseline scenario, mean over seeds
    traces = [r["trace"]["weights_by_review"] for r in idx[("baseline", "amdie")].values()]
    n = min(len(t) for t in traces)
    weeks = np.arange(1, n + 1)
    fig, ax = plt.subplots(figsize=(3.45, 1.55))
    agents = ["inventory", "sales", "finance", "procurement"]
    for color, a in zip(SERIES, agents):
        series = np.mean([[t[k][a] for k in range(n)] for t in traces], axis=0)
        ax.plot(weeks, series, color=color, linewidth=1.4, label=a.title())
        ax.annotate(a.title(), (weeks[-1], series[-1]), xytext=(3, 0), textcoords="offset points",
                    fontsize=6.5, color=INK_2, va="center")
    ax.axhline(0.25, color=BASELINE, linewidth=0.8)
    ax.set_xlim(1, n + 4.5)
    ax.set_ylim(0, 0.85)
    ax.set_xticks([1, 5, 10, 15, 20])
    ax.set_xlabel("Review week")
    ax.set_ylabel("Mean weight")
    style(ax, grid_axis="y")
    ax.legend(frameon=False, fontsize=6, ncol=4, loc="lower center", bbox_to_anchor=(0.45, 1.0),
              handlelength=1.2, columnspacing=0.9)
    fig.savefig(out / "weights.pdf", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    print("wrote", out / "profit.pdf", "and", out / "weights.pdf")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "backend/experiments/results/main")
