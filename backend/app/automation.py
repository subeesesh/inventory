"""
Business Automation & Alert System
==================================
BizTwin AI Business Automation & Alert System (§III-J).

Every decision produced by the autonomous pipeline (monitoring event -> AMDIE)
is routed through the AutomationPolicyEngine and persisted as an
AutomationAction:

- Routine, low-risk actions (reorders under the auto-approval cost limit) are
  dispatched immediately as owner/supplier notifications (status "notified").
- High-impact actions (pricing, staffing, or anything over the cost limit) are
  queued as "pending_review" and require explicit owner approval.

Nothing here mutates stock, prices or purchase orders: even an approved action
is a reviewed instruction, which the owner then carries out in the POS /
Purchases screens.  Unrestricted auto-purchasing / auto-pricing is out of scope.
"""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.app.clock import utcnow
from backend.app.config import settings
from backend.app.db import AutomationAction, Product
from backend.app.decision_registry import DECISION_TYPE_AXIS

logger = logging.getLogger(__name__)

# Decision types that always require an owner, regardless of cost
HIGH_IMPACT_ACTIONS = ("price_adjustment", "staffing_adjustment")


class AutomationPolicyEngine:
    """
    Evaluates proposed actions against business safety policies to determine
    whether an action can auto-execute or requires human review.
    """
    def __init__(self, tenant_id: str, db: Session):
        self.tenant_id = tenant_id
        self.db = db

    def evaluate_action_policy(self, action_type: str, estimated_cost: float) -> Dict[str, Any]:
        """
        Evaluate if an action is eligible for routine auto-execution.
        """
        cost_limit = settings.AUTOMATION_AUTO_APPROVAL_COST_LIMIT

        if estimated_cost > cost_limit or action_type in HIGH_IMPACT_ACTIONS:
            return {
                "action_type": action_type,
                "auto_executable": False,
                "requires_owner_review": True,
                "policy_reason": f"High impact action ({action_type}) or cost (${estimated_cost:.2f}) exceeds auto-approval threshold (${cost_limit:.2f}). Required role review: Owner/Manager."
            }

        return {
            "action_type": action_type,
            "auto_executable": True,
            "requires_owner_review": False,
            "policy_reason": f"Routine low-risk action under auto-approval threshold (${cost_limit:.2f})."
        }

    def route_decision(
        self,
        decision: Dict[str, Any],
        product_id: str,
        monitoring_event_id: Optional[str] = None,
    ) -> AutomationAction:
        """
        Apply the policy to an AMDIE decision result (as returned by
        trigger_decision_internal) and persist the resulting AutomationAction.
        """
        action_type = decision["decision_type"]
        fused = float(decision["fused_recommendation"])

        product = self.db.query(Product).filter_by(tenant_id=self.tenant_id, id=product_id).first()
        product_name = product.name if product else product_id
        estimated_cost = 0.0
        if action_type == "reorder_quantity" and product:
            estimated_cost = fused * product.unit_cost

        policy = self.evaluate_action_policy(action_type, estimated_cost)
        axis = DECISION_TYPE_AXIS.get(action_type, "value")
        description = (
            f"{action_type.replace('_', ' ').title()} for {product_name}: "
            f"{fused:,.2f} {axis}"
        )

        action = AutomationAction(
            tenant_id=self.tenant_id,
            decision_id=decision.get("decision_id"),
            monitoring_event_id=monitoring_event_id,
            action_type=action_type,
            product_id=product_id,
            description=description,
            estimated_cost=round(estimated_cost, 2),
            auto_executable=policy["auto_executable"],
            status="notified" if policy["auto_executable"] else "pending_review",
            policy_reason=policy["policy_reason"],
        )
        self.db.add(action)
        self.db.commit()

        if action.status == "notified":
            # Notification channel (email/SMS/webhook) is a deployment concern; the
            # persisted action is the alert-feed entry the dashboard shows.
            logger.info("[Automation] tenant=%s notified: %s", self.tenant_id, description)
        return action

    def review(self, action_id: str, approve: bool, reviewer_id: Optional[str]) -> tuple[Optional[AutomationAction], bool]:
        """
        Owner approval / rejection of a pending action.
        Returns (action, reviewed): action is None if not found; reviewed is False
        when the action was not awaiting review.
        """
        action = self.db.query(AutomationAction).filter_by(
            id=action_id, tenant_id=self.tenant_id
        ).first()
        if not action or action.status != "pending_review":
            return action, False
        action.status = "approved" if approve else "rejected"
        action.reviewed_at = utcnow()
        action.reviewed_by = reviewer_id
        self.db.commit()
        return action, True


def serialize_action(a: AutomationAction) -> Dict[str, Any]:
    return {
        "id": a.id,
        "decision_id": a.decision_id,
        "monitoring_event_id": a.monitoring_event_id,
        "action_type": a.action_type,
        "product_id": a.product_id,
        "description": a.description,
        "estimated_cost": a.estimated_cost,
        "auto_executable": a.auto_executable,
        "status": a.status,
        "policy_reason": a.policy_reason,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
    }
