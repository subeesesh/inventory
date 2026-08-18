"""
Risk Agent  (meta-agent — NOT a fusion participant)
====================================================
The Risk Agent does NOT emit a DecisionObject and does NOT participate in any
AMDIE LP fusion cycle.  It is a post-processing modifier called inside goals.py
when tenant.business_goal == "minimize_risk".

It computes an `overall_risk_score` by aggregating:
  1. Agent-level risk_score fields from all participating DecisionObjects.
  2. Seasonality volatility (coefficient of variation of daily sales).
  3. Supplier concentration (HHI-based, from Supplier table).

The overall_risk_score is passed back to adjust_objective_for_goals(), which
uses it to further scale down all agent weights — pushing the LP toward the
conservative end of each agent's utility triangle.
"""

from datetime import date, timedelta
from typing import Dict
import numpy as np
from sqlalchemy.orm import Session

from backend.app.agents.base import DecisionObject
from backend.app.db import SalesRecord, Supplier
from backend.app.amdie.goals import compute_seasonality_volatility, compute_supplier_concentration


# Weight decomposition of the three risk signals
_W_AGENT_RISK        = 0.50   # individual agent risk_scores
_W_SEASONALITY       = 0.25   # demand volatility
_W_CONCENTRATION     = 0.25   # supplier concentration


class RiskAgent:
    """
    Meta-agent: produces a single `overall_risk_score` float, not a DecisionObject.
    Instantiate once and call `compute_overall_risk()` after all domain agents
    have produced their DecisionObjects.
    """

    def compute_overall_risk(
        self,
        tenant_id: str,
        product_id: str,
        run_date: date,
        decisions: Dict[str, DecisionObject],
        db: Session,
    ) -> float:
        """
        Returns overall_risk_score ∈ [0, 1].

        Raises no exceptions — returns 0.5 (neutral) on any data error so that
        the main pipeline is never blocked by the risk agent.
        """
        try:
            # ── 1. Agent aggregate risk ───────────────────────────────────
            if decisions:
                agent_risks = [d.risk_score for d in decisions.values()]
                # Use the 75th-percentile agent risk (not mean) to be sensitive
                # to one high-risk agent even if others are low-risk.
                agent_aggregate = float(np.percentile(agent_risks, 75))
            else:
                agent_aggregate = 0.5

            # ── 2. Seasonality / demand volatility ────────────────────────
            start_90 = run_date - timedelta(days=90)
            sales_records = db.query(SalesRecord).filter(
                SalesRecord.tenant_id == tenant_id,
                SalesRecord.product_id == product_id,
                SalesRecord.date >= start_90,
                SalesRecord.date <= run_date,
            ).all()
            seasonality_vol = compute_seasonality_volatility(sales_records)

            # ── 3. Supplier concentration ─────────────────────────────────
            suppliers = db.query(Supplier).filter_by(
                tenant_id=tenant_id, product_id=product_id
            ).all()
            supplier_conc = compute_supplier_concentration(suppliers)

            # ── 4. Weighted aggregate ─────────────────────────────────────
            overall = (
                _W_AGENT_RISK    * agent_aggregate
                + _W_SEASONALITY * seasonality_vol
                + _W_CONCENTRATION * supplier_conc
            )
            return float(np.clip(overall, 0.0, 1.0))

        except Exception as exc:
            print(f"[RiskAgent] Error computing overall risk: {exc}. Returning neutral 0.5.")
            return 0.5

    def get_risk_breakdown(
        self,
        tenant_id: str,
        product_id: str,
        run_date: date,
        decisions: Dict[str, DecisionObject],
        db: Session,
    ) -> dict:
        """
        Returns a detailed breakdown dict for explainability traces.
        Safe to call independently of compute_overall_risk.
        """
        try:
            start_90 = run_date - timedelta(days=90)
            sales_records = db.query(SalesRecord).filter(
                SalesRecord.tenant_id == tenant_id,
                SalesRecord.product_id == product_id,
                SalesRecord.date >= start_90,
                SalesRecord.date <= run_date,
            ).all()
            suppliers = db.query(Supplier).filter_by(
                tenant_id=tenant_id, product_id=product_id
            ).all()

            agent_risks = {k: v.risk_score for k, v in decisions.items()}
            seasonality = compute_seasonality_volatility(sales_records)
            concentration = compute_supplier_concentration(suppliers)

            return {
                "agent_risk_scores":       agent_risks,
                "seasonality_volatility":  seasonality,
                "supplier_concentration":  concentration,
                "n_suppliers":             len(suppliers),
                "n_sales_observations":    len(sales_records),
            }
        except Exception as exc:
            return {"error": str(exc)}
