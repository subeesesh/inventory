import random
from backend.app.clock import utcnow
from datetime import datetime, timedelta
import math
from sqlalchemy.orm import Session
from backend.app.db import (
    Tenant, Product, InventoryState, SalesRecord, FinanceLedger,
    AgentAccuracy, WeightCoefficients, HistoricalAccuracyLog, Supplier,
)
from backend.app.config import settings
from backend.app.vector_db import vector_db
from backend.app.decision_registry import all_decision_types

# 20 Products Configuration
# Phase 2: each product also carries a KNOWN ground-truth elasticity so the
# Pricing Agent's regression estimate can be validated against the true value.
PRODUCT_TEMPLATES = [
    {
        "id": f"PROD-{i:03d}",
        "name": f"SME Widget model {chr(65 + i % 26)}{i}",
        "category": random.choice(["Electronics", "Office Supply", "Industrial", "Consumer Goods"]),
        "price_range": (15.0, 120.0),
        # Ground-truth price elasticity baked into generated sales data.
        # Ranges from -0.5 (inelastic) to -2.5 (highly elastic).
        "true_elasticity": round(random.uniform(-2.5, -0.5), 2),
    }
    for i in range(1, 21)
]

# Store ground-truth elasticities as a module-level dict for test access
GROUND_TRUTH_ELASTICITY: dict[str, float] = {
    t["id"]: t["true_elasticity"] for t in PRODUCT_TEMPLATES
}


