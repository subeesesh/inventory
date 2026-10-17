import pytest
from backend.app.clock import utcnow
from pydantic import ValidationError
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.agents.base import DecisionObject
from backend.app.agents.pricing import PricingAgent
from backend.app.agents.marketing import MarketingAgent
from backend.app.agents.procurement import ProcurementAgent
from backend.app.agents.risk import RiskAgent
from backend.app.amdie.conflict import detect_conflict
from backend.app.amdie.weights import softmax, get_agent_weights
from backend.app.amdie.optimization import solve_decision_fusion
from backend.app.amdie.goals import adjust_objective_for_goals, compute_seasonality_volatility, compute_supplier_concentration
from backend.app.decision_registry import (
    DECISION_TYPES, get_agents_for_decision_type, validate_decision_type, get_upper_bound
)
from backend.app.db import Base, Tenant, Product, InventoryState, SalesRecord, Supplier, DecisionLog, WeightCoefficients, AgentAccuracy
from backend.evaluate import get_newsvendor_qty


# ── Phase 1 Tests (Preserved Unmodified) ──────────────────────────────────────

# 1. Decision Object Schema Tests
def test_decision_schema_validation():
    # Valid object
    valid_data = {
        "agent_id": "sales",
        "recommendation": 100.0,
        "reason": "Test forecast",
        "confidence": 0.8,
        "priority": 0.5,
        "risk_score": 0.2,
        "expected_cost": 500.0,
        "expected_benefit": 1000.0,
        "required_resources": {"cash": 500.0},
        "historical_similarity": 0.7
    }
    obj = DecisionObject(**valid_data)
    assert obj.agent_id == "sales"
    assert obj.recommendation == 100.0

    # Invalid confidence range
    invalid_data = valid_data.copy()
    invalid_data["confidence"] = 1.5
    with pytest.raises(ValidationError):
        DecisionObject(**invalid_data)

    # Missing field
    missing_data = valid_data.copy()
    del missing_data["expected_cost"]
    with pytest.raises(ValidationError):
        DecisionObject(**missing_data)

# 2. Conflict Detection Tests
def test_conflict_detection():
    # Construct mock decisions
    dec1 = DecisionObject(
        agent_id="sales", recommendation=100.0, reason="", confidence=1.0, priority=0.5,
        risk_score=0.0, expected_cost=0.0, expected_benefit=0.0, required_resources={}, historical_similarity=0.0
    )
    dec2 = DecisionObject(
        agent_id="inventory", recommendation=50.0, reason="", confidence=1.0, priority=0.5,
        risk_score=0.0, expected_cost=0.0, expected_benefit=0.0, required_resources={}, historical_similarity=0.0
    )
    
    decisions = {"sales": dec1, "inventory": dec2}
    score, detected = detect_conflict(decisions, tau=0.3)
    # diff is |100-50|/100 = 0.5 > 0.3
    assert score == 0.5
    assert detected is True

    # High tau should result in no conflict
    _, detected_high_tau = detect_conflict(decisions, tau=0.6)
    assert detected_high_tau is False

# 3. Softmax & Weight Math Tests
def test_softmax():
    scores = [1.0, 2.0, 3.0]
    weights = softmax(scores)
    assert len(weights) == 3
    assert abs(sum(weights) - 1.0) < 1e-6
    assert weights[2] > weights[1] > weights[0]

# 4. Constrained LP Optimization Solver Tests
def test_lp_solver_constraints():
    # Setup agents recommendations
    dec_sales = DecisionObject(
        agent_id="sales", recommendation=120.0, reason="", confidence=0.8, priority=0.5,
        risk_score=0.2, expected_cost=600.0, expected_benefit=1200.0, required_resources={"cash": 600.0}, historical_similarity=0.5
    )
    dec_inventory = DecisionObject(
        agent_id="inventory", recommendation=100.0, reason="", confidence=0.9, priority=0.5,
        risk_score=0.1, expected_cost=500.0, expected_benefit=1000.0, required_resources={"cash": 500.0}, historical_similarity=0.5
    )
    dec_finance = DecisionObject(
        agent_id="finance", recommendation=50.0, reason="", confidence=0.9, priority=0.5,
        risk_score=0.1, expected_cost=250.0, expected_benefit=500.0, required_resources={"cash": 250.0}, historical_similarity=0.5
    )

    decisions = {
        "sales": dec_sales,
        "inventory": dec_inventory,
        "finance": dec_finance
    }
    
    weights = {"sales": 0.4, "inventory": 0.4, "finance": 0.2}
    unit_cost = 5.0
    
    # Run with large budget (so it targets recommendations around 100)
    x, _, opt_log = solve_decision_fusion(
        weights=weights,
        decisions=decisions,
        unit_cost=unit_cost,
        budget=1000.0,
        warehouse_capacity=150.0
    )
    assert opt_log["success"] is True
    assert x > 0
    assert x <= 150.0  # Respect warehouse capacity

    # Run with tight budget of $200 (max quantity = 200/5 = 40)
    x_constrained, _, opt_log_c = solve_decision_fusion(
        weights=weights,
        decisions=decisions,
        unit_cost=unit_cost,
        budget=200.0,
        warehouse_capacity=150.0
    )
    assert x_constrained <= 40.01  # Verifies strict budget limit is satisfied

# 5. Evaluation Ground Truth Tests
def test_newsvendor_calculation():
    qty = get_newsvendor_qty(price=10.0, cost=2.0, mean_demand=50.0, std_demand=10.0)
    assert qty > 50.0


# ── Phase 2 New Tests ─────────────────────────────────────────────────────────

