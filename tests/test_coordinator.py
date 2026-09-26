"""Coordinator: wires the full agent sequence -> persistence.

Agents are stubbed here (they're tested against mocked LLM calls in their own
test files) so this test focuses purely on the coordinator's sequencing and
the write to SQLite.
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from src.agents.clarification import ClarificationIssue, ClarificationResult
from src.agents.compliance import ComplianceProposal
from src.agents.conflict_detection import ConflictFinding
from src.agents.coordinator import Coordinator
from src.agents.extraction import ExtractedRequirementCandidate
from src.agents.risk_analysis import RiskScores
from src.models.db import Base, RequirementORM, engine
from src.models.requirement import ApprovalStatus, RequirementCategory, RiskLevel


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.rollback()
        session.query(RequirementORM).delete()
        session.commit()
        session.close()


def _stub_agents(clarification_issues: list[ClarificationIssue] | None = None):
    fake_extraction = MagicMock()
    fake_extraction.run.return_value = [
        ExtractedRequirementCandidate(
            statement="The system shall require step-up authentication above "
            "the risk threshold.",
            source_stakeholder="Marcus Webb (Security Lead)",
            open_questions=["What is the web fallback method?"],
        )
    ]

    fake_classification = MagicMock()
    fake_classification.run.side_effect = lambda requirements, db_session=None: {
        requirements[0].id: [RequirementCategory.SECURITY]
    }

    fake_compliance = MagicMock()
    fake_compliance.run.return_value = [
        ComplianceProposal(
            regulation="RBI",
            clause_id="AFA-2",
            citation="RBI AFA-2 - Risk-Based Step-Up Authentication",
            confidence=0.85,
            rationale="Matches automatic risk-based step-up authentication.",
        )
    ]

    fake_clarification = MagicMock()
    fake_clarification.run.return_value = ClarificationResult(
        is_complete=clarification_issues is None,
        issues=clarification_issues or [],
    )

    fake_security_privacy = MagicMock()
    fake_security_privacy.run.return_value = []

    fake_risk_analysis = MagicMock()
    fake_risk_analysis.run.return_value = RiskScores(
        business_risk=0.6,
        technical_risk=0.4,
        compliance_risk=0.7,
        overall_risk_level=RiskLevel.HIGH,
        confidence=0.75,
        rationale="High compliance exposure given RBI/PCI-DSS overlap.",
    )

    fake_conflict_detection = MagicMock()
    fake_conflict_detection.run.return_value = []

    return {
        "extraction_agent": fake_extraction,
        "classification_agent": fake_classification,
        "compliance_agent": fake_compliance,
        "clarification_agent": fake_clarification,
        "security_privacy_agent": fake_security_privacy,
        "risk_analysis_agent": fake_risk_analysis,
        "conflict_detection_agent": fake_conflict_detection,
    }


def test_coordinator_persists_fully_processed_requirement(db_session: Session) -> None:
    coordinator = Coordinator(**_stub_agents())
    requirements = coordinator.run("irrelevant transcript text", db_session)

    assert len(requirements) == 1
    req = requirements[0]
    assert req.category == [RequirementCategory.SECURITY]
    assert req.applicable_regulations == ["RBI AFA-2 - Risk-Based Step-Up Authentication"]
    assert req.risk_level == RiskLevel.HIGH
    assert req.confidence_score == pytest.approx(0.75)
    assert req.approval_status == ApprovalStatus.PENDING
    assert coordinator.clarification_issues == {}
    assert coordinator.conflicts == []

    persisted = db_session.get(RequirementORM, req.id)
    assert persisted is not None
    assert persisted.risk_level == "high"
    assert persisted.approval_status == "pending"


def test_coordinator_flags_incomplete_requirement_for_revision(db_session: Session) -> None:
    issue = ClarificationIssue(
        issue="No web fallback method specified.",
        follow_up_question="What authentication method should web users see?",
    )
    coordinator = Coordinator(**_stub_agents(clarification_issues=[issue]))
    requirements = coordinator.run("irrelevant transcript text", db_session)

    req = requirements[0]
    assert req.approval_status == ApprovalStatus.NEEDS_REVISION
    assert coordinator.clarification_issues[req.id] == [issue]

    persisted = db_session.get(RequirementORM, req.id)
    assert persisted.approval_status == "needs_revision"


def test_coordinator_flags_conflicting_requirements_for_revision(db_session: Session) -> None:
    agents = _stub_agents()
    fake_extraction = MagicMock()
    fake_extraction.run.return_value = [
        ExtractedRequirementCandidate(
            statement="The system shall lock the account after 3 failed attempts.",
            source_stakeholder="Marcus Webb (Security Lead)",
        ),
        ExtractedRequirementCandidate(
            statement="The system shall never lock the account regardless of "
            "failed attempts.",
            source_stakeholder="Marcus Webb (Security Lead)",
        ),
    ]
    agents["extraction_agent"] = fake_extraction
    agents["classification_agent"].run.side_effect = lambda requirements, db_session=None: {
        r.id: [] for r in requirements
    }

    coordinator = Coordinator(**agents)

    def detect_conflict(requirements, db_session=None):
        return [
            ConflictFinding(
                requirement_id_a=requirements[0].id,
                requirement_id_b=requirements[1].id,
                conflict_type="contradiction",
                explanation="One mandates lockout, the other forbids it.",
                confidence=0.9,
            )
        ]

    coordinator.conflict_detection_agent.run.side_effect = detect_conflict

    requirements = coordinator.run("irrelevant transcript text", db_session)

    assert all(r.approval_status == ApprovalStatus.NEEDS_REVISION for r in requirements)
    assert len(coordinator.conflicts) == 1
