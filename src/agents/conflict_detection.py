"""Flags contradicting or duplicate requirements within one batch.

Operates on the whole extracted set at once (not one requirement at a time)
since a conflict is, by definition, a relationship between two requirements.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.llm_client import call_agent_json
from src.models.requirement import Requirement

SYSTEM_PROMPT = """\
You are the conflict-detection agent in a requirements-gathering pipeline for a \
bank's payment-processing feature. You will be given a JSON list of requirements, \
each with an "id" and a "statement".

Find pairs of requirements that either:
- "duplicate": say materially the same thing, so one is redundant, or
- "contradiction": cannot both be true/implemented as written (conflicting
  thresholds, conflicting mandatory-vs-optional behavior, etc.)

Only report a pair if the relationship is real and specific — do not report two
requirements just because they're both about the same general topic (e.g. two
different requirements about step-up authentication are NOT a conflict unless
they actually duplicate or contradict each other). Each pair should be reported
at most once.

Respond with ONLY valid JSON matching this schema, no prose before or after:
{"conflicts": [{"requirement_id_a": str, "requirement_id_b": str,
"conflict_type": "duplicate" | "contradiction", "explanation": str,
"confidence": float}]}
If there are no conflicts, return {"conflicts": []}.
"""


class ConflictFinding(BaseModel):
    requirement_id_a: str
    requirement_id_b: str
    conflict_type: Literal["duplicate", "contradiction"]
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)


class ConflictDetectionOutput(BaseModel):
    conflicts: list[ConflictFinding]


class ConflictDetectionAgent:
    """Flags duplicate/contradicting requirement pairs across a batch."""

    def run(
        self, requirements: list[Requirement], db_session: Session | None = None
    ) -> list[ConflictFinding]:
        if len(requirements) < 2:
            return []

        payload = [{"id": r.id, "statement": r.statement} for r in requirements]
        result = call_agent_json(
            agent_name="conflict_detection",
            system_prompt=SYSTEM_PROMPT,
            user_content=json.dumps(payload),
            output_model=ConflictDetectionOutput,
            db_session=db_session,
        )
        return result.conflicts
