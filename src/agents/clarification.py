"""Flags incomplete or ambiguous requirements and drafts follow-up questions.

Since this pipeline runs on a recorded transcript rather than a live interview,
"sending a requirement back" means marking it NEEDS_REVISION with concrete
follow-up questions logged for a human reviewer — not re-querying a stakeholder.
"""

from __future__ import annotations

import json

from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.agents.llm_client import call_agent_json
from src.models.requirement import Requirement

SYSTEM_PROMPT = """\
You are the clarification agent in a requirements-gathering pipeline for a bank's \
payment-processing feature. You will be given a requirement statement, any \
assumptions already recorded against it, and any open questions the extraction \
agent already flagged as unresolved in the source transcript.

Decide whether the requirement is complete enough for a developer to design and \
build against without guessing. A requirement is incomplete if it has a vague \
qualifier with no concrete value ("fast", "secure", "soon"), a missing actor,
condition, or threshold, or an assumption that contradicts something else stated.

If it's complete, return is_complete: true and an empty issues list.
If not, list each specific issue with a concrete follow-up question a business
analyst could put to the stakeholder to resolve it. Do not invent issues that
aren't actually present.

Respond with ONLY valid JSON matching this schema, no prose before or after:
{"is_complete": bool, "issues": [{"issue": str, "follow_up_question": str}]}
"""


class ClarificationIssue(BaseModel):
    issue: str
    follow_up_question: str


class ClarificationResult(BaseModel):
    is_complete: bool
    issues: list[ClarificationIssue]


class ClarificationAgent:
    """Flags incomplete/ambiguous requirements for human follow-up."""

    def run(
        self,
        requirement: Requirement,
        open_questions: list[str] | None = None,
        db_session: Session | None = None,
    ) -> ClarificationResult:
        payload = {
            "statement": requirement.statement,
            "assumptions": requirement.assumptions,
            "open_questions": open_questions or [],
        }
        return call_agent_json(
            agent_name="clarification",
            system_prompt=SYSTEM_PROMPT,
            user_content=json.dumps(payload),
            output_model=ClarificationResult,
            db_session=db_session,
        )
