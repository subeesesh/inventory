"""
Counterfactual 'What-If' Scenario Simulator
=============================================
BizTwin AI scenario simulation engine (§III-G).
Performs isolated in-memory counterfactual simulations over hypothetical parameter
adjustments (price change, supplier delay, demand shock, staffing change).
Reads current business state from the DB, builds a pure in-memory trajectory, then
re-applies the predictive models under the hypothetical parameters — guaranteeing
ZERO mutation to any production database row or table. No database cloning occurs.

When a product_id is given, the shock is applied only to that product's share of
revenue; the rest of the business follows its baseline.  Every result carries an
`assumptions` block so the owner can judge the scenario before acting (§V-D).
"""

from datetime import date, timedelta
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.db import SalesRecord, StaffShift
from backend.app.predictive import forecast_demand, forecast_revenue, forecast_cash_flow

# Used when the product's own price history can't support an elasticity estimate
_DEFAULT_ELASTICITY = -1.2
# Same labour rate the HR Agent uses
_HOURLY_LABOR_RATE = 25.0
_DEFAULT_DAILY_STAFF_HOURS = 8.0
# A supplier delay can at most wipe out half the horizon's sales
_MAX_LOST_SALES_FRACTION = 0.5


class ScenarioSimulateRequest(BaseModel):
    type: str = Field(..., description="Scenario type: price_change, supplier_delay, demand_shock, staffing_change")
    product_id: Optional[str] = Field(None, description="Target product ID")
    delta_pct: Optional[float] = Field(0.0, description="Percentage delta e.g. +0.10 for +10%")
    delay_days: Optional[int] = Field(0, description="Supplier delay days")
    horizon_days: Optional[int] = Field(30, description="Simulation horizon in days")


def _product_revenue(product_id: str, tenant_id: str, horizon: int, db: Session, run_date: date) -> float:
    """Projected revenue of one product over the horizon (trailing 30-day run rate)."""
    start = run_date - timedelta(days=30)
    rows = db.query(SalesRecord).filter(
        SalesRecord.tenant_id == tenant_id,
        SalesRecord.product_id == product_id,
        SalesRecord.date >= start,
        SalesRecord.date <= run_date,
    ).all()
    return sum(r.qty_sold * r.price for r in rows) / 30.0 * horizon


def _estimate_elasticity(product_id: Optional[str], tenant_id: str, db: Session, run_date: date) -> tuple[float, str]:
    if product_id:
        from backend.app.agents.pricing import PricingAgent
        rows = db.query(SalesRecord).filter(
            SalesRecord.tenant_id == tenant_id,
            SalesRecord.product_id == product_id,
            SalesRecord.date >= run_date - timedelta(days=180),
            SalesRecord.date <= run_date,
            SalesRecord.price > 0,
            SalesRecord.qty_sold > 0,
        ).all()
        elasticity, r2, _ = PricingAgent()._estimate_elasticity_and_delta(rows, 1.0, 0.0)
        if elasticity < 0 and r2 > 0:
            return elasticity, f"estimated from {len(rows)} days of price/quantity history (R²={r2:.2f})"
    return _DEFAULT_ELASTICITY, "default (insufficient price variation to estimate)"


def _daily_staff_hours(tenant_id: str, db: Session, run_date: date) -> float:
    shifts = db.query(StaffShift).filter(
        StaffShift.tenant_id == tenant_id,
        StaffShift.shift_date >= run_date - timedelta(days=30),
        StaffShift.shift_date <= run_date,
    ).all()
    if not shifts:
        return _DEFAULT_DAILY_STAFF_HOURS
    days = len({s.shift_date for s in shifts})
    return sum(s.hours for s in shifts) / max(days, 1)


