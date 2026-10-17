"""
Sales Agent
===========
Participates in several decision types, so its demand view is projected onto
the axis of the decision being made (see decision_registry.DECISION_TYPE_AXIS):

  reorder_quantity           units to order = forecast over lead time + review period
                             + safety buffer - inventory position (on hand + on order)
  price_adjustment           price delta: rising demand supports a raise, falling
                             demand argues for a cut (±10% of price max)
  staffing_adjustment        staffing hours delta needed to cover peak demand
                             (forecast + 1 std error) at 15 units per staff hour
  customer_retention_action  retention level [0, 1]: grows as demand declines
"""

import numpy as np
from datetime import date, timedelta
from sqlalchemy.orm import Session
from backend.app.agents.base import BaseAgent, DecisionObject
from backend.app.retrieval import get_postgres_context, get_vector_context
from backend.app.predictive import forecast_demand
from backend.app.db import StaffShift
from backend.app.config import settings

# Price response to demand trend: delta = price * clip(_TREND_PRICE_GAIN * growth, ±_MAX_TREND_PRICE_STEP)
_TREND_PRICE_GAIN = 0.5
_MAX_TREND_PRICE_STEP = 0.10
# Same staffing productivity assumption as the HR Agent
_UNITS_PER_STAFF_HOUR = 15.0
_MIN_STAFF_HOURS = 4.0
_DEFAULT_SCHEDULED_HOURS = 8.0


class SalesAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="sales")

    def run(self, tenant_id: str, product_id: str, run_date: date, db: Session, decision_type: str = "reorder_quantity") -> DecisionObject:
        # Retrieve context from retrieval manager
        context = get_postgres_context(tenant_id, self.agent_id, product_id, run_date, db)
        product = context["product"]
        inventory = context["inventory"]
        sales_records = context["sales"]
        on_order = context.get("on_order", 0)
        stock_level = inventory.stock_level if inventory else 0

        unit_price = product.unit_price if product else 10.0
        unit_cost = product.unit_cost if product else 5.0
        lead_time = inventory.lead_time_days if inventory else 5

        # 1. Forecast demand over the protection interval (lead time + review period)
        horizon = lead_time + settings.REORDER_REVIEW_PERIOD_DAYS
        fc = forecast_demand(product_id=product_id, horizon_days=horizon, db=db, tenant_id=tenant_id, run_date=run_date)
        forecast_val = fc["forecast_total"]
        std_error = fc["std_error"]

        # 2. Reorder recommendation: order-up-to target minus inventory position
        # Safety buffer = 1.0 * std_error * sqrt(horizon)
        safety_buffer = 1.0 * std_error * np.sqrt(horizon)
        target_level = forecast_val + safety_buffer
        position = stock_level + on_order
        reorder_qty = max(0.0, round(target_level - position, 2))

        # 3. Confidence & Risk metrics (relative to the demand forecast, not the net order)
        error_margin = 1.96 * std_error * np.sqrt(horizon)
        interval_width = error_margin * 2

        denom = target_level if target_level > 0 else 1.0
        confidence = 1.0 - min(interval_width / (denom * 2), 1.0)
        confidence = max(0.0, min(1.0, float(confidence)))
        risk_score = 1.0 - confidence

        # 4. Priority based on daily forecast level vs average
        priority = max(0.0, min(1.0, float(fc["daily_avg"] / (fc["daily_avg"] + 10.0))))

        # 5. Demand trend: forecast daily rate vs trailing 30-day actual rate
        start_30 = run_date - timedelta(days=30)
        recent_qty = sum(r.qty_sold for r in sales_records if r.date >= start_30)
        hist_daily = recent_qty / 30.0
        growth = (fc["daily_avg"] - hist_daily) / max(hist_daily, 1.0)

        # 6. Project onto the decision axis
        if decision_type == "price_adjustment":
            step = float(np.clip(_TREND_PRICE_GAIN * growth, -_MAX_TREND_PRICE_STEP, _MAX_TREND_PRICE_STEP))
            recommendation = round(unit_price * step, 2)
            expected_cost = 0.0
            expected_benefit = recommendation * fc["daily_avg"] * 30
            required_resources = {}
            reason = (
                f"Sales Agent sees a demand trend of {growth:+.1%} (forecast {fc['daily_avg']:.2f}/day vs "
                f"trailing {hist_daily:.2f}/day) and recommends a price delta of {recommendation:+.2f}."
            )
        elif decision_type == "staffing_adjustment":
            peak_daily_units = fc["daily_avg"] + std_error
            required_hours = max(_MIN_STAFF_HOURS, peak_daily_units / _UNITS_PER_STAFF_HOUR)
            shifts = db.query(StaffShift).filter(
                StaffShift.tenant_id == tenant_id,
                StaffShift.shift_date == run_date,
            ).all()
            current_hours = sum(s.hours for s in shifts) if shifts else _DEFAULT_SCHEDULED_HOURS
            recommendation = round(required_hours - current_hours, 1)
            expected_cost = 0.0
            expected_benefit = 0.0
            required_resources = {"staff_hours": abs(recommendation)}
            reason = (
                f"Sales Agent sizes staffing for peak demand of {peak_daily_units:.1f} units/day "
                f"({required_hours:.1f}h needed vs {current_hours:.1f}h scheduled): "
                f"{recommendation:+.1f} hours."
            )
        elif decision_type == "customer_retention_action":
            decline = max(0.0, -growth)
            recommendation = round(float(np.clip(0.05 + 0.5 * decline, 0.0, 0.40)), 3)
            expected_cost = recommendation * unit_price * 10.0
            expected_benefit = expected_cost * 2.0
            required_resources = {}
            reason = (
                f"Sales Agent sees a demand trend of {growth:+.1%} and recommends a retention "
                f"level of {recommendation:.1%} to protect repeat purchases."
            )
        else:
            recommendation = reorder_qty
            expected_cost = recommendation * unit_cost
            expected_benefit = recommendation * unit_price
            required_resources = {"cash": expected_cost}
            reason = (
                f"Sales Agent recommends ordering {recommendation} units: {horizon}-day demand forecast "
                f"{forecast_val:.2f} + safety stock {safety_buffer:.2f}, less inventory position {position} "
                f"(on hand {stock_level} + on order {on_order})."
            )

        # 7. Retrieve Vector DB knowledge
        category = product.category if product else "Electronics"
        prod_name = product.name if product else "Product"
        vector_hits, query_text = get_vector_context(
            tenant_id=tenant_id,
            agent_id=self.agent_id,
            product_name=prod_name,
            category=category,
            decision_type="sales",
            current_date=run_date,
            limit=1
        )

        hist_sim = 0.5
        if vector_hits:
            hist_sim = max(0.0, min(1.0, float(vector_hits[0]["score"])))

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
            historical_similarity=hist_sim
        )
