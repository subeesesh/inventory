"""
Procurement Agent  (decision_type: reorder_quantity)
=====================================================
Joins the existing Inventory / Sales / Finance agents in the reorder_quantity
AMDIE cycle.  Unlike the Inventory Agent (which uses a fixed lead_time_days),
the Procurement Agent models *supplier lead-time uncertainty* via the Supplier
table and recommends an order quantity that accounts for variability.

recommendation = quantity to order, accounting for lead-time variance:
    demand_during_lead_time_mean   = avg_daily_sales * avg_lead_time_days
    demand_during_lead_time_stddev = avg_daily_sales * lead_time_std_dev
    safety_stock = z * sqrt(demand_during_lead_time_stddev²)
                     where z ≈ 1.65 (95th percentile service level)
    recommendation = max(min_order_qty, demand_during_lead_time_mean + safety_stock)

confidence = clamp(1 - lead_time_std_dev / avg_lead_time_days, 0, 1)
risk_score  = clamp(1 - reliability_score, 0, 1)
priority    = rises when Inventory Agent risk is high AND min_order_qty
              exceeds what Finance can currently afford.

INTENTIONAL CONFLICT: because this agent adds safety-stock on top of the mean
demand, it will recommend more than the Inventory Agent (which uses fixed lead
times) whenever lead-time variance is high.  Do NOT suppress this conflict —
it is the information signal the system is designed to surface.
"""

from datetime import date, timedelta
import numpy as np
from sqlalchemy.orm import Session

from backend.app.agents.base import BaseAgent, DecisionObject
from backend.app.config import settings
from backend.app.db import (
    SalesRecord, InventoryState, FinanceLedger, Product, Supplier
)
from backend.app.retrieval import get_postgres_context, get_vector_context, get_graph_context

# Service-level Z-score (95th percentile → z = 1.645)
_SERVICE_LEVEL_Z = 1.645


class ProcurementAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="procurement")

    def run(
        self,
        tenant_id: str,
        product_id: str,
        run_date: date,
        db: Session,
        decision_type: str = "reorder_quantity",
    ) -> DecisionObject:

        # ── 1. Base context (reuses existing retrieval function) ──────────
        context = get_postgres_context(tenant_id, self.agent_id, product_id, run_date, db)
        product   = context["product"]
        inventory = context["inventory"]
        sales     = context["sales"]
        ledger    = context["ledger"]
        on_order  = context.get("on_order", 0)

        current_price = product.unit_price if product else 10.0
        unit_cost = product.unit_cost if product else 5.0
        stock_level = inventory.stock_level if inventory else 0
        reorder_point = inventory.reorder_point if inventory else 50

        # ── 2. Supplier profile (graph context or flat SQL fallback) ───────
        supplier = self._get_best_supplier(tenant_id, product_id, db, run_date)

        avg_lead_time = supplier.avg_lead_time_days if supplier else 7.0
        lead_time_std = supplier.lead_time_std_dev if supplier else 2.0
        reliability   = supplier.reliability_score if supplier else 0.85
        min_order_qty = supplier.min_order_qty if supplier else 10

        # ── 3. Demand statistics from sales history ────────────────────────
        if sales:
            unique_dates = len(set(r.date for r in sales))
            total_qty = sum(r.qty_sold for r in sales)
            avg_daily_sales = total_qty / max(unique_dates, 1)
            daily_std = float(np.std([r.qty_sold for r in sales]))
        else:
            avg_daily_sales = 2.0
            daily_std = 1.0

        # ── 4. Recommendation: demand + safety stock for lead-time variance ─
        protection = avg_lead_time + settings.REORDER_REVIEW_PERIOD_DAYS
        mean_demand_lt = avg_daily_sales * protection

        # Combined variance: demand variance over the protection interval + lead-time variance in demand
        # σ²_combined = (L + R) * σ²_daily + (avg_daily)² * σ²_lead_time
        variance_combined = (
            protection * (daily_std ** 2)
            + (avg_daily_sales ** 2) * (lead_time_std ** 2)
        )
        safety_stock = _SERVICE_LEVEL_Z * float(np.sqrt(max(variance_combined, 0.0)))

        # Order-up-to on inventory position; the supplier MOQ applies only when ordering at all
        position = stock_level + on_order
        raw_recommendation = mean_demand_lt + safety_stock - position
        recommendation = float(max(min_order_qty, raw_recommendation)) if raw_recommendation > 0 else 0.0

        # ── 5. Score fields ────────────────────────────────────────────────
        confidence = float(np.clip(
            1.0 - (lead_time_std / max(avg_lead_time, 1.0)), 0.0, 1.0
        ))
        risk_score = float(np.clip(1.0 - reliability, 0.0, 1.0))

        # Priority rises when stock is dangerously low AND min_order_qty exceeds budget
        inv_risk = 1.0 - (stock_level / max(reorder_point, 1))
        inv_risk = float(np.clip(inv_risk, 0.0, 1.0))

        budget = ledger.budget_per_period if ledger else 5000.0
        affordable_qty = budget / max(unit_cost, 0.01)
        budget_squeeze = float(np.clip(min_order_qty / max(affordable_qty, 1.0), 0.0, 1.0))

        priority = float(np.clip(inv_risk * (0.5 + 0.5 * budget_squeeze), 0.0, 1.0))

        expected_cost = recommendation * unit_cost
        expected_benefit = recommendation * current_price

        # ── 6. Vector context ────────────────────────────────────────────
        category = product.category if product else "General"
        prod_name = product.name if product else "Product"
        vector_hits, _ = get_vector_context(
            tenant_id=tenant_id,
            agent_id=self.agent_id,
            product_name=prod_name,
            category=category,
            decision_type="reorder_quantity",
            current_date=run_date,
            limit=1,
        )
        hist_sim = float(vector_hits[0]["score"]) if vector_hits else 0.5
        hist_sim = float(np.clip(hist_sim, 0.0, 1.0))

        reason = (
            f"Procurement Agent: supplier avg lead time = {avg_lead_time:.1f} days "
            f"(std dev = {lead_time_std:.1f} days, reliability = {reliability:.2f}). "
            f"Mean demand during lead time = {mean_demand_lt:.1f} units; "
            f"safety stock (95th pct service level) = {safety_stock:.1f} units. "
            f"Inventory position = {position} (on hand {stock_level} + on order {on_order}). "
            f"Min order qty constraint = {min_order_qty} units. "
            f"Recommended order = {recommendation:.1f} units. "
            f"Note: this recommendation intentionally differs from the Inventory Agent "
            f"when lead-time variance is high — that conflict is by design."
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
            required_resources={"cash": expected_cost, "min_order_qty": min_order_qty},
            historical_similarity=hist_sim,
        )

    def _get_best_supplier(
        self, tenant_id: str, product_id: str, db: Session, run_date: date
    ) -> Supplier | None:
        """
        Return the best supplier for this product:
        - Tries graph context first (when Neo4j is enabled).
        - Falls back to flat Postgres Supplier query.
        - 'Best' = highest reliability_score among available suppliers.
        """
        # Graph context (no-op when NEO4J_ENABLED=False)
        try:
            graph_suppliers = get_graph_context(
                tenant_id=tenant_id,
                agent_id=self.agent_id,
                query=f"MATCH (s:Supplier)-[:SUPPLIES]->(p:Product {{id: '{product_id}', tenant_id: '{tenant_id}'}}) RETURN s",
                db=db,
                run_date=run_date,
            )
            # graph_context returns raw dicts when enabled — not ORM objects
            # If it returns data, convert to a lightweight namespace for scoring
            if graph_suppliers:
                # Pick the one with the highest reliability
                best = max(graph_suppliers, key=lambda s: s.get("reliability_score", 0.0))
                return _SupplierProxy(best)
        except Exception:
            pass  # Graph not enabled or query failed — fall through to Postgres

        # Flat Postgres fallback
        suppliers = db.query(Supplier).filter_by(
            tenant_id=tenant_id, product_id=product_id
        ).all()
        if not suppliers:
            return None
        return max(suppliers, key=lambda s: s.reliability_score)


class _SupplierProxy:
    """Thin namespace to expose Supplier-like attributes from graph dict results."""
    def __init__(self, d: dict):
        self.avg_lead_time_days = d.get("avg_lead_time_days", 7.0)
        self.lead_time_std_dev  = d.get("lead_time_std_dev", 2.0)
        self.reliability_score  = d.get("reliability_score", 0.85)
        self.min_order_qty      = int(d.get("min_order_qty", 10))
