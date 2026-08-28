from fastapi import APIRouter, Depends, HTTPException, Query
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
)
from backend.app.auth import get_current_tenant, require_role, get_current_user
from backend.app.retrieval import retrieval_log_var
from backend.app.agents import (
    SalesAgent, InventoryAgent, FinanceAgent,
    PricingAgent, MarketingAgent, ProcurementAgent, RiskAgent,
)
from backend.app.amdie import (
    detect_conflict,
    get_agent_weights,
    adjust_objective_for_goals,
    solve_decision_fusion,
    update_reliability_and_logs,
    check_and_trigger_retraining,
)
from backend.app.llm import llm_adapter
from backend.app.decision_registry import (
    DECISION_TYPES, DECISION_TYPE_LABELS, validate_decision_type,
    get_agents_for_decision_type, get_upper_bound, all_decision_types,
)

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
        "inventory":   InventoryAgent,
        "sales":       SalesAgent,
        "finance":     FinanceAgent,
        "pricing":     PricingAgent,
        "marketing":   MarketingAgent,
        "procurement": ProcurementAgent,
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


@router.post("/tenants/decisions/trigger")
def trigger_decision(
    req: TriggerDecisionRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer"]))
):
    # Validate decision_type
    if not validate_decision_type(req.decision_type):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown decision_type '{req.decision_type}'. Valid: {all_decision_types()}"
        )

    try:
        run_date = datetime.strptime(req.date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    product = db.query(Product).filter(
        Product.tenant_id == tenant.id, Product.id == req.product_id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found for this tenant")

    # Set up thread-local audit log
    retrieval_log_var.set([])

    # ── 1. Run domain agents for this decision_type ───────────────────────
    agent_ids = get_agents_for_decision_type(req.decision_type)

    # Build and run each agent (risk agent is a meta-agent, excluded from fusion)
    fusion_agent_ids = [aid for aid in agent_ids if aid != "risk"]
    decisions: Dict[str, Any] = {}
    for aid in fusion_agent_ids:
        agent = _build_agent(aid)
        decisions[aid] = agent.run(tenant.id, product.id, run_date, db)

    # ── 2. Risk Agent post-processing (only when relevant) ───────────────
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

    # ── 3. Conflict Detection ─────────────────────────────────────────────
    conflict_score, conflict_detected = detect_conflict(decisions, tau=0.3)

    # ── 4. Adaptive Weight Assignment (scoped by decision_type) ──────────
    query_text = (
        f"{req.decision_type} decision for product {product.name} "
        f"(category: {product.category}) on {run_date} for tenant {tenant.id}"
    )
    weights, components = get_agent_weights(
        tenant.id, decisions, query_text, db, decision_type=req.decision_type
    )

    # ── 5. Business Goal Objective Modification ───────────────────────────
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

    # Forecasted demand proxy (only meaningful for reorder_quantity)
    forecasted_demand = 0.0
    if "sales" in decisions:
        forecasted_demand = decisions["sales"].recommendation

    goals_adj = adjust_objective_for_goals(
        weights=weights,
        decisions=decisions,
        business_goal=tenant.business_goal,
        unit_cost=product.unit_cost,
        forecasted_demand=forecasted_demand,
        overall_risk_score=overall_risk_score,
    )

    # ── 6. Constrained Optimization Solver ───────────────────────────────
    # For price_adjustment / promotion_trigger, set unit_cost=0 so the budget
    # constraint is non-binding (pricing and promotions don't incur procurement cost).
    lp_unit_cost = product.unit_cost if req.decision_type == "reorder_quantity" else 0.0
    lp_budget    = budget if req.decision_type == "reorder_quantity" else 1e9
    lp_capacity  = product.warehouse_capacity_limit if req.decision_type == "reorder_quantity" else None
    x_upper      = get_upper_bound(req.decision_type)

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
    )

    # ── 7. Explainability & NLG ───────────────────────────────────────────
    summary_dict = {
        "date":                 str(run_date),
        "product_id":           product.id,
        "decision_type":        req.decision_type,
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
    explanation = llm_adapter.generate_explanation(summary_dict)

    # ── 8. Persist trace ──────────────────────────────────────────────────
    dec_log = DecisionLog(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        product_id=product.id,
        date=run_date,
        decision_type=req.decision_type,
        business_goal_applied=tenant.business_goal,
        conflict_detected=conflict_detected,
        conflict_score=conflict_score,
        fused_recommendation=fused_rec,
        fused_utility=fused_utility,
        agent_decisions=json.dumps({aid: dec.model_dump() for aid, dec in decisions.items()}),
        weights=json.dumps(components),
        optimization_problem=json.dumps({
            "objective":              "piecewise_linear_triangular",
            "decision_type":          req.decision_type,
            "budget_limit":           budget,
            "cost_penalty_applied":   goals_adj["cost_penalty"],
            "turnover_bonus_applied": goals_adj["turnover_bonus"],
            "capacity_limit":         lp_capacity,
            "x_upper_bound":          x_upper,
            "overall_risk_score":     overall_risk_score,
            "solver_details":         opt_log,
        }),
        retrieval_log=json.dumps(retrieval_log_var.get()),
        natural_language_explanation=explanation,
    )
    db.add(dec_log)
    db.commit()

    return {
        "decision_id":          dec_log.id,
        "decision_type":        req.decision_type,
        "fused_recommendation": fused_rec,
        "conflict_detected":    conflict_detected,
        "conflict_score":       conflict_score,
        "overall_risk_score":   overall_risk_score,
        "explanation":          explanation,
    }


@router.get("/tenants/decisions/{id}/explain")
def get_decision_explain(
    id: str,
    tenant: Tenant = Depends(get_current_tenant),
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: bool = Depends(require_role(["owner", "inventory_manager", "procurement_officer", "finance_officer"]))
):
    log = db.query(DecisionLog).filter_by(id=id, tenant_id=tenant.id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Decision log not found")

    agent_decisions = json.loads(log.agent_decisions)
    opt_problem = json.loads(log.optimization_problem)

    is_finance = user and user.role == "finance_officer"
    is_owner = user and user.role == "owner"
    is_redacted = not (is_finance or is_owner)
    
    if is_redacted:
        for agent, dec in agent_decisions.items():
            if "expected_cost" in dec:
                dec["expected_cost"] = "[REDACTED]"
            if "expected_benefit" in dec:
                dec["expected_benefit"] = "[REDACTED]"
        if "budget_limit" in opt_problem:
            opt_problem["budget_limit"] = "[REDACTED]"
        if "cash_balance" in opt_problem:
            opt_problem["cash_balance"] = "[REDACTED]"

    return {
        "id":                          log.id,
        "product_id":                  log.product_id,
        "date":                        str(log.date),
        "decision_type":               log.decision_type,
        "business_goal_applied":       log.business_goal_applied,
        "conflict_detected":           log.conflict_detected,
        "conflict_score":              log.conflict_score,
        "fused_recommendation":        log.fused_recommendation,
        "fused_utility":               log.fused_utility,
        "agent_decisions":             agent_decisions,
        "weights":                     json.loads(log.weights),
        "optimization_problem":        opt_problem,
        "retrieval_log":               json.loads(log.retrieval_log),
        "natural_language_explanation": log.natural_language_explanation,
        "actual_outcome":              log.actual_outcome,
    }


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
    logs = db.query(DecisionLog).filter_by(tenant_id=tenant.id).order_by(DecisionLog.date.desc()).limit(3).all()
    context_str = "Recent decisions:\n"
    for l in logs:
        context_str += (
            f"- Product: {l.product_id}, Date: {l.date}, "
            f"Type: {l.decision_type}, "
            f"Fused Recommendation: {l.fused_recommendation}, "
            f"Goal: {l.business_goal_applied}, "
            f"Explanation: {l.natural_language_explanation[:150]}...\n"
        )

    latest_ledger = db.query(FinanceLedger).filter_by(tenant_id=tenant.id).order_by(FinanceLedger.date.desc()).first()
    if latest_ledger:
        context_str += f"Latest Finance: Cash Balance {latest_ledger.cash_balance:.2f}, Budget {latest_ledger.budget_per_period:.2f}\n"

    ans = llm_adapter.copilot_chat(req.messages, context_str)
    return {"role": "assistant", "content": ans}


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
    today = datetime.utcnow().date()
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
