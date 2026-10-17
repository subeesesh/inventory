from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from sqlalchemy.orm import Session
from datetime import date

class DecisionObject(BaseModel):
    agent_id: str = Field(..., description="Unique identifier for the agent")
    recommendation: float = Field(..., description="Numeric recommendation on the decision type's axis (see decision_registry.DECISION_TYPE_AXIS)")
    reason: str = Field(..., description="Text rationale explaining the recommendation")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score [0, 1]")
    priority: float = Field(..., ge=0.0, le=1.0, description="Priority rating [0, 1]")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Calculated risk score [0, 1]")
    expected_cost: float = Field(..., description="Total cost of recommendation")
    expected_benefit: float = Field(..., description="Total expected benefit of recommendation")
    required_resources: Dict[str, Any] = Field(..., description="Resource dictionary needed (e.g. cash, space)")
    historical_similarity: float = Field(..., ge=0.0, le=1.0, description="Cosine similarity to similar past decisions [0, 1]")
    upper_limit: Optional[float] = Field(
        default=None,
        description="Hard feasibility cap this agent imposes on the decision (e.g. what Finance can afford). "
                    "AMDIE applies it as an LP constraint, separate from the agent's preferred `recommendation`.",
    )

class BaseAgent(ABC):
    def __init__(self, agent_id: str):
        self.agent_id = agent_id

    @abstractmethod
    def run(
        self,
        tenant_id: str,
        product_id: str,
        run_date: date,
        db: Session,
        decision_type: str = "reorder_quantity",
    ) -> DecisionObject:
        """Run the agent logic using Retrieval Manager context and output a validated DecisionObject.

        `decision_type` selects the axis the recommendation is expressed on.
        Agents that participate in several decision types (Sales, Finance,
        Marketing) must project their view onto that axis so AMDIE never fuses
        values with different units.  Single-axis agents may ignore it.
        """
        pass