def run_scenario_simulation(
    req: ScenarioSimulateRequest,
    tenant_id: str,
    db: Session,
    run_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Execute counterfactual simulation on an in-memory snapshot.
    Guarantees zero mutation to production DB rows.
    """
    if run_date is None:
        run_date = date.today()

    horizon = req.horizon_days or 30
    delta_pct = req.delta_pct or 0.0

    # 1. Baseline Trajectory (Unmodified)
    base_demand = forecast_demand(req.product_id, horizon, db, tenant_id=tenant_id, run_date=run_date) if req.product_id else {"forecast_total": 0.0, "daily_avg": 0.0}
    base_rev = forecast_revenue(horizon, db, tenant_id=tenant_id, run_date=run_date)
    base_cash = forecast_cash_flow(horizon, db, tenant_id=tenant_id, run_date=run_date)

    total_revenue = base_rev["projected_revenue"]
    current_cash = base_cash["current_cash"]
    outflow = base_cash["projected_outflow"]

    # Revenue exposed to the shock: one product's share, or the whole business
    if req.product_id:
        exposed_revenue = min(_product_revenue(req.product_id, tenant_id, horizon, db, run_date), total_revenue)
        scope = f"product {req.product_id}"
    else:
        exposed_revenue = total_revenue
        scope = "all products"

    assumptions: Dict[str, Any] = {
        "scope": scope,
        "baseline_revenue_model": "trailing 30-day daily revenue run rate",
        "baseline_demand_model": "Holt exponential smoothing on 90 days of sales" if req.product_id else "n/a (no product selected)",
        "outflow_model": "period budget pro-rated over the horizon",
        "exposed_revenue": round(exposed_revenue, 2),
    }

    # 2. Simulated Trajectory (In-Memory Parameter Adjustments)
    sim_demand_total = base_demand["forecast_total"]
    revenue_factor = 1.0
    extra_cost = 0.0

    if req.type == "price_change":
        elasticity, source = _estimate_elasticity(req.product_id, tenant_id, db, run_date)
        demand_factor = max(0.2, 1.0 + elasticity * delta_pct)
        sim_demand_total = base_demand["forecast_total"] * demand_factor
        revenue_factor = (1.0 + delta_pct) * demand_factor
        assumptions["price_elasticity"] = round(elasticity, 3)
        assumptions["elasticity_source"] = source

    elif req.type == "demand_shock":
        sim_demand_total = base_demand["forecast_total"] * (1.0 + delta_pct)
        revenue_factor = 1.0 + delta_pct

    elif req.type == "supplier_delay":
        delay = req.delay_days or 5
        lost_sales_frac = min(_MAX_LOST_SALES_FRACTION, delay / max(horizon, 1))
        sim_demand_total = base_demand["forecast_total"] * (1.0 - lost_sales_frac)
        revenue_factor = 1.0 - lost_sales_frac
        assumptions["delay_days"] = delay
        assumptions["lost_sales_fraction"] = round(lost_sales_frac, 3)
        assumptions["lost_sales_model"] = "sales lost for the delay period, capped at 50% of horizon"

    elif req.type == "staffing_change":
        daily_hours = _daily_staff_hours(tenant_id, db, run_date)
        extra_cost = delta_pct * daily_hours * _HOURLY_LABOR_RATE * horizon
        assumptions["baseline_daily_staff_hours"] = round(daily_hours, 1)
        assumptions["hourly_labor_rate"] = _HOURLY_LABOR_RATE
        assumptions["revenue_effect"] = "none modelled (capacity assumed non-binding)"

    sim_revenue = total_revenue - exposed_revenue + exposed_revenue * revenue_factor
    sim_net = sim_revenue - outflow - extra_cost
    sim_cash = max(0.0, current_cash + sim_net)

    current_trajectory = {
        "forecast_demand_units": round(base_demand["forecast_total"], 2),
        "projected_revenue": round(total_revenue, 2),
        "projected_cash_balance": round(base_cash["projected_cash"], 2),
        "net_cash_flow": round(base_cash["net_cash_flow"], 2),
    }
    simulated_trajectory = {
        "forecast_demand_units": round(sim_demand_total, 2),
        "projected_revenue": round(sim_revenue, 2),
        "projected_cash_balance": round(sim_cash, 2),
        "net_cash_flow": round(sim_net, 2),
    }

    # 3. Delta Computation
    delta = {
        "demand_delta_units": round(sim_demand_total - base_demand["forecast_total"], 2),
        "revenue_delta": round(sim_revenue - total_revenue, 2),
        "cash_delta": round(sim_cash - base_cash["projected_cash"], 2),
    }

    return {
        "scenario_type": req.type,
        "horizon_days": horizon,
        "current_trajectory": current_trajectory,
        "simulated_trajectory": simulated_trajectory,
        "delta": delta,
        "assumptions": assumptions,
    }
