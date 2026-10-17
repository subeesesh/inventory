"""
Real-Time Business Monitoring Engine
=====================================
BizTwin AI continuous monitoring module (§III-C).

Scans inventory depletion, cash flow, sales activity and supplier delivery
profiles for threshold- and baseline-based anomalies.  Each scan:

1. Opens a MonitoringEvent for every new anomaly (deduplicated per entity).
2. Resolves open events whose condition has cleared (e.g. stock replenished).
3. For stock events, triggers an AMDIE reorder cycle and routes the result
   through the Automation & Alert System (§III-J).

`run_monitoring_cycle` scans every tenant and is invoked periodically by the
background scheduler started in main.py (MONITORING_INTERVAL_SECONDS).
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session

from backend.app.clock import utcnow
from backend.app.config import settings
from backend.app.db import (
    MonitoringEvent, InventoryState, Product, Sale, FinanceLedger, Supplier, Tenant,
)

logger = logging.getLogger(__name__)

STOCK_EVENT_TYPES = ("stockout_risk", "low_stock_depletion")

# Sales spike: today's transactions vs the trailing daily average
_SPIKE_BASELINE_DAYS = 14
_SPIKE_MULTIPLIER = 2.0
_SPIKE_MIN_TRANSACTIONS = 5
_SPIKE_NO_BASELINE_TRANSACTIONS = 10

# Supplier delay risk thresholds
_SUPPLIER_MAX_LEAD_TIME_DAYS = 10.0
_SUPPLIER_MIN_RELIABILITY = 0.75


def _open_event(db: Session, tenant_id: str, event_type: str, entity_type: str) -> dict:
    """Map entity_id -> open MonitoringEvent for this tenant/event type."""
    rows = db.query(MonitoringEvent).filter(
        MonitoringEvent.tenant_id == tenant_id,
        MonitoringEvent.event_type == event_type,
        MonitoringEvent.entity_type == entity_type,
        MonitoringEvent.resolved == False,  # noqa: E712
    ).all()
    return {r.entity_id: r for r in rows}


def _raise(db: Session, new_events: list, tenant_id: str, event_type: str,
           entity_type: str, entity_id: Optional[str], severity: str, now: datetime) -> None:
    evt = MonitoringEvent(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        severity=severity,
        detected_at=now,
        resolved=False,
    )
    db.add(evt)
    new_events.append(evt)


def _resolve(evt: MonitoringEvent, now: datetime) -> None:
    evt.resolved = True
    evt.resolved_at = now


def scan_business_monitoring_events(
    tenant_id: str,
    db: Session,
    auto_trigger: bool = True,
) -> List[MonitoringEvent]:
    """
    Scan business state for anomalies across inventory, sales, finance and suppliers.
    Returns the newly opened MonitoringEvent records.
    """
    new_events: List[MonitoringEvent] = []
    now = utcnow()
    today = now.date()

    # 1. Inventory depletion -------------------------------------------------
    open_stock = {
        et: _open_event(db, tenant_id, et, "product") for et in STOCK_EVENT_TYPES
    }
    inv_states = db.query(InventoryState).filter(InventoryState.tenant_id == tenant_id).all()
    for inv in inv_states:
        prod = db.query(Product).filter(Product.tenant_id == tenant_id, Product.id == inv.product_id).first()
        min_stock = prod.min_stock if (prod and prod.min_stock is not None and prod.min_stock > 0) else settings.MONITORING_DEFAULT_MIN_STOCK

        if inv.stock_level <= 0:
            current = "stockout_risk"
        elif inv.stock_level <= min_stock:
            current = "low_stock_depletion"
        else:
            current = None

        for et in STOCK_EVENT_TYPES:
            existing = open_stock[et].get(inv.product_id)
            if existing and et != current:
                _resolve(existing, now)
        if current and inv.product_id not in open_stock[current]:
            severity = "critical" if current == "stockout_risk" else "warning"
            _raise(db, new_events, tenant_id, current, "product", inv.product_id, severity, now)

    # 2. Cash flow -------------------------------------------------------------
    ledger = db.query(FinanceLedger).filter(
        FinanceLedger.tenant_id == tenant_id
    ).order_by(FinanceLedger.date.desc()).first()
    open_cash = _open_event(db, tenant_id, "cash_flow_warning", "finance")

    if ledger:
        if ledger.cash_balance < ledger.budget_per_period * 0.7:
            if not open_cash:
                severity = "warning" if ledger.cash_balance >= ledger.budget_per_period * 0.3 else "critical"
                _raise(db, new_events, tenant_id, "cash_flow_warning", "finance", ledger.id, severity, now)
        else:
            for evt in open_cash.values():
                _resolve(evt, now)

    # 3. Sales spike vs trailing baseline --------------------------------------
    day_start = datetime.combine(today, datetime.min.time())
    count_today = db.query(Sale).filter(
        Sale.tenant_id == tenant_id,
        Sale.created_at >= day_start,
    ).count()
    baseline_count = db.query(Sale).filter(
        Sale.tenant_id == tenant_id,
        Sale.created_at >= day_start - timedelta(days=_SPIKE_BASELINE_DAYS),
        Sale.created_at < day_start,
    ).count()
    baseline_daily = baseline_count / _SPIKE_BASELINE_DAYS
    if baseline_daily > 0:
        is_spike = count_today >= max(_SPIKE_MIN_TRANSACTIONS, _SPIKE_MULTIPLIER * baseline_daily)
    else:
        is_spike = count_today >= _SPIKE_NO_BASELINE_TRANSACTIONS

    spike_entity = today.isoformat()
    open_spikes = _open_event(db, tenant_id, "sales_spike", "sales")
    for entity_id, evt in open_spikes.items():
        if entity_id != spike_entity:  # spikes are per-day; close previous days
            _resolve(evt, now)
    if is_spike and spike_entity not in open_spikes:
        _raise(db, new_events, tenant_id, "sales_spike", "sales", spike_entity, "info", now)

    # 4. Supplier delivery risk ------------------------------------------------
    open_supp = _open_event(db, tenant_id, "supplier_delay_risk", "supplier")
    for supp in db.query(Supplier).filter_by(tenant_id=tenant_id).all():
        at_risk = (
            supp.avg_lead_time_days > _SUPPLIER_MAX_LEAD_TIME_DAYS
            or (supp.reliability_score is not None and supp.reliability_score < _SUPPLIER_MIN_RELIABILITY)
        )
        if at_risk and supp.id not in open_supp:
            _raise(db, new_events, tenant_id, "supplier_delay_risk", "supplier", supp.id, "warning", now)
        elif not at_risk and supp.id in open_supp:
            _resolve(open_supp[supp.id], now)

    db.commit()

    # 5. Proactive response: stock events -> AMDIE reorder -> automation policy
    if auto_trigger:
        for evt in new_events:
            if evt.entity_type == "product" and evt.entity_id:
                _respond_to_stock_event(tenant_id, evt, today.isoformat(), db)

    return new_events


def _respond_to_stock_event(tenant_id: str, evt: MonitoringEvent, date_str: str, db: Session) -> None:
    from backend.app.api import trigger_decision_internal
    from backend.app.automation import AutomationPolicyEngine
    try:
        decision = trigger_decision_internal(
            tenant_id=tenant_id,
            product_id=evt.entity_id,
            date_str=date_str,
            decision_type="reorder_quantity",
            db=db,
        )
        AutomationPolicyEngine(tenant_id, db).route_decision(
            decision, product_id=evt.entity_id, monitoring_event_id=evt.id
        )
    except Exception:
        db.rollback()
        logger.exception(
            "[Monitoring] Automatic reorder decision failed for tenant=%s product=%s",
            tenant_id, evt.entity_id,
        )


def run_monitoring_cycle(session_factory) -> int:
    """Scan every tenant once.  Returns the number of new events opened."""
    db = session_factory()
    try:
        tenant_ids = [t.id for t in db.query(Tenant.id).all()]
        total = 0
        for tid in tenant_ids:
            try:
                total += len(scan_business_monitoring_events(tid, db))
            except Exception:
                db.rollback()
                logger.exception("[Monitoring] Scan failed for tenant=%s", tid)
        return total
    finally:
        db.close()
