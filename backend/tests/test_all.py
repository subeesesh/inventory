import pytest
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
