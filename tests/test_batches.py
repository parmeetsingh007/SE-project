"""Batch tracking: db.py's create/load/scope helpers, no LLM calls involved."""

import pytest
from sqlalchemy.orm import Session

from src.models.db import (
    Base,
    BatchORM,
    RequirementORM,
    create_batch,
    engine,
    get_batch,
    load_batches,
    load_requirements,
    save_batch_sdlc_recommendation,
)
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
        session.query(BatchORM).delete()
        session.commit()
        session.close()


def _persist(db_session: Session, batch_id: str, statement: str) -> Requirement:
    requirement = Requirement(
        batch_id=batch_id, statement=statement, source_stakeholder="Marcus Webb"
    )
    db_session.add(RequirementORM(**requirement.model_dump(mode="json")))
    db_session.commit()
    return requirement


def test_load_requirements_scopes_to_one_batch(db_session: Session) -> None:
    create_batch(db_session, "batch-a", "First transcript")
    create_batch(db_session, "batch-b", "Second transcript")
    _persist(db_session, "batch-a", "Requirement from batch A")
    _persist(db_session, "batch-b", "Requirement from batch B")

    batch_a_reqs = load_requirements(db_session, batch_id="batch-a")

    assert len(batch_a_reqs) == 1
    assert batch_a_reqs[0].statement == "Requirement from batch A"

    all_reqs = load_requirements(db_session)
    assert len(all_reqs) == 2


def test_load_batches_orders_most_recent_first(db_session: Session) -> None:
    create_batch(db_session, "older", "Older transcript")
    create_batch(db_session, "newer", "Newer transcript")

    batches = load_batches(db_session)

    assert [b.id for b in batches] == ["newer", "older"]


def test_save_and_read_back_sdlc_recommendation(db_session: Session) -> None:
    create_batch(db_session, "batch-a", "First transcript")
    recommendation = [{"model": "V-Model", "confidence": 0.9, "rationale": "High regulation."}]

    save_batch_sdlc_recommendation(db_session, "batch-a", recommendation)

    batch = get_batch(db_session, "batch-a")
    assert batch is not None
    assert batch.sdlc_recommendation == recommendation


def test_save_sdlc_recommendation_raises_on_unknown_batch(db_session: Session) -> None:
    with pytest.raises(ValueError, match="not found"):
        save_batch_sdlc_recommendation(db_session, "does-not-exist", [])
