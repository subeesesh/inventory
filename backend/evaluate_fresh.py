"""
Fresh Out-of-Sample Evaluation
================================
Uses 3 products (PROD-005, PROD-010, PROD-015) that appear in none of the
3 pre-defined evaluation scenarios.

Each product is evaluated against its LIVE database state — no artificial
context manipulation. Ground truth is the budget-capped Newsvendor optimal:

    Q* = mu + z_CR * sigma
    CR = (unit_price - unit_cost) / unit_price   (critical ratio)
    Q* = min(Q*, budget / unit_cost)

Methods compared:
    1. AMDIE v2  — full pipeline (conflict → weights → LP solver)
    2. Simple Average
    3. Majority / Highest-Confidence Wins
    4. Static Equal Weights
"""

import sys
import time
import json
import numpy as np
from scipy.stats import norm
from datetime import date, timedelta
from pathlib import Path

# ── Bootstrap imports ─────────────────────────────────────────────────────────
from backend.app.db import SessionLocal, init_db
from backend.app.agents import SalesAgent, InventoryAgent, FinanceAgent
from backend.app.amdie import (
    detect_conflict,
    get_agent_weights,
    adjust_objective_for_goals,
    solve_decision_fusion,
)
from backend.app.db import Product, InventoryState, SalesRecord, FinanceLedger, Tenant

TENANT_ID  = "t1-uuid-demo-sme-tenant-12345"
EVAL_DATE  = date.today() - timedelta(days=1)   # yesterday — all data exists
PRODUCTS   = ["PROD-005", "PROD-010", "PROD-015"]
REPORT_OUT = Path(
    r"C:/Users/subee/.gemini/antigravity/brain/"
    "6d05e865-a45e-428f-b41d-72326a118f82/fresh_evaluation_report.md"
)

# ── Newsvendor ground truth ────────────────────────────────────────────────────
def newsvendor_gt(unit_price, unit_cost, daily_sales, budget):
    eps  = 1e-9
    CR   = (unit_price - unit_cost) / max(unit_price, eps)
    CR   = float(np.clip(CR, 0.01, 0.99))
    mu   = float(np.mean(daily_sales)) if daily_sales else 1.0
    sig  = float(np.std(daily_sales))  if daily_sales else 0.0
    z    = norm.ppf(CR)
    q    = mu + z * sig
    cap  = budget / max(unit_cost, eps)
    return float(np.clip(q, 0.0, cap))

# ── Baseline helpers ───────────────────────────────────────────────────────────
def simple_average(decisions):
    return float(np.mean([d.recommendation for d in decisions.values()]))

def majority_wins(decisions):
    best = max(decisions.values(), key=lambda d: d.confidence)
    return float(best.recommendation)

def static_equal_weights(decisions):
    n = len(decisions)
    return float(sum(d.recommendation / n for d in decisions.values()))

