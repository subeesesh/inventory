from fastapi import APIRouter, Depends, HTTPException
from backend.app.clock import utcnow
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import uuid

from backend.app.db import (
    get_db, Tenant, User, Product, Customer, Sale, SaleItem,
    SupplierProfile, PurchaseOrder, PurchaseOrderItem, StockMovement, InventoryState, SalesRecord
)
from backend.app.auth import get_current_tenant, require_role, get_current_user

router = APIRouter()

# ── Schemas ───────────────────────────────────────────────────────────────────

class CustomerCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None

class SaleItemCreate(BaseModel):
    product_id: str
    qty: int
    unit_price: float
    discount: float = 0.0

class CheckoutRequest(BaseModel):
    customer_id: Optional[str] = None
    payment_method: str
    discount: float = 0.0
    tax: float = 0.0
    subtotal: float
    total: float
    items: List[SaleItemCreate]

class SupplierProfileCreate(BaseModel):
    name: str
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    address: Optional[str] = None

class POItemCreate(BaseModel):
    product_id: str
    qty: int
    unit_cost: float

class PurchaseOrderCreate(BaseModel):
    supplier_profile_id: str
    items: List[POItemCreate]

class ProductCreate(BaseModel):
    id: str
    name: str
    category: str
    unit_price: float
    unit_cost: float
    warehouse_capacity_limit: Optional[float] = None
    barcode: Optional[str] = None
    sku: Optional[str] = None
    min_stock: int = 0
    max_stock: int = 1000
    is_active: bool = True

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    unit_price: Optional[float] = None
    unit_cost: Optional[float] = None
    barcode: Optional[str] = None
    sku: Optional[str] = None
    min_stock: Optional[int] = None
    max_stock: Optional[int] = None
    is_active: Optional[bool] = None

# ── POS & Sales ───────────────────────────────────────────────────────────────

@router.post("/tenants/pos/checkout")
def checkout(
    req: CheckoutRequest,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "cashier"]))
):
    try:
        # Create Sale
        sale = Sale(
            tenant_id=tenant.id,
            customer_id=req.customer_id,
            user_id=user.id,
            payment_method=req.payment_method,
            discount=req.discount,
            tax=req.tax,
            subtotal=req.subtotal,
            total=req.total
        )
        db.add(sale)
        db.flush()

        today = utcnow().date()

        for item in req.items:
            sale_item = SaleItem(
                sale_id=sale.id,
                product_id=item.product_id,
                qty=item.qty,
                unit_price=item.unit_price,
                discount=item.discount
            )
            db.add(sale_item)

            # Update Inventory
            inv = db.query(InventoryState).filter_by(tenant_id=tenant.id, product_id=item.product_id).with_for_update().first()
            if not inv:
                raise HTTPException(status_code=400, detail=f"Product {item.product_id} not in inventory")
            if inv.stock_level < item.qty:
                raise HTTPException(status_code=400, detail=f"Insufficient stock for {item.product_id}")
            inv.stock_level -= item.qty

            # Log StockMovement
            movement = StockMovement(
                tenant_id=tenant.id,
                product_id=item.product_id,
                delta=-item.qty,
                reason="sale",
                reference_id=sale.id
            )
            db.add(movement)

            # Upsert SalesRecord for AMDIE agents
            sales_record = db.query(SalesRecord).filter_by(tenant_id=tenant.id, product_id=item.product_id, date=today).first()
            if sales_record:
                sales_record.qty_sold += item.qty
            else:
                sales_record = SalesRecord(
                    tenant_id=tenant.id,
                    product_id=item.product_id,
                    qty_sold=item.qty,
                    price=item.unit_price,
                    date=today
                )
                db.add(sales_record)

        db.commit()
        return {"status": "success", "sale_id": sale.id}
    except Exception as e:
        db.rollback()
        raise e

@router.get("/tenants/sales")
def get_sales(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "finance_officer"]))
):
    sales = db.query(Sale).filter_by(tenant_id=tenant.id).order_by(Sale.created_at.desc()).limit(100).all()
    return sales

