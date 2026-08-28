import uuid
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Float, Integer, Date, DateTime, Boolean, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from backend.app.config import settings
from backend.app.security import encrypt_val, decrypt_val

Base = declarative_base()

# Engine and Session setup
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── Models ─────────────────────────────────────────────────────────────────────

class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    api_key_hash = Column(String, unique=True, nullable=False)
    business_goal = Column(String, default="maximize_profit")  # maximize_profit, minimize_cost, minimize_risk, maximize_turnover
    # Phase 2: feature-flag for HR Agent (not activated this pass — schema only)
    enables_hr_agent = Column(Boolean, default=False)

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="owner") # "owner" or "maintenance"
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

class Product(Base):
    __tablename__ = "products"
    id = Column(String, primary_key=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    unit_price = Column(Float, nullable=False)
    unit_cost_encrypted = Column(String, nullable=False)
    warehouse_capacity_limit = Column(Float, nullable=True)
    
    # Phase 3: Retail/POS extensions
    barcode = Column(String, nullable=True)
    sku = Column(String, nullable=True)
    min_stock = Column(Integer, default=0)
    max_stock = Column(Integer, default=1000)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'barcode', name='uq_tenant_barcode'),
    )

    @property
    def unit_cost(self) -> float:
        return decrypt_val(self.unit_cost_encrypted, float)

    @unit_cost.setter
    def unit_cost(self, val: float):
        self.unit_cost_encrypted = encrypt_val(val)