def generate_synthetic_data(db: Session, tenant_id: str, start_date: datetime.date, days: int = 365):
    # 1. Create 20 products
    products = []
    for temp in PRODUCT_TEMPLATES:
        price = round(random.uniform(*temp["price_range"]), 2)
        # unit cost is between 40% and 60% of unit price
        cost = round(price * random.uniform(0.4, 0.6), 2)
        prod = Product(
            id=temp["id"],
            tenant_id=tenant_id,
            name=temp["name"],
            category=temp["category"],
            unit_price=price,
            warehouse_capacity_limit=500.0
        )
        prod.unit_cost = cost
        db.add(prod)
        products.append(prod)
    db.commit()

    # 2. Create initial Inventory State for each product
    for prod in products:
        reorder = random.randint(30, 80)
        stock = random.randint(50, 150)
        lead_time = random.choice([3, 5, 7, 10])
        inv = InventoryState(
            product_id=prod.id,
            tenant_id=tenant_id,
            stock_level=stock,
            lead_time_days=lead_time,
            reorder_point=reorder
        )
        db.add(inv)
    db.commit()

    # 3. Create Daily Sales Records (12 months)
    # Phase 2: prices vary on a randomized schedule with KNOWN ground-truth elasticity
    # baked in, so Pricing Agent's regression estimate can be checked against it.
    current_date = start_date
    sales_records = []

    prod_baselines = {}
    prod_price_schedules = {}   # Phase 2: price variation schedule per product
    for p in products:
        true_elast = GROUND_TRUTH_ELASTICITY.get(p.id, -1.0)
        prod_baselines[p.id] = {
            "base_qty": random.randint(3, 15),
            "trend": random.uniform(-0.02, 0.05),
            "seasonality_phase": random.uniform(0, 2 * math.pi),
            "true_elasticity": true_elast,
            "base_price": p.unit_price,
        }
        # Price change schedule: every 30-90 days, price changes ±10-25%
        changes = []
        change_day = random.randint(30, 90)
        while change_day < days:
            pct_change = random.uniform(-0.20, 0.20)
            changes.append((change_day, pct_change))
            change_day += random.randint(30, 90)
        prod_price_schedules[p.id] = changes

    # Compute effective price per product per day
    def effective_price(product_id: str, day_idx: int) -> float:
        base = prod_baselines[product_id]["base_price"]
        cumulative = 0.0
        for (change_day, pct) in prod_price_schedules[product_id]:
            if day_idx >= change_day:
                cumulative += pct
        return round(max(base * 0.5, base * (1.0 + cumulative)), 2)

    for d_idx in range(days):
        for prod in products:
            meta = prod_baselines[prod.id]
            true_elast = meta["true_elasticity"]
            base_price = meta["base_price"]
            eff_price = effective_price(prod.id, d_idx)

            # Demand affected by price via ground-truth elasticity:
            # qty = base_qty * (eff_price / base_price) ^ true_elasticity
            price_ratio = eff_price / max(base_price, 0.01)
            price_effect = price_ratio ** true_elast if price_ratio > 0 else 1.0

            # seasonality: weekly + yearly
            weekly = math.sin(2 * math.pi * d_idx / 7)
            yearly = math.sin(2 * math.pi * d_idx / 365 + meta["seasonality_phase"])
            trend_factor = (meta["trend"] * (d_idx / 365))

            mean_demand = max(1, meta["base_qty"] * price_effect * (1.0 + trend_factor + 0.25 * weekly + 0.35 * yearly))
            qty = max(0, int(random.gauss(mean_demand, 2)))

            if qty > 0:
                record = SalesRecord(
                    tenant_id=tenant_id,
                    product_id=prod.id,
                    qty_sold=qty,
                    price=eff_price,   # Phase 2: record actual price (not constant base price)
                    date=current_date
                )
                db.add(record)
                sales_records.append(record)
        current_date += timedelta(days=1)
    db.commit()

    # 4. Create Finance Ledger (daily cash balance & budget)
    cash = 50000.0
    budget = 15000.0
    current_date = start_date

    sales_by_date = {}
    for r in sales_records:
        sales_by_date.setdefault(r.date, 0.0)
        sales_by_date[r.date] += r.qty_sold * r.price

    for d_idx in range(days):
        day_sales = sales_by_date.get(current_date, 0.0)
        expenses = day_sales * random.uniform(0.3, 0.5) + random.uniform(50.0, 150.0)
        cash += (day_sales - expenses)

        if current_date.day == 1:
            budget = max(5000.0, cash * 0.3)

        ledger = FinanceLedger(
            tenant_id=tenant_id,
            date=current_date,
        )
        ledger.cash_balance = round(cash, 2)
        ledger.budget_per_period = round(budget, 2)
        db.add(ledger)
        current_date += timedelta(days=1)
    db.commit()

    # 5. Phase 2: Supplier records (one per product, randomised variance + reliability)
    for prod in products:
        supplier = Supplier(
            tenant_id=tenant_id,
            product_id=prod.id,
            name=f"Supplier for {prod.name}",
            avg_lead_time_days=round(random.uniform(3.0, 14.0), 1),
            lead_time_std_dev=round(random.uniform(0.5, 4.0), 2),
            reliability_score=round(random.uniform(0.60, 0.99), 2),
            min_order_qty=random.choice([5, 10, 20, 25, 50]),
        )
        db.add(supplier)
    db.commit()

    # Sync suppliers to Neo4j graph (no-op when disabled)
    try:
        from backend.app.graph_db import graph_db as neo4j
        if neo4j.enabled:
            neo4j.sync_products_to_graph(tenant_id, products)
            suppliers_all = db.query(Supplier).filter_by(tenant_id=tenant_id).all()
            for s in suppliers_all:
                neo4j.sync_supplier_to_graph(tenant_id, s)
    except Exception as exc:
        print(f"[Generator] Neo4j sync skipped: {exc}")

    # 6. Populate AMDIE initial tenant state — Phase 2: scoped per decision_type
    all_agent_ids = ["inventory", "sales", "finance", "pricing", "marketing", "procurement"]
    # Map each agent to its primary decision_type
    agent_dt_map = {
        "inventory":   "reorder_quantity",
        "sales":       "reorder_quantity",
        "finance":     "reorder_quantity",
        "procurement": "reorder_quantity",
        "pricing":     "price_adjustment",
        "marketing":   "promotion_trigger",
    }

    for agent_id in all_agent_ids:
        dt = agent_dt_map[agent_id]
        metric = AgentAccuracy(
            tenant_id=tenant_id,
            agent_id=agent_id,
            decision_type=dt,
            last_accuracy=0.85,
            reliability=0.85
        )
        db.add(metric)

    # Seed historical accuracy (past 90 days) — only for Phase 1 agents initially
    h_date = start_date + timedelta(days=days - 90)
    for _ in range(90):
        for agent_id in ["inventory", "sales", "finance"]:
            log = HistoricalAccuracyLog(
                tenant_id=tenant_id,
                agent_id=agent_id,
                decision_type="reorder_quantity",
                date=h_date,
                accuracy=random.uniform(0.75, 0.95)
            )
            db.add(log)
        h_date += timedelta(days=1)

    # Phase 2: seed WeightCoefficients for each decision_type
    for dt in all_decision_types():
        weights = WeightCoefficients(
            tenant_id=tenant_id,
            decision_type=dt,
            w1=0.30, w2=0.20, w3=0.25, w4=0.10, w5=0.15, w6=0.15,
            trained_on_n_decisions=0
        )
        db.add(weights)
    db.commit()

    # 7. Seed Vector Knowledge
    supplier_notes = [
        "Supplier Acme Widgets delivery lead time is usually 5 days for Category Electronics.",
        "Reorder policy: Min order quantity for category Electronics is 20 units.",
        "Budget constraint rule: Purchasing expenses must not exceed available period budget.",
        "Holiday warning: Deliveries are delayed by 3 days during December.",
        # Phase 2 knowledge
        "Pricing policy: Discount promotions deeper than 30% require Owner approval.",
        "Procurement policy: Single-source suppliers carry higher delivery risk — diversify where possible.",
    ]
    for note in supplier_notes:
        vector_db.upsert_knowledge(tenant_id, "supplier_note", note)

    policies = [
        "Store policy indicates to maintain a minimum safety stock of 15% of lead time demand.",
        "Turnover policy: Priority is given to clearance of slow-moving inventory.",
        "Pricing policy: Price changes greater than 15% in a single cycle should be reviewed.",
    ]
    for policy in policies:
        vector_db.upsert_knowledge(tenant_id, "policy", policy)

    past_logs = [
        "Reorder decision for product PROD-001 category Electronics was executed successfully last quarter with high accuracy.",
        "Price adjustment for product PROD-003 resulted in 12% revenue increase with minimal stockout risk.",
    ]
    for log in past_logs:
        vector_db.upsert_knowledge(tenant_id, "past_decision_log", log)