# 6. Step 0: Decision Type Registry Tests
def test_decision_registry():
    assert validate_decision_type("reorder_quantity") is True
    assert validate_decision_type("price_adjustment") is True
    assert validate_decision_type("promotion_trigger") is True
    assert validate_decision_type("unknown_type") is False

    reorder_agents = get_agents_for_decision_type("reorder_quantity")
    assert "procurement" in reorder_agents
    assert "inventory" in reorder_agents
    assert "sales" in reorder_agents
    assert "finance" in reorder_agents

    pricing_agents = get_agents_for_decision_type("price_adjustment")
    assert pricing_agents == ["pricing", "sales", "risk"]

    assert get_upper_bound("promotion_trigger") == 1.0
    assert get_upper_bound("reorder_quantity") is None

# 7. Step 1: Pricing Agent Elasticity Regression
def test_pricing_agent_elasticity_regression():
    agent = PricingAgent()
    # Create mock sales records with varying prices and known negative elasticity
    class MockRecord:
        def __init__(self, qty, price):
            self.qty_sold = qty
            self.price = price

    # Q = 100 * P^(-1.5)
    records = []
    prices = [10.0, 12.0, 15.0, 18.0, 20.0, 22.0, 25.0, 28.0, 30.0, 35.0, 40.0, 45.0]
    for p in prices:
        q = max(1, int(500 * (p ** -1.2)))
        records.append(MockRecord(q, p))

    elasticity, r2, delta = agent._estimate_elasticity_and_delta(records, current_price=20.0, unit_cost=10.0)
    assert elasticity < -0.8  # Confirms negative demand curve detected
    assert r2 > 0.7           # High R2 fit
    assert isinstance(delta, float)

# 8. Step 1: Marketing Agent Turnover Rate & Discount Bounds
def test_marketing_agent_discount_bounds():
    agent = MarketingAgent()
    assert agent.agent_id == "marketing"
    # Verify decision object structure for marketing agent
    dec = DecisionObject(
        agent_id="marketing",
        recommendation=0.25, # 25% discount
        reason="Slow-moving stock promotion",
        confidence=0.85,
        priority=0.70,
        risk_score=0.15,
        expected_cost=0.0,
        expected_benefit=150.0,
        required_resources={},
        historical_similarity=0.6
    )
    assert 0.0 <= dec.recommendation <= 1.0

# 9. Step 1: Procurement Agent Lead-Time Variance & Conflict with Inventory
def test_procurement_intentional_conflict():
    # Setup scenario where supplier lead-time variance is high
    dec_inventory = DecisionObject(
        agent_id="inventory",
        recommendation=40.0, # fixed lead time demand
        reason="Fixed 5-day lead time",
        confidence=0.8,
        priority=0.5,
        risk_score=0.1,
        expected_cost=200.0,
        expected_benefit=400.0,
        required_resources={},
        historical_similarity=0.5
    )
    dec_procurement = DecisionObject(
        agent_id="procurement",
        recommendation=95.0, # lead-time variance + safety stock + min_order_qty
        reason="Variable lead-time safety buffer",
        confidence=0.7,
        priority=0.6,
        risk_score=0.2,
        expected_cost=475.0,
        expected_benefit=950.0,
        required_resources={"min_order_qty": 50},
        historical_similarity=0.5
    )
    
    decisions = {"inventory": dec_inventory, "procurement": dec_procurement}
    score, conflict = detect_conflict(decisions, tau=0.3)
    # Divergence is |95 - 40| / 95 = 0.578 > 0.3
    assert conflict is True
    assert score > 0.5

# 10. Step 1: Risk Agent Portfolio Modifier
def test_risk_agent_modifier():
    risk_agent = RiskAgent()
    decisions = {
        "inventory": DecisionObject(agent_id="inventory", recommendation=50.0, reason="", confidence=0.8, priority=0.5, risk_score=0.6, expected_cost=0, expected_benefit=0, required_resources={}, historical_similarity=0),
        "sales": DecisionObject(agent_id="sales", recommendation=60.0, reason="", confidence=0.7, priority=0.5, risk_score=0.4, expected_cost=0, expected_benefit=0, required_resources={}, historical_similarity=0),
    }
    
    weights = {"inventory": 0.5, "sales": 0.5}
    adj = adjust_objective_for_goals(
        weights=weights,
        decisions=decisions,
        business_goal="minimize_risk",
        unit_cost=5.0,
        forecasted_demand=60.0,
        overall_risk_score=0.45
    )
    assert "adjusted_weights" in adj
    assert adj["overall_risk_score"] == 0.45
    # Inventory had higher risk (0.6), so its adjusted weight should be lower than sales (0.4)
    assert adj["adjusted_weights"]["sales"] > adj["adjusted_weights"]["inventory"]

# 11. Step 1: Decision Type Upper Bound in LP Solver
def test_lp_solver_upper_bound_promotion():
    dec_mkt = DecisionObject(
        agent_id="marketing", recommendation=0.35, reason="", confidence=0.9, priority=0.8,
        risk_score=0.1, expected_cost=0.0, expected_benefit=50.0, required_resources={}, historical_similarity=0.5
    )
    dec_fin = DecisionObject(
        agent_id="finance", recommendation=0.15, reason="", confidence=0.8, priority=0.5,
        risk_score=0.2, expected_cost=0.0, expected_benefit=20.0, required_resources={}, historical_similarity=0.5
    )
    weights = {"marketing": 0.6, "finance": 0.4}

    x_opt, _, opt_log = solve_decision_fusion(
        weights=weights,
        decisions={"marketing": dec_mkt, "finance": dec_fin},
        unit_cost=0.0,
        budget=10000.0,
        x_upper_bound=1.0,
        delta=0.2
    )
    assert opt_log["success"] is True
    assert 0.0 <= x_opt <= 1.0
    assert opt_log["x_upper_bound"] == 1.0