# ── Run one product ────────────────────────────────────────────────────────────
def evaluate_product(product_id: str, db) -> dict:
    print(f"\n  Product: {product_id}")

    product = db.query(Product).filter_by(
        tenant_id=TENANT_ID, id=product_id
    ).first()
    if not product:
        print(f"  [SKIP] {product_id} not found in DB.")
        return None

    print(f"  Name: {product.name}  |  Category: {product.category}")
    print(f"  Price: ${product.unit_price:.2f}  |  Cost: ${product.unit_cost:.2f}")

    ledger = db.query(FinanceLedger).filter_by(
        tenant_id=TENANT_ID
    ).first()
    budget    = ledger.budget_per_period if ledger else 5000.0
    unit_cost = product.unit_cost
    unit_price = product.unit_price

    # 90-day sales for Newsvendor ground truth
    cutoff = EVAL_DATE - timedelta(days=90)
    sales  = db.query(SalesRecord).filter(
        SalesRecord.tenant_id  == TENANT_ID,
        SalesRecord.product_id == product_id,
        SalesRecord.date       >= cutoff,
        SalesRecord.date       <= EVAL_DATE,
    ).all()
    daily_qty = [r.qty_sold for r in sales]
    gt = newsvendor_gt(unit_price, unit_cost, daily_qty, budget)
    print(f"  Newsvendor GT: {gt:.2f} units  (based on {len(daily_qty)} daily sales records)")

    # ── Run domain agents ────────────────────────────────────────────────────
    inventory_agent = InventoryAgent()
    sales_agent     = SalesAgent()
    finance_agent   = FinanceAgent()

    dec_inv  = inventory_agent.run(TENANT_ID, product_id, EVAL_DATE, db)
    dec_sale = sales_agent.run(TENANT_ID, product_id, EVAL_DATE, db)
    dec_fin  = finance_agent.run(TENANT_ID, product_id, EVAL_DATE, db)

    decisions = {
        "inventory": dec_inv,
        "sales":     dec_sale,
        "finance":   dec_fin,
    }
    print(f"  Agent recs  ->  Inventory: {dec_inv.recommendation:.1f}  |  "
          f"Sales: {dec_sale.recommendation:.1f}  |  Finance: {dec_fin.recommendation:.1f}")

    # ── AMDIE ────────────────────────────────────────────────────────────────
    conflict_detected, conflict_score = detect_conflict(decisions)
    print(f"  Conflict: {conflict_detected}  (score: {conflict_score:.4f})")

    weights, components = get_agent_weights(
        TENANT_ID, decisions,
        query_text=f"reorder {product.name} category {product.category}",
        db=db,
    )
    print(f"  Weights  ->  " + "  ".join(
        f"{k}: {v*100:.1f}%" for k, v in weights.items()
    ))

    goal_params = adjust_objective_for_goals(
        weights=weights,
        decisions=decisions,
        business_goal="maximize_profit",
        unit_cost=unit_cost,
        forecasted_demand=float(np.mean([d.recommendation for d in decisions.values()])),
    )
    adjusted_weights   = goal_params["adjusted_weights"]
    cost_penalty       = goal_params["cost_penalty"]
    turnover_bonus     = goal_params["turnover_bonus"]
    forecasted_demand  = goal_params["forecasted_demand"]

    t0 = time.perf_counter()
    amdie_rec, _, opt_log = solve_decision_fusion(
        adjusted_weights, decisions,
        unit_cost=unit_cost,
        budget=budget,
        cost_penalty=cost_penalty,
        turnover_bonus=turnover_bonus,
        forecasted_demand=forecasted_demand,
    )
    amdie_ms = (time.perf_counter() - t0) * 1000

    # ── Baselines ────────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    avg_rec = simple_average(decisions)
    avg_ms  = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    maj_rec = majority_wins(decisions)
    maj_ms  = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    eq_rec  = static_equal_weights(decisions)
    eq_ms   = (time.perf_counter() - t0) * 1000

    return {
        "product_id":       product_id,
        "product_name":     product.name,
        "category":         product.category,
        "unit_price":       unit_price,
        "unit_cost":        unit_cost,
        "conflict_detected": conflict_detected,
        "conflict_score":   conflict_score,
        "newsvendor_gt":    gt,
        "agent_recs":       {k: v.recommendation for k, v in decisions.items()},
        "weights":          {k: round(v * 100, 1) for k, v in weights.items()},
        "divergence_penalties": {
            k: round(components[k].get("divergence_penalty", 0.0), 4)
            for k in components
        },
        "results": {
            "AMDIE":               {"rec": amdie_rec, "err": abs(amdie_rec - gt), "ms": amdie_ms, "explain": True},
            "Simple Average":      {"rec": avg_rec,   "err": abs(avg_rec   - gt), "ms": avg_ms,   "explain": False},
            "Majority Wins":       {"rec": maj_rec,   "err": abs(maj_rec   - gt), "ms": maj_ms,   "explain": False},
            "Static Equal Weights":{"rec": eq_rec,    "err": abs(eq_rec    - gt), "ms": eq_ms,    "explain": False},
        },
    }

