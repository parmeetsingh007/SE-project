"""Recommends SDLC model(s), ranked by confidence, from project characteristics.

Characteristics are computed deterministically from the requirement batch (no
LLM guessing at counts) and only then handed to Gemini to reason over.
"""

from __future__ import annotations

import json
from collections import Counter

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.llm_client import call_agent_json
from src.models.requirement import ApprovalStatus, Requirement, RiskLevel

SYSTEM_PROMPT = """\
You are the SDLC-selection agent for a bank's payment-processing feature project. \
You will be given aggregate characteristics computed from the project's gathered \
requirements: how many there are, their category and risk-level distribution, how \
many still need revision (incomplete/ambiguous) or have unresolved conflicts, and \
how many cite a specific regulation.

Recommend one or more SDLC models, ranked by confidence, that best fit these \
characteristics. Consider standard models: Waterfall, V-Model, Incremental, Spiral, \
Agile (Scrum/Kanban), and Agile-with-security-gates (DevSecOps-style). Ground each \
recommendation in the specific characteristics given — e.g. high regulatory density \
and compliance risk favor models with formal sign-off gates (V-Model, Waterfall, or \
Agile-with-security-gates); a high proportion of items needing revision favors an \
iterative model with tight stakeholder feedback loops (Agile, Incremental). Do not \
recommend a model without tying it to at least one specific characteristic you were \
given.

Respond with ONLY valid JSON matching this schema, no prose before or after, ranked \
highest confidence first:
{"recommendations": [{"model": str, "confidence": float, "rationale": str}]}
"""


class SDLCRecommendation(BaseModel):
    model: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class SDLCSelectionOutput(BaseModel):
    recommendations: list[SDLCRecommendation]


def summarize_requirements(requirements: list[Requirement]) -> dict:
    """Deterministic aggregate characteristics used by SDLC selection and docs."""
    category_counts: Counter[str] = Counter()
    risk_counts: Counter[str] = Counter()
    for r in requirements:
        category_counts.update(c.value for c in r.category)
        risk_counts[r.risk_level.value if r.risk_level else "unscored"] += 1

    return {
        "total_requirements": len(requirements),
        "category_counts": dict(category_counts),
        "risk_level_counts": dict(risk_counts),
        "num_needing_revision": sum(
            1 for r in requirements if r.approval_status == ApprovalStatus.NEEDS_REVISION
        ),
        "num_high_risk": risk_counts.get(RiskLevel.HIGH.value, 0),
        "num_citing_regulations": sum(1 for r in requirements if r.applicable_regulations),
    }


class SDLCSelectionAgent:
    """Recommends SDLC model(s) for the whole project, from aggregate characteristics."""

    def run(
        self, requirements: list[Requirement], db_session: Session | None = None
    ) -> list[SDLCRecommendation]:
        characteristics = summarize_requirements(requirements)
        result = call_agent_json(
            agent_name="sdlc_selection",
            system_prompt=SYSTEM_PROMPT,
            user_content=json.dumps(characteristics),
            output_model=SDLCSelectionOutput,
            db_session=db_session,
        )
        return result.recommendations
