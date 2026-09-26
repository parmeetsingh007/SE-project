"""Pydantic data contract for a single extracted software requirement."""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field


class RequirementCategory(str, Enum):
    """Multi-label tags a requirement can carry (assigned by classification.py)."""

    FUNCTIONAL = "functional"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    PERFORMANCE = "performance"
    USABILITY = "usability"
    OTHER = "other"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ApprovalStatus(str, Enum):
    """Nothing may be ``APPROVED`` without an explicit human click in the UI."""

    PENDING = "pending"
    NEEDS_REVISION = "needs_revision"
    APPROVED = "approved"
    REJECTED = "rejected"


class Requirement(BaseModel):
    """A single structured requirement extracted from stakeholder input.

    Field set matches the data model described in CLAUDE.md exactly, so every
    agent that produces or consumes requirements can validate against this
    one contract instead of passing raw dicts around.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    statement: str
    category: list[RequirementCategory] = Field(default_factory=list)
    source_stakeholder: str
    business_justification: str | None = None
    priority: Priority = Priority.MEDIUM
    dependencies: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    applicable_regulations: list[str] = Field(default_factory=list)
    risk_level: RiskLevel | None = None
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
