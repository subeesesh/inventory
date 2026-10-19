from fastapi import APIRouter, Depends, HTTPException, Query
from backend.app.clock import utcnow
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime, date
import json
import uuid
import numpy as np

from backend.app.db import (
    get_db, Tenant, Product, DecisionLog, InventoryState, FinanceLedger,
    AgentAccuracy, User, Supplier, WeightCoefficients, Sale, PurchaseOrder,
    MonitoringEvent, StaffShift, AutomationAction,
)
from backend.app.auth import get_current_tenant, require_role, get_current_user
from backend.app.retrieval import retrieval_log_var
from backend.app.agents import (
    SalesAgent, InventoryAgent, FinanceAgent,
    PricingAgent, MarketingAgent, ProcurementAgent, RiskAgent,
    HRAgent, CustomerManagementAgent,
)
from backend.app.amdie import (
    detect_conflict,
    get_agent_weights,
    adjust_objective_for_goals,
    solve_decision_fusion,
    update_reliability_and_logs,
    check_and_trigger_retraining,
    AmdieOptions,
    DEFAULT_OPTIONS,
)
from backend.app.llm import llm_adapter
from backend.app.decision_registry import (
    DECISION_TYPES, DECISION_TYPE_LABELS, validate_decision_type,
    get_agents_for_decision_type, get_upper_bound, get_lower_bound, all_decision_types,
)
from backend.app.monitoring import scan_business_monitoring_events
from backend.app.scenario import run_scenario_simulation, ScenarioSimulateRequest
from backend.app.explain import build_structured_explanation
from backend.app.automation import AutomationPolicyEngine, serialize_action

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────

class TriggerDecisionRequest(BaseModel):
    product_id: str
    date_str: str   # Format: YYYY-MM-DD
    # Phase 2: defaults to "reorder_quantity" for full backwards compatibility
    decision_type: str = Field(default="reorder_quantity")

class OutcomeRequest(BaseModel):
    actual_outcome: float

class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]  # [{"role": "user", "content": "..."}]

class GoalUpdateRequest(BaseModel):
    business_goal: str

class SupplierCreate(BaseModel):
    product_id: str
    name: str = "Default Supplier"
    avg_lead_time_days: float = 7.0
    lead_time_std_dev: float = 1.5
    reliability_score: float = Field(default=0.85, ge=0.0, le=1.0)
    min_order_qty: int = 10


# ── Agent factory — maps agent_id string → agent instance ─────────────────────

def _build_agent(agent_id: str):
    """Instantiate the correct agent class by ID string from the registry."""
    mapping = {
        "inventory":           InventoryAgent,
        "sales":               SalesAgent,
        "finance":             FinanceAgent,
        "pricing":             PricingAgent,
        "marketing":           MarketingAgent,
        "procurement":         ProcurementAgent,
        "hr":                  HRAgent,
        "customer_management": CustomerManagementAgent,
    }
    cls = mapping.get(agent_id)
    if cls is None:
        raise ValueError(f"No agent class registered for agent_id='{agent_id}'")
    return cls()


# ── Existing Phase 1 endpoints (UNCHANGED) ────────────────────────────────────

@router.post("/tenants/goal")
def update_tenant_goal(
    req: GoalUpdateRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner"]))
):
    if req.business_goal not in ["maximize_profit", "minimize_cost", "minimize_risk", "maximize_turnover"]:
        raise HTTPException(status_code=400, detail="Invalid business goal")
    tenant.business_goal = req.business_goal
    db.commit()
    return {"status": "success", "business_goal": tenant.business_goal}

@router.get("/tenants/me")
def get_tenant_info(
    tenant: Tenant = Depends(get_current_tenant),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer", "finance_officer"]))
):
    return {
        "id": tenant.id,
        "name": tenant.name,
        "business_goal": tenant.business_goal,
        "enables_hr_agent": tenant.enables_hr_agent,
    }

