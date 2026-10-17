"""
Formalized Explainable AI (XAI) Layer
======================================
BizTwin AI explainability module (§III-H).
Provides structured, agent-traceable explanations for AMDIE decisions.
Exposes decision rationales, agent weights, confidence scores, and conflict resolution notes.
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
import json

from backend.app.db import DecisionLog, AgentAccuracy, Product


def build_structured_explanation(decision_id: str, db: Session, tenant_id: str) -> Dict[str, Any]:
    """
    Retrieve and format a structured XAI explanation for a specific decision log entry.
    """
    log = db.query(DecisionLog).filter(
        DecisionLog.id == decision_id,
        DecisionLog.tenant_id == tenant_id
    ).first()

    if not log:
        return {
            "error": "Decision log not found",
            "decision_id": decision_id
        }

    # Extract optimization & agent details if saved in log
    contributing_agents = []
    conflict_notes = "No significant inter-agent conflict detected."
    if log.conflict_detected:
        conflict_notes = f"Conflict detected (score={log.conflict_score:.2f}). AMDIE solved LP optimization to align agent goals."

    try:
        if log.optimization_problem:
            opt_data = json.loads(log.optimization_problem)
            weights = opt_data.get("weights", {})
            recs = opt_data.get("agent_recommendations", {})
            for agent_id, weight in weights.items():
                rec_val = recs.get(agent_id, {}).get("recommendation", None)
                reason = recs.get(agent_id, {}).get("reason", f"{agent_id.capitalize()} Agent recommendation")
                contributing_agents.append({
                    "agent": agent_id,
                    "weight": round(float(weight), 4),
                    "recommendation": rec_val,
                    "rationale": reason
                })
    except Exception:
        pass

    if not contributing_agents:
        contributing_agents = [
            {"agent": "primary", "weight": 1.0, "recommendation": log.fused_recommendation, "rationale": "Fused recommendation"}
        ]

    return {
        "decision_id": log.id,
        "product_id": log.product_id,
        "decision_type": log.decision_type,
        "recommendation": log.fused_recommendation,
        "confidence": float(round(min(1.0, max(0.0, 1.0 - (log.conflict_score or 0.1))), 2)),
        "contributing_agents": contributing_agents,
        "conflict_detected": log.conflict_detected,
        "conflict_score": log.conflict_score,
        "conflict_resolution_notes": conflict_notes,
        "natural_language_summary": log.natural_language_explanation or f"Recommendation: {log.fused_recommendation}",
    }
