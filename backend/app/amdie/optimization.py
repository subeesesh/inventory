import numpy as np
from scipy.optimize import linprog
from typing import Dict, Optional
from backend.app.agents.base import DecisionObject


def _clamp(x: float, lower: Optional[float], upper: Optional[float]) -> float:
    if lower is not None:
        x = max(lower, x)
    if upper is not None:
        x = min(upper, x)
    return x


def solve_decision_fusion(
    weights: Dict[str, float],
    decisions: Dict[str, DecisionObject],
    unit_cost: float,
    budget: float,
    warehouse_capacity: float = None,
    cost_penalty: float = 0.0,
    turnover_bonus: float = 0.0,
    forecasted_demand: float = 0.0,
    delta: float = 50.0,
    # Phase 2: upper bound on the decision variable (e.g. 1.0 for discount_depth)
    x_upper_bound: Optional[float] = None,
    # Lower bound on the decision variable; None = signed axis (price cuts,
    # staffing reductions are valid negative recommendations).
    x_lower_bound: Optional[float] = 0.0,
) -> tuple[float, float, dict]:
    """
    Solves the fused decision problem via LP (HiGHS solver):

        maximize  sum_i( weight_i * U_i(x) ) - cost_penalty*x + turnover_bonus*min(x, demand)
        subject to:
            x >= x_lower_bound        (default 0; None for signed axes)
            x * unit_cost <= budget
            x <= warehouse_capacity   (if specified)
            x <= x_upper_bound        (Phase 2: e.g. 1.0 for promotion_trigger discount depth)

    Utility function (v2 — relative spread):
        U_i(x) = max(0, 1 - |x - R_i| / spread_i)

    where  spread_i = (0.4 * R_i + delta) / max(confidence_i, 0.01)

    The LP reformulation introduces auxiliary variables u_i (one per agent) and z
    (for the turnover min() term):
        Variables: [x, u_1, ..., u_n, z]   (n = number of agents)
    """
    agents = list(decisions.keys())
    n_agents = len(agents)
    n_vars = 1 + n_agents + 1   # x, u_i..., z

    # ── Objective (linprog minimises, so negate the maximisation target) ────
    c = np.zeros(n_vars)
    c[0] = cost_penalty                          # + cost_penalty * x
    for idx, aid in enumerate(agents):
        c[1 + idx] = -weights[aid]               # - weight_i * u_i
    c[-1] = -turnover_bonus                      # - turnover_bonus * z

    # ── Inequality constraints: A_ub @ v <= b_ub ────────────────────────────
    A_ub, b_ub = [], []

    for idx, aid in enumerate(agents):
        dec    = decisions[aid]
        rec    = dec.recommendation
        conf   = max(dec.confidence, 0.01)

        # ── Relative spread (v2) ──────────────────────────────────────────
        spread = (0.4 * abs(rec) + delta) / conf   # abs() handles price deltas

        # u_i + x / spread <= 1 + R_i / spread    (right side of triangle)
        row1 = np.zeros(n_vars); row1[0] = 1.0 / spread; row1[1 + idx] = 1.0
        A_ub.append(row1); b_ub.append(1.0 + rec / spread)

        # u_i - x / spread <= 1 - R_i / spread    (left side of triangle)
        row2 = np.zeros(n_vars); row2[0] = -1.0 / spread; row2[1 + idx] = 1.0
        A_ub.append(row2); b_ub.append(1.0 - rec / spread)

    # Budget constraint: x * unit_cost <= budget
    if unit_cost > 0:
        row_budget = np.zeros(n_vars); row_budget[0] = unit_cost
        A_ub.append(row_budget); b_ub.append(budget)

    # Warehouse capacity: x <= warehouse_capacity
    if warehouse_capacity is not None and warehouse_capacity > 0:
        row_wh = np.zeros(n_vars); row_wh[0] = 1.0
        A_ub.append(row_wh); b_ub.append(warehouse_capacity)

    # Phase 2: generic upper bound (e.g. discount_depth <= 1.0 for promotion_trigger)
    if x_upper_bound is not None:
        row_ub = np.zeros(n_vars); row_ub[0] = 1.0
        A_ub.append(row_ub); b_ub.append(x_upper_bound)

    # Turnover: z <= x  →  -x + z <= 0
    row_t1 = np.zeros(n_vars); row_t1[0] = -1.0; row_t1[-1] = 1.0
    A_ub.append(row_t1); b_ub.append(0.0)

    # Turnover: z <= forecasted_demand
    row_t2 = np.zeros(n_vars); row_t2[-1] = 1.0
    A_ub.append(row_t2); b_ub.append(max(forecasted_demand, 0.0))

    # ── Bounds ─────────────────────────────────────────────────────────────
    # None = unconstrained (HiGHS handles None).  z is left free so that the
    # z <= x row does not implicitly force x >= 0 on signed axes; when
    # turnover_bonus > 0 the maximisation still drives z to min(x, demand).
    bounds = [(x_lower_bound, x_upper_bound)] + [(0, 1.0)] * n_agents + [(None, None)]

    # ── Solve ───────────────────────────────────────────────────────────────
    res = linprog(
        c=c,
        A_ub=np.array(A_ub) if A_ub else None,
        b_ub=np.array(b_ub) if b_ub else None,
        bounds=bounds,
        method="highs",
    )

    if res.success:
        x_opt = _clamp(float(res.x[0]), x_lower_bound, x_upper_bound)
        opt_log = {
            "success":          True,
            "x":                x_opt,
            "fused_utility":    float(-res.fun),
            "agent_utilities":  {agents[i]: float(res.x[1 + i]) for i in range(n_agents)},
            "turnover_val":     float(res.x[-1]),
            "status_message":   str(res.message),
            "x_upper_bound":    x_upper_bound,
            "x_lower_bound":    x_lower_bound,
            "spread_values":    {
                agents[i]: (0.4 * abs(decisions[agents[i]].recommendation) + delta)
                           / max(decisions[agents[i]].confidence, 0.01)
                for i in range(n_agents)
            },
        }
        return x_opt, float(-res.fun), opt_log

    # ── Fallback: budget-capped weighted average ─────────────────────────
    weighted_avg = sum(weights[a] * decisions[a].recommendation for a in agents)
    max_budget_qty = budget / unit_cost if unit_cost > 0 else weighted_avg
    x_fallback = min(weighted_avg, max_budget_qty)
    if warehouse_capacity is not None:
        x_fallback = min(x_fallback, warehouse_capacity)
    x_fallback = _clamp(x_fallback, x_lower_bound, x_upper_bound)

    opt_log = {
        "success":       False,
        "error":         str(res.message),
        "fallback_used": True,
        "x":             x_fallback,
        "fused_utility": 0.0,
        "agent_utilities": {},
    }
    return x_fallback, 0.0, opt_log
