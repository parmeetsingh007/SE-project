"""Coordinator.resume(): a previously-interrupted batch picks up where it
left off, skipping requirements already marked processing_complete instead
of reprocessing (and re-billing) everything from scratch.
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from src.agents.clarification import ClarificationResult
from src.agents.coordinator import Coordinator
from src.agents.risk_analysis import RiskScores
from src.models.db import Base, RequirementORM, create_batch, create_requirements, engine
from src.models.requirement import ApprovalStatus, Requirement, RiskLevel


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


def _stub_agents():
    fake_compliance = MagicMock()
    fake_compliance.run.return_value = []

    fake_clarification = MagicMock()
    fake_clarification.run.return_value = ClarificationResult(is_complete=True, issues=[])

    fake_security_privacy = MagicMock()
    fake_security_privacy.run.return_value = []

    fake_acceptance_criteria = MagicMock()
    fake_acceptance_criteria.run.return_value = ["Given ..., when ..., then ..."]

    fake_risk_analysis = MagicMock()
    fake_risk_analysis.run.return_value = RiskScores(
        business_risk=0.5,
        technical_risk=0.5,
        compliance_risk=0.5,
        overall_risk_level=RiskLevel.MEDIUM,
        confidence=0.8,
        rationale="stub",
    )

    fake_conflict_detection = MagicMock()
    fake_conflict_detection.run.return_value = []

    fake_validation = MagicMock()
    fake_validation.run.return_value = []

    return {
        "compliance_agent": fake_compliance,
        "clarification_agent": fake_clarification,
        "security_privacy_agent": fake_security_privacy,
        "acceptance_criteria_agent": fake_acceptance_criteria,
        "risk_analysis_agent": fake_risk_analysis,
        "conflict_detection_agent": fake_conflict_detection,
        "validation_agent": fake_validation,
    }


def test_resume_skips_already_complete_requirements(db_session: Session) -> None:
    batch_id = "resumable-batch"
    create_batch(db_session, batch_id, "A transcript that failed partway through")

    already_done = Requirement(
        batch_id=batch_id,
        statement="Already fully processed before the crash.",
        source_stakeholder="Someone",
        acceptance_criteria=["Pre-existing criterion, must be left untouched."],
        risk_level=RiskLevel.HIGH,
        confidence_score=0.95,
        processing_complete=True,
    )
    still_pending = Requirement(
        batch_id=batch_id,
        statement="Never got processed before the crash.",
        source_stakeholder="Someone",
        processing_complete=False,
    )
    create_requirements(db_session, [already_done, still_pending])

    coordinator = Coordinator(**_stub_agents())
    results = coordinator.resume(batch_id, db_session)

    assert len(results) == 2
    result_by_id = {r.id: r for r in results}

    # The already-complete requirement's per-requirement agents were never
    # called again for it, and its earlier data survives untouched.
    resumed_done = result_by_id[already_done.id]
    assert resumed_done.acceptance_criteria == ["Pre-existing criterion, must be left untouched."]
    assert resumed_done.confidence_score == pytest.approx(0.95)

    # The pending one actually got processed this time.
    resumed_pending = result_by_id[still_pending.id]
    assert resumed_pending.processing_complete is True
    assert resumed_pending.acceptance_criteria == ["Given ..., when ..., then ..."]
    assert resumed_pending.risk_level == RiskLevel.MEDIUM

    # Per-requirement agents ran exactly once — only for the pending one.
    assert coordinator.acceptance_criteria_agent.run.call_count == 1
    assert coordinator.risk_analysis_agent.run.call_count == 1

    # Batch-level agents still run over the *whole* set on every resume.
    conflict_call_args = coordinator.conflict_detection_agent.run.call_args
    assert len(conflict_call_args[0][0]) == 2

    persisted = db_session.get(RequirementORM, already_done.id)
    assert persisted.acceptance_criteria == ["Pre-existing criterion, must be left untouched."]


def test_resume_raises_for_unknown_batch(db_session: Session) -> None:
    coordinator = Coordinator(**_stub_agents())

    with pytest.raises(ValueError, match="nothing to resume"):
        coordinator.resume("does-not-exist", db_session)
