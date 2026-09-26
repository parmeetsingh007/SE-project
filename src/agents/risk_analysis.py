"""Scores business/technical/compliance risk for a single requirement.

Populates the Requirement's risk_level and confidence_score fields — the only
two risk-related fields in the fixed data model — while keeping the full
per-dimension breakdown available via the audit log for traceability.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.llm_client import call_agent_json
from src.models.requirement import Requirement, RiskLevel

SYSTEM_PROMPT = """\
You are the risk-analysis agent in a requirements-gathering pipeline for a bank's \
payment-processing feature. You will be given a requirement statement and its \
category tags.

Score three risk dimensions from 0.0 (negligible) to 1.0 (severe):
- business_risk: impact on revenue, customer trust, or transaction friction if
  this requirement is done wrong or omitted
- technical_risk: implementation difficulty, dependency on unreliable systems
  (e.g. carrier SMS delivery, third-party biometric SDKs), or performance risk
- compliance_risk: risk of a regulatory finding or audit failure if this
  requirement is done wrong or omitted

Then give overall_risk_level as "low", "medium", or "high", and a confidence
score (0.0-1.0) reflecting how confident you are in this assessment given the
information available (a vague or underspecified requirement should lower
confidence, not risk).

Respond with ONLY valid JSON matching this schema, no prose before or after:
{"business_risk": float, "technical_risk": float, "compliance_risk": float,
"overall_risk_level": "low" | "medium" | "high", "confidence": float,
"rationale": str}
"""


class RiskScores(BaseModel):
    business_risk: float = Field(ge=0.0, le=1.0)
    technical_risk: float = Field(ge=0.0, le=1.0)
    compliance_risk: float = Field(ge=0.0, le=1.0)
    overall_risk_level: RiskLevel
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class RiskAnalysisAgent:
    """Scores business/technical/compliance risk for one requirement."""

    def run(
        self, requirement: Requirement, db_session: Session | None = None
    ) -> RiskScores:
        payload = {
            "statement": requirement.statement,
            "category": [c.value for c in requirement.category],
        }
        return call_agent_json(
            agent_name="risk_analysis",
            system_prompt=SYSTEM_PROMPT,
            user_content=json.dumps(payload),
            output_model=RiskScores,
            db_session=db_session,
        )
