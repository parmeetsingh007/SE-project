"""Final completeness/consistency check across the whole batch, run once,
right before the human-approval gate.

Deterministic, not an LLM call: the checks here (a field is missing, or a
requirement has no traceability link back to the transcript) don't need
judgment — that's what clarification.py is for, earlier in the pipeline,
per-requirement. This agent's job is a reliable, final structural gate before
a requirement reaches a human reviewer, so it stays free of LLM variance.
"""

from __future__ import annotations

import json

from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.models.db import AuditLogORM
from src.models.requirement import Requirement


class ValidationIssue(BaseModel):
    requirement_id: str
    problems: list[str]


class ValidationAgent:
    """Checks each requirement for missing acceptance criteria, missing
    source stakeholder, missing business justification, and missing
    traceability back to its source transcript excerpt."""

    def run(
        self,
        requirements: list[Requirement],
        source_excerpts: dict[str, str] | None = None,
        db_session: Session | None = None,
    ) -> list[ValidationIssue]:
        source_excerpts = source_excerpts or {}
        issues: list[ValidationIssue] = []

        for requirement in requirements:
            problems: list[str] = []
            if not requirement.acceptance_criteria:
                problems.append("Missing acceptance criteria.")
            if not requirement.source_stakeholder.strip():
                problems.append("Missing source stakeholder.")
            if not (requirement.business_justification or "").strip():
                problems.append("Missing business justification.")
            if not source_excerpts.get(requirement.id, "").strip():
                problems.append("No traceability link back to the source transcript.")

            if problems:
                issues.append(ValidationIssue(requirement_id=requirement.id, problems=problems))

        if db_session is not None:
            db_session.add(
                AuditLogORM(
                    agent_name="validation",
                    input_payload=json.dumps([r.id for r in requirements]),
                    output_payload=json.dumps([issue.model_dump() for issue in issues]),
                )
            )
            db_session.commit()

        return issues
