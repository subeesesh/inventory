"""
Analyse experiment results: tables, paired significance tests and figures.

    python -m backend.experiments.analyze backend/experiments/results/main

Reads <dir>/runs.jsonl and writes:
  summary.csv          per (scenario, policy) means, std devs and 95% CIs
  tables.md / .tex     main comparison, per-scenario detail, ablation
  stats.md             AMDIE vs every other policy: paired t-test, Wilcoxon
                       (seed level and product level), Holm-corrected
  figures/*.png|pdf    profit comparison, service-inventory trade-off,
                       AMDIE weight evolution, ablation

Primary metric: profit relative to the base-stock (95% service) policy on the
same instance, in percent.  Every policy runs on identical demand and lead-time
draws, so all comparisons are paired by (scenario, seed).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

REFERENCE = "base_stock"
PRIMARY = "amdie"

DISPLAY = {
    "oracle": "Perfect-foresight order-up-to (ref.)",
    "base_stock": "Base-stock, 95% service",
    "newsvendor": "Newsvendor order-up-to",
    "agent_inventory": "Inventory agent only",
    "agent_sales": "Sales agent only",
    "agent_procurement": "Procurement agent only",
    "agent_finance": "Finance agent only",
    "ensemble_mean": "Agent mean",
    "ensemble_median": "Agent median",
    "amdie": "AMDIE (full)",
    "amdie_static_weights": "– adaptive weights (equal)",
    "amdie_no_lp": "– LP fusion (weighted avg.)",
    "amdie_no_divergence": "– divergence penalty",
    "amdie_no_context": "– context relevance",
    "amdie_no_caps": "– agent hard caps",
    "amdie_no_learning": "– outcome learning",
    "amdie_untuned": "– tuning (T=1, symmetric scoring)",
    "llm": "LLM decision maker",
}
MAIN_ORDER = ["newsvendor", "base_stock", "agent_procurement", "agent_finance", "agent_inventory",
              "agent_sales", "ensemble_mean", "ensemble_median", "llm", "amdie", "oracle"]
ABLATION_ORDER = ["amdie", "amdie_untuned", "amdie_static_weights", "amdie_no_lp", "amdie_no_learning",
                  "amdie_no_divergence", "amdie_no_context", "amdie_no_caps"]
SCENARIO_ORDER = ["baseline", "tight_budget", "volatile"]

# Chart tokens (dataviz reference palette, light mode; figures are for print)
INK, INK_2, MUTED, GRID, BASELINE, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]


def display(p: str) -> str:
    return DISPLAY.get(p, p)


def load(results_dir: Path) -> list[dict]:
    path = results_dir / "runs.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    # Keep the newest result per job key
    latest = {}
    for r in rows:
        latest[(r["scenario"], r["seed"], r["policy"])] = r
    return list(latest.values())


def ci95(values) -> tuple[float, float, float]:
    v = np.asarray(values, dtype=float)
    mean = float(v.mean())
    if len(v) < 2:
        return mean, mean, mean
    half = float(stats.t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v)))
    return mean, mean - half, mean + half


def holm(pvalues: list[float]) -> list[float]:
    order = np.argsort(pvalues)
    m, adjusted, running = len(pvalues), [0.0] * len(pvalues), 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[idx]))
        adjusted[idx] = running
    return adjusted


def build_frame(rows):
    """index[(scenario, policy)][seed] -> run, plus relative profit vs REFERENCE."""
    idx = defaultdict(dict)
    for r in rows:
        idx[(r["scenario"], r["policy"])][r["seed"]] = r
    rel = defaultdict(dict)
    for (sc, pol), by_seed in idx.items():
        ref = idx.get((sc, REFERENCE), {})
        for seed, r in by_seed.items():
            if seed in ref:
                rel[(sc, pol)][seed] = 100.0 * (r["metrics"]["profit"] / ref[seed]["metrics"]["profit"] - 1.0)
    return idx, rel


METRICS = [
    ("rel_profit", "Δ profit vs base-stock (%)", "{:+.2f}"),
    ("fill_rate", "Fill rate", "{:.3f}"),
    ("stockout_rate", "Stock-out days", "{:.3f}"),
    ("avg_inventory_value", "Avg. inventory value", "{:,.0f}"),
    ("truncation_rate", "Budget-truncated orders", "{:.3f}"),
    ("decision_wape", "WAPE vs perfect foresight", "{:.3f}"),
    ("conflict_rate", "Conflict rate", "{:.2f}"),
]


def summarise(idx, rel):
    out = []
    for (sc, pol), by_seed in idx.items():
        row = {"scenario": sc, "policy": pol, "n_seeds": len(by_seed)}
        for key, _, _ in METRICS:
            if key == "rel_profit":
                vals = list(rel.get((sc, pol), {}).values())
            elif key == "conflict_rate":
                vals = [r["trace"].get("conflict_rate", np.nan) for r in by_seed.values()]
            else:
                vals = [r["metrics"][key] for r in by_seed.values()]
            vals = [v for v in vals if v is not None and not np.isnan(v)]
            if vals:
                m, lo, hi = ci95(vals)
                row[key], row[f"{key}_lo"], row[f"{key}_hi"] = m, lo, hi
                row[f"{key}_sd"] = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
        row["sec_per_decision"] = float(np.mean([r["metrics"]["runtime_s"] / max(r["metrics"]["n_decisions"], 1)
                                                 for r in by_seed.values()]))
        out.append(row)
    return out


def paired_tests(idx, rel, scenarios, policies):
    """AMDIE vs each policy, per scenario.  Seed-level paired t / Wilcoxon on relative
    profit, and product-level Wilcoxon on per-product profit (seed x product pairs)."""
    results = []
    for sc in scenarios:
        a = rel.get((sc, PRIMARY), {})
        rows = []
        for pol in policies:
            if pol == PRIMARY or (sc, pol) not in rel:
                continue
            b = rel[(sc, pol)]
            seeds = sorted(set(a) & set(b))
            if len(seeds) < 2:
                continue
            diff = np.array([a[s] - b[s] for s in seeds])
            t_p = float(stats.ttest_rel([a[s] for s in seeds], [b[s] for s in seeds]).pvalue) if diff.std() > 0 else 1.0
            w_p = float(stats.wilcoxon(diff).pvalue) if np.any(diff != 0) else 1.0
            pa, pb = [], []
            for s in seeds:
                ra, rb = idx[(sc, PRIMARY)][s]["per_product"], idx[(sc, pol)][s]["per_product"]
                for pid in ra:
                    pa.append(ra[pid]["profit"])
                    pb.append(rb[pid]["profit"])
            pdiff = np.array(pa) - np.array(pb)
            prod_p = float(stats.wilcoxon(pdiff).pvalue) if np.any(pdiff != 0) else 1.0
            m, lo, hi = ci95(diff)
            rows.append({"scenario": sc, "vs": pol, "n": len(seeds), "diff": m, "lo": lo, "hi": hi,
                         "wins": int((diff > 0).sum()), "t_p": t_p, "wilcoxon_p": w_p,
                         "product_wilcoxon_p": prod_p, "n_products": len(pdiff)})
        for key in ("t_p", "product_wilcoxon_p"):
            adj = holm([r[key] for r in rows]) if rows else []
            for r, v in zip(rows, adj):
                r[f"{key}_holm"] = v
        results.extend(rows)
    return results


# ── Tables ───────────────────────────────────────────────────────────────────

def _cell(summary_row, key, fmt, with_ci=False):
    if summary_row is None or key not in summary_row:
        return "–"
    s = fmt.format(summary_row[key])
    if with_ci:
        s += f" [{fmt.format(summary_row[key + '_lo'])}, {fmt.format(summary_row[key + '_hi'])}]"
    return s


def _md_table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def _tex_table(caption, label, header, rows, align):
    esc = lambda s: s.replace("%", r"\%").replace("&", r"\&").replace("–", "--").replace("Δ", r"$\Delta$")  # noqa: E731
    body = " \\\\\n".join(" & ".join(esc(c) for c in r) for r in rows)
    return (
        "\\begin{table}[t]\n\\centering\\small\n"
        f"\\caption{{{caption}}}\\label{{{label}}}\n"
        f"\\begin{{tabular}}{{{align}}}\n\\toprule\n"
        + " & ".join(esc(h) for h in header) + " \\\\\n\\midrule\n" + body + " \\\\\n\\bottomrule\n"
        "\\end{tabular}\n\\end{table}\n"
    )


def write_tables(out: Path, summary, tests, scenarios, policies):
    S = {(r["scenario"], r["policy"]): r for r in summary}
    md, tex = [], []

    main = [p for p in MAIN_ORDER if p in policies] + \
           [p for p in policies if p not in MAIN_ORDER and p not in ABLATION_ORDER]
    header = ["Method"] + [f"{sc}: Δ profit % [95% CI]" for sc in scenarios] + [f"{sc}: fill" for sc in scenarios]
    rows = [[display(p)] + [_cell(S.get((sc, p)), "rel_profit", "{:+.2f}", True) for sc in scenarios]
            + [_cell(S.get((sc, p)), "fill_rate", "{:.3f}") for sc in scenarios] for p in main]
    md += ["## Table 1. Profit relative to base-stock and fill rate (mean over seeds)", "", _md_table(header, rows), ""]
    tex.append(_tex_table("Profit relative to the base-stock (95\\% service) policy, mean and 95\\% CI over seeds, and fill rate.",
                          "tab:main", header, rows, "l" + "c" * (len(header) - 1)))

    for sc in scenarios:
        header = ["Method"] + [m[1] for m in METRICS]
        rows = [[display(p)] + [_cell(S.get((sc, p)), k, f) for k, _, f in METRICS]
                for p in main + [a for a in ABLATION_ORDER if a in policies and a != PRIMARY]]
        md += [f"## Table 2-{sc}. Detailed metrics, scenario '{sc}'", "", _md_table(header, rows), ""]
        tex.append(_tex_table(f"Detailed metrics, scenario \\texttt{{{sc.replace('_', chr(92) + '_')}}}.",
                              f"tab:detail-{sc}", header, rows, "l" + "r" * len(METRICS)))

    abl = [p for p in ABLATION_ORDER if p in policies]
    if len(abl) > 1:
        T = {(t["scenario"], t["vs"]): t for t in tests}
        header = ["Variant"] + [f"{sc}: Δ vs full (pp) [95% CI]" for sc in scenarios] + [f"{sc}: p (Holm)" for sc in scenarios]
        rows = []
        for p in abl[1:]:
            cells_d, cells_p = [], []
            for sc in scenarios:
                t = T.get((sc, p))
                if t:  # tests are AMDIE - variant; ablation reports variant - AMDIE
                    cells_d.append(f"{-t['diff']:+.2f} [{-t['hi']:+.2f}, {-t['lo']:+.2f}]")
                    cells_p.append(f"{t['t_p_holm']:.3f}")
                else:
                    cells_d.append("–"); cells_p.append("–")
            rows.append([display(p)] + cells_d + cells_p)
        md += ["## Table 3. Ablation: change in profit when a component is removed (percentage points vs full AMDIE)", "",
               _md_table(header, rows), ""]
        tex.append(_tex_table("Ablation: profit change (percentage points of base-stock profit) when one AMDIE component is removed; paired over seeds, Holm-corrected $p$.",
                              "tab:ablation", header, rows, "l" + "c" * (len(header) - 1)))

    (out / "tables.md").write_text("\n".join(md), encoding="utf-8")
    (out / "tables.tex").write_text("% requires \\usepackage{booktabs}\n" + "\n".join(tex), encoding="utf-8")


def write_stats(out: Path, tests):
    lines = ["# Paired comparisons: AMDIE vs each policy", "",
             "diff = AMDIE minus the other policy, in percentage points of base-stock profit (positive = AMDIE better).",
             "Seed-level tests pair instances; product-level Wilcoxon pairs per-product profit (seed x product).",
             "Holm correction is applied within each scenario.", ""]
    for sc in sorted({t["scenario"] for t in tests}, key=lambda s: SCENARIO_ORDER.index(s) if s in SCENARIO_ORDER else 99):
        rows = [[display(t["vs"]), f"{t['diff']:+.2f} [{t['lo']:+.2f}, {t['hi']:+.2f}]", f"{t['wins']}/{t['n']}",
                 f"{t['t_p']:.4f}", f"{t['t_p_holm']:.4f}", f"{t['wilcoxon_p']:.4f}",
                 f"{t['product_wilcoxon_p']:.4f}", f"{t['product_wilcoxon_p_holm']:.4f}"]
                for t in tests if t["scenario"] == sc]
        lines += [f"## {sc}", "", _md_table(["vs", "diff pp [95% CI]", "AMDIE wins", "t p", "t p (Holm)",
                                             "Wilcoxon p", "product Wilcoxon p", "product p (Holm)"], rows), ""]
    (out / "stats.md").write_text("\n".join(lines), encoding="utf-8")


def write_csv(out: Path, summary):
    keys = ["scenario", "policy", "n_seeds"] + [f"{k}{s}" for k, _, _ in METRICS for s in ("", "_sd", "_lo", "_hi")] + ["sec_per_decision"]
    lines = [",".join(keys)]
    for r in sorted(summary, key=lambda r: (r["scenario"], r["policy"])):
        lines.append(",".join("" if r.get(k) is None else str(r.get(k)) for k in keys))
    (out / "summary.csv").write_text("\n".join(lines), encoding="utf-8")


# ── Figures ──────────────────────────────────────────────────────────────────

def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(colors=INK_2, labelsize=8, length=0)
    ax.grid(True, axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def write_figures(out: Path, idx, summary, scenarios, policies):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 9, "text.color": INK, "axes.labelcolor": INK_2,
                         "figure.facecolor": SURFACE, "savefig.facecolor": SURFACE})
    figdir = out / "figures"
    figdir.mkdir(exist_ok=True)
    S = {(r["scenario"], r["policy"]): r for r in summary}

    def save(fig, name):
        fig.savefig(figdir / f"{name}.png", dpi=200, bbox_inches="tight")
        fig.savefig(figdir / f"{name}.pdf", bbox_inches="tight")
        plt.close(fig)

    def dot_panel(ax, pols, sc, key="rel_profit"):
        ys = np.arange(len(pols))[::-1]
        for y, p in zip(ys, pols):
            r = S.get((sc, p))
            if not r or key not in r:
                continue
            is_amdie = p.startswith("amdie")
            color = SERIES[0] if is_amdie else MUTED
            ax.plot([r[key + "_lo"], r[key + "_hi"]], [y, y], color=color, linewidth=2, solid_capstyle="round")
            ax.plot(r[key], y, "o", color=color, markersize=6, markeredgecolor=SURFACE, markeredgewidth=1.5)
        ax.axvline(0, color=BASELINE, linewidth=1)
        ax.set_yticks(ys)
        ax.set_title(sc.replace("_", " "), fontsize=9, color=INK, loc="left")
        _style(ax)

    # Fig 1: profit vs base-stock, one panel per scenario
    main = [p for p in MAIN_ORDER if p in policies and p != REFERENCE]
    fig, axes = plt.subplots(1, len(scenarios), figsize=(3.2 * len(scenarios) + 1.6, 0.32 * len(main) + 1.2), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, sc in zip(axes, scenarios):
        dot_panel(ax, main, sc)
        ax.set_xlabel("Δ profit vs base-stock (%)")
    axes[0].set_yticklabels([display(p) for p in main])
    fig.suptitle("Profit relative to base-stock policy (mean, 95% CI over seeds)", x=0.01, ha="left", fontsize=10)
    save(fig, "fig1_profit")

    # Fig 2: service vs inventory trade-off
    fig, axes = plt.subplots(1, len(scenarios), figsize=(3.4 * len(scenarios), 3.2), sharey=True)
    axes = np.atleast_1d(axes)
    highlight = {PRIMARY: SERIES[0], "newsvendor": SERIES[1], "base_stock": SERIES[1]}
    for ax, sc in zip(axes, scenarios):
        for p in main + [REFERENCE]:
            r = S.get((sc, p))
            if not r:
                continue
            color = highlight.get(p, MUTED)
            ax.plot(r["avg_inventory_value"] / 1000, r["fill_rate"], "o", color=color, markersize=7 if p in highlight else 5,
                    markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=3 if p in highlight else 2)
            if p in highlight or p.startswith("agent_"):
                ax.annotate(display(p).replace(" agent only", "").replace(", 95% service", "").replace(" order-up-to", ""),
                            (r["avg_inventory_value"] / 1000, r["fill_rate"]), xytext=(4, 3), textcoords="offset points",
                            fontsize=7, color=INK_2)
        ax.set_xlabel("Avg. inventory value (thousands)")
        ax.set_title(sc.replace("_", " "), fontsize=9, color=INK, loc="left")
        _style(ax)
        ax.grid(True, axis="y", color=GRID, linewidth=0.8)
    axes[0].set_ylabel("Fill rate")
    save(fig, "fig2_service_inventory")

    # Fig 3: AMDIE weight evolution (mean over seeds) per scenario
    fig, axes = plt.subplots(1, len(scenarios), figsize=(3.4 * len(scenarios), 2.8), sharey=True)
    axes = np.atleast_1d(axes)
    agents = ["inventory", "sales", "finance", "procurement"]
    for ax, sc in zip(axes, scenarios):
        traces = [r["trace"].get("weights_by_review", []) for r in idx.get((sc, PRIMARY), {}).values()]
        traces = [t for t in traces if t]
        if not traces:
            continue
        n = min(len(t) for t in traces)
        weeks = np.arange(n)
        for color, a in zip(SERIES, agents):
            series = np.mean([[t[k][a] for k in range(n)] for t in traces], axis=0)
            ax.plot(weeks, series, color=color, linewidth=2, label=a.title())
            ax.annotate(a.title(), (weeks[-1], series[-1]), xytext=(4, 0), textcoords="offset points",
                        fontsize=7, color=INK_2, va="center")
        ax.axhline(0.25, color=BASELINE, linewidth=1)
        ax.set_xlim(0, weeks[-1] + 0.3 * len(weeks))   # room for direct labels
        ax.set_xlabel("Review week")
        ax.set_title(sc.replace("_", " "), fontsize=9, color=INK, loc="left")
        _style(ax)
        ax.grid(True, axis="y", color=GRID, linewidth=0.8)
    axes[0].set_ylabel("Mean AMDIE weight")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=7, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.08))
    save(fig, "fig3_weights")

    # Fig 4: ablation
    abl = [p for p in ABLATION_ORDER if p in policies]
    if len(abl) > 1:
        fig, axes = plt.subplots(1, len(scenarios), figsize=(3.2 * len(scenarios) + 1.6, 0.34 * len(abl) + 1.2), sharey=True)
        axes = np.atleast_1d(axes)
        for ax, sc in zip(axes, scenarios):
            dot_panel(ax, abl, sc)
            ax.set_xlabel("Δ profit vs base-stock (%)")
        axes[0].set_yticklabels([display(p) for p in abl])
        fig.suptitle("Ablation of AMDIE components (mean, 95% CI over seeds)", x=0.01, ha="left", fontsize=10)
        save(fig, "fig4_ablation")


def analyze(results_dir: Path) -> None:
    results_dir = Path(results_dir)
    rows = load(results_dir)
    idx, rel = build_frame(rows)
    present = {r["policy"] for r in rows}
    scenarios = [s for s in SCENARIO_ORDER if any(r["scenario"] == s for r in rows)] + \
                sorted({r["scenario"] for r in rows} - set(SCENARIO_ORDER))
    policies = [p for p in MAIN_ORDER + ABLATION_ORDER if p in present] + sorted(present - set(MAIN_ORDER + ABLATION_ORDER))
    summary = summarise(idx, rel)
    tests = paired_tests(idx, rel, scenarios, policies) if PRIMARY in present else []
    write_csv(results_dir, summary)
    write_tables(results_dir, summary, tests, scenarios, policies)
    if tests:
        write_stats(results_dir, tests)
    write_figures(results_dir, idx, summary, scenarios, policies)
    print(f"Analysis written to {results_dir} (tables.md, tables.tex, stats.md, summary.csv, figures/)")


if __name__ == "__main__":
    analyze(Path(sys.argv[1] if len(sys.argv) > 1 else "backend/experiments/results/main"))
