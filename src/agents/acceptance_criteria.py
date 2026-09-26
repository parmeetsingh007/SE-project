"""Generates acceptance criteria for a requirement.

Closes a gap flagged when validation.py shipped: nothing populated
Requirement.acceptance_criteria, so validation's completeness check always
failed. This agent fills that field before validation runs.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.llm_client import call_agent_json
from src.models.requirement import Requirement

SYSTEM_PROMPT = """\
You are the acceptance-criteria agent in a requirements-gathering pipeline for a \
bank's payment-processing feature. You will be given a requirement statement, its \
business justification (if any), and its category tags.

Write 2-4 concrete, testable acceptance criteria for this requirement — each one \
a specific pass/fail condition a QA engineer could verify directly, not a restatement \
of the requirement. Prefer "Given/When/Then" phrasing where it fits naturally. Ground \
every criterion strictly in what the requirement actually says; do not invent scope, \
numeric thresholds, or behavior that isn't stated or clearly implied.

Respond with ONLY valid JSON matching this schema, no prose before or after:
{"acceptance_criteria": [str, ...]}
"""


class AcceptanceCriteriaOutput(BaseModel):
    acceptance_criteria: list[str] = Field(min_length=1)


class AcceptanceCriteriaAgent:
    """Drafts concrete, testable acceptance criteria for one requirement."""

    def run(self, requirement: Requirement, db_session: Session | None = None) -> list[str]:
        payload = {
            "statement": requirement.statement,
            "business_justification": requirement.business_justification,
            "category": [c.value for c in requirement.category],
        }
        result = call_agent_json(
            agent_name="acceptance_criteria",
            system_prompt=SYSTEM_PROMPT,
            user_content=json.dumps(payload),
            output_model=AcceptanceCriteriaOutput,
            db_session=db_session,
        )
        return result.acceptance_criteria