def seed_db_script():
    import os
    from passlib.context import CryptContext
    from backend.app.db import SessionLocal, init_db, User
    init_db()   # Creates tables + runs Phase 2 migration backfill
    db = SessionLocal()
    # Check if a tenant already exists
    tenant = db.query(Tenant).filter_by(id=settings.DEMO_TENANT_ID).first()
    if not tenant:
        # Create Demo Tenant
        tenant = Tenant(
            id=settings.DEMO_TENANT_ID,
            name="Demo SME",
            api_key_hash="demo_api_key_hash",
            business_goal="maximize_profit"
        )
        db.add(tenant)
        db.commit()

    # Seed users if none exist for this tenant
    user_count = db.query(User).filter_by(tenant_id=tenant.id).count()
    if user_count == 0:
        from backend.app.auth import get_password_hash
        owner = User(
            tenant_id=tenant.id,
            email="owner@example.com",
            password_hash=get_password_hash(settings.SEED_DEFAULT_PASSWORD),
            role="owner"
        )
        maint = User(
            tenant_id=tenant.id,
            email="maint@example.com",
            password_hash=get_password_hash(settings.SEED_DEFAULT_PASSWORD),
            role="maintenance"
        )
        db.add(owner)
        db.add(maint)
        db.commit()
        print("Seeded owner and maintenance users.")


    # Verify if we have products seeded for this tenant
    prod_count = db.query(Product).filter_by(tenant_id=tenant.id).count()
    if prod_count == 0:
        print("Generating synthetic data for the demo tenant...")
        start_date = (utcnow() - timedelta(days=370)).date()
        generate_synthetic_data(db, tenant.id, start_date, days=370)
        print("Database seeded successfully with Tenant, Products, Sales, Supplier, Ledger and Vector Knowledge.")
    else:
        print("Database already contains seed products and transactions.")

        # Phase 2 migration: backfill Supplier records if missing
        supplier_count = db.query(Supplier).filter_by(tenant_id=tenant.id).count()
        if supplier_count == 0:
            print("Backfilling Supplier records for existing products...")
            products = db.query(Product).filter_by(tenant_id=tenant.id).all()
            for prod in products:
                supplier = Supplier(
                    tenant_id=tenant.id,
                    product_id=prod.id,
                    name=f"Supplier for {prod.name}",
                    avg_lead_time_days=round(random.uniform(3.0, 14.0), 1),
                    lead_time_std_dev=round(random.uniform(0.5, 4.0), 2),
                    reliability_score=round(random.uniform(0.60, 0.99), 2),
                    min_order_qty=random.choice([5, 10, 20, 25, 50]),
                )
                db.add(supplier)
            db.commit()
            print(f"Backfilled {len(products)} supplier records.")

        # Phase 2 migration: backfill WeightCoefficients for new decision_types
        for dt in all_decision_types():
            existing = db.query(WeightCoefficients).filter_by(
                tenant_id=tenant.id, decision_type=dt
            ).first()
            if not existing:
                db.add(WeightCoefficients(
                    tenant_id=tenant.id,
                    decision_type=dt,
                    w1=0.30, w2=0.20, w3=0.25, w4=0.10, w5=0.15, w6=0.15,
                    trained_on_n_decisions=0,
                ))
        db.commit()

    db.close()