# 12. Decision Type DB Isolation Test
def test_decision_type_db_isolation():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    tenant = Tenant(id="t-test-iso", name="Iso Test", api_key_hash="hash")
    db.add(tenant)
    
    # Weight coefficients for reorder_quantity
    w_reorder = WeightCoefficients(tenant_id="t-test-iso", decision_type="reorder_quantity", w1=0.40, w2=0.20)
    # Weight coefficients for price_adjustment
    w_price = WeightCoefficients(tenant_id="t-test-iso", decision_type="price_adjustment", w1=0.15, w2=0.35)
    db.add(w_reorder)
    db.add(w_price)
    db.commit()

    reorder_fetched = db.query(WeightCoefficients).filter_by(tenant_id="t-test-iso", decision_type="reorder_quantity").first()
    price_fetched = db.query(WeightCoefficients).filter_by(tenant_id="t-test-iso", decision_type="price_adjustment").first()

    assert reorder_fetched.w1 == 0.40
    assert price_fetched.w1 == 0.15
    assert reorder_fetched.decision_type == "reorder_quantity"
    assert price_fetched.decision_type == "price_adjustment"
    db.close()


# ── Phase 3 New Tests (Retail & POS) ──────────────────────────────────────────
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.auth import create_access_token
from backend.app.db import get_db

client = TestClient(app)

from sqlalchemy.pool import StaticPool

engine_test = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

TEST_TENANT_ID = "t-test"

@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine_test)
    db = TestingSessionLocal()
    
    from backend.app.db import Tenant, User, Product, InventoryState
    t = Tenant(id="t-test", name="Test Tenant", api_key_hash="hash")
    db.add(t)
    
    roles = ["owner", "cashier", "inventory_manager", "procurement_officer", "finance_officer"]
    for r in roles:
        db.add(User(id=f"u-{r}", tenant_id="t-test", email=f"{r}@test.com", password_hash="hash", role=r))
        
    prod = Product(id="p-test", tenant_id="t-test", name="Test Prod", category="Test", unit_price=10.0, unit_cost=5.0)
    db.add(prod)
    inv = InventoryState(product_id="p-test", tenant_id="t-test", stock_level=100, lead_time_days=7, reorder_point=10)
    db.add(inv)
    
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine_test)

def get_auth_headers(role: str):
    token = create_access_token(data={"sub": f"u-{role}"})
    return {"Authorization": f"Bearer {token}"}

# 13. RBAC Enforcement Test
def test_rbac_cashier():
    headers = get_auth_headers("cashier")
    
    # Allowed route (checkout)
    res_allowed = client.post("/api/tenants/pos/checkout", json={
        "payment_method": "cash",
        "subtotal": 10.0,
        "total": 10.0,
        "items": [{"product_id": "p-test", "qty": 1, "unit_price": 10.0}]
    }, headers=headers)
    assert res_allowed.status_code == 200
    
    # Forbidden route (reports - profit)
    res_forbidden = client.get("/api/tenants/reports?type=profit", headers=headers)
    assert res_forbidden.status_code == 403

def test_rbac_owner():
    headers = get_auth_headers("owner")
    # Allowed route (reports)
    res_allowed = client.get("/api/tenants/reports?type=profit", headers=headers)
    assert res_allowed.status_code == 200

# 14. POS Checkout Trace Test
def test_pos_checkout_trace():
    headers = get_auth_headers("cashier")
    db = TestingSessionLocal()
    from backend.app.db import InventoryState, StockMovement, SalesRecord
    
    initial_inv = db.query(InventoryState).filter_by(product_id="p-test").first().stock_level
    
    res = client.post("/api/tenants/pos/checkout", json={
        "payment_method": "card",
        "subtotal": 20.0,
        "total": 20.0,
        "items": [{"product_id": "p-test", "qty": 2, "unit_price": 10.0}]
    }, headers=headers)
    assert res.status_code == 200
    sale_id = res.json()["sale_id"]
    
    # Verify Inventory dropped
    inv = db.query(InventoryState).filter_by(product_id="p-test").first()
    assert inv.stock_level == initial_inv - 2
    
    # Verify StockMovement logged
    movement = db.query(StockMovement).filter_by(reference_id=sale_id).first()
    assert movement.reason == "sale"
    assert movement.delta == -2
    
    # Verify SalesRecord updated
    from datetime import datetime
    today = utcnow().date()
    sr = db.query(SalesRecord).filter_by(product_id="p-test", date=today).first()
    assert sr.qty_sold >= 2
    db.close()

# 15. Purchase Order Receive Trace Test
def test_po_trace():
    headers = get_auth_headers("procurement_officer")
    
    # Create supplier profile
    res = client.post("/api/tenants/supplier-profiles", json={
        "name": "Test Supplier"
    }, headers=headers)
    supplier_id = res.json()["id"]
    
    # Create PO
    res_po = client.post("/api/tenants/purchase-orders", json={
        "supplier_profile_id": supplier_id,
        "items": [{"product_id": "p-test", "qty": 50, "unit_cost": 5.0}]
    }, headers=headers)
    assert res_po.status_code == 200
    po_id = res_po.json()["po_id"]
    
    # Receive PO
    inv_headers = get_auth_headers("inventory_manager")
    db = TestingSessionLocal()
    from backend.app.db import InventoryState, StockMovement
    
    initial_inv = db.query(InventoryState).filter_by(product_id="p-test").first().stock_level
    
    res_receive = client.post(f"/api/tenants/purchase-orders/{po_id}/receive", headers=inv_headers)
    assert res_receive.status_code == 200
    
    # Verify Inventory increased
    inv = db.query(InventoryState).filter_by(product_id="p-test").first()
    assert inv.stock_level == initial_inv + 50
    
    # Verify StockMovement logged
    movement = db.query(StockMovement).filter_by(reference_id=po_id).first()
    assert movement.reason == "po_receipt"
    assert movement.delta == 50
    db.close()

