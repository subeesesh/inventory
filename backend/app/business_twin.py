"""
Business Digital Twin Module
=============================
BizTwin AI Business Digital Twin (§III-B).
Provides a unified, read-only operational state representation across inventory,
sales, finance, customer relations, supplier networks, workforce staffing, and risk/monitoring.

Acts as the shared state representation consulted by domain agents, predictive engines,
scenario simulators, and the conversational copilot.
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta

from backend.app.db import (
    Tenant, Product, InventoryState, SalesRecord, Sale,
    FinanceLedger, Customer, SupplierProfile, Supplier, StaffShift, MonitoringEvent
)
from backend.app.config import settings
from backend.app.predictive import forecast_risk_level, forecast_revenue, forecast_cash_flow


class BusinessDigitalTwin:
    """
    Unified, read-only state snapshot of an SME business twin instance.
    """
    def __init__(self, tenant_id: str, db: Session):
        self.tenant_id = tenant_id
        self.db = db

    def get_state(self, run_date: Optional[date] = None) -> Dict[str, Any]:
        if run_date is None:
            run_date = date.today()

        # 1. Tenant metadata
        tenant = self.db.query(Tenant).filter_by(id=self.tenant_id).first()

        # 2. Supply network: per-product delivery profiles (the relation layer
        #    linking suppliers to the inventory items they supply)
        delivery_profiles = self.db.query(Supplier).filter_by(tenant_id=self.tenant_id).all()
        supplier_ids_by_product: Dict[str, List[str]] = {}
        for s in delivery_profiles:
            supplier_ids_by_product.setdefault(s.product_id, []).append(s.id)
        supply_network = [
            {
                "supplier_id": s.id,
                "name": s.name,
                "product_id": s.product_id,
                "supplier_profile_id": s.supplier_profile_id,
                "avg_lead_time_days": s.avg_lead_time_days,
                "lead_time_std_dev": s.lead_time_std_dev,
                "reliability_score": s.reliability_score,
                "min_order_qty": s.min_order_qty,
            }
            for s in delivery_profiles
        ]

        # 3. Inventory state
        products = self.db.query(Product).filter_by(tenant_id=self.tenant_id, is_active=True).all()
        inventory_summary = []
        for p in products:
            inv = self.db.query(InventoryState).filter_by(tenant_id=self.tenant_id, product_id=p.id).first()
            stock = inv.stock_level if inv else 0
            min_stock = p.min_stock if p.min_stock else settings.MONITORING_DEFAULT_MIN_STOCK
            inventory_summary.append({
                "product_id": p.id,
                "name": p.name,
                "category": p.category,
                "stock_level": stock,
                "min_stock": p.min_stock or 0,
                "max_stock": p.max_stock or 1000,
                "reorder_point": inv.reorder_point if inv else 0,
                "unit_price": p.unit_price,
                "low_stock": stock <= min_stock,
                "supplier_ids": supplier_ids_by_product.get(p.id, []),
            })

        # 4. Recent sales summary
        start_30 = run_date - timedelta(days=30)
        recent_sales = self.db.query(SalesRecord).filter(
            SalesRecord.tenant_id == self.tenant_id,
            SalesRecord.date >= start_30,
            SalesRecord.date <= run_date,
        ).all()
        total_30d_units = sum(r.qty_sold for r in recent_sales)
        total_30d_revenue = sum(r.qty_sold * r.price for r in recent_sales)

        # 5. Finance ledger state
        ledger = self.db.query(FinanceLedger).filter(
            FinanceLedger.tenant_id == self.tenant_id
        ).order_by(FinanceLedger.date.desc()).first()

        finance_summary = {
            "cash_balance": ledger.cash_balance if ledger else 50000.0,
            "period_budget": ledger.budget_per_period if ledger else 15000.0,
        }

        # 6. Customer relationships summary
        customer_count = self.db.query(Customer).filter_by(tenant_id=self.tenant_id).count()

        # 7. Supplier contact directory
        suppliers = self.db.query(SupplierProfile).filter_by(tenant_id=self.tenant_id).all()
        supplier_summary = [
            {"id": s.id, "name": s.name, "contact_phone": s.contact_phone}
            for s in suppliers
        ]

        # 8. Staffing shifts
        shifts = self.db.query(StaffShift).filter(
            StaffShift.tenant_id == self.tenant_id,
            StaffShift.shift_date == run_date
        ).all()
        scheduled_hours = sum(s.hours for s in shifts) if shifts else 8.0

        # 9. Monitoring events
        active_events = self.db.query(MonitoringEvent).filter(
            MonitoringEvent.tenant_id == self.tenant_id,
            MonitoringEvent.resolved == False
        ).order_by(MonitoringEvent.detected_at.desc()).all()

        monitoring_summary = [
            {"id": e.id, "event_type": e.event_type, "severity": e.severity, "entity_id": e.entity_id}
            for e in active_events
        ]

        # 10. Risk score and 30-day outlook
        risk_score = forecast_risk_level(tenant_id=self.tenant_id, db=self.db, run_date=run_date)
        revenue_30 = forecast_revenue(30, self.db, tenant_id=self.tenant_id, run_date=run_date)
        cash_30 = forecast_cash_flow(30, self.db, tenant_id=self.tenant_id, run_date=run_date)

        return {
            "tenant_id": self.tenant_id,
            "business_name": tenant.name if tenant else "SME Business",
            "business_goal": tenant.business_goal if tenant else "maximize_profit",
            "run_date": str(run_date),
            "inventory": inventory_summary,
            "sales_30d": {
                "total_units": total_30d_units,
                "total_revenue": round(total_30d_revenue, 2),
            },
            "finance": finance_summary,
            "customer_count": customer_count,
            "suppliers": supplier_summary,
            "supply_network": supply_network,
            "staffing": {
                "scheduled_hours_today": scheduled_hours,
                "shift_count": len(shifts),
            },
            "monitoring_active_events": monitoring_summary,
            "risk_level": round(risk_score, 2),
            "outlook_30d": {
                "projected_revenue": revenue_30["projected_revenue"],
                "projected_cash": cash_30["projected_cash"],
                "net_cash_flow": cash_30["net_cash_flow"],
            },
        }


def get_business_digital_twin(tenant_id: str, db: Session) -> BusinessDigitalTwin:
    """Factory helper to obtain a Business Digital Twin instance."""
    return BusinessDigitalTwin(tenant_id=tenant_id, db=db)
