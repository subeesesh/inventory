from typing import Dict, Optional
from backend.app.agents.base import DecisionObject


def adjust_objective_for_goals(
    weights: Dict[str, float],
    decisions: Dict[str, DecisionObject],
    business_goal: str,
    unit_cost: float,
    forecasted_demand: float,
    lambda_cost: float = 0.01,
    lambda_turnover: float = 0.01,
    # Phase 2: optional Risk Agent modifier (computed externally when goal == minimize_risk)
    overall_risk_score: Optional[float] = None,
) -> dict:
    """
    Adjusts optimization parameters according to the business goal.
    Returns modifiers to be incorporated by the LP solver.

    Phase 2 additions:
    - `overall_risk_score`: when provided (and goal == minimize_risk), the risk
      modifier is applied AFTER the per-agent risk-score scaling.  This is the
      output of the Risk Agent meta-agent's `compute_overall_risk()` — it captures
      portfolio-level signals (seasonality volatility, supplier concentration) that
      individual agents cannot see.
    """
    adjusted_weights = weights.copy()
    cost_penalty = 0.0
    turnover_bonus = 0.0

    if business_goal == "minimize_risk":
        # Scale agent weight by (1 - risk_score) — original Phase 1 logic unchanged
        for agent_id, dec in decisions.items():
            adjusted_weights[agent_id] = weights[agent_id] * (1.0 - dec.risk_score)

        # Phase 2: further scale all weights by (1 - overall_risk_score) when the
        # Risk Agent's portfolio-level signal is available.  This pushes the LP
        # toward the conservative end of each agent's utility triangle without
        # changing the individual agent formulas.
        if overall_risk_score is not None:
            portfolio_safety_factor = 1.0 - float(overall_risk_score)
            for k in adjusted_weights:
                adjusted_weights[k] *= portfolio_safety_factor

        # Re-normalize
        total = sum(adjusted_weights.values())
        if total > 0:
            for k in adjusted_weights:
                adjusted_weights[k] /= total

    elif business_goal == "minimize_cost":
        # Subtract cost term: - lambda_cost * (x * unit_cost)
        cost_penalty = lambda_cost * unit_cost

    elif business_goal == "maximize_turnover":
        # Reward turnover up to forecasted demand: + lambda_turnover * min(x, forecasted_demand)
        turnover_bonus = lambda_turnover

    return {
        "adjusted_weights":   adjusted_weights,
        "cost_penalty":       cost_penalty,
        "turnover_bonus":     turnover_bonus,
        "forecasted_demand":  forecasted_demand,
        "overall_risk_score": overall_risk_score,
    }


def compute_seasonality_volatility(sales_records: list) -> float:
    """
    Helper used by the Risk Agent: coefficient of variation of daily qty_sold.
    Returns a float in [0, 1] where higher = more volatile demand.
    """
    import numpy as np
    if not sales_records:
        return 0.5
    quantities = [r.qty_sold for r in sales_records]
    mean_qty = float(np.mean(quantities))
    std_qty = float(np.std(quantities))
    cv = std_qty / max(mean_qty, 1.0)
    return float(np.clip(cv, 0.0, 1.0))


def compute_supplier_concentration(suppliers: list) -> float:
    """
    Helper used by the Risk Agent: measures over-dependence on a single supplier.
    Returns 0.0 if many reliable suppliers exist, 1.0 if there's only one source.
    """
    import numpy as np
    if not suppliers:
        return 1.0  # no supplier info = maximum concentration risk
    n = len(suppliers)
    if n == 1:
        return 1.0
    # Weight by reliability_score — low-reliability suppliers contribute less diversity
    reliabilities = [max(s.reliability_score, 0.01) for s in suppliers]
    total = sum(reliabilities)
    shares = [r / total for r in reliabilities]
    # Herfindahl-Hirschman Index (HHI): sum of squared market shares, normalised
    hhi = sum(s ** 2 for s in shares)
    hhi_min = 1.0 / n  # perfectly equal split
    hhi_max = 1.0      # monopoly
    normalised = (hhi - hhi_min) / max(hhi_max - hhi_min, 1e-6)
    return float(np.clip(normalised, 0.0, 1.0))