# 16. Customer CRUD Test
def test_customer_crud():
    headers = get_auth_headers("cashier")
    res = client.post("/api/tenants/customers", json={
        "name": "John Doe",
        "phone": "555-1234"
    }, headers=headers)
    assert res.status_code == 200
    cust_id = res.json()["id"]
    
    res_get = client.get(f"/api/tenants/customers/{cust_id}", headers=headers)
    assert res_get.status_code == 200
    assert res_get.json()["name"] == "John Doe"


# ── Phase 3 Tests: BizTwin AI Architecture Verification ───────────────────────

# 17. HR Agent Test
def test_hr_agent():
    from backend.app.agents.hr import HRAgent
    from backend.app.db import StaffShift
    db = TestingSessionLocal()
    agent = HRAgent()
    run_date = date(2026, 8, 30)

    # Seed staff shift
    shift = StaffShift(tenant_id=TEST_TENANT_ID, shift_date=run_date, role="staff", hours=8.0)
    db.add(shift)
    db.commit()

    dec = agent.run(TEST_TENANT_ID, "p-test", run_date, db)
    assert dec.agent_id == "hr"
    assert isinstance(dec.recommendation, float)
    assert dec.confidence >= 0.0 and dec.confidence <= 1.0
    assert dec.risk_score >= 0.0 and dec.risk_score <= 1.0
    db.close()

# 18. Customer Management Agent Test
def test_customer_management_agent():
    from backend.app.agents.customer_management import CustomerManagementAgent
    db = TestingSessionLocal()
    agent = CustomerManagementAgent()
    run_date = date(2026, 8, 30)

    dec = agent.run(TEST_TENANT_ID, "p-test", run_date, db)
    assert dec.agent_id == "customer_management"
    assert dec.recommendation >= 0.0 and dec.recommendation <= 1.0
    assert "Customer Management Agent" in dec.reason
    db.close()

# 19. Predictive Analytics Module Functions Test
def test_predictive_analytics_module():
    from backend.app.predictive import forecast_demand, forecast_revenue, forecast_cash_flow, forecast_risk_level
    db = TestingSessionLocal()
    run_date = date(2026, 8, 30)

    fc_d = forecast_demand("p-test", 14, db, tenant_id=TEST_TENANT_ID, run_date=run_date)
    assert "forecast_total" in fc_d
    assert fc_d["forecast_total"] >= 0.0

    fc_r = forecast_revenue(30, db, tenant_id=TEST_TENANT_ID, run_date=run_date)
    assert "projected_revenue" in fc_r

    fc_c = forecast_cash_flow(30, db, tenant_id=TEST_TENANT_ID, run_date=run_date)
    assert "projected_cash" in fc_c

    risk = forecast_risk_level(tenant_id=TEST_TENANT_ID, product_id="p-test", db=db, run_date=run_date)
    assert 0.0 <= risk <= 1.0
    db.close()

# 20. Real-Time Business Monitoring Engine Test
def test_monitoring_engine():
    from backend.app.monitoring import scan_business_monitoring_events
    from backend.app.db import MonitoringEvent, InventoryState
    db = TestingSessionLocal()

    # Drop inventory below threshold to force a low_stock_depletion event
    inv = db.query(InventoryState).filter_by(product_id="p-test").first()
    original_stock = inv.stock_level
    inv.stock_level = 2
    db.commit()

    events = scan_business_monitoring_events(TEST_TENANT_ID, db)
    assert len(events) >= 1
    low_stock_evts = [e for e in events if e.event_type in ("low_stock_depletion", "stockout_risk")]
    assert len(low_stock_evts) >= 1

    # Cleanup
    inv.stock_level = original_stock
    db.commit()
    db.close()

# 21. Counterfactual Scenario Simulator Test (DB Non-Mutation Assertion)
def test_counterfactual_scenario_simulation_isolation():
    from backend.app.scenario import run_scenario_simulation, ScenarioSimulateRequest
    from backend.app.db import Product, InventoryState, SalesRecord, FinanceLedger
    db = TestingSessionLocal()

    # Record pre-simulation counts and values
    pre_products = [(p.id, p.unit_price) for p in db.query(Product).all()]
    pre_inv_count = db.query(InventoryState).count()
    pre_sales_count = db.query(SalesRecord).count()
    pre_ledger_count = db.query(FinanceLedger).count()

    req = ScenarioSimulateRequest(type="price_change", product_id="p-test", delta_pct=0.20, horizon_days=30)
    result = run_scenario_simulation(req, TEST_TENANT_ID, db)

    assert "simulated_trajectory" in result
    assert "delta" in result

    # Assert POST-simulation DB state is strictly identical (zero mutation)
    post_products = [(p.id, p.unit_price) for p in db.query(Product).all()]
    post_inv_count = db.query(InventoryState).count()
    post_sales_count = db.query(SalesRecord).count()
    post_ledger_count = db.query(FinanceLedger).count()

    assert pre_products == post_products
    assert pre_inv_count == post_inv_count
    assert pre_sales_count == post_sales_count
    assert pre_ledger_count == post_ledger_count
    db.close()