@router.get("/tenants/products")
def get_products(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "cashier", "inventory_manager", "procurement_officer"]))
):
    prods = db.query(Product).filter(Product.tenant_id == tenant.id).all()
    results = []
    for p in prods:
        inv = db.query(InventoryState).filter_by(product_id=p.id, tenant_id=tenant.id).first()
        results.append({
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "unit_price": p.unit_price,
            "unit_cost": p.unit_cost,
            "stock_level": inv.stock_level if inv else 0,
            "reorder_point": inv.reorder_point if inv else 0,
            "sku": p.sku,
            "barcode": p.barcode,
            "min_stock": p.min_stock,
            "max_stock": p.max_stock,
            "is_active": p.is_active is not False,
        })
    return results


# ── Decision endpoints (Phase 2: decision_type filter) ───────────────────────

@router.get("/tenants/decisions")
def get_decisions(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    decision_type: Optional[str] = Query(default=None, description="Filter by decision type"),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer", "finance_officer"]))
):
    query = db.query(DecisionLog).filter(DecisionLog.tenant_id == tenant.id)
    if decision_type:
        if not validate_decision_type(decision_type):
            raise HTTPException(status_code=400, detail=f"Unknown decision_type '{decision_type}'")
        query = query.filter(DecisionLog.decision_type == decision_type)
    logs = query.order_by(DecisionLog.date.desc()).all()
    results = []
    for l in logs:
        results.append({
            "id": l.id,
            "product_id": l.product_id,
            "date": str(l.date),
            "decision_type": l.decision_type,
            "business_goal_applied": l.business_goal_applied,
            "conflict_detected": l.conflict_detected,
            "conflict_score": l.conflict_score,
            "fused_recommendation": l.fused_recommendation,
            "actual_outcome": l.actual_outcome,
            "natural_language_explanation": l.natural_language_explanation
        })
    return results


