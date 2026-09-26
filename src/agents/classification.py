"""Assigns multi-label category tags (functional, security, compliance, ...)
to already-extracted requirements."""

from __future__ import annotations

import json

from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.agents.llm_client import call_agent_json
from src.models.requirement import Requirement, RequirementCategory

SYSTEM_PROMPT = """\
You are the classification agent in a requirements-gathering pipeline for a bank's \
payment-processing feature. You will be given a JSON list of requirements, each with \
an "id" and a "statement".

For each requirement, assign one or more category labels from this fixed set:
functional, security, compliance, performance, usability, other.
A requirement can (and often should) have more than one label — e.g. a step-up
authentication requirement is typically both "security" and "compliance".

Respond with ONLY valid JSON matching this schema, no prose before or after:
{"classifications": [{"id": str, "category": [str, ...]}]}
Every "id" from the input must appear exactly once in the output, and every
"category" value must be one of the fixed labels above.
"""


class ClassificationItem(BaseModel):
    id: str
    category: list[RequirementCategory]


class ClassificationOutput(BaseModel):
    classifications: list[ClassificationItem]


class ClassificationAgent:
    """Tags requirements with multi-label categories."""

    def run(
        self, requirements: list[Requirement], db_session: Session | None = None
    ) -> dict[str, list[RequirementCategory]]:
        """Returns a mapping of requirement id -> assigned categories."""
        payload = [{"id": r.id, "statement": r.statement} for r in requirements]
        result = call_agent_json(
            agent_name="classification",
            system_prompt=SYSTEM_PROMPT,
            user_content=json.dumps(payload),
            output_model=ClassificationOutput,
            db_session=db_session,
        )
        return {item.id: item.category for item in result.classifications}
