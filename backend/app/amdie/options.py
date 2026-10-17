"""
AMDIE pipeline switches.

The production pipeline always runs with the defaults.  The switches exist so
the experiment harness (backend/experiments) can ablate one component at a
time through the exact code path the API uses, rather than a re-implementation.
"""

from dataclasses import dataclass, field
from typing import FrozenSet, Optional

# Terms of the adaptive weight score that can be ablated (see weights.get_agent_weights)
WEIGHT_TERMS = ("reliability", "confidence", "historical_accuracy", "context_relevance", "risk", "divergence")


@dataclass(frozen=True)
class AmdieOptions:
    # False -> every agent gets weight 1/n (static equal weights)
    adaptive_weights: bool = True
    # Score terms dropped from the adaptive weight formula
    disabled_weight_terms: FrozenSet[str] = field(default_factory=frozenset)
    # False -> fused value = weighted average of recommendations (clipped to the
    # same constraints) instead of the constrained LP
    lp_fusion: bool = True
    # False -> agents' hard caps (DecisionObject.upper_limit) are ignored
    agent_caps: bool = True
    # False -> skip natural-language explanation generation (no LLM call)
    explain: bool = True
    # Softmax temperature for adaptive weights; None -> settings.AMDIE_WEIGHT_TEMPERATURE
    weight_temperature: Optional[float] = None

    def __post_init__(self):
        unknown = set(self.disabled_weight_terms) - set(WEIGHT_TERMS)
        if unknown:
            raise ValueError(f"Unknown weight terms: {sorted(unknown)}")


DEFAULT_OPTIONS = AmdieOptions()
