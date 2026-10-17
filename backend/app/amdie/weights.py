import numpy as np
from backend.app.clock import utcnow
from datetime import datetime
from typing import Dict, Optional
from sqlalchemy.orm import Session
from backend.app.db import AgentAccuracy, WeightCoefficients, HistoricalAccuracyLog, DecisionLog
from backend.app.agents.base import DecisionObject
from backend.app.vector_db import get_embedding
from backend.app.config import settings

# ── Domain descriptions for context-relevance embedding ───────────────────────
# Phase 2: extended with descriptions for all registered agents.
# Used at startup to precompute embeddings; looked up during weight scoring.
AGENT_DOMAINS = {
    # Phase 1 agents
    "inventory":    "inventory state, stock levels, warehouse capacity, lead times, safety stock, reorder point, stockout risk",
    "sales":        "sales history, demand forecasting, growth rate, seasonality, prediction intervals, customer orders",
    "finance":      "finance ledger, cash balance, period budget, purchasing limits, expected cost, budget headroom",
    # Phase 2 agents
    "procurement":  "supplier lead time distribution, delivery variance, minimum order quantity, supplier reliability, procurement timing, order cost",
    "pricing":      "demand elasticity, price sensitivity, unit price adjustment, margin erosion, log-log regression, revenue optimisation",
    "marketing":    "inventory turnover rate, slow-moving stock, discount depth, promotional trigger, margin impact, stock clearance",
    "risk":         "overall risk aggregation, supplier concentration, seasonality volatility, risk modifier, portfolio risk",
    # Phase 3 agents
    "hr":           "staffing hours, shift scheduling, workforce capacity, labor cost, staffing gap, peak demand coverage",
    "customer_management": "customer retention, churn risk, loyalty incentives, shortage notification, customer relationships",
}

_domain_embeddings: dict | None = None

def get_domain_embedding(agent_id: str) -> list[float]:
    global _domain_embeddings
    if _domain_embeddings is None:
        _domain_embeddings = {aid: get_embedding(desc) for aid, desc in AGENT_DOMAINS.items()}
    return _domain_embeddings.get(agent_id)

def compute_context_relevance(agent_id: str, query_embedding: list[float]) -> float:
    agent_emb = get_domain_embedding(agent_id)
    if agent_emb is None:
        return 0.5  # default for unknown agents
    agent_emb = np.array(agent_emb)
    q_emb = np.array(query_embedding)
    dot = np.dot(agent_emb, q_emb)
    denom = np.linalg.norm(agent_emb) * np.linalg.norm(q_emb)
    return float(np.clip(dot / denom if denom > 0 else 0.0, 0.0, 1.0))

def softmax(x: list[float], temperature: float = 1.0) -> list[float]:
    arr = np.array(x, dtype=float) / max(temperature, 1e-6)
    e = np.exp(arr - arr.max())
    return (e / e.sum()).tolist()


def quantile_level_for(decision_type: str, override: Optional[float] = None) -> float:
    if override is not None:
        return float(override)
    return settings.AMDIE_REORDER_SERVICE_LEVEL if decision_type == "reorder_quantity" else 0.5


def recommendation_accuracy(rec: float, actual: float, level: float = 0.5) -> float:
    """
    Accuracy in [0, 1] of a recommendation against the realised outcome, from the
    pinball (quantile) loss at `level`:
        loss = level * under + (1 - level) * over
    normalised by the worst-case weight so that level = 0.5 reduces to the
    symmetric relative error 1 - |rec - actual| / max(|rec|, |actual|, 1).
    Minimising expected pinball loss at level tau is the newsvendor condition, so
    tau acts as the target service level for replenishment decisions.
    """
    under = max(actual - rec, 0.0)
    over = max(rec - actual, 0.0)
    loss = level * under + (1.0 - level) * over
    denom = max(level, 1.0 - level) * max(abs(rec), abs(actual), 1.0)
    return float(np.clip(1.0 - loss / denom, 0.0, 1.0))

# ── Weight computation ──────────────────────────────────────────────────────────

