import numpy as np
from datetime import date
from sqlalchemy.orm import Session
from backend.app.agents.base import BaseAgent, DecisionObject
from backend.app.retrieval import get_postgres_context, get_vector_context
from backend.app.predictive import forecast_demand
from backend.app.db import StaffShift, Product, Tenant

class HRAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="hr")

    def run(self, tenant_id: str, product_id: str, run_date: date, db: Session, decision_type: str = "staffing_adjustment") -> DecisionObject:
        context = get_postgres_context(tenant_id, self.agent_id, product_id, run_date, db)
        product = context["product"]

        # 1. Forecast daily demand
        fc = forecast_demand(product_id=product_id, horizon_days=7, db=db, tenant_id=tenant_id, run_date=run_date)
        projected_daily_units = fc["daily_avg"]

        # 2. Check scheduled staff shifts for run_date
        shifts = db.query(StaffShift).filter(
            StaffShift.tenant_id == tenant_id,
            StaffShift.shift_date == run_date
        ).all()
        current_hours = sum(s.hours for s in shifts) if shifts else 8.0

        # Required hours rule of thumb: 1 staff hour per 15 projected units (minimum 4 hours base)
        required_hours = max(4.0, projected_daily_units / 15.0)

        # Recommendation = delta in staffing hours needed
        hours_delta = round(required_hours - current_hours, 1)
        recommendation = float(hours_delta)

        # Confidence & Risk
        confidence = float(np.clip(1.0 - (fc["std_error"] / (projected_daily_units + 10.0)), 0.5, 0.95))
        risk_score = float(np.clip(1.0 - confidence, 0.05, 0.5))

        # Priority rises when staffing gap is large
        priority = float(np.clip(abs(hours_delta) / 10.0, 0.2, 0.9))

        # Estimated labor cost rate $25/hr
        hourly_rate = 25.0
        expected_cost = max(0.0, hours_delta) * hourly_rate
        expected_benefit = max(0.0, hours_delta) * 40.0 # estimated productivity gain

        # Retrieve Vector context
        category = product.category if product else "General"
        prod_name = product.name if product else "Product"
        vector_hits, _ = get_vector_context(
            tenant_id=tenant_id,
            agent_id=self.agent_id,
            product_name=prod_name,
            category=category,
            decision_type="staffing_adjustment",
            current_date=run_date,
            limit=1
        )
        hist_sim = float(np.clip(vector_hits[0]["score"], 0.0, 1.0)) if vector_hits else 0.5

        reason = (
            f"HR Agent recommends a staffing adjustment of {recommendation:+.1f} hours on {run_date} "
            f"given projected daily demand of {projected_daily_units:.1f} units vs current shift capacity of {current_hours:.1f} hours."
        )

        return DecisionObject(
            agent_id=self.agent_id,
            recommendation=recommendation,
            reason=reason,
            confidence=confidence,
            priority=priority,
            risk_score=risk_score,
            expected_cost=expected_cost,
            expected_benefit=expected_benefit,
            required_resources={"staff_hours": abs(recommendation)},
            historical_similarity=hist_sim
        )