@router.get("/tenants/sales/{id}")
def get_sale(
    id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "finance_officer", "cashier"]))
):
    sale = db.query(Sale).filter_by(tenant_id=tenant.id, id=id).first()
    if not sale:
        raise HTTPException(status_code=404)
    items = db.query(SaleItem).filter_by(sale_id=sale.id).all()
    return {"sale": sale, "items": items}

# ── Customers ─────────────────────────────────────────────────────────────────

@router.get("/tenants/customers")
def get_customers(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "cashier", "finance_officer"]))
):
    return db.query(Customer).filter_by(tenant_id=tenant.id).all()

@router.post("/tenants/customers")
def create_customer(
    req: CustomerCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "cashier"]))
):
    customer = Customer(
        tenant_id=tenant.id,
        name=req.name,
        phone=req.phone,
        email=req.email
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return {"status": "success", "id": customer.id}

@router.get("/tenants/customers/{id}")
def get_customer(
    id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "cashier", "finance_officer"]))
):
    cust = db.query(Customer).filter_by(tenant_id=tenant.id, id=id).first()
    if not cust:
        raise HTTPException(status_code=404)
    return cust

# ── Products CRUD ─────────────────────────────────────────────────────────────

@router.post("/tenants/products")
def create_product(
    req: ProductCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "inventory_manager"]))
):
    if db.query(Product).filter_by(tenant_id=tenant.id, id=req.id).first():
        raise HTTPException(status_code=400, detail="Product ID exists")
    
    prod = Product(
        id=req.id,
        tenant_id=tenant.id,
        name=req.name,
        category=req.category,
        unit_price=req.unit_price,
        unit_cost=req.unit_cost, # setter encrypts
        warehouse_capacity_limit=req.warehouse_capacity_limit,
        barcode=req.barcode,
        sku=req.sku,
        min_stock=req.min_stock,
        max_stock=req.max_stock,
        is_active=req.is_active
    )
    db.add(prod)
    # create default inventory state
    inv = InventoryState(
        product_id=prod.id,
        tenant_id=tenant.id,
        stock_level=0,
        lead_time_days=7,
        reorder_point=req.min_stock if req.min_stock > 0 else 10
    )
    db.add(inv)
    db.commit()
    return {"status": "success", "product_id": prod.id}

@router.put("/tenants/products/{id}")
def update_product(
    id: str,
    req: ProductUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "inventory_manager"]))
):
    prod = db.query(Product).filter_by(tenant_id=tenant.id, id=id).first()
    if not prod:
        raise HTTPException(status_code=404)
    
    if req.name is not None: prod.name = req.name
    if req.category is not None: prod.category = req.category
    if req.unit_price is not None: prod.unit_price = req.unit_price
    if req.unit_cost is not None: prod.unit_cost = req.unit_cost
    if req.barcode is not None: prod.barcode = req.barcode
    if req.sku is not None: prod.sku = req.sku
    if req.min_stock is not None: prod.min_stock = req.min_stock
    if req.max_stock is not None: prod.max_stock = req.max_stock
    if req.is_active is not None: prod.is_active = req.is_active
    db.commit()
    return {"status": "success"}

@router.delete("/tenants/products/{id}")
def delete_product(
    id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "inventory_manager"]))
):
    prod = db.query(Product).filter_by(tenant_id=tenant.id, id=id).first()
    if not prod:
        raise HTTPException(status_code=404)
    prod.is_active = False
    db.commit()
    return {"status": "success"}

# ── Supplier Profiles & POs ───────────────────────────────────────────────────

@router.get("/tenants/supplier-profiles")
def get_supplier_profiles(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "procurement_officer", "finance_officer"]))
):
    return db.query(SupplierProfile).filter_by(tenant_id=tenant.id).all()

@router.post("/tenants/supplier-profiles")
def create_supplier_profile(
    req: SupplierProfileCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "procurement_officer"]))
):
    sp = SupplierProfile(
        tenant_id=tenant.id,
        name=req.name,
        contact_phone=req.contact_phone,
        contact_email=req.contact_email,
        address=req.address
    )
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return {"status": "success", "id": sp.id}