def get_agent_weights(
    tenant_id: str,
    decisions: Dict[str, DecisionObject],
    query_text: str,
    db: Session,
    decision_type: str = "reorder_quantity",   # Phase 2: scope all DB lookups by type
    disabled_terms: frozenset = frozenset(),    # ablation: score terms forced to 0 (see amdie.options)
    temperature: Optional[float] = None,        # softmax temperature; None -> settings
) -> tuple[Dict[str, float], Dict[str, Dict[str, float]]]:
    """
    Computes tenant-scoped adaptive weights for each agent, isolated per decision_type.

    Score formula (v2):
        score_i = w1*reliability_i + w2*confidence_i + w3*historical_accuracy_i
                + w4*context_relevance_i - w5*risk_score_i - w6*divergence_i

    COLD-START: w1..w6 are initialised to domain-informed priors.  They are
    refitted via linear regression once >= 30 decisions with outcomes exist
    for the (tenant, decision_type) pair (see check_and_trigger_retraining).

    Phase 2 change: every DB query now includes `decision_type` so that a
    tenant's pricing-agent weights are never contaminated by reorder-quantity
    training data, and vice versa.
    """
    # 1. Load or create tenant weight coefficients for this decision_type
    coefs = db.query(WeightCoefficients).filter_by(
        tenant_id=tenant_id, decision_type=decision_type
    ).first()
    if not coefs:
        coefs = WeightCoefficients(
            tenant_id=tenant_id,
            decision_type=decision_type,
            w1=0.30, w2=0.20, w3=0.25, w4=0.10, w5=0.15, w6=0.15,
        )
        db.add(coefs)
        db.commit()

    # 2. Query embedding for context relevance
    q_emb = get_embedding(query_text)

    # 3. Ensemble median recommendation for outlier penalty
    recs = [dec.recommendation for dec in decisions.values()]
    median_rec = float(np.median(recs)) if recs else 1.0

    scores: Dict[str, float] = {}
    components: Dict[str, Dict[str, float]] = {}

    for agent_id, dec in decisions.items():
        # Reliability (EMA) and trailing historical accuracy — scoped by decision_type
        acc_rec = db.query(AgentAccuracy).filter_by(
            tenant_id=tenant_id, agent_id=agent_id, decision_type=decision_type
        ).first()
        reliability = acc_rec.reliability if acc_rec else 1.0

        hist_logs = db.query(HistoricalAccuracyLog).filter_by(
            tenant_id=tenant_id, agent_id=agent_id, decision_type=decision_type
        ).all()
        historical_accuracy = float(np.mean([l.accuracy for l in hist_logs])) if hist_logs else 1.0

        # Context relevance via cosine similarity
        context_relevance = compute_context_relevance(agent_id, q_emb)

        # Agent's own fields
        confidence  = dec.confidence
        risk_score  = dec.risk_score

        # ── Outlier divergence penalty (v2) ──────────────────────────────────
        divergence = abs(dec.recommendation - median_rec) / max(abs(median_rec), 1.0)
        divergence = float(np.clip(divergence, 0.0, 1.0))

        # ── Score ─────────────────────────────────────────────────────────────
        w6 = getattr(coefs, "w6", 0.15)
        on = lambda term: 0.0 if term in disabled_terms else 1.0  # noqa: E731
        score = (
            on("reliability")         * coefs.w1 * reliability
            + on("confidence")        * coefs.w2 * confidence
            + on("historical_accuracy") * coefs.w3 * historical_accuracy
            + on("context_relevance") * coefs.w4 * context_relevance
            - on("risk")              * coefs.w5 * risk_score
            - on("divergence")        * w6       * divergence
        )
        scores[agent_id] = float(score)
        components[agent_id] = {
            "reliability":         reliability,
            "confidence":          confidence,
            "historical_accuracy": historical_accuracy,
            "context_relevance":   context_relevance,
            "risk_score":          risk_score,
            "divergence_penalty":  divergence,
            "raw_score":           float(score),
        }

    # 4. Softmax weights
    agent_ids = list(decisions.keys())
    temp = settings.AMDIE_WEIGHT_TEMPERATURE if temperature is None else temperature
    weights_list = softmax([scores[a] for a in agent_ids], temperature=temp)
    weights = {agent_ids[i]: weights_list[i] for i in range(len(agent_ids))}
    return weights, components


# ── Reliability update ──────────────────────────────────────────────────────────

