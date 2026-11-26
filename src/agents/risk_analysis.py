"""Builds the risk register: one scored risk per requirement, with mitigation."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.common import DOMAIN, JSON_ONLY, dumps
from src.agents.llm_client import call_agent_json
from src.models.requirement import RiskItem, RiskLevel, Requirement

RISK_TYPES = ["business", "technical", "compliance", "security", "operational"]

SYSTEM_PROMPT = f"""\
You are the risk-analysis agent for {DOMAIN}. You receive a JSON list of requirements with \
"ref", "statement", "categories", "weak" (true if the requirement is still vague or incomplete) \
and "regulations" (clause ids it maps to).

For EACH requirement write the single most significant risk if it is built wrongly, built too \
late or left out:
- risk: one sentence describing what could go wrong and why it matters
- risk_type: one of {", ".join(RISK_TYPES)}
- likelihood: integer 1 (rare) to 5 (almost certain). A weak requirement is more likely to be \
built wrongly, so raise likelihood for vague ones.
- impact: integer 1 (minor) to 5 (severe: regulatory penalty, fraud loss, customer harm, data breach)
- mitigation: one concrete action
- confidence: 0.0-1.0, how confident you are in this assessment given the information available. \
Vague input lowers confidence; it does not by itself raise the risk score.

{JSON_ONLY}
{{"risks": [{{"ref": str, "risk": str, "risk_type": str, "likelihood": int, "impact": int,
"mitigation": str, "confidence": float}}]}}
Every input "ref" must appear exactly once.
"""


class RiskOut(BaseModel):
    ref: str
    risk: str
    risk_type: str = "business"
    likelihood: int = Field(default=3, ge=1, le=5)
    impact: int = Field(default=3, ge=1, le=5)
    mitigation: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class RiskOutput(BaseModel):
    risks: list[RiskOut]


def requirement_confidence(requirement: Requirement, model_confidence: float) -> float:
    """Explainable score: 40% the model's own confidence, 30% clarity, 30% regulatory support."""
    clarity = 0.35 if requirement.is_weak else 1.0
    if requirement.regulations:
        support = sum(m.confidence for m in requirement.regulations) / len(requirement.regulations)
    else:
        support = 0.5
    return round(0.4 * model_confidence + 0.3 * clarity + 0.3 * support, 2)


class RiskAnalysisAgent:
    def run(
        self, requirements: list[Requirement], db_session: Session | None = None
    ) -> list[RiskItem]:
        """Returns the risk register entries and sets risk_level/risk_scores/confidence_score."""
        payload = [
            {
                "ref": r.ref,
                "statement": r.statement,
                "categories": [c.value for c in r.categories],
                "weak": r.is_weak,
                "regulations": [m.clause_id for m in r.regulations],
            }
            for r in requirements
        ]
        output = call_agent_json(
            agent_name="risk_analysis",
            system_prompt=SYSTEM_PROMPT,
            user_content=dumps(payload),
            output_model=RiskOutput,
            db_session=db_session,
        )
        by_ref = {item.ref: item for item in output.risks}
        items: list[RiskItem] = []
        for requirement in requirements:
            raw = by_ref.get(requirement.ref)
            if raw is None:
                continue
            item = RiskItem(
                requirement_id=requirement.id,
                risk=raw.risk,
                risk_type=raw.risk_type if raw.risk_type in RISK_TYPES else "business",
                likelihood=raw.likelihood,
                impact=raw.impact,
                mitigation=raw.mitigation,
                confidence=raw.confidence,
            )
            items.append(item)
            requirement.risk_level = item.level
            requirement.risk_scores = {
                "likelihood": item.likelihood,
                "impact": item.impact,
                "score": item.score,
            }
            requirement.confidence_score = requirement_confidence(requirement, raw.confidence)
        return items


__all__ = ["RiskAnalysisAgent", "RiskLevel", "requirement_confidence"]