class InventoryState(Base):
    __tablename__ = "inventory_states"
    product_id = Column(String, ForeignKey("products.id"), primary_key=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    stock_level = Column(Integer, nullable=False)
    lead_time_days = Column(Integer, nullable=False)
    reorder_point = Column(Integer, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SalesRecord(Base):
    __tablename__ = "sales_records"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    product_id = Column(String, ForeignKey("products.id"), nullable=False)
    qty_sold = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    date = Column(Date, nullable=False)

class FinanceLedger(Base):
    __tablename__ = "finance_ledgers"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    date = Column(Date, nullable=False)
    cash_balance_encrypted = Column(String, nullable=False)
    budget_per_period_encrypted = Column(String, nullable=False)

    @property
    def cash_balance(self) -> float:
        return decrypt_val(self.cash_balance_encrypted, float)

    @cash_balance.setter
    def cash_balance(self, val: float):
        self.cash_balance_encrypted = encrypt_val(val)

    @property
    def budget_per_period(self) -> float:
        return decrypt_val(self.budget_per_period_encrypted, float)

    @budget_per_period.setter
    def budget_per_period(self, val: float):
        self.budget_per_period_encrypted = encrypt_val(val)

# ── Phase 3: Retail POS & Store Management Tables ─────────────────────────────

class Customer(Base):
    __tablename__ = "customers"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Sale(Base):
    __tablename__ = "sales"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    payment_method = Column(String, nullable=False)
    discount = Column(Float, default=0.0)
    tax = Column(Float, default=0.0)
    subtotal = Column(Float, nullable=False)
    total = Column(Float, nullable=False)
    status = Column(String, default="completed") # completed, held
    created_at = Column(DateTime, default=datetime.utcnow)

class SaleItem(Base):
    __tablename__ = "sale_items"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sale_id = Column(String, ForeignKey("sales.id"), nullable=False)
    product_id = Column(String, ForeignKey("products.id"), nullable=False)
    qty = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    discount = Column(Float, default=0.0)

class SupplierProfile(Base):
    __tablename__ = "supplier_profiles"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    name = Column(String, nullable=False)
    contact_phone = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    address = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    supplier_profile_id = Column(String, ForeignKey("supplier_profiles.id"), nullable=False)
    status = Column(String, default="draft") # draft, ordered, received
    created_at = Column(DateTime, default=datetime.utcnow)
    received_at = Column(DateTime, nullable=True)

class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    po_id = Column(String, ForeignKey("purchase_orders.id"), nullable=False)
    product_id = Column(String, ForeignKey("products.id"), nullable=False)
    qty = Column(Integer, nullable=False)
    unit_cost = Column(Float, nullable=False)

class StockMovement(Base):
    __tablename__ = "stock_movements"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    product_id = Column(String, ForeignKey("products.id"), nullable=False)
    delta = Column(Integer, nullable=False)
    reason = Column(String, nullable=False) # sale, po_receipt, manual_adj
    reference_id = Column(String, nullable=True) # sale_id or po_id
    created_at = Column(DateTime, default=datetime.utcnow)

# ── Phase 2: Supplier table ───────────────────────────────────────────────────

class Supplier(Base):
    """
    Per-supplier delivery profile used by the Procurement Agent.
    One supplier row per (tenant, product) pair — a product may have multiple
    suppliers (different rows with same product_id).  The Procurement Agent
    picks the *best* supplier (lowest combined risk / lead-time variance).
    """
    __tablename__ = "suppliers"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    product_id = Column(String, ForeignKey("products.id"), nullable=False)
    name = Column(String, nullable=False, default="Default Supplier")
    avg_lead_time_days = Column(Float, nullable=False, default=7.0)
    lead_time_std_dev = Column(Float, nullable=False, default=1.5)
    reliability_score = Column(Float, nullable=False, default=0.85)  # [0, 1]
    min_order_qty = Column(Integer, nullable=False, default=10)
    
    # Phase 3: Link delivery profile to global Supplier Profile
    supplier_profile_id = Column(String, ForeignKey("supplier_profiles.id"), nullable=True)

# ── AMDIE tracking tables (Phase 2 — decision_type scoped) ───────────────────

class AgentAccuracy(Base):
    __tablename__ = "agent_accuracies"
    tenant_id = Column(String, ForeignKey("tenants.id"), primary_key=True)
    agent_id = Column(String, primary_key=True)  # "inventory", "sales", "finance", "pricing", …
    # Phase 2: each agent tracks accuracy independently per decision_type
    decision_type = Column(String, primary_key=True, default="reorder_quantity")
    last_accuracy = Column(Float, default=1.0)
    reliability = Column(Float, default=1.0)
    updated_at = Column(DateTime, default=datetime.utcnow)

class HistoricalAccuracyLog(Base):
    __tablename__ = "historical_accuracy_logs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    agent_id = Column(String, nullable=False)
    # Phase 2: scope logs by decision_type so reorder and pricing histories don't mix
    decision_type = Column(String, nullable=False, default="reorder_quantity")
    date = Column(Date, nullable=False)
    accuracy = Column(Float, nullable=False)

class DecisionLog(Base):
    __tablename__ = "decision_logs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    product_id = Column(String, ForeignKey("products.id"), nullable=False)
    date = Column(Date, nullable=False)
    # Phase 2: which AMDIE cycle produced this log
    decision_type = Column(String, nullable=False, default="reorder_quantity")
    business_goal_applied = Column(String, nullable=False)
    conflict_detected = Column(Boolean, default=False)
    conflict_score = Column(Float, default=0.0)
    fused_recommendation = Column(Float, nullable=False)
    fused_utility = Column(Float, nullable=False)

    # Store complex JSON payloads as strings/texts (compatible with all backends)
    agent_decisions = Column(Text, nullable=False)
    weights = Column(Text, nullable=False)
    optimization_problem = Column(Text, nullable=False)
    retrieval_log = Column(Text, nullable=False)
    natural_language_explanation = Column(Text, nullable=False)
    actual_outcome = Column(Float, nullable=True)

class WeightCoefficients(Base):
    __tablename__ = "weight_coefficients"
    tenant_id = Column(String, ForeignKey("tenants.id"), primary_key=True)
    # Phase 2: a tenant's weight for "sales" in reorder_quantity may differ from
    # its weight in price_adjustment — each (tenant, decision_type) pair has its
    # own w1..w6 coefficients trained independently.
    decision_type = Column(String, primary_key=True, default="reorder_quantity")
    # Domain-informed cold-start priors (uniform 0.2 replaced by evidence-based defaults).
    # These are overwritten once >= 30 decisions with outcomes are logged (see weights.py).
    w1 = Column(Float, default=0.30)   # reliability — strongest predictor of past accuracy
    w2 = Column(Float, default=0.20)   # confidence — agent's self-assessed uncertainty
    w3 = Column(Float, default=0.25)   # historical_accuracy — direct outcome tracking
    w4 = Column(Float, default=0.10)   # context_relevance — embedding similarity
    w5 = Column(Float, default=0.15)   # risk_score penalty
    w6 = Column(Float, default=0.15)   # outlier divergence penalty
    trained_on_n_decisions = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)


# ── Database initialisation + Phase 2 migration backfill ─────────────────────

def _backfill_decision_type(engine):
    """
    Backfill Phase 1 rows and safely migrate SQLite table schemas to support
    composite primary keys (tenant_id, decision_type). Idempotent.
    """
    from sqlalchemy import text
    with engine.connect() as conn:
        # 1. Safely add missing columns
        column_additions = [
            ("tenants", "enables_hr_agent", "BOOLEAN DEFAULT 0"),
            ("decision_logs", "decision_type", "VARCHAR DEFAULT 'reorder_quantity'"),
            ("historical_accuracy_logs", "decision_type", "VARCHAR DEFAULT 'reorder_quantity'"),
            ("products", "barcode", "VARCHAR"),
            ("products", "sku", "VARCHAR"),
            ("products", "min_stock", "INTEGER DEFAULT 0"),
            ("products", "max_stock", "INTEGER DEFAULT 1000"),
            ("products", "is_active", "BOOLEAN DEFAULT 1"),
            ("suppliers", "supplier_profile_id", "VARCHAR"),
        ]
        for table, col, col_type in column_additions:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                conn.commit()
            except Exception:
                pass

        # 2. SQLite Migration: Rebuild tables where Primary Key changed to include decision_type
        # If weight_coefficients has a single PK on tenant_id, rebuild it with (tenant_id, decision_type)
        if engine.dialect.name == "sqlite":
            try:
                # Check if weight_coefficients needs migration
                pk_info = conn.execute(text("PRAGMA table_info(weight_coefficients)")).fetchall()
                # pk_info: [(cid, name, type, notnull, dflt_value, pk), ...]
                pk_cols = [row[1] for row in pk_info if row[5] > 0]
                if "decision_type" not in pk_cols and len(pk_info) > 0:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS weight_coefficients_new (
                            tenant_id VARCHAR NOT NULL,
                            decision_type VARCHAR NOT NULL DEFAULT 'reorder_quantity',
                            w1 FLOAT,
                            w2 FLOAT,
                            w3 FLOAT,
                            w4 FLOAT,
                            w5 FLOAT,
                            w6 FLOAT,
                            trained_on_n_decisions INTEGER,
                            updated_at DATETIME,
                            PRIMARY KEY (tenant_id, decision_type),
                            FOREIGN KEY(tenant_id) REFERENCES tenants (id)
                        )
                    """))
                    conn.execute(text("""
                        INSERT OR IGNORE INTO weight_coefficients_new (tenant_id, decision_type, w1, w2, w3, w4, w5, w6, trained_on_n_decisions, updated_at)
                        SELECT tenant_id, 'reorder_quantity', w1, w2, w3, w4, w5, COALESCE(w6, 0.15), trained_on_n_decisions, updated_at FROM weight_coefficients
                    """))
                    conn.execute(text("DROP TABLE weight_coefficients"))
                    conn.execute(text("ALTER TABLE weight_coefficients_new RENAME TO weight_coefficients"))
                    conn.commit()
            except Exception as e:
                pass

            try:
                # Check if agent_accuracies needs migration
                pk_info_acc = conn.execute(text("PRAGMA table_info(agent_accuracies)")).fetchall()
                pk_cols_acc = [row[1] for row in pk_info_acc if row[5] > 0]
                if "decision_type" not in pk_cols_acc and len(pk_info_acc) > 0:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS agent_accuracies_new (
                            tenant_id VARCHAR NOT NULL,
                            agent_id VARCHAR NOT NULL,
                            decision_type VARCHAR NOT NULL DEFAULT 'reorder_quantity',
                            last_accuracy FLOAT,
                            reliability FLOAT,
                            updated_at DATETIME,
                            PRIMARY KEY (tenant_id, agent_id, decision_type),
                            FOREIGN KEY(tenant_id) REFERENCES tenants (id)
                        )
                    """))
                    conn.execute(text("""
                        INSERT OR IGNORE INTO agent_accuracies_new (tenant_id, agent_id, decision_type, last_accuracy, reliability, updated_at)
                        SELECT tenant_id, agent_id, 'reorder_quantity', last_accuracy, reliability, updated_at FROM agent_accuracies
                    """))
                    conn.execute(text("DROP TABLE agent_accuracies"))
                    conn.execute(text("ALTER TABLE agent_accuracies_new RENAME TO agent_accuracies"))
                    conn.commit()
            except Exception as e:
                pass

        # --- decision_logs backfill ---
        try:
            conn.execute(text(
                "UPDATE decision_logs SET decision_type = 'reorder_quantity' "
                "WHERE decision_type IS NULL OR decision_type = ''"
            ))
            conn.commit()
        except Exception:
            pass

        # --- historical_accuracy_logs backfill ---
        try:
            conn.execute(text(
                "UPDATE historical_accuracy_logs SET decision_type = 'reorder_quantity' "
                "WHERE decision_type IS NULL OR decision_type = ''"
            ))
            conn.commit()
        except Exception:
            pass



def init_db():
    Base.metadata.create_all(bind=engine)
    _backfill_decision_type(engine)

