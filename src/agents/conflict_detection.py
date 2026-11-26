"""Finds contradictions and duplicates across the whole requirement set."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.common import DOMAIN, JSON_ONLY, dumps
from src.agents.llm_client import call_agent_json
from src.models.requirement import Conflict, Requirement

SYSTEM_PROMPT = f"""\
You are the conflict-detection agent for {DOMAIN}. You receive a JSON list of requirements \
with "ref", "statement" and "stakeholder".

Report pairs (or small groups) that are:
- "contradiction": cannot both be implemented as written (conflicting thresholds, \
mandatory vs optional, speed vs depth of checks, who may approve, retention periods, \
different stakeholders wanting incompatible things)
- "duplicate": say materially the same thing, so one is redundant

Only report a real, specific relationship. Two requirements about the same topic are NOT a \
conflict unless they contradict or repeat each other. Report each group once. Explain the \
conflict in one or two sentences naming what exactly clashes.

{JSON_ONLY}
{{"conflicts": [{{"refs": [str, str], "kind": "contradiction" | "duplicate",
"explanation": str, "confidence": float}}]}}
If there are none, return {{"conflicts": []}}.
"""


class ConflictItem(BaseModel):
    refs: list[str] = Field(min_length=2)
    kind: Literal["contradiction", "duplicate"]
    explanation: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ConflictOutput(BaseModel):
    conflicts: list[ConflictItem] = Field(default_factory=list)


class ConflictDetectionAgent:
    def run(self, requirements: list[Requirement], db_session: Session | None = None) -> list[Conflict]:
        if len(requirements) < 2:
            return []
        payload = [
            {"ref": r.ref, "statement": r.statement, "stakeholder": r.source_stakeholder}
            for r in requirements
        ]
        result = call_agent_json(
            agent_name="conflict_detection",
            system_prompt=SYSTEM_PROMPT,
            user_content=dumps(payload),
            output_model=ConflictOutput,
            db_session=db_session,
        )
        id_by_ref = {r.ref: r.id for r in requirements}
        conflicts: list[Conflict] = []
        for item in result.conflicts:
            ids = [id_by_ref[ref] for ref in dict.fromkeys(item.refs) if ref in id_by_ref]
            if len(ids) < 2:
                continue  # references a requirement that does not exist
            conflicts.append(
                Conflict(
                    requirement_ids=ids,
                    kind=item.kind,
                    explanation=item.explanation,
                    confidence=item.confidence,
                )
            )
        return conflicts
