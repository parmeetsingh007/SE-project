"""Coordinator: wires extraction -> classification -> compliance -> persistence.

Agents are stubbed here (they're tested against mocked LLM calls in their own
test files) so this test focuses purely on the coordinator's sequencing and
the write to SQLite.
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from src.agents.compliance import ComplianceProposal
from src.agents.coordinator import Coordinator
from src.agents.extraction import ExtractedRequirementCandidate
from src.models.db import Base, RequirementORM, engine
from src.models.requirement import RequirementCategory


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


def test_coordinator_persists_classified_requirements(db_session: Session) -> None:
    fake_extraction = MagicMock()
    fake_extraction.run.return_value = [
        ExtractedRequirementCandidate(
            statement="The system shall require step-up authentication above "
            "the risk threshold.",
            source_stakeholder="Marcus Webb (Security Lead)",
        )
    ]

    fake_classification = MagicMock()

    def classify(requirements, db_session=None):
        return {requirements[0].id: [RequirementCategory.SECURITY]}

    fake_classification.run.side_effect = classify

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

    coordinator = Coordinator(
        extraction_agent=fake_extraction,
        classification_agent=fake_classification,
        compliance_agent=fake_compliance,
    )
    requirements = coordinator.run("irrelevant transcript text", db_session)

    assert len(requirements) == 1
    assert requirements[0].category == [RequirementCategory.SECURITY]
    assert requirements[0].applicable_regulations == [
        "RBI AFA-2 - Risk-Based Step-Up Authentication"
    ]

    persisted = db_session.get(RequirementORM, requirements[0].id)
    assert persisted is not None
    assert persisted.category == ["security"]
    assert persisted.applicable_regulations == ["RBI AFA-2 - Risk-Based Step-Up Authentication"]
