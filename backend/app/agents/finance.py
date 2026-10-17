"""
Finance Agent
=============
Participates in several decision types; its liquidity view is projected onto
the axis of the decision being made.  Finance contributes two things:

  recommendation  its *preferred* value (a vote in AMDIE fusion)
  upper_limit     the hard affordability cap (an LP constraint, not a vote)

  reorder_quantity     prefers covering lead time + review period of demand net of
                       inventory position, scaled down when cash is tight; capped
                       at the max affordable quantity
  promotion_trigger    prefers half of the affordable discount depth; capped at
                       the depth whose 30-day cost fits in 10% of spendable funds
                       and never goes below unit cost
  staffing_adjustment  affordable change in daily staffing hours: positive when
                       cash exceeds the period budget, negative when it falls short
"""

import math
import numpy as np
from datetime import date, timedelta
from sqlalchemy.orm import Session
from backend.app.agents.base import BaseAgent, DecisionObject
from backend.app.retrieval import get_postgres_context, get_vector_context
from backend.app.config import settings


# Floor on the liquidity scaling of the reorder preference
_MIN_LIQUIDITY_FACTOR = 0.25
# Share of the affordable discount depth Finance prefers to commit (margin protection)
_PROMO_PREFERENCE_SHARE = 0.5
# Share of spendable funds a 30-day promotion may consume
_PROMO_BUDGET_SHARE = 0.10
_MAX_DISCOUNT_DEPTH = 0.40
# Hours of daily staffing change per unit of (cash / budget - 1), capped at ±_MAX_STAFF_DELTA
_STAFF_HOURS_PER_LIQUIDITY = 4.0
_MAX_STAFF_DELTA = 4.0


class FinanceAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="finance")

    def run(self, tenant_id: str, product_id: str, run_date: date, db: Session, decision_type: str = "reorder_quantity") -> DecisionObject:
        context = get_postgres_context(tenant_id, self.agent_id, product_id, run_date, db)
        product      = context["product"]
        ledger       = context["ledger"]
        sales_records = context["sales"]
        inventory    = context["inventory"]
        on_order     = context.get("on_order", 0)
        stock_level  = inventory.stock_level if inventory else 0

        unit_price = product.unit_price if product else 10.0
        unit_cost  = product.unit_cost  if product else 5.0

        cash_balance     = ledger.cash_balance     if ledger else 10_000.0
        budget_per_period = ledger.budget_per_period if ledger else  5_000.0

        eps = 1e-5
        lead_time = inventory.lead_time_days if inventory else 5
        avg_daily_qty = (
            sum(r.qty_sold for r in sales_records) / max(len({r.date for r in sales_records}), 1)
            if sales_records else 1.0
        )
        liquidity_ratio = cash_balance / max(budget_per_period, eps)

        # ── Reorder: prudent quantity, capped by affordability ────────────────
        max_by_cash   = math.floor(cash_balance     / unit_cost) if unit_cost > 0 else 0
        max_by_budget = math.floor(budget_per_period / unit_cost) if unit_cost > 0 else 0
        max_affordable = float(max(0, min(max_by_cash, max_by_budget)))
        liquidity_factor = float(np.clip(liquidity_ratio, _MIN_LIQUIDITY_FACTOR, 1.0))
        demand_cover = avg_daily_qty * (lead_time + settings.REORDER_REVIEW_PERIOD_DAYS)
        net_need = max(0.0, demand_cover - (stock_level + on_order))
        recommendation = round(min(max_affordable, net_need * liquidity_factor), 2)
        upper_limit = max_affordable

        # ── Raw cash-based confidence ─────────────────────────────────────────
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
        required_resources = {"cash": expected_cost}
        reason = (
            f"Finance Agent prefers ordering {recommendation:.0f} units (net demand cover {net_need:.0f}, "
            f"liquidity factor {liquidity_factor:.2f}) and caps orders at {max_affordable:.0f} affordable units "
            f"given cash balance of {cash_balance:.2f} and period budget of {budget_per_period:.2f}. "
            f"Demand uncertainty (CV={demand_uncertainty:.2f}) has been factored into confidence."
        )

        # ── Project onto non-reorder decision axes ────────────────────────────
        spendable = max(0.0, min(cash_balance, budget_per_period))
        if decision_type == "promotion_trigger":
            discount_cost_per_depth = unit_price * max(avg_daily_qty, eps) * 30
            affordable_depth = _PROMO_BUDGET_SHARE * spendable / discount_cost_per_depth
            margin_ratio = max(0.0, (unit_price - unit_cost) / max(unit_price, 0.01))
            upper_limit = round(float(np.clip(min(affordable_depth, margin_ratio), 0.0, _MAX_DISCOUNT_DEPTH)), 3)
            recommendation = round(upper_limit * _PROMO_PREFERENCE_SHARE, 3)
            expected_cost = recommendation * discount_cost_per_depth
            expected_benefit = 0.0
            required_resources = {"cash": expected_cost}
            reason = (
                f"Finance Agent prefers a discount depth of {recommendation:.1%} and caps it at {upper_limit:.1%}: "
                f"a 30-day promotion may use {_PROMO_BUDGET_SHARE:.0%} of spendable funds ({spendable:.2f}) "
                f"and must not go below unit cost (margin {margin_ratio:.1%})."
            )
        elif decision_type == "staffing_adjustment":
            upper_limit = None
            recommendation = round(float(np.clip(
                (liquidity_ratio - 1.0) * _STAFF_HOURS_PER_LIQUIDITY, -_MAX_STAFF_DELTA, _MAX_STAFF_DELTA
            )), 1)
            expected_cost = 0.0
            expected_benefit = 0.0
            required_resources = {}
            reason = (
                f"Finance Agent sets an affordable staffing change of {recommendation:+.1f} hours/day "
                f"(cash {cash_balance:.2f} vs period budget {budget_per_period:.2f}, "
                f"liquidity ratio {liquidity_ratio:.2f})."
            )

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
            reason=reason,
            confidence=confidence,
            priority=priority,
            risk_score=risk_score,
            expected_cost=expected_cost,
            expected_benefit=expected_benefit,
            required_resources=required_resources,
            historical_similarity=hist_sim,
            upper_limit=upper_limit,
        )
