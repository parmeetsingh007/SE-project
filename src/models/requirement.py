"""Pydantic data contracts shared by every agent, the API and the artefact writers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Category(str, Enum):
    """The 13 requirement dimensions from the problem statement (multi-label)."""

    BUSINESS = "business"
    STAKEHOLDER = "stakeholder"
    FUNCTIONAL = "functional"
    SECURITY = "security"
    PRIVACY = "privacy"
    REGULATORY = "regulatory"
    PERFORMANCE = "performance"
    AVAILABILITY = "availability"
    USABILITY = "usability"
    DATA = "data"
    INTEGRATION = "integration"
    AUDIT = "audit"
    OPERATIONAL = "operational"


# Prefix used to build a readable id such as "KYC-SEC-004" from the primary category.
CATEGORY_PREFIX = {
    Category.BUSINESS: "BR",
    Category.STAKEHOLDER: "STK",
    Category.FUNCTIONAL: "FR",
    Category.SECURITY: "SEC",
    Category.PRIVACY: "PRV",
    Category.REGULATORY: "REG",
    Category.PERFORMANCE: "PERF",
    Category.AVAILABILITY: "AVL",
    Category.USABILITY: "UX",
    Category.DATA: "DATA",
    Category.INTEGRATION: "INT",
    Category.AUDIT: "AUD",
    Category.OPERATIONAL: "OPS",
}


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
    """Nothing becomes APPROVED without an explicit human decision."""

    PENDING = "pending"
    NEEDS_REVISION = "needs_revision"
    APPROVED = "approved"
    REJECTED = "rejected"


class RegulationMapping(BaseModel):
    """One proposed link from a requirement to a knowledge-base clause."""

    regulation: str
    clause_id: str
    citation: str
    jurisdiction: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str = ""
    needs_legal_review: bool = False


class QualityFlag(BaseModel):
    """A defect found by the quality agent (ambiguity, missing detail, ...)."""

    kind: str
    detail: str


class Requirement(BaseModel):
    id: str = Field(default_factory=new_id)
    project_id: str = ""
    ref: str = ""
    statement: str
    categories: list[Category] = Field(default_factory=list)
    primary_category: Category | None = None
    source_stakeholder: str = "Unspecified"
    source_document: str = ""
    source_excerpt: str = ""
    business_justification: str | None = None
    priority: Priority = Priority.MEDIUM
    dependencies: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    regulations: list[RegulationMapping] = Field(default_factory=list)
    risk_level: RiskLevel | None = None
    risk_scores: dict[str, float] = Field(default_factory=dict)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    origin: Literal["stated", "derived"] = "stated"
    derived_reason: str = ""
    quality_flags: list[QualityFlag] = Field(default_factory=list)
    is_weak: bool = False
    hints: list[str] = Field(default_factory=list)  # extraction's raw "left unclear" notes
    history: list[dict] = Field(default_factory=list)


class Question(BaseModel):
    """A clarification question. Answering is always optional."""

    id: str = Field(default_factory=new_id)
    project_id: str = ""
    requirement_id: str
    question: str
    why: str = ""
    options: list[str] = Field(default_factory=list)  # optional quick-pick answers
    status: Literal["open", "answered", "skipped"] = "open"
    answer: str | None = None
    applied: bool = False  # True once a re-analysis has folded the answer into the requirement
    created_at: str = Field(default_factory=now_iso)
    answered_at: str | None = None


class Conflict(BaseModel):
    id: str = Field(default_factory=new_id)
    requirement_ids: list[str]
    kind: Literal["duplicate", "contradiction"]
    explanation: str
    confidence: float = 0.5
    status: Literal["open", "resolved"] = "open"
    resolution: str | None = None
    sig: str = ""  # fingerprint of the involved statements when it was found


class ControlCoverage(BaseModel):
    """Whether a mandatory regulatory control is covered by at least one requirement."""

    control_id: str
    title: str
    description: str
    regulations: list[str]
    status: Literal["covered", "partial", "gap", "not_applicable"]
    covered_by: list[str] = Field(default_factory=list)  # requirement refs
    suggested_requirement: str = ""


class RiskItem(BaseModel):
    id: str = Field(default_factory=new_id)
    requirement_id: str
    risk: str
    risk_type: Literal["business", "technical", "compliance", "security", "operational"] = "business"
    likelihood: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    mitigation: str = ""
    confidence: float = 0.5

    @property
    def score(self) -> int:
        return self.likelihood * self.impact

    @property
    def level(self) -> RiskLevel:
        if self.score >= 15:
            return RiskLevel.HIGH
        if self.score >= 8:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW


class Threat(BaseModel):
    id: str = Field(default_factory=new_id)
    stride: str
    threat: str
    asset: str = ""
    mitigated_by: list[str] = Field(default_factory=list)  # requirement ids


class Factor(BaseModel):
    """One SDLC decision factor, scored 1-5 with the evidence behind the score."""

    key: str
    label: str
    score: int = Field(ge=1, le=5)
    evidence: str


class SdlcOption(BaseModel):
    model: str
    score: float  # 0-100 suitability
    reasons: list[str] = Field(default_factory=list)


class WorkflowPhase(BaseModel):
    name: str
    goal: str
    activities: list[str]
    roles: list[str]
    deliverables: list[str]
    security_activities: list[str]
    testing: list[str]
    compliance_checkpoints: list[str]
    entry_criteria: list[str]
    exit_criteria: list[str]
    approval_gate: str
    traceability: str = ""