def trigger_decision_internal(
    tenant_id: str,
    product_id: str,
    date_str: str,
    decision_type: str,
    db: Session,
    options: AmdieOptions = DEFAULT_OPTIONS,
) -> Dict[str, Any]:
    """
    One full AMDIE cycle: agents -> conflict detection -> adaptive weights ->
    goal adjustment -> constrained fusion -> explanation -> DecisionLog.
    `options` is only changed by the experiment harness for ablations.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise ValueError("Tenant not found")

    if not validate_decision_type(decision_type):
        raise ValueError(f"Unknown decision_type '{decision_type}'")

    try:
        run_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        run_date = date.today()

    product = db.query(Product).filter(
        Product.tenant_id == tenant.id, Product.id == product_id
    ).first()
    if not product:
        raise ValueError("Product not found")

    retrieval_log_var.set([])

    agent_ids = get_agents_for_decision_type(decision_type)
    fusion_agent_ids = [aid for aid in agent_ids if aid != "risk"]
    decisions: Dict[str, Any] = {}
    for aid in fusion_agent_ids:
        agent = _build_agent(aid)
        decisions[aid] = agent.run(tenant.id, product.id, run_date, db, decision_type=decision_type)

    overall_risk_score = None
    risk_breakdown = {}
    if tenant.business_goal == "minimize_risk":
        risk_agent = RiskAgent()
        overall_risk_score = risk_agent.compute_overall_risk(
            tenant.id, product.id, run_date, decisions, db
        )
        risk_breakdown = risk_agent.get_risk_breakdown(
            tenant.id, product.id, run_date, decisions, db
        )

    conflict_score, conflict_detected = detect_conflict(decisions, tau=0.3)

    query_text = (
        f"{decision_type} decision for product {product.name} "
        f"(category: {product.category}) on {run_date} for tenant {tenant.id}"
    )
    weights, components = get_agent_weights(
        tenant.id, decisions, query_text, db, decision_type=decision_type,
        disabled_terms=options.disabled_weight_terms,
        temperature=options.weight_temperature,
    )
    if not options.adaptive_weights:
        weights = {aid: 1.0 / len(decisions) for aid in decisions}

    ledger = db.query(FinanceLedger).filter(
        FinanceLedger.tenant_id == tenant.id,
        FinanceLedger.date == run_date
    ).first()
    if not ledger:
        ledger = db.query(FinanceLedger).filter(
            FinanceLedger.tenant_id == tenant.id,
            FinanceLedger.date <= run_date
        ).order_by(FinanceLedger.date.desc()).first()

    budget = ledger.budget_per_period if ledger else 5000.0

    # Cost penalty and turnover bonus are expressed in units of stock, so they
    # only apply to reorder decisions; other axes (price delta, hours, fractions)
    # are shaped by the weight adjustments alone.
    is_reorder = decision_type == "reorder_quantity"
    forecasted_demand = 0.0
    if is_reorder and "sales" in decisions:
        forecasted_demand = decisions["sales"].recommendation

    goals_adj = adjust_objective_for_goals(
        weights=weights,
        decisions=decisions,
        business_goal=tenant.business_goal,
        unit_cost=product.unit_cost,
        forecasted_demand=forecasted_demand,
        overall_risk_score=overall_risk_score,
    )

    if not is_reorder:
        goals_adj["cost_penalty"] = 0.0
        goals_adj["turnover_bonus"] = 0.0

    lp_unit_cost = product.unit_cost if is_reorder else 0.0
    lp_budget    = budget if is_reorder else 1e9
    lp_capacity  = product.warehouse_capacity_limit if is_reorder else None
    x_lower      = get_lower_bound(decision_type)
    # Hard caps contributed by agents (e.g. Finance affordability) are constraints, not votes
    agent_caps = [d.upper_limit for d in decisions.values()] if options.agent_caps else []
    upper_caps = [get_upper_bound(decision_type)] + agent_caps
    upper_caps = [c for c in upper_caps if c is not None]
    x_upper      = min(upper_caps) if upper_caps else None
    if x_upper is not None and x_lower is not None:
        x_upper = max(x_upper, x_lower)

    if options.lp_fusion:
        fused_rec, fused_utility, opt_log = solve_decision_fusion(
            weights=goals_adj["adjusted_weights"],
            decisions=decisions,
            unit_cost=lp_unit_cost,
            budget=lp_budget,
            warehouse_capacity=lp_capacity,
            cost_penalty=goals_adj["cost_penalty"],
            turnover_bonus=goals_adj["turnover_bonus"],
            forecasted_demand=goals_adj["forecasted_demand"],
            x_upper_bound=x_upper,
            x_lower_bound=x_lower,
        )
    else:
        # Ablation: weighted average under the same hard constraints
        adj_w = goals_adj["adjusted_weights"]
        total_w = sum(adj_w.values()) or 1.0
        fused_rec = sum(adj_w[a] * decisions[a].recommendation for a in decisions) / total_w
        caps = [x_upper, lp_capacity, (lp_budget / lp_unit_cost) if lp_unit_cost > 0 else None]
        caps = [c for c in caps if c is not None]
        if caps:
            fused_rec = min(fused_rec, min(caps))
        if x_lower is not None:
            fused_rec = max(fused_rec, x_lower)
        fused_utility = 0.0
        opt_log = {"success": True, "method": "weighted_average", "x": fused_rec}

    summary_dict = {
        "date":                 str(run_date),
        "product_id":           product.id,
        "decision_type":        decision_type,
        "business_goal":        tenant.business_goal,
        "conflict_detected":    conflict_detected,
        "conflict_score":       conflict_score,
        "fused_recommendation": fused_rec,
        "fused_utility":        fused_utility,
        "agent_decisions":      {aid: dec.model_dump() for aid, dec in decisions.items()},
        "weights":              weights,
        "weight_components":    components,
        "opt_log":              opt_log,
        "overall_risk_score":   overall_risk_score,
        "risk_breakdown":       risk_breakdown,
    }
    explanation = llm_adapter.generate_explanation(summary_dict) if options.explain else ""

    dec_log = DecisionLog(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        product_id=product.id,
        date=run_date,
        decision_type=decision_type,
        business_goal_applied=tenant.business_goal,
        conflict_detected=conflict_detected,
        conflict_score=conflict_score,
        fused_recommendation=fused_rec,
        fused_utility=fused_utility,
        agent_decisions=json.dumps({aid: dec.model_dump() for aid, dec in decisions.items()}),
        weights=json.dumps(components),
        optimization_problem=json.dumps({
            "objective":              "piecewise_linear_triangular",
            "decision_type":          decision_type,
            "budget_limit":           budget,
            "cost_penalty_applied":   goals_adj["cost_penalty"],
            "turnover_bonus_applied": goals_adj["turnover_bonus"],
            "capacity_limit":         lp_capacity,
            "x_upper_bound":          x_upper,
            "x_lower_bound":          x_lower,
            "overall_risk_score":     overall_risk_score,
            "solver_details":         opt_log,
            "weights":                weights,
            "agent_recommendations":  {aid: dec.model_dump() for aid, dec in decisions.items()},
        }),
        retrieval_log=json.dumps(retrieval_log_var.get()),
        natural_language_explanation=explanation,
    )
    db.add(dec_log)
    db.commit()

    return {
        "decision_id":          dec_log.id,
        "decision_type":        decision_type,
        "fused_recommendation": fused_rec,
        "conflict_detected":    conflict_detected,
        "conflict_score":       conflict_score,
        "overall_risk_score":   overall_risk_score,
        "explanation":          explanation,
        "weights":              weights,
        "agent_recommendations": {aid: dec.recommendation for aid, dec in decisions.items()},
    }


@router.post("/tenants/decisions/trigger")
def trigger_decision(
    req: TriggerDecisionRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer", "finance_officer"]))
):
    try:
        return trigger_decision_internal(
            tenant_id=tenant.id,
            product_id=req.product_id,
            date_str=req.date_str,
            decision_type=req.decision_type,
            db=db,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.get("/tenants/decisions/{id}/explain")
def get_decision_explain(
    id: str,
    tenant: Tenant = Depends(get_current_tenant),
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer", "finance_officer"]))
):
    explanation = build_structured_explanation(decision_id=id, db=db, tenant_id=tenant.id)
    if "error" in explanation:
        raise HTTPException(status_code=404, detail=explanation["error"])
    return explanation


# ── Phase 3: Real-Time Business Monitoring Endpoints ─────────────────────────

@router.post("/tenants/monitoring/scan")
def trigger_monitoring_scan(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer", "finance_officer"]))
):
    events = scan_business_monitoring_events(tenant_id=tenant.id, db=db)
    return {
        "status": "success",
        "events_detected": len(events),
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "severity": e.severity,
                "detected_at": e.detected_at.isoformat() if e.detected_at else None,
                "resolved": e.resolved
            }
            for e in events
        ]
    }


@router.get("/tenants/monitoring/events")
def get_monitoring_events(
    include_resolved: bool = Query(default=False),
    tenant: Tenant = Depends(get_current_tenant),
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer", "finance_officer"]))
):
    query = db.query(MonitoringEvent).filter(MonitoringEvent.tenant_id == tenant.id)
    role = user.role if user else "owner"

    if role == "inventory_manager":
        query = query.filter(MonitoringEvent.entity_type.in_(["product", "inventory"]))
    elif role == "finance_officer":
        query = query.filter(MonitoringEvent.entity_type == "finance")
    elif role == "procurement_officer":
        query = query.filter(MonitoringEvent.entity_type.in_(["product", "supplier"]))

    if not include_resolved:
        query = query.filter(MonitoringEvent.resolved == False)  # noqa: E712
    events = query.order_by(MonitoringEvent.detected_at.desc()).limit(200).all()
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "severity": e.severity,
            "detected_at": e.detected_at.isoformat() if e.detected_at else None,
            "resolved": e.resolved,
        }
        for e in events
    ]


# ── Phase 3: Counterfactual "What-If" Scenario Simulator Endpoint ─────────────

@router.post("/tenants/scenarios/simulate")
def simulate_scenario(
    req: ScenarioSimulateRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer", "finance_officer"]))
):
    return run_scenario_simulation(req=req, tenant_id=tenant.id, db=db)


@router.post("/tenants/decisions/{id}/outcome")
def submit_outcome(
    id: str,
    req: OutcomeRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer"]))
):
    log = db.query(DecisionLog).filter_by(id=id, tenant_id=tenant.id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Decision log not found")

    # Scope reliability updates by the decision_type stored in the log
    update_reliability_and_logs(
        tenant.id, log.id, req.actual_outcome, db, decision_type=log.decision_type
    )
    check_and_trigger_retraining(
        tenant.id, db, decision_type=log.decision_type
    )
    return {"status": "success", "message": "Outcome logged and metrics updated successfully."}


# ── Copilot (unchanged) ───────────────────────────────────────────────────────

@router.post("/tenants/copilot/chat")
def copilot_chat(
    req: ChatRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer", "finance_officer"]))
):
    """
    Business Copilot (§III-I): grounds answers in the digital twin, open monitoring
    alerts, the 30-day outlook, pending automated actions and recent AMDIE decisions.
    """
    from backend.app.business_twin import get_business_digital_twin

    twin = get_business_digital_twin(tenant_id=tenant.id, db=db).get_state()
    open_events = [
        {"event_type": e.event_type, "entity_type": e.entity_type, "entity_id": e.entity_id, "severity": e.severity}
        for e in db.query(MonitoringEvent).filter_by(tenant_id=tenant.id, resolved=False)
                   .order_by(MonitoringEvent.detected_at.desc()).limit(10).all()
    ]
    pending_actions = [
        {"description": a.description, "policy_reason": a.policy_reason}
        for a in db.query(AutomationAction).filter_by(tenant_id=tenant.id, status="pending_review")
                   .order_by(AutomationAction.created_at.desc()).limit(5).all()
    ]
    recent_decisions = [
        {
            "product_id": l.product_id, "date": str(l.date), "decision_type": l.decision_type,
            "fused_recommendation": l.fused_recommendation, "conflict_detected": l.conflict_detected,
            "conflict_score": l.conflict_score or 0.0, "goal": l.business_goal_applied,
            "explanation": (l.natural_language_explanation or "")[:300],
        }
        for l in db.query(DecisionLog).filter_by(tenant_id=tenant.id)
                   .order_by(DecisionLog.date.desc()).limit(3).all()
    ]

    low_stock = [p for p in twin["inventory"] if p["low_stock"]]
    context_str = (
        f"Business: {twin['business_name']} (goal: {twin['business_goal']}, risk level {twin['risk_level']})\n"
        f"Finance: cash {twin['finance']['cash_balance']:.2f}, period budget {twin['finance']['period_budget']:.2f}\n"
        f"Last 30 days: {twin['sales_30d']['total_units']} units, revenue {twin['sales_30d']['total_revenue']:.2f}\n"
        f"Next 30 days outlook: {json.dumps(twin['outlook_30d'])}\n"
        f"Low-stock products: {json.dumps([{k: p[k] for k in ('name', 'stock_level', 'min_stock')} for p in low_stock[:10]])}\n"
        f"Open alerts: {json.dumps(open_events)}\n"
        f"Actions awaiting owner review: {json.dumps(pending_actions)}\n"
        f"Recent decisions: {json.dumps(recent_decisions)}\n"
    )
    facts = {
        "twin": twin,
        "open_events": open_events,
        "pending_actions": pending_actions,
        "recent_decisions": recent_decisions,
    }

    ans = llm_adapter.copilot_chat(req.messages, context_str, facts=facts)
    return {"role": "assistant", "content": ans}


# ── Automation & Alert System (§III-J) ───────────────────────────────────────

class ActionReviewRequest(BaseModel):
    approve: bool


@router.get("/tenants/automation/actions")
def get_automation_actions(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    status: Optional[str] = Query(default=None, description="notified | pending_review | approved | rejected"),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer", "finance_officer"]))
):
    query = db.query(AutomationAction).filter_by(tenant_id=tenant.id)
    if status:
        query = query.filter_by(status=status)
    actions = query.order_by(AutomationAction.created_at.desc()).limit(50).all()
    return [serialize_action(a) for a in actions]


@router.post("/tenants/automation/actions/{id}/review")
def review_automation_action(
    id: str,
    req: ActionReviewRequest,
    tenant: Tenant = Depends(get_current_tenant),
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner"]))
):
    action, reviewed = AutomationPolicyEngine(tenant.id, db).review(id, req.approve, user.id if user else None)
    if not action:
        raise HTTPException(status_code=404, detail="Automation action not found")
    if not reviewed:
        raise HTTPException(status_code=409, detail=f"Action is '{action.status}' and cannot be reviewed")
    return serialize_action(action)


# ── Metrics (Phase 2: per-decision_type breakdown) ────────────────────────────

@router.get("/tenants/metrics")
def get_metrics(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer", "finance_officer"]))
):
    # 1. Overall cumulative accuracy
    completed_decisions = db.query(DecisionLog).filter(
        DecisionLog.tenant_id == tenant.id,
        DecisionLog.actual_outcome.isnot(None)
    ).all()

    avg_accuracy = 0.85
    if completed_decisions:
        accuracies = []
        for dec in completed_decisions:
            rec = dec.fused_recommendation
            actual = dec.actual_outcome
            denom = max(abs(rec), abs(actual), 1.0)
            accuracy = 1.0 - (abs(rec - actual) / denom)
            accuracies.append(max(0.0, accuracy))
        avg_accuracy = float(np.mean(accuracies))

    # 2. Latest ledger
    ledger = db.query(FinanceLedger).filter_by(tenant_id=tenant.id).order_by(FinanceLedger.date.desc()).first()
    cash = ledger.cash_balance if ledger else 50000.0
    budget = ledger.budget_per_period if ledger else 15000.0

    # 3. Agent reliability — all agents, all decision_types
    agents_q = db.query(AgentAccuracy).filter_by(tenant_id=tenant.id).all()
    agent_reliability = {}
    for a in agents_q:
        agent_reliability[a.agent_id] = a.reliability
    # Phase 1 defaults for seeded agents (backward compat)
    for aid in ["inventory", "sales", "finance"]:
        agent_reliability.setdefault(aid, 0.85)

    # 4. Per-decision-type stats (Phase 2: Maintenance sees all types)
    decision_type_stats = {}
    for dt in all_decision_types():
        dt_logs = db.query(DecisionLog).filter(
            DecisionLog.tenant_id == tenant.id,
            DecisionLog.decision_type == dt,
        ).all()
        total_dt = len(dt_logs)
        conflict_dt = sum(1 for l in dt_logs if l.conflict_detected)
        completed_dt = [l for l in dt_logs if l.actual_outcome is not None]

        # Solver success rate (opt log embedded in JSON)
        solver_successes = 0
        for l in dt_logs:
            try:
                opt = json.loads(l.optimization_problem)
                if opt.get("solver_details", {}).get("success", False):
                    solver_successes += 1
            except Exception:
                pass

        decision_type_stats[dt] = {
            "label":               DECISION_TYPE_LABELS.get(dt, dt),
            "total_decisions":     total_dt,
            "conflict_rate":       (conflict_dt / max(total_dt, 1)) * 100.0,
            "solver_success_rate": (solver_successes / max(total_dt, 1)) * 100.0,
            "outcomes_logged":     len(completed_dt),
        }

    # 5. Total decision counts
    total_decisions = db.query(DecisionLog).filter_by(tenant_id=tenant.id).count()
    conflict_decisions = db.query(DecisionLog).filter_by(tenant_id=tenant.id, conflict_detected=True).count()

    # 6. POS KPIs (Phase 2)
    today = utcnow().date()
    today_sales = db.query(Sale).filter(
        Sale.tenant_id == tenant.id,
        Sale.created_at >= datetime.combine(today, datetime.min.time())
    ).all()
    total_revenue_today = sum(s.total for s in today_sales)
    total_transactions_today = len(today_sales)

    all_inv = db.query(InventoryState).filter_by(tenant_id=tenant.id).all()
    low_stock_count = 0
    for inv_item in all_inv:
        prod = db.query(Product).filter_by(id=inv_item.product_id, tenant_id=tenant.id).first()
        if prod and prod.min_stock is not None and inv_item.stock_level <= prod.min_stock:
            low_stock_count += 1

    pending_po_count = db.query(PurchaseOrder).filter_by(
        tenant_id=tenant.id, status="ordered"
    ).count()

    return {
        "cumulative_accuracy":       avg_accuracy,
        "cash_balance":              cash,
        "period_budget":             budget,
        "agent_reliability":         agent_reliability,
        "total_decisions":           total_decisions,
        "conflict_percentage":       (conflict_decisions / max(total_decisions, 1)) * 100.0,
        "decision_type_stats":       decision_type_stats,
        "available_decision_types":  all_decision_types(),
        # Phase 2 POS KPIs
        "total_revenue_today":       total_revenue_today,
        "total_transactions_today":  total_transactions_today,
        "low_stock_count":           low_stock_count,
        "pending_po_count":          pending_po_count,
    }


# ── Supplier endpoints (Phase 2 — owner: write, owner+maintenance: read) ──────

@router.get("/tenants/suppliers")
def get_suppliers(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    product_id: Optional[str] = Query(default=None),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer", "finance_officer"]))
):
    """List suppliers for the tenant. Optionally filter by product_id."""
    query = db.query(Supplier).filter_by(tenant_id=tenant.id)
    if product_id:
        query = query.filter_by(product_id=product_id)
    suppliers = query.all()
    return [
        {
            "id":                s.id,
            "product_id":        s.product_id,
            "name":              s.name,
            "avg_lead_time_days": s.avg_lead_time_days,
            "lead_time_std_dev": s.lead_time_std_dev,
            "reliability_score": s.reliability_score,
            "min_order_qty":     s.min_order_qty,
        }
        for s in suppliers
    ]


@router.post("/tenants/suppliers")
def create_supplier(
    req: SupplierCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner"]))
):
    """Create a supplier record for a product. Owner-only."""
    product = db.query(Product).filter_by(
        id=req.product_id, tenant_id=tenant.id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found for this tenant")

    supplier = Supplier(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        product_id=req.product_id,
        name=req.name,
        avg_lead_time_days=req.avg_lead_time_days,
        lead_time_std_dev=req.lead_time_std_dev,
        reliability_score=req.reliability_score,
        min_order_qty=req.min_order_qty,
    )
    db.add(supplier)
    db.commit()

    # Sync to Neo4j graph (no-op when disabled)
    try:
        from backend.app.graph_db import graph_db as neo4j
        neo4j.sync_supplier_to_graph(tenant.id, supplier)
    except Exception:
        pass

    return {
        "id":                supplier.id,
        "product_id":        supplier.product_id,
        "name":              supplier.name,
        "avg_lead_time_days": supplier.avg_lead_time_days,
        "lead_time_std_dev": supplier.lead_time_std_dev,
        "reliability_score": supplier.reliability_score,
        "min_order_qty":     supplier.min_order_qty,
    }


# ── Decision Registry meta-endpoint ──────────────────────────────────────────

@router.get("/tenants/decision-types")
def get_decision_types(
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer", "finance_officer"]))
):
    """Return all registered decision types with their participating agents."""
    return {
        dt: {
            "agents": agents,
            "label":  DECISION_TYPE_LABELS.get(dt, dt),
        }
        for dt, agents in DECISION_TYPES.items()
    }


# ── Business Digital Twin endpoint ────────────────────────────────────────────

@router.get("/tenants/twin")
def get_digital_twin(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "finance_officer", "inventory_manager", "procurement_officer", "cashier"])),
):
    """
    Retrieve a unified read-only snapshot of the Business Digital Twin (§III-B).
    Aggregates inventory, sales, finance, customers, suppliers, staffing, and risk state.
    """
    from backend.app.business_twin import get_business_digital_twin
    twin = get_business_digital_twin(tenant_id=tenant.id, db=db)
    return twin.get_state()


# ── Data Integration Summary endpoint ─────────────────────────────────────────

@router.get("/tenants/integration/summary")
def get_integration_summary(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner"])),
):
    """
    Return a normalized data integration summary across all source adapters (§III-A).
    External connectors (Shopify, QuickBooks, Salesforce) are future extension adapters.
    """
    from backend.app.data_integration import DataIntegrationEngine
    engine = DataIntegrationEngine(tenant_id=tenant.id, db=db)
    return engine.get_unified_data_summary()


# ── Compliance Audit Summary endpoint ─────────────────────────────────────────

@router.get("/tenants/compliance/audit")
def get_compliance_audit(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "finance_officer"])),
):
    """
    Return operational compliance audit summary (§III-K).
    Full regulatory filing/tax-export integrations are future extensions.
    """
    from backend.app.compliance import generate_compliance_audit_summary
    return generate_compliance_audit_summary(tenant_id=tenant.id, db=db)

