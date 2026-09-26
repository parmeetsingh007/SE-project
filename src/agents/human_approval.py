"""Data contract for human-approval decisions.

Not an LLM call. This is the one place approval_status is allowed to become
APPROVED — the Streamlit UI calls apply_approval_decision only in direct
response to an explicit reviewer click, never automatically.
"""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.models.db import RequirementORM
from src.models.requirement import ApprovalStatus


class ApprovalDecision(BaseModel):
    """What the UI needs to render and submit one reviewer decision."""

    requirement_id: str
    decision: ApprovalStatus
    reviewer: str | None = None
    note: str | None = None


def apply_approval_decision(decision: ApprovalDecision, db_session: Session) -> None:
    """Persists a human reviewer's decision on one requirement.

    Raises if the requirement doesn't exist — never silently no-ops.
    """
    row = db_session.get(RequirementORM, decision.requirement_id)
    if row is None:
        raise ValueError(f"Requirement {decision.requirement_id} not found")
    row.approval_status = decision.decision.value
    db_session.commit()