def update_reliability_and_logs(
    tenant_id: str,
    decision_log_id: str,
    actual_outcome: float,
    db: Session,
    decision_type: str = "reorder_quantity",   # Phase 2: scoped by type
    quantile_level: Optional[float] = None,    # None -> service level from settings
):
    """
    Called when a decision's actual outcome is POSTed.
    Updates agent reliability EMA and appends to the historical accuracy log,
    scoped by decision_type so pricing accuracy never bleeds into reorder scores.
    """
    import json
    dec_log = db.query(DecisionLog).filter_by(
        id=decision_log_id, tenant_id=tenant_id
    ).first()
    if not dec_log:
        return

    dec_log.actual_outcome = actual_outcome
    agent_decisions = json.loads(dec_log.agent_decisions)
    alpha = 0.3   # EMA smoothing factor
    level = quantile_level_for(decision_type, quantile_level)

    for agent_id, dec_raw in agent_decisions.items():
        rec = dec_raw["recommendation"]
        accuracy = recommendation_accuracy(rec, actual_outcome, level)

        acc_rec = db.query(AgentAccuracy).filter_by(
            tenant_id=tenant_id, agent_id=agent_id, decision_type=decision_type
        ).first()
        if not acc_rec:
            acc_rec = AgentAccuracy(
                tenant_id=tenant_id, agent_id=agent_id,
                decision_type=decision_type,
                last_accuracy=accuracy, reliability=accuracy,
            )
            db.add(acc_rec)
        else:
            acc_rec.last_accuracy = accuracy
            acc_rec.reliability = alpha * accuracy + (1.0 - alpha) * acc_rec.reliability
            acc_rec.updated_at = utcnow()

        db.add(HistoricalAccuracyLog(
            tenant_id=tenant_id,
            agent_id=agent_id,
            decision_type=decision_type,
            date=dec_log.date,
            accuracy=accuracy,
        ))

    db.commit()


# ── Periodic retraining ────────────────────────────────────────────────────────

def check_and_trigger_retraining(
    tenant_id: str,
    db: Session,
    decision_type: str = "reorder_quantity",   # Phase 2: scoped by type
    quantile_level: Optional[float] = None,
):
    """
    Refits w1..w6 via linear regression once >= 30 decisions with logged outcomes
    exist for the (tenant, decision_type) pair.

    COLD-START RULE: Before 30 outcomes are available the domain-informed priors
    (w1=0.30, w2=0.20, w3=0.25, w4=0.10, w5=0.15, w6=0.15) remain in effect.
    Each decision_type retrains independently — 30 pricing outcomes are needed
    before pricing weights are updated, regardless of reorder_quantity history.
    """
    coefs = db.query(WeightCoefficients).filter_by(
        tenant_id=tenant_id, decision_type=decision_type
    ).first()
    if not coefs:
        coefs = WeightCoefficients(
            tenant_id=tenant_id,
            decision_type=decision_type,
            w1=0.30, w2=0.20, w3=0.25, w4=0.10, w5=0.15, w6=0.15,
        )
        db.add(coefs)
        db.commit()

    # Only fetch completed decisions for this decision_type
    completed = db.query(DecisionLog).filter(
        DecisionLog.tenant_id == tenant_id,
        DecisionLog.decision_type == decision_type,
        DecisionLog.actual_outcome.isnot(None),
    ).all()

    if len(completed) < 30 or len(completed) <= coefs.trained_on_n_decisions:
        return   # Cold-start guard: not enough data yet

    import json
    from sklearn.linear_model import LinearRegression

    level = quantile_level_for(decision_type, quantile_level)
    X, y = [], []
    for dec in completed:
        actual      = dec.actual_outcome
        weights_info = json.loads(dec.weights)
        agent_decs   = json.loads(dec.agent_decisions)

        for agent_id, comps in weights_info.items():
            if agent_id not in agent_decs:
                continue
            rec = agent_decs[agent_id]["recommendation"]
            accuracy = recommendation_accuracy(rec, actual, level)

            X.append([
                comps.get("reliability",         1.0),
                comps.get("confidence",          1.0),
                comps.get("historical_accuracy", 1.0),
                comps.get("context_relevance",   1.0),
                -comps.get("risk_score",         0.0),
                -comps.get("divergence_penalty", 0.0),
            ])
            y.append(accuracy)

    if len(X) >= 30:
        reg = LinearRegression(fit_intercept=False)
        reg.fit(X, y)
        w = np.clip(reg.coef_, 0.0, 2.0)
        coefs.w1, coefs.w2, coefs.w3 = float(w[0]), float(w[1]), float(w[2])
        coefs.w4, coefs.w5           = float(w[3]), float(w[4])
        coefs.w6                     = float(w[5]) if len(w) > 5 else 0.15
        coefs.trained_on_n_decisions = len(completed)
        coefs.updated_at = utcnow()
        db.commit()
        print(
            f"[AMDIE] Retrained weights for tenant={tenant_id} decision_type={decision_type}: "
            f"w={coefs.w1:.3f},{coefs.w2:.3f},{coefs.w3:.3f},"
            f"{coefs.w4:.3f},{coefs.w5:.3f},{coefs.w6:.3f}"
        )