@router.get("/tenants/purchase-orders")
def get_pos(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "procurement_officer", "finance_officer"]))
):
    pos = db.query(PurchaseOrder).filter_by(tenant_id=tenant.id).order_by(PurchaseOrder.created_at.desc()).all()
    results = []
    for po in pos:
        items = db.query(PurchaseOrderItem).filter_by(po_id=po.id).all()
        results.append({
            "id": po.id,
            "supplier_profile_id": po.supplier_profile_id,
            "status": po.status,
            "created_at": po.created_at,
            "received_at": po.received_at,
            "items": [{"product_id": i.product_id, "qty": i.qty, "unit_cost": i.unit_cost} for i in items]
        })
    return results

@router.post("/tenants/purchase-orders")
def create_po(
    req: PurchaseOrderCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "procurement_officer"]))
):
    po = PurchaseOrder(
        tenant_id=tenant.id,
        supplier_profile_id=req.supplier_profile_id,
        status="ordered"
    )
    db.add(po)
    db.flush()
    for i in req.items:
        pi = PurchaseOrderItem(
            po_id=po.id,
            product_id=i.product_id,
            qty=i.qty,
            unit_cost=i.unit_cost
        )
        db.add(pi)
    db.commit()
    return {"status": "success", "po_id": po.id}

@router.post("/tenants/purchase-orders/{id}/receive")
def receive_po(
    id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer"]))
):
    po = db.query(PurchaseOrder).filter_by(tenant_id=tenant.id, id=id).with_for_update().first()
    if not po or po.status == "received":
        raise HTTPException(status_code=400, detail="PO not found or already received")
    
    po.status = "received"
    po.received_at = utcnow()

    items = db.query(PurchaseOrderItem).filter_by(po_id=po.id).all()
    for item in items:
        # Update Inventory
        inv = db.query(InventoryState).filter_by(tenant_id=tenant.id, product_id=item.product_id).first()
        if inv:
            inv.stock_level += item.qty
        else:
            inv = InventoryState(
                product_id=item.product_id,
                tenant_id=tenant.id,
                stock_level=item.qty,
                lead_time_days=7,
                reorder_point=10
            )
            db.add(inv)
            
        # Log StockMovement
        movement = StockMovement(
            tenant_id=tenant.id,
            product_id=item.product_id,
            delta=item.qty,
            reason="po_receipt",
            reference_id=po.id
        )
        db.add(movement)
    
    db.commit()
    return {"status": "success"}

# ── Reports ───────────────────────────────────────────────────────────────────

# Per-type role whitelist (enforced in-handler after the broad role guard)
_REPORT_ROLES = {
    "sales_summary":    {"owner", "finance_officer"},
    "inventory_status": {"owner", "inventory_manager", "procurement_officer"},
    "purchase_orders":  {"owner", "procurement_officer", "finance_officer"},
    "profit":           {"owner", "finance_officer"},
    "customers":        {"owner", "finance_officer"},
}

