import math
import numpy as np
from datetime import date, timedelta
from sqlalchemy.orm import Session
from backend.app.agents.base import BaseAgent, DecisionObject
from backend.app.retrieval import get_postgres_context, get_vector_context


class FinanceAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="finance")

    def run(self, tenant_id: str, product_id: str, run_date: date, db: Session) -> DecisionObject:
        context = get_postgres_context(tenant_id, self.agent_id, product_id, run_date, db)
        product      = context["product"]
        ledger       = context["ledger"]
        sales_records = context["sales"]

        unit_price = product.unit_price if product else 10.0
        unit_cost  = product.unit_cost  if product else 5.0

        cash_balance     = ledger.cash_balance     if ledger else 10_000.0
        budget_per_period = ledger.budget_per_period if ledger else  5_000.0

        # ── Recommendation: max affordable quantity ───────────────────────────
        max_by_cash   = math.floor(cash_balance     / unit_cost) if unit_cost > 0 else 0
        max_by_budget = math.floor(budget_per_period / unit_cost) if unit_cost > 0 else 0
        recommendation = float(max(0, min(max_by_cash, max_by_budget)))

        # ── Raw cash-based confidence ─────────────────────────────────────────
        eps = 1e-5
        cash_confidence = float(np.clip(cash_balance / (budget_per_period + eps), 0.0, 1.0))

        # ── Cross-confidence calibration (v2) ─────────────────────────────────
        # When demand is low or uncertain, Finance's pure cash-based confidence
        # is misleadingly high — it knows it can afford a lot, but it doesn't
        # know that buying a lot is the right decision.
        # We dampen Finance's confidence by demand volatility derived from recent
        # sales history so that an abundant cash position during a low-demand
        # period still produces moderate confidence rather than near-1.0.
        if sales_records and len(sales_records) > 1:
            qtys = [r.qty_sold for r in sales_records]
            mean_demand = max(float(np.mean(qtys)), eps)
            std_demand  = float(np.std(qtys))
            demand_cv   = std_demand / mean_demand          # coefficient of variation
            demand_uncertainty = float(np.clip(demand_cv, 0.0, 1.0))
        else:
            demand_uncertainty = 0.3   # conservative default when no sales data

        # Final confidence = cash confidence dampened by demand uncertainty
        confidence = float(np.clip(cash_confidence * (1.0 - demand_uncertainty), 0.01, 1.0))

        risk_score = 1.0 - confidence

        # Priority rises as cash approaches the budget threshold
        priority = float(np.clip(1.0 - (cash_balance / (2.0 * budget_per_period + eps)), 0.0, 1.0))

        expected_cost    = recommendation * unit_cost
        expected_benefit = recommendation * unit_price

        # ── Historical similarity from Vector DB ─────────────────────────────
        category  = product.category if product else "Electronics"
        prod_name = product.name     if product else "Product"
        vector_hits, _ = get_vector_context(
            tenant_id=tenant_id,
            agent_id=self.agent_id,
            product_name=prod_name,
            category=category,
            decision_type="finance",
            current_date=run_date,
            limit=1,
        )
        hist_sim = float(np.clip(vector_hits[0]["score"], 0.0, 1.0)) if vector_hits else 0.5

        return DecisionObject(
            agent_id=self.agent_id,
            recommendation=recommendation,
            reason=(
                f"Finance Agent recommends max budget-safe order of {recommendation:.0f} units "
                f"given cash balance of {cash_balance:.2f} and period budget of {budget_per_period:.2f}. "
                f"Demand uncertainty (CV={demand_uncertainty:.2f}) has been factored into confidence."
            ),
            confidence=confidence,
            priority=priority,
            risk_score=risk_score,
            expected_cost=expected_cost,
            expected_benefit=expected_benefit,
            required_resources={"cash": expected_cost},
            historical_similarity=hist_sim,
        )
