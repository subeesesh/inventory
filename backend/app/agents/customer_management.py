import numpy as np
from datetime import date, timedelta
from sqlalchemy.orm import Session
from backend.app.agents.base import BaseAgent, DecisionObject
from backend.app.retrieval import get_postgres_context, get_vector_context
from backend.app.db import Customer, Sale, InventoryState, StockMovement, Product

class CustomerManagementAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="customer_management")

    def run(self, tenant_id: str, product_id: str, run_date: date, db: Session, decision_type: str = "customer_retention_action") -> DecisionObject:
        context = get_postgres_context(tenant_id, self.agent_id, product_id, run_date, db)
        product = context["product"]
        inventory = context["inventory"]

        stock_level = inventory.stock_level if inventory else 10
        min_stock = product.min_stock if product and product.min_stock is not None else 5

        # Check total active customers for tenant
        customer_count = db.query(Customer).filter_by(tenant_id=tenant_id).count()

        # Check shortage signal
        is_shortage = stock_level <= min_stock

        # Calculate retention action score (fraction [0.0, 1.0])
        if is_shortage:
            # Proactively notify and offer retention incentive (e.g. 15% discount / priority reservation)
            retention_action = 0.15
            reason = (
                f"Customer Management Agent recommends proactive customer shortage notification "
                f"and a {retention_action*100:.0f}% retention discount due to low stock level ({stock_level} <= min {min_stock})."
            )
            confidence = 0.85
            priority = 0.8
        else:
            # Regular churn prevention check
            retention_action = 0.05
            reason = (
                f"Customer Management Agent recommends a standard {retention_action*100:.0f}% retention engagement "
                f"for {customer_count} registered customer accounts."
            )
            confidence = 0.70
            priority = 0.4

        unit_price = product.unit_price if product else 10.0
        expected_cost = retention_action * unit_price * 10.0
        expected_benefit = expected_cost * 2.5 # Customer lifetime value preservation

        # Vector context
        category = product.category if product else "General"
        prod_name = product.name if product else "Product"
        vector_hits, _ = get_vector_context(
            tenant_id=tenant_id,
            agent_id=self.agent_id,
            product_name=prod_name,
            category=category,
            decision_type="customer_retention_action",
            current_date=run_date,
            limit=1
        )
        hist_sim = float(np.clip(vector_hits[0]["score"], 0.0, 1.0)) if vector_hits else 0.5

        return DecisionObject(
            agent_id=self.agent_id,
            recommendation=float(round(retention_action, 2)),
            reason=reason,
            confidence=confidence,
            priority=priority,
            risk_score=float(round(1.0 - confidence, 2)),
            expected_cost=float(round(expected_cost, 2)),
            expected_benefit=float(round(expected_benefit, 2)),
            required_resources={"marketing_budget": expected_cost},
            historical_similarity=hist_sim
        )
