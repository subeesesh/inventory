"""
Marketing Agent  (decision_type: promotion_trigger)
====================================================
recommendation = suggested discount depth [0.0, 1.0] (fraction of unit_price)
                 to apply to slow-moving stock.

Algorithm:
  - Compute turnover_rate = avg daily qty_sold / stock_level.
  - Compare against a rolling median across all products to identify slow-movers.
  - Discount depth is proportional to how far below median the turnover is.
  - confidence = scales with the number of turnover-rate observations available
    (more history = higher confidence).
  - risk_score = margin impact: clamp(discount_depth * (1 - margin_ratio), 0, 1).
  - priority = clamp(1 / max(turnover_rate, 0.01), 0, 1) — inverse of turnover
    (slow stock = most urgent).
"""

from datetime import date, timedelta
import numpy as np
from sqlalchemy.orm import Session

from backend.app.agents.base import BaseAgent, DecisionObject
from backend.app.db import SalesRecord, InventoryState, Product
from backend.app.retrieval import get_vector_context

# Threshold below which a product is considered "slow-moving" relative to peers
_SLOW_MOVER_PERCENTILE = 0.25   # bottom quartile of turnover rates
# Maximum discount depth recommended in a single cycle
_MAX_DISCOUNT_DEPTH = 0.40
# Minimum observations before confidence is high
_CONF_SCALING_MAX_DAYS = 90


class MarketingAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="marketing")

    def run(
        self,
        tenant_id: str,
        product_id: str,
        run_date: date,
        db: Session,
    ) -> DecisionObject:

        # ── 1. Retrieve product + inventory + 90-day sales ────────────────
        product = db.query(Product).filter_by(
            tenant_id=tenant_id, id=product_id
        ).first()

        current_price = product.unit_price if product else 10.0
        unit_cost = product.unit_cost if product else 5.0
        margin_ratio = (current_price - unit_cost) / max(current_price, 0.01)

        inventory = db.query(InventoryState).filter_by(
            tenant_id=tenant_id, product_id=product_id
        ).first()
        stock_level = inventory.stock_level if inventory else 50

        start_90 = run_date - timedelta(days=90)
        records = db.query(SalesRecord).filter(
            SalesRecord.tenant_id == tenant_id,
            SalesRecord.product_id == product_id,
            SalesRecord.date >= start_90,
            SalesRecord.date <= run_date,
        ).all()

        # ── 2. Compute this product's turnover rate ────────────────────────
        n_days = len(set(r.date for r in records)) if records else 1
        total_qty = sum(r.qty_sold for r in records)
        avg_daily_qty = total_qty / max(n_days, 1)
        turnover_rate = avg_daily_qty / max(stock_level, 1)

        # ── 3. Compute discount depth based on turnover gap ────────────────
        # Fetch peer turnover rates for this tenant to contextualise slow-mover status
        all_inv = db.query(InventoryState).filter_by(tenant_id=tenant_id).all()
        peer_turnover_rates = []
        for inv_item in all_inv:
            if inv_item.product_id == product_id:
                continue
            peer_records = db.query(SalesRecord).filter(
                SalesRecord.tenant_id == tenant_id,
                SalesRecord.product_id == inv_item.product_id,
                SalesRecord.date >= start_90,
                SalesRecord.date <= run_date,
            ).count()
            if peer_records > 0:
                peer_total = db.query(SalesRecord).filter(
                    SalesRecord.tenant_id == tenant_id,
                    SalesRecord.product_id == inv_item.product_id,
                    SalesRecord.date >= start_90,
                    SalesRecord.date <= run_date,
                ).all()
                peer_avg_daily = sum(r.qty_sold for r in peer_total) / max(
                    len(set(r.date for r in peer_total)), 1
                )
                peer_tr = peer_avg_daily / max(inv_item.stock_level, 1)
                peer_turnover_rates.append(peer_tr)

        if peer_turnover_rates:
            # Relative slowness: how much below the p25 threshold
            threshold = float(np.percentile(peer_turnover_rates, 25)) if len(peer_turnover_rates) >= 4 else float(np.median(peer_turnover_rates))
            slowness_gap = max(0.0, threshold - turnover_rate)
            # Discount depth proportional to the gap, normalised by threshold
            raw_discount = (slowness_gap / max(threshold, 1e-6)) * _MAX_DISCOUNT_DEPTH
        else:
            # No peer data — use absolute threshold: turnover < 0.05 triggers max discount
            raw_discount = _MAX_DISCOUNT_DEPTH * max(0.0, 1.0 - turnover_rate / 0.05)

        discount_depth = float(np.clip(raw_discount, 0.0, _MAX_DISCOUNT_DEPTH))

        # ── 4. Score fields ────────────────────────────────────────────────
        # Confidence: scales with data availability (90 days = max confidence)
        confidence = float(np.clip(n_days / _CONF_SCALING_MAX_DAYS, 0.0, 1.0))

        # Risk: margin erosion from the discount
        risk_score = float(np.clip(discount_depth * (1.0 - margin_ratio), 0.0, 1.0))

        # Priority: inverse of turnover — slowest stock = highest priority
        priority = float(np.clip(1.0 / max(turnover_rate, 0.01) / 100.0, 0.0, 1.0))

        expected_cost = 0.0  # promotion cost model — simplified to margin impact
        expected_benefit = avg_daily_qty * current_price * discount_depth * 1.5 * 30
        # (1.5 = estimated lift factor from discount)

        # ── 5. Vector context ────────────────────────────────────────────
        category = product.category if product else "General"
        prod_name = product.name if product else "Product"
        vector_hits, _ = get_vector_context(
            tenant_id=tenant_id,
            agent_id=self.agent_id,
            product_name=prod_name,
            category=category,
            decision_type="promotion_trigger",
            current_date=run_date,
            limit=1,
        )
        hist_sim = float(vector_hits[0]["score"]) if vector_hits else 0.5
        hist_sim = float(np.clip(hist_sim, 0.0, 1.0))

        reason = (
            f"Marketing Agent: product turnover rate = {turnover_rate:.4f} units/unit-stock/day "
            f"(based on {n_days} days of sales data, {total_qty} units sold, stock = {stock_level}). "
            f"Recommending discount depth of {discount_depth:.1%} "
            f"(margin ratio: {margin_ratio:.1%}, risk of margin erosion: {risk_score:.1%}). "
            f"Priority score: {priority:.3f} (higher = slower-moving stock)."
        )

        return DecisionObject(
            agent_id=self.agent_id,
            recommendation=discount_depth,
            reason=reason,
            confidence=confidence,
            priority=priority,
            risk_score=risk_score,
            expected_cost=expected_cost,
            expected_benefit=float(expected_benefit),
            required_resources={},
            historical_similarity=hist_sim,
        )