@router.get("/tenants/reports")
def get_reports(
    type: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer", "finance_officer"]))
):
    # Fine-grained per-type role check
    allowed = _REPORT_ROLES.get(type)
    if allowed is None:
        raise HTTPException(status_code=400, detail=f"Unknown report type '{type}'")
    if user and user.role not in allowed:
        raise HTTPException(status_code=403, detail=f"Role '{user.role}' cannot access report '{type}'")

    # Date range — default last 30 days
    end = datetime.strptime(to_date, "%Y-%m-%d").date() if to_date else utcnow().date()
    start = datetime.strptime(from_date, "%Y-%m-%d").date() if from_date else end - timedelta(days=29)
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    # ── sales_summary ────────────────────────────────────────────────────
    if type == "sales_summary":
        sales = db.query(Sale).filter(
            Sale.tenant_id == tenant.id,
            Sale.created_at >= start_dt,
            Sale.created_at <= end_dt,
        ).all()
        by_day: dict = {}
        for s in sales:
            day = s.created_at.date().isoformat()
            if day not in by_day:
                by_day[day] = {"date": day, "revenue": 0.0, "transactions": 0, "avg_basket": 0.0}
            by_day[day]["revenue"] += s.total
            by_day[day]["transactions"] += 1
        for d in by_day.values():
            d["avg_basket"] = round(d["revenue"] / d["transactions"], 2)
            d["revenue"] = round(d["revenue"], 2)
        return {"type": type, "data": sorted(by_day.values(), key=lambda x: x["date"])}

    # ── inventory_status ─────────────────────────────────────────────────
    elif type == "inventory_status":
        prods = db.query(Product).filter_by(tenant_id=tenant.id, is_active=True).all()
        data = []
        for p in prods:
            inv = db.query(InventoryState).filter_by(product_id=p.id, tenant_id=tenant.id).first()
            sl = inv.stock_level if inv else 0
            mn = p.min_stock or 0
            mx = p.max_stock or 9999
            if sl <= mn:
                status = "low"
            elif sl > mx:
                status = "overstocked"
            else:
                status = "healthy"
            data.append({
                "product_id":   p.id,
                "name":         p.name,
                "category":     p.category,
                "sku":          p.sku,
                "stock_level":  sl,
                "min_stock":    mn,
                "max_stock":    mx,
                "reorder_point": inv.reorder_point if inv else 0,
                "status":       status,
            })
        return {"type": type, "data": data}

    # ── purchase_orders ──────────────────────────────────────────────────
    elif type == "purchase_orders":
        pos = db.query(PurchaseOrder).filter(
            PurchaseOrder.tenant_id == tenant.id,
            PurchaseOrder.created_at >= start_dt,
            PurchaseOrder.created_at <= end_dt,
        ).order_by(PurchaseOrder.created_at.desc()).all()
        data = []
        for po in pos:
            sp = db.query(SupplierProfile).filter_by(id=po.supplier_profile_id).first()
            items = db.query(PurchaseOrderItem).filter_by(po_id=po.id).all()
            total_cost = sum(i.qty * i.unit_cost for i in items)
            data.append({
                "id":             po.id,
                "supplier_name":  sp.name if sp else po.supplier_profile_id,
                "status":         po.status,
                "created_at":     po.created_at.isoformat(),
                "received_at":    po.received_at.isoformat() if po.received_at else None,
                "total_cost":     round(total_cost, 2),
                "line_items":     len(items),
            })
        return {"type": type, "data": data}

    # ── profit ───────────────────────────────────────────────────────────
    elif type == "profit":
        sale_items = (
            db.query(SaleItem, Sale, Product)
            .join(Sale, SaleItem.sale_id == Sale.id)
            .join(Product, SaleItem.product_id == Product.id)
            .filter(
                Sale.tenant_id == tenant.id,
                Sale.created_at >= start_dt,
                Sale.created_at <= end_dt,
            )
            .all()
        )
        by_day: dict = {}
        for si, sale, prod in sale_items:
            day = sale.created_at.date().isoformat()
            if day not in by_day:
                by_day[day] = {"date": day, "revenue": 0.0, "cost": 0.0, "gross_profit": 0.0}
            revenue = si.unit_price * si.qty
            cost = (prod.unit_cost or 0) * si.qty
            by_day[day]["revenue"] += revenue
            by_day[day]["cost"] += cost
            by_day[day]["gross_profit"] += (revenue - cost)
        for d in by_day.values():
            d["revenue"] = round(d["revenue"], 2)
            d["cost"] = round(d["cost"], 2)
            d["gross_profit"] = round(d["gross_profit"], 2)
        return {"type": type, "data": sorted(by_day.values(), key=lambda x: x["date"])}

    # ── customers ────────────────────────────────────────────────────────
    elif type == "customers":
        customers = db.query(Customer).filter_by(tenant_id=tenant.id).all()
        data = []
        for c in customers:
            sales = db.query(Sale).filter(
                Sale.tenant_id == tenant.id,
                Sale.customer_id == c.id,
            ).all()
            lifetime_spend = round(sum(s.total for s in sales), 2)
            last_purchase = max((s.created_at for s in sales), default=None)
            data.append({
                "id":             c.id,
                "name":           c.name,
                "phone":          c.phone,
                "email":          c.email,
                "transaction_count": len(sales),
                "lifetime_spend": lifetime_spend,
                "last_purchase":  last_purchase.isoformat() if last_purchase else None,
                "created_at":     c.created_at.isoformat(),
            })
        return {"type": type, "data": data}

