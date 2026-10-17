"""
Predictive Analytics Module
===========================
BizTwin AI shared forecasting engine (§III-D).
Provides cross-functional forecasting functions for demand, revenue, cash flow,
and risk levels over a specified horizon. Agents and monitoring engines consult
this module for unified predictive signals.
"""

import numpy as np
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from statsmodels.tsa.api import ExponentialSmoothing

from backend.app.db import SalesRecord, Sale, InventoryState, FinanceLedger, Product, SupplierProfile


def forecast_demand(
    product_id: str,
    horizon_days: int,
    db: Session,
    tenant_id: Optional[str] = None,
    run_date: Optional[date] = None,
) -> Dict[str, float]:
    """
    Forecast demand for a given product over horizon_days.
    Uses trailing 90 days of SalesRecord with ExponentialSmoothing fallback to Moving Average.
    """
    if run_date is None:
        run_date = date.today()
    if horizon_days <= 0:
        horizon_days = 1

    # Fit on the 90 completed days before run_date: the decision day's own sales
    # are still partial, and a trailing partial day reads as a demand collapse.
    start_date = run_date - timedelta(days=90)
    last_full_day = run_date - timedelta(days=1)

    query = db.query(SalesRecord).filter(
        SalesRecord.product_id == product_id,
        SalesRecord.date >= start_date,
        SalesRecord.date <= last_full_day,
    )
    if tenant_id:
        query = query.filter(SalesRecord.tenant_id == tenant_id)

    sales_records = query.all()
    sales_by_day: Dict[date, float] = {}
    for r in sales_records:   # several records per day are possible (one per POS sale)
        sales_by_day[r.date] = sales_by_day.get(r.date, 0) + r.qty_sold

    date_range = pd.date_range(start=start_date, end=last_full_day, freq='D')
    ts_data = [sales_by_day.get(d.date(), 0) for d in date_range]
    ts = pd.Series(ts_data, index=date_range, dtype=float)

    forecast_val = 0.0
    std_error = 2.0

    try:
        if len(ts) >= 14 and ts.sum() > 0:
            model = ExponentialSmoothing(ts, trend='add', seasonal=None, initialization_method='estimated')
            fit = model.fit(smoothing_level=0.3, smoothing_trend=0.1, optimized=False)
            forecast = fit.forecast(steps=horizon_days)
            forecast_val = max(0.0, float(forecast.sum()))
            residuals = fit.resid
            std_error = float(np.std(residuals)) if len(residuals) > 1 else 2.0
        else:
            mean_daily = float(ts.mean())
            forecast_val = max(0.0, mean_daily * horizon_days)
            std_error = float(ts.std()) if len(ts) > 1 else 2.0
    except Exception:
        mean_daily = float(ts.mean()) if len(ts) > 0 else 0.0
        forecast_val = max(0.0, mean_daily * horizon_days)
        std_error = float(ts.std()) if len(ts) > 1 else 2.0

    daily_avg = forecast_val / max(horizon_days, 1)

    return {
        "forecast_total": float(round(forecast_val, 2)),
        "daily_avg": float(round(daily_avg, 2)),
        "std_error": float(round(std_error, 2)),
    }


def forecast_revenue(
    horizon_days: int,
    db: Session,
    tenant_id: Optional[str] = None,
    run_date: Optional[date] = None,
) -> Dict[str, float]:
    """
    Forecast revenue across all products or for a tenant over horizon_days.
    """
    if run_date is None:
        run_date = date.today()
    start_date = run_date - timedelta(days=30)

    # Calculate average daily revenue from recent sales
    query = db.query(SalesRecord).filter(
        SalesRecord.date >= start_date,
        SalesRecord.date <= run_date,
    )
    if tenant_id:
        query = query.filter(SalesRecord.tenant_id == tenant_id)

    records = query.all()
    total_rev = sum(r.qty_sold * r.price for r in records)
    days_count = max((run_date - start_date).days, 1)
    daily_avg_revenue = total_rev / days_count

    projected_revenue = daily_avg_revenue * horizon_days

    return {
        "projected_revenue": float(round(projected_revenue, 2)),
        "daily_revenue": float(round(daily_avg_revenue, 2)),
    }


def forecast_cash_flow(
    horizon_days: int,
    db: Session,
    tenant_id: Optional[str] = None,
    run_date: Optional[date] = None,
) -> Dict[str, float]:
    """
    Forecast cash balance and net cash flow over horizon_days.
    """
    if run_date is None:
        run_date = date.today()

    ledger = None
    if tenant_id:
        ledger = db.query(FinanceLedger).filter(
            FinanceLedger.tenant_id == tenant_id
        ).order_by(FinanceLedger.date.desc()).first()

    current_cash = ledger.cash_balance if ledger else 50000.0
    budget = ledger.budget_per_period if ledger else 15000.0

    rev = forecast_revenue(horizon_days, db, tenant_id=tenant_id, run_date=run_date)
    projected_inflow = rev["projected_revenue"]
    projected_outflow = budget * (horizon_days / 30.0)

    net_cash_flow = projected_inflow - projected_outflow
    projected_cash = max(0.0, current_cash + net_cash_flow)

    return {
        "current_cash": float(round(current_cash, 2)),
        "projected_cash": float(round(projected_cash, 2)),
        "net_cash_flow": float(round(net_cash_flow, 2)),
        "projected_inflow": float(round(projected_inflow, 2)),
        "projected_outflow": float(round(projected_outflow, 2)),
    }


def forecast_risk_level(
    tenant_id: Optional[str] = None,
    product_id: Optional[str] = None,
    db: Optional[Session] = None,
    run_date: Optional[date] = None,
) -> float:
    """
    Forecast overall operational & financial risk score in range [0.0, 1.0].
    """
    if db is None or tenant_id is None:
        return 0.25

    risk_factors = []

    # 1. Cash risk
    ledger = db.query(FinanceLedger).filter(
        FinanceLedger.tenant_id == tenant_id
    ).order_by(FinanceLedger.date.desc()).first()
    if ledger:
        if ledger.cash_balance < ledger.budget_per_period * 0.5:
            risk_factors.append(0.8)
        elif ledger.cash_balance < ledger.budget_per_period:
            risk_factors.append(0.5)
        else:
            risk_factors.append(0.15)

    # 2. Stockout risk
    if product_id:
        inv = db.query(InventoryState).filter_by(tenant_id=tenant_id, product_id=product_id).first()
        if inv:
            if inv.stock_level <= 0:
                risk_factors.append(0.9)
            elif inv.stock_level <= inv.reorder_point:
                risk_factors.append(0.6)
            else:
                risk_factors.append(0.1)

    if not risk_factors:
        return 0.2

    overall_risk = float(np.mean(risk_factors))
    return float(np.clip(overall_risk, 0.0, 1.0))
