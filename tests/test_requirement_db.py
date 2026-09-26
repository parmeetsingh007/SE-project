"""Insert a Requirement into SQLite and read it back."""

import pytest
from sqlalchemy.orm import Session

from src.models.db import Base, RequirementORM, engine
from src.models.requirement import Priority, Requirement, RequirementCategory


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


def test_insert_and_read_back_requirement(db_session: Session) -> None:
    requirement = Requirement(
        statement="System shall require biometric step-up authentication for "
        "app payments flagged above the risk threshold.",
        category=[RequirementCategory.SECURITY, RequirementCategory.COMPLIANCE],
        source_stakeholder="Marcus Webb (Security Lead)",
        business_justification="Reduce fraud on high-risk payments per RBI/PCI-DSS.",
        priority=Priority.HIGH,
        applicable_regulations=["RBI additional factor authentication", "PCI-DSS SCA"],
        confidence_score=0.8,
    )

    row = RequirementORM(**requirement.model_dump(mode="json"))
    db_session.add(row)
    db_session.commit()

    fetched = db_session.get(RequirementORM, requirement.id)

    assert fetched is not None
    assert fetched.statement == requirement.statement
    assert fetched.source_stakeholder == "Marcus Webb (Security Lead)"
    assert fetched.category == ["security", "compliance"]
    assert fetched.priority == "high"
    assert fetched.confidence_score == pytest.approx(0.8)
