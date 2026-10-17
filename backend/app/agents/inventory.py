from datetime import date
import numpy as np
from sqlalchemy.orm import Session
from backend.app.agents.base import BaseAgent, DecisionObject
from backend.app.retrieval import get_postgres_context, get_vector_context
from backend.app.config import settings

class InventoryAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="inventory")

    def run(self, tenant_id: str, product_id: str, run_date: date, db: Session, decision_type: str = "reorder_quantity") -> DecisionObject:
        context = get_postgres_context(tenant_id, self.agent_id, product_id, run_date, db)
        product = context["product"]
        inventory = context["inventory"]
        sales_records = context["sales"]
        on_order = context.get("on_order", 0)

        unit_price = product.unit_price if product else 10.0
        unit_cost = product.unit_cost if product else 5.0

        stock_level = inventory.stock_level if inventory else 0
        reorder_point = inventory.reorder_point if inventory else 50
        lead_time = inventory.lead_time_days if inventory else 5

        # Calculate average daily sales over the retrieved 90-day history
        if sales_records:
            total_qty = sum(r.qty_sold for r in sales_records)
            # Find unique dates to divide by
            unique_dates = len(set(r.date for r in sales_records))
            avg_daily_sales = total_qty / max(unique_dates, 1)
        else:
            avg_daily_sales = 2.0

        forecasted_demand = avg_daily_sales * (lead_time + settings.REORDER_REVIEW_PERIOD_DAYS)

        # Reorder-point rule on inventory position (on-hand + on-order), so stock
        # already in transit is not ordered twice
        position = stock_level + on_order
        if position < reorder_point:
            recommendation = float((reorder_point - position) + forecasted_demand)
            recommendation = max(0.0, round(recommendation, 2))
        else:
            recommendation = 0.0

        # Calculate runway (days of stock remaining)
        eps = 1e-5
        days_of_stock_remaining = stock_level / (avg_daily_sales + eps)
        
        # Confidence increases as runway shrinks relative to lead time
        confidence = 1.0 - (days_of_stock_remaining / (lead_time + eps))
        confidence = float(np.clip(confidence, 0.0, 1.0))

        # Risk of stockout: high when stock level is below reorder point
        risk_score = 1.0 - (stock_level / (reorder_point + eps))
        risk_score = float(np.clip(risk_score, 0.0, 1.0))

        # Priority is driven directly by stockout risk
        priority = risk_score

        expected_cost = recommendation * unit_cost
        expected_benefit = recommendation * unit_price

        # Retrieve Vector DB knowledge to calculate historical similarity
        category = product.category if product else "Electronics"
        prod_name = product.name if product else "Product"
        vector_hits, _ = get_vector_context(
            tenant_id=tenant_id,
            agent_id=self.agent_id,
            product_name=prod_name,
            category=category,
            decision_type="inventory",
            current_date=run_date,
            limit=1
        )
        
        hist_sim = 0.5
        if vector_hits:
            hist_sim = max(0.0, min(1.0, float(vector_hits[0]["score"])))

        return DecisionObject(
            agent_id=self.agent_id,
            recommendation=recommendation,
            reason=(
                f"Inventory Agent recommends ordering {recommendation} units: inventory position "
                f"{position} (on hand {stock_level} + on order {on_order}) vs reorder point {reorder_point}, "
                f"{days_of_stock_remaining:.1f} days of stock on hand."
            ),
            confidence=confidence,
            priority=priority,
            risk_score=risk_score,
            expected_cost=expected_cost,
            expected_benefit=expected_benefit,
            required_resources={"cash": expected_cost},
            historical_similarity=hist_sim
        )
