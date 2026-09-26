"""Validation agent: deterministic completeness/consistency checks.

Not an LLM call, so nothing here needs to be mocked — these are direct
assertions against ValidationAgent's logic.
"""

import pytest
from sqlalchemy.orm import Session

from src.agents.validation import ValidationAgent
from src.models.db import AuditLogORM, Base, RequirementORM, engine
from src.models.requirement import Requirement


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.rollback()
        session.query(RequirementORM).delete()
        session.query(AuditLogORM).delete()
        session.commit()
        session.close()


def test_validation_agent_flags_all_missing_fields() -> None:
    requirement = Requirement(
        statement="The system shall do something.",
        source_stakeholder="",
        business_justification=None,
        acceptance_criteria=[],
    )

    issues = ValidationAgent().run([requirement], source_excerpts={})

    assert len(issues) == 1
    assert issues[0].requirement_id == requirement.id
    assert set(issues[0].problems) == {
        "Missing acceptance criteria.",
        "Missing source stakeholder.",
        "Missing business justification.",
        "No traceability link back to the source transcript.",
    }


def test_validation_agent_passes_a_complete_requirement() -> None:
    requirement = Requirement(
        statement="The system shall lock the account after 3 failed attempts.",
        source_stakeholder="Marcus Webb (Security Lead)",
        business_justification="Prevent brute-force account takeover.",
        acceptance_criteria=["Account locks after exactly 3 failed attempts."],
    )

    issues = ValidationAgent().run(
        [requirement],
        source_excerpts={requirement.id: "they get three attempts, then declined"},
    )

    assert issues == []


def test_validation_agent_logs_to_audit_table(db_session: Session) -> None:
    requirement = Requirement(
        statement="The system shall do something.",
        source_stakeholder="Marcus Webb (Security Lead)",
    )

    ValidationAgent().run([requirement], source_excerpts={}, db_session=db_session)

    # Other test files' real (unmocked) ValidationAgent runs share this same
    # test database and aren't cleaned up by their own fixtures, so assert
    # "at least one" rather than an exact count.
    logged = db_session.query(AuditLogORM).filter_by(agent_name="validation").all()
    assert len(logged) >= 1
    assert logged[-1].input_payload == f'["{requirement.id}"]'
