from typing import Dict
from backend.app.agents.base import DecisionObject

def detect_conflict(decisions: Dict[str, DecisionObject], tau: float = 0.3) -> tuple[float, bool]:
    """
    Computes pairwise divergence between agent recommendations.
    conflict_score = min(1, max_pairwise( |rec_i - rec_j| / max(|rec_i|, |rec_j|, 1) ))
    If conflict_score > tau, conflict_detected = True.

    Magnitudes are used in the denominator so signed axes (price deltas,
    staffing deltas) are scored correctly; recommendations of opposite sign
    saturate at 1.0 (maximal disagreement).
    """
    agent_ids = list(decisions.keys())
    if len(agent_ids) < 2:
        return 0.0, False

    max_div = 0.0
    for i in range(len(agent_ids)):
        for j in range(i + 1, len(agent_ids)):
            rec_i = decisions[agent_ids[i]].recommendation
            rec_j = decisions[agent_ids[j]].recommendation
            denom = max(abs(rec_i), abs(rec_j), 1.0)
            div = min(1.0, abs(rec_i - rec_j) / denom)
            if div > max_div:
                max_div = div

    conflict_detected = max_div > tau
    return float(max_div), bool(conflict_detected)