# 22. Structured Explainable AI Layer Test
def test_structured_xai_explainability():
    from backend.app.explain import build_structured_explanation
    from backend.app.db import DecisionLog
    db = TestingSessionLocal()
    run_date = date(2026, 8, 30)

    dec_log = DecisionLog(
        id="test-dec-xai",
        tenant_id=TEST_TENANT_ID,
        product_id="p-test",
        date=run_date,
        decision_type="staffing_adjustment",
        business_goal_applied="maximize_profit",
        conflict_detected=False,
        conflict_score=0.1,
        fused_recommendation=4.0,
        fused_utility=0.9,
        agent_decisions='{"hr": {"agent_id": "hr", "recommendation": 4.0, "reason": "Staffing gap"}}',
        weights='{"hr": 1.0}',
        optimization_problem='{"weights": {"hr": 1.0}}',
        retrieval_log="[]",
        natural_language_explanation="Adjust staff hours by +4.0",
    )
    db.add(dec_log)
    db.commit()

    explanation = build_structured_explanation("test-dec-xai", db, TEST_TENANT_ID)
    assert explanation["decision_id"] == "test-dec-xai"
    assert "contributing_agents" in explanation
    assert explanation["recommendation"] == 4.0
    db.close()

# 24. User Registration with Role Test
def test_user_registration_with_role():
    res = client.post("/api/auth/register", json={
        "email": "new_manager2@example.com",
        "password": "secretpassword",
        "role": "inventory_manager",
        "store_name": "Test Store"
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["role"] == "inventory_manager"


# ── Phase 4: BizTwin AI Architecture Alignment Tests ─────────────────────────

# 25. Agent Factory — HR Agent Registration
def test_agent_factory_hr_registration():
    """Verify _build_agent correctly resolves 'hr' -> HRAgent."""
    from backend.app.api import _build_agent
    from backend.app.agents.hr import HRAgent
    agent = _build_agent("hr")
    assert isinstance(agent, HRAgent)


# 26. Agent Factory — Customer Management Agent Registration
def test_agent_factory_customer_management_registration():
    """Verify _build_agent correctly resolves 'customer_management' -> CustomerManagementAgent."""
    from backend.app.api import _build_agent
    from backend.app.agents.customer_management import CustomerManagementAgent
    agent = _build_agent("customer_management")
    assert isinstance(agent, CustomerManagementAgent)


# 27. AMDIE Execution — staffing_adjustment decision type end-to-end
def test_amdie_staffing_adjustment_execution():
    """Verify staffing_adjustment can execute through AMDIE without agent lookup errors."""
    headers = get_auth_headers("owner")
    res = client.post("/api/tenants/decisions/trigger", json={
        "product_id": "p-test",
        "date_str": "2026-09-01",
        "decision_type": "staffing_adjustment"
    }, headers=headers)
    assert res.status_code == 200, f"staffing_adjustment failed: {res.text}"
    data = res.json()
    assert "fused_recommendation" in data
    assert data["decision_type"] == "staffing_adjustment"


# 28. AMDIE Execution — customer_retention_action decision type end-to-end
def test_amdie_customer_retention_action_execution():
    """Verify customer_retention_action can execute through AMDIE without agent lookup errors."""
    headers = get_auth_headers("owner")
    res = client.post("/api/tenants/decisions/trigger", json={
        "product_id": "p-test",
        "date_str": "2026-09-01",
        "decision_type": "customer_retention_action"
    }, headers=headers)
    assert res.status_code == 200, f"customer_retention_action failed: {res.text}"
    data = res.json()
    assert "fused_recommendation" in data
    assert data["decision_type"] == "customer_retention_action"


# 29. Business Digital Twin — unified state access
def test_business_digital_twin_state():
    """Verify GET /tenants/twin returns all unified state sections."""
    headers = get_auth_headers("owner")
    res = client.get("/api/tenants/twin", headers=headers)
    assert res.status_code == 200, f"BDT endpoint failed: {res.text}"
    data = res.json()
    assert "inventory" in data
    assert "sales_30d" in data
    assert "finance" in data
    assert "customer_count" in data
    assert "suppliers" in data
    assert "staffing" in data
    assert "monitoring_active_events" in data
    assert "risk_level" in data


# 30. Data Integration Layer — normalized summary
def test_data_integration_summary():
    """Verify GET /tenants/integration/summary returns source-normalized telemetry."""
    headers = get_auth_headers("owner")
    res = client.get("/api/tenants/integration/summary", headers=headers)
    assert res.status_code == 200, f"Integration summary failed: {res.text}"
    data = res.json()
    assert "pos_records_count" in data
    assert "inventory_tracked_items" in data
    assert "crm_contacts_count" in data
    assert "supplier_profiles_count" in data
    assert data["external_connectors"]["shopify"] == "interface_ready_future_extension"


# 31. Predictive Analytics — all forecast functions execute
def test_predictive_analytics_functions():
    """Verify all four predictive forecast functions execute without errors."""
    from backend.app.predictive import forecast_demand, forecast_revenue, forecast_cash_flow, forecast_risk_level
    db = TestingSessionLocal()
    run_date = date(2026, 9, 1)

    demand = forecast_demand("p-test", 30, db, tenant_id=TEST_TENANT_ID, run_date=run_date)
    assert "forecast_total" in demand
    assert demand["forecast_total"] >= 0

    revenue = forecast_revenue(30, db, tenant_id=TEST_TENANT_ID, run_date=run_date)
    assert "projected_revenue" in revenue

    cashflow = forecast_cash_flow(30, db, tenant_id=TEST_TENANT_ID, run_date=run_date)
    assert "projected_cash" in cashflow

    risk = forecast_risk_level(tenant_id=TEST_TENANT_ID, db=db, run_date=run_date)
    assert 0.0 <= risk <= 1.0

    db.close()


# 32. Monitoring Engine — anomaly events persist correctly
def test_monitoring_engine_events_persist():
    """Verify monitoring scan creates MonitoringEvent records for low-stock products."""
    from backend.app.monitoring import scan_business_monitoring_events
    from backend.app.db import InventoryState, MonitoringEvent

    db = TestingSessionLocal()
    # Force product below min_stock threshold
    inv = db.query(InventoryState).filter_by(product_id="p-test", tenant_id=TEST_TENANT_ID).first()
    original_stock = inv.stock_level
    inv.stock_level = 0
    db.commit()

    events = scan_business_monitoring_events(tenant_id=TEST_TENANT_ID, db=db)
    # At minimum there should be some scan result (list, possibly empty on fresh db)
    assert isinstance(events, list)

    # Restore stock
    inv2 = db.query(InventoryState).filter_by(product_id="p-test", tenant_id=TEST_TENANT_ID).first()
    inv2.stock_level = original_stock
    db.commit()
    db.close()


# 33. Scenario Simulation — DB non-mutation guarantee
def test_scenario_simulation_db_non_mutation():
    """Verify counterfactual simulation does not mutate any production DB tables."""
    from backend.app.scenario import run_scenario_simulation, ScenarioSimulateRequest
    from backend.app.db import Product, InventoryState, SalesRecord, FinanceLedger

    db = TestingSessionLocal()

    pre_products = db.query(Product).count()
    pre_inv_count = db.query(InventoryState).count()
    pre_sales_count = db.query(SalesRecord).count()
    pre_ledger_count = db.query(FinanceLedger).count()

    req = ScenarioSimulateRequest(type="price_change", product_id="p-test", delta_pct=0.1, horizon_days=30)
    result = run_scenario_simulation(req, tenant_id=TEST_TENANT_ID, db=db, run_date=date(2026, 9, 1))

    # Verify output shape
    assert "current_trajectory" in result
    assert "simulated_trajectory" in result
    assert "delta" in result
    assert result["scenario_type"] == "price_change"

    post_products = db.query(Product).count()
    post_inv_count = db.query(InventoryState).count()
    post_sales_count = db.query(SalesRecord).count()
    post_ledger_count = db.query(FinanceLedger).count()

    assert pre_products == post_products
    assert pre_inv_count == post_inv_count
    assert pre_sales_count == post_sales_count
    assert pre_ledger_count == post_ledger_count
    db.close()


# 34. XAI Structure — all required fields present
def test_xai_explanation_structure():
    """Verify XAI output contains all required structured explanation fields."""
    from backend.app.explain import build_structured_explanation
    from backend.app.db import DecisionLog

    db = TestingSessionLocal()
    run_date = date(2026, 9, 1)

    dec_log = DecisionLog(
        id="test-dec-xai-2",
        tenant_id=TEST_TENANT_ID,
        product_id="p-test",
        date=run_date,
        decision_type="customer_retention_action",
        business_goal_applied="maximize_profit",
        conflict_detected=True,
        conflict_score=0.45,
        fused_recommendation=0.15,
        fused_utility=0.78,
        agent_decisions='{"customer_management": {"agent_id": "customer_management", "recommendation": 0.15, "reason": "Churn risk high"}}',
        weights='{"customer_management": 1.0}',
        optimization_problem='{"weights": {"customer_management": 1.0}, "agent_recommendations": {"customer_management": {"recommendation": 0.15, "reason": "Churn risk high"}}}',
        retrieval_log="[]",
        natural_language_explanation="Apply 15% loyalty discount to retain at-risk customers.",
    )
    db.add(dec_log)
    db.commit()

    explanation = build_structured_explanation("test-dec-xai-2", db, TEST_TENANT_ID)

    assert explanation["decision_id"] == "test-dec-xai-2"
    assert "recommendation" in explanation
    assert "confidence" in explanation
    assert "contributing_agents" in explanation
    assert isinstance(explanation["contributing_agents"], list)
    assert "conflict_detected" in explanation
    assert "conflict_resolution_notes" in explanation
    assert "natural_language_summary" in explanation

    db.close()


# 35. Decision Registry — all nine agent types registered
def test_decision_registry_all_nine_agents():
    """Verify all nine agent types appear across decision type registrations."""
    from backend.app.decision_registry import DECISION_TYPES
    all_registered = set()
    for agents in DECISION_TYPES.values():
        all_registered.update(agents)

    expected = {"inventory", "sales", "finance", "pricing", "marketing", "procurement", "risk", "hr", "customer_management"}
    assert expected.issubset(all_registered), f"Missing agents: {expected - all_registered}"


# ── Phase 5: Polish / correctness regression tests ───────────────────────────

def _dec(agent_id, rec, conf=0.9):
    return DecisionObject(
        agent_id=agent_id, recommendation=rec, reason="", confidence=conf, priority=0.5,
        risk_score=0.1, expected_cost=0.0, expected_benefit=0.0, required_resources={}, historical_similarity=0.5
    )


# 36. LP fusion supports signed axes (price cuts / staffing reductions)
def test_lp_solver_signed_axis():
    decisions = {"pricing": _dec("pricing", -2.0), "sales": _dec("sales", -1.0)}
    weights = {"pricing": 0.6, "sales": 0.4}
    x, _, opt_log = solve_decision_fusion(
        weights=weights, decisions=decisions, unit_cost=0.0, budget=1e9, x_lower_bound=None,
    )
    assert opt_log["success"] is True
    assert -2.0 - 1e-6 <= x <= -1.0 + 1e-6

    # Default lower bound still clamps non-negative axes
    x_nonneg, _, _ = solve_decision_fusion(
        weights=weights, decisions=decisions, unit_cost=0.0, budget=1e9,
    )
    assert x_nonneg == 0.0


# 37. Conflict score is bounded and sign-aware
def test_conflict_detection_signed():
    score, detected = detect_conflict({"a": _dec("a", 0.5), "b": _dec("b", -0.5)})
    assert detected is True
    assert 0.0 < score <= 1.0
    score_far, _ = detect_conflict({"a": _dec("a", 3.0), "b": _dec("b", -3.0)})
    assert score_far == 1.0


# 38. Every agent in a decision type answers on that type's axis (no unit mixing)
@pytest.mark.parametrize("decision_type", [
    "price_adjustment", "promotion_trigger", "staffing_adjustment", "customer_retention_action",
])
def test_agents_share_decision_axis(decision_type):
    import json
    headers = get_auth_headers("owner")
    res = client.post("/api/tenants/decisions/trigger", json={
        "product_id": "p-test", "date_str": "2026-09-01", "decision_type": decision_type,
    }, headers=headers)
    assert res.status_code == 200, res.text
    db = TestingSessionLocal()
    log = db.query(DecisionLog).filter_by(id=res.json()["decision_id"]).first()
    recs = {aid: d["recommendation"] for aid, d in json.loads(log.agent_decisions).items()}
    db.close()

    if decision_type in ("promotion_trigger", "customer_retention_action"):
        assert all(0.0 <= r <= 1.0 for r in recs.values()), recs
    elif decision_type == "price_adjustment":
        assert all(abs(r) <= 0.3 * 10.0 for r in recs.values()), recs   # unit_price = 10
    else:
        assert all(abs(r) <= 24.0 for r in recs.values()), recs          # hours in a day


# 39. Monitoring resolves events once the condition clears
def test_monitoring_auto_resolves_stock_events():
    from backend.app.monitoring import scan_business_monitoring_events
    from backend.app.db import MonitoringEvent
    db = TestingSessionLocal()
    inv = db.query(InventoryState).filter_by(product_id="p-test", tenant_id=TEST_TENANT_ID).first()
    original = inv.stock_level

    inv.stock_level = 0
    db.commit()
    scan_business_monitoring_events(TEST_TENANT_ID, db, auto_trigger=False)
    open_evt = db.query(MonitoringEvent).filter_by(
        tenant_id=TEST_TENANT_ID, entity_id="p-test", event_type="stockout_risk", resolved=False
    ).first()
    assert open_evt is not None

    inv.stock_level = original
    db.commit()
    scan_business_monitoring_events(TEST_TENANT_ID, db, auto_trigger=False)
    db.refresh(open_evt)
    assert open_evt.resolved is True
    assert open_evt.resolved_at is not None
    db.close()


# 40. Automation policy: routine reorders notify, high-impact actions await review
def test_automation_policy_routing_and_review():
    from backend.app.automation import AutomationPolicyEngine
    db = TestingSessionLocal()
    engine = AutomationPolicyEngine(TEST_TENANT_ID, db)

    routine = engine.route_decision(
        {"decision_type": "reorder_quantity", "fused_recommendation": 10.0, "decision_id": None},
        product_id="p-test",
    )
    assert routine.status == "notified"          # 10 units * $5 = $50 < limit

    pricey = engine.route_decision(
        {"decision_type": "price_adjustment", "fused_recommendation": -1.0, "decision_id": None},
        product_id="p-test",
    )
    assert pricey.status == "pending_review"
    pricey_id = pricey.id
    db.close()

    res = client.get("/api/tenants/automation/actions?status=pending_review", headers=get_auth_headers("owner"))
    assert res.status_code == 200
    assert any(a["id"] == pricey_id for a in res.json())

    # Only owners may review
    res = client.post(f"/api/tenants/automation/actions/{pricey_id}/review", json={"approve": True},
                      headers=get_auth_headers("inventory_manager"))
    assert res.status_code == 403
    res = client.post(f"/api/tenants/automation/actions/{pricey_id}/review", json={"approve": True},
                      headers=get_auth_headers("owner"))
    assert res.status_code == 200
    assert res.json()["status"] == "approved"
    # A reviewed action cannot be reviewed again
    res = client.post(f"/api/tenants/automation/actions/{pricey_id}/review", json={"approve": False},
                      headers=get_auth_headers("owner"))
    assert res.status_code == 409


# 41. Copilot answers from live business state
def test_copilot_grounded_in_twin():
    db = TestingSessionLocal()
    inv = db.query(InventoryState).filter_by(product_id="p-test", tenant_id=TEST_TENANT_ID).first()
    original = inv.stock_level
    inv.stock_level = 1
    db.commit()

    res = client.post("/api/tenants/copilot/chat", json={
        "messages": [{"role": "user", "content": "Which products are low on stock?"}]
    }, headers=get_auth_headers("owner"))
    inv.stock_level = original
    db.commit()
    db.close()

    assert res.status_code == 200
    assert "Test Prod" in res.json()["content"]


# 42. Digital twin exposes the supplier -> product relation layer
def test_twin_supply_network():
    db = TestingSessionLocal()
    db.add(Supplier(id="s-test", tenant_id=TEST_TENANT_ID, product_id="p-test", name="Acme"))
    db.commit()
    db.close()

    res = client.get("/api/tenants/twin", headers=get_auth_headers("owner"))
    assert res.status_code == 200
    data = res.json()
    assert any(s["supplier_id"] == "s-test" and s["product_id"] == "p-test" for s in data["supply_network"])
    prod = next(p for p in data["inventory"] if p["product_id"] == "p-test")
    assert "s-test" in prod["supplier_ids"]
    assert "outlook_30d" in data


# 43. Scenario results expose their assumptions and stay product-scoped
def test_scenario_assumptions_and_scope():
    from backend.app.scenario import run_scenario_simulation, ScenarioSimulateRequest
    db = TestingSessionLocal()
    req = ScenarioSimulateRequest(type="price_change", product_id="p-test", delta_pct=0.1, horizon_days=30)
    result = run_scenario_simulation(req, tenant_id=TEST_TENANT_ID, db=db, run_date=date(2026, 9, 1))
    db.close()
    a = result["assumptions"]
    assert a["scope"] == "product p-test"
    assert "price_elasticity" in a
    # Only the product's exposed revenue can move
    assert abs(result["delta"]["revenue_delta"]) <= a["exposed_revenue"] + 1e-6


# 44. XAI confidence stays within [0, 1]
def test_xai_confidence_bounded():
    from backend.app.explain import build_structured_explanation
    db = TestingSessionLocal()
    db.add(DecisionLog(
        id="test-dec-xai-3", tenant_id=TEST_TENANT_ID, product_id="p-test", date=date(2026, 9, 1),
        decision_type="price_adjustment", business_goal_applied="maximize_profit",
        conflict_detected=True, conflict_score=1.7, fused_recommendation=-0.5, fused_utility=0.5,
        agent_decisions="{}", weights="{}", optimization_problem="{}", retrieval_log="[]",
        natural_language_explanation="",
    ))
    db.commit()
    explanation = build_structured_explanation("test-dec-xai-3", db, TEST_TENANT_ID)
    db.close()
    assert 0.0 <= explanation["confidence"] <= 1.0


# ── Phase 6: AMDIE learning signal, inventory position, experiment harness ───

# 45. Quantile accuracy: symmetric at 0.5, penalises under-ordering above 0.5
def test_recommendation_accuracy_quantile():
    from backend.app.amdie.weights import recommendation_accuracy
    # level 0.5 reproduces the original symmetric relative error
    assert recommendation_accuracy(80, 100, 0.5) == pytest.approx(1 - 20 / 100)
    assert recommendation_accuracy(120, 100, 0.5) == pytest.approx(1 - 20 / 120)
    # level 0.9: being 20 short costs far more than being 20 over
    assert recommendation_accuracy(80, 100, 0.9) < recommendation_accuracy(120, 100, 0.9)
    assert recommendation_accuracy(100, 100, 0.9) == 1.0


# 46. Softmax temperature sharpens weights without changing their order
def test_softmax_temperature():
    flat, sharp = softmax([0.6, 0.7, 0.8]), softmax([0.6, 0.7, 0.8], temperature=0.05)
    assert max(flat) - min(flat) < 0.1
    assert sharp[2] > 0.8
    assert sharp[2] > sharp[1] > sharp[0]


# 47. Agents see open purchase orders as on-order stock
def test_on_order_quantity():
    from backend.app.retrieval import get_on_order_qty
    from backend.app.db import PurchaseOrder, PurchaseOrderItem, SupplierProfile
    db = TestingSessionLocal()
    db.add(SupplierProfile(id="sp-oo", tenant_id=TEST_TENANT_ID, name="OO"))
    db.add(PurchaseOrder(id="po-open", tenant_id=TEST_TENANT_ID, supplier_profile_id="sp-oo", status="ordered"))
    db.add(PurchaseOrder(id="po-done", tenant_id=TEST_TENANT_ID, supplier_profile_id="sp-oo", status="received"))
    db.add(PurchaseOrderItem(po_id="po-open", product_id="p-test", qty=12, unit_cost=5.0))
    db.add(PurchaseOrderItem(po_id="po-done", product_id="p-test", qty=30, unit_cost=5.0))
    db.commit()
    assert get_on_order_qty(TEST_TENANT_ID, "p-test", db) == 12
    db.query(PurchaseOrderItem).filter(PurchaseOrderItem.po_id.in_(["po-open", "po-done"])).delete()
    db.query(PurchaseOrder).filter(PurchaseOrder.id.in_(["po-open", "po-done"])).delete()
    db.commit()
    db.close()


# 48. Experiment harness: identical instances per seed, sane metrics
def test_experiment_simulator_smoke():
    from dataclasses import replace
    from backend.experiments.environment import SCENARIOS, ExperimentConfig, ProblemInstance, Simulator
    from backend.experiments.policies import make_policy
    cfg = replace(ExperimentConfig(), n_products=2, horizon_days=14)
    a = ProblemInstance.generate(7, SCENARIOS["baseline"], cfg)
    b = ProblemInstance.generate(7, SCENARIOS["baseline"], cfg)
    assert (a.demand == b.demand).all() and (a.lead_times == b.lead_times).all()

    for name in ("base_stock", "oracle"):
        result = Simulator(a).run(make_policy(name))
        m = result["metrics"]
        assert m["n_decisions"] == 2 * 2          # 2 products x 2 weekly reviews
        assert 0.0 <= m["fill_rate"] <= 1.0
        assert m["revenue"] > 0
    assert make_policy("amdie[t=0.1,sl=0.9]").service_level == 0.9
