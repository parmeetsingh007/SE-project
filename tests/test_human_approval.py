"""Human approval: not an LLM call — just the persistence gate for a decision."""

import pytest
from sqlalchemy.orm import Session

from src.agents.human_approval import ApprovalDecision, apply_approval_decision
from src.models.db import Base, RequirementORM, engine
from src.models.requirement import ApprovalStatus, Requirement


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


def test_apply_approval_decision_updates_status(db_session: Session) -> None:
    requirement = Requirement(
        statement="The system shall require step-up authentication above the "
        "risk threshold.",
        source_stakeholder="Marcus Webb (Security Lead)",
    )
    db_session.add(RequirementORM(**requirement.model_dump(mode="json")))
    db_session.commit()

    apply_approval_decision(
        ApprovalDecision(requirement_id=requirement.id, decision=ApprovalStatus.APPROVED),
        db_session,
    )

    persisted = db_session.get(RequirementORM, requirement.id)
    assert persisted.approval_status == "approved"


def test_apply_approval_decision_raises_on_unknown_id(db_session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        apply_approval_decision(
            ApprovalDecision(requirement_id="does-not-exist", decision=ApprovalStatus.APPROVED),
            db_session,
        )