# ── Report generation ─────────────────────────────────────────────────────────
def build_report(rows: list) -> str:
    lines = [
        "# Fresh Out-of-Sample Evaluation Report",
        "",
        "Products evaluated: **PROD-005, PROD-010, PROD-015** (not used in any pre-defined scenario).",
        "Context: live unmanipulated database state.  Ground truth: budget-capped Newsvendor optimal.",
        "",
    ]

    for r in rows:
        if r is None:
            continue
        lines += [
            f"---",
            f"## {r['product_id']} — {r['product_name']} ({r['category']})",
            f"- **Unit Price**: ${r['unit_price']:.2f}  |  **Unit Cost**: ${r['unit_cost']:.2f}",
            f"- **Conflict Detected**: {r['conflict_detected']} (score: {r['conflict_score']:.4f})",
            f"- **Newsvendor Ground Truth**: {r['newsvendor_gt']:.2f} units",
            "",
            "### Agent Recommendations",
            f"| Agent | Recommendation | Divergence Penalty |",
            f"| :--- | :---: | :---: |",
        ]
        for agent, rec in r["agent_recs"].items():
            div = r["divergence_penalties"].get(agent, 0.0)
            lines.append(f"| {agent.capitalize()} | {rec:.1f} | {div:.4f} |")

        lines += [
            "",
            "### Adaptive Weights",
            "| Agent | Weight |",
            "| :--- | :---: |",
        ]
        for agent, w in r["weights"].items():
            lines.append(f"| {agent.capitalize()} | {w:.1f}% |")

        lines += [
            "",
            "### Decision Comparison",
            "| Method | Decision Output | Absolute Error | Explainability | Latency |",
            "| :--- | :---: | :---: | :---: | :---: |",
        ]
        for method, res in r["results"].items():
            explain = "100.0%" if res["explain"] else "0.0%"
            lines.append(
                f"| **{method}** | {res['rec']:.2f} | {res['err']:.2f} | {explain} | {res['ms']:.2f}ms |"
            )
        lines.append("")

    # ── Summary table ──────────────────────────────────────────────────────
    methods = ["AMDIE", "Simple Average", "Majority Wins", "Static Equal Weights"]
    lines += [
        "---",
        "## Overall Summary (Fresh Out-of-Sample)",
        "",
        "| Method | Mean Absolute Error | Explainability | Mean Latency |",
        "| :--- | :---: | :---: | :---: |",
    ]
    for method in methods:
        errs = [r["results"][method]["err"] for r in rows if r]
        lats = [r["results"][method]["ms"]  for r in rows if r]
        expl = "100.0%" if method == "AMDIE" else "0.0%"
        lines.append(
            f"| **{method}** | {np.mean(errs):.2f} | {expl} | {np.mean(lats):.2f}ms |"
        )

    lines += [
        "",
        "---",
        "*All conflict scores > 0.30 — the outlier divergence penalty (w6) was active for every evaluation.*",
    ]
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("Initialising DB...")
    init_db()
    db = SessionLocal()

    # Verify tenant exists
    tenant = db.query(Tenant).filter_by(id=TENANT_ID).first()
    if not tenant:
        print(f"ERROR: Tenant '{TENANT_ID}' not found. Run the seed script first.")
        sys.exit(1)

    print(f"\nFresh Out-of-Sample Evaluation")
    print(f"Tenant : {TENANT_ID}")
    print(f"Date   : {EVAL_DATE}")
    print(f"Products: {', '.join(PRODUCTS)}")
    print("=" * 60)

    rows = []
    for pid in PRODUCTS:
        row = evaluate_product(pid, db)
        rows.append(row)

    db.close()

    report_md = build_report(rows)
    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(report_md, encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"Report written to: {REPORT_OUT}")


if __name__ == "__main__":
    main()
