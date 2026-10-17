"""
Decision Type Registry
======================
Phase 2 structural prerequisite.  Every AMDIE cycle is now scoped to a
*decision_type*, and only the agents registered for that type participate in
conflict detection, weight assignment, goal optimisation and LP fusion.

Adding a new decision type = add one entry here.  Nothing else changes in
the pipeline code.
"""

from typing import Dict, List

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
DECISION_TYPES: Dict[str, List[str]] = {
    # Inventory replenishment — original Phase 1 agents + Procurement (Phase 2)
    "reorder_quantity": ["inventory", "sales", "finance", "procurement"],

    # Pricing optimisation — Pricing Agent drives, Sales + Risk provide context
    "price_adjustment": ["pricing", "sales", "risk"],

    # Promotion / discount triggers — Marketing drives, Customer + Finance check feasibility
    "promotion_trigger": ["marketing", "finance"],

    # Staffing / workforce adjustment — HR drives, Sales (demand) + Finance (labor budget)
    "staffing_adjustment": ["hr", "sales", "finance"],

    # Customer retention action — Customer Management drives, Sales + Marketing check feasibility
    "customer_retention_action": ["customer_management", "sales", "marketing"],
}

# Human-readable labels used by the frontend
DECISION_TYPE_LABELS: Dict[str, str] = {
    "reorder_quantity":          "Reorder Quantity",
    "price_adjustment":          "Price Adjustment",
    "promotion_trigger":         "Promotion Trigger",
    "staffing_adjustment":       "Staffing Adjustment",
    "customer_retention_action": "Customer Retention Action",
}

# The recommendation axis description per type — used in LP bound hints and
# explainability NLG
DECISION_TYPE_AXIS: Dict[str, str] = {
    "reorder_quantity":          "units to order",
    "price_adjustment":          "price delta (currency units)",
    "promotion_trigger":         "discount depth (fraction 0-1)",
    "staffing_adjustment":       "staffing hours delta",
    "customer_retention_action": "retention action level (0-1)",
}

# Upper bound for the LP decision variable per type.
# None = unconstrained (only budget / warehouse capacity apply)
# For promotion_trigger and customer_retention_action the decision variable is a fraction [0, 1].
DECISION_TYPE_UPPER_BOUND: Dict[str, float | None] = {
    "reorder_quantity":          None,
    "price_adjustment":          None,  # delta is signed but LP works on magnitude
    "promotion_trigger":         1.0,
    "staffing_adjustment":       None,
    "customer_retention_action": 1.0,
}

# Lower bound for the LP decision variable per type.
# None = unbounded below: signed axes where a negative value is a real action
# (a price cut, a reduction in staffing hours).
DECISION_TYPE_LOWER_BOUND: Dict[str, float | None] = {
    "reorder_quantity":          0.0,
    "price_adjustment":          None,
    "promotion_trigger":         0.0,
    "staffing_adjustment":       None,
    "customer_retention_action": 0.0,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_agents_for_decision_type(decision_type: str) -> List[str]:
    """Return the list of agent IDs that participate in this decision type's
    AMDIE cycle.  Raises ValueError if the type is unknown."""
    if decision_type not in DECISION_TYPES:
        raise ValueError(
            f"Unknown decision_type '{decision_type}'. "
            f"Valid types: {list(DECISION_TYPES.keys())}"
        )
    return DECISION_TYPES[decision_type]


def validate_decision_type(decision_type: str) -> bool:
    """Return True if the decision_type is registered, False otherwise."""
    return decision_type in DECISION_TYPES


def get_upper_bound(decision_type: str) -> float | None:
    """Return the LP upper-bound for the decision variable, or None if
    unconstrained (additional constraints like budget / capacity still apply)."""
    return DECISION_TYPE_UPPER_BOUND.get(decision_type)


def get_lower_bound(decision_type: str) -> float | None:
    """Return the LP lower-bound for the decision variable, or None if the
    axis is signed (negative recommendations are valid actions)."""
    return DECISION_TYPE_LOWER_BOUND.get(decision_type, 0.0)


def all_decision_types() -> List[str]:
    """Return all registered decision type keys."""
    return list(DECISION_TYPES.keys())
