"""SQLAlchemy models and SQLite session setup for requirements + audit log."""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, String, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from src.models.requirement import Requirement

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./sdlc_requirements.db")

# Requirements persisted before batch tracking existed are grouped under this
# fixed id, rather than each getting its own random batch, so History still
# shows one coherent (if transcript-less) entry for old data.
LEGACY_BATCH_ID = "00000000-0000-0000-0000-000000000000"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class RequirementORM(Base):
    """Persisted form of ``src.models.requirement.Requirement``.

    List fields are stored as JSON since SQLite has no native array type.
    """

    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    statement: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[list] = mapped_column(JSON, default=list)
    source_stakeholder: Mapped[str] = mapped_column(String, nullable=False)
    business_justification: Mapped[str | None] = mapped_column(String, nullable=True)
    priority: Mapped[str] = mapped_column(String, default="medium")
    dependencies: Mapped[list] = mapped_column(JSON, default=list)
    assumptions: Mapped[list] = mapped_column(JSON, default=list)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    applicable_regulations: Mapped[list] = mapped_column(JSON, default=list)
    risk_level: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    approval_status: Mapped[str] = mapped_column(String, default="pending")
    source_excerpt: Mapped[str] = mapped_column(String, default="")
    open_questions: Mapped[list] = mapped_column(JSON, default=list)
    # True once this requirement has been through compliance/clarification/
    # security/acceptance-criteria/risk-analysis — lets Coordinator.resume()
    # skip requirements a previous, interrupted run already finished.
    processing_complete: Mapped[bool] = mapped_column(Boolean, default=False)


class BatchORM(Base):
    """One row per transcript ingestion — groups the requirements it produced
    and (once generated) the SDLC recommendation for that batch."""

    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    transcript_preview: Mapped[str] = mapped_column(String, nullable=False)
    sdlc_recommendation: Mapped[list | None] = mapped_column(JSON, nullable=True)


class AuditLogORM(Base):
    """One row per agent invocation, for traceability (input, output, timestamp)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String, nullable=False)
    input_payload: Mapped[str] = mapped_column(String, nullable=False)
    output_payload: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


def init_db() -> None:
    """Creates all tables if they don't already exist, and migrates a
    database created before batch tracking existed."""
    Base.metadata.create_all(bind=engine)
    _migrate_legacy_requirements()


def _migrate_legacy_requirements() -> None:
    """Adds any requirements columns introduced after a database was first
    created (batch_id, and later source_excerpt/open_questions/
    processing_complete), backfilling sensible defaults for existing rows."""
    with engine.connect() as conn:
        columns = [row[1] for row in conn.execute(text("PRAGMA table_info(requirements)"))]
        if "batch_id" not in columns:
            conn.execute(text("ALTER TABLE requirements ADD COLUMN batch_id VARCHAR"))
            conn.execute(
                text("UPDATE requirements SET batch_id = :legacy WHERE batch_id IS NULL"),
                {"legacy": LEGACY_BATCH_ID},
            )
        if "source_excerpt" not in columns:
            conn.execute(text("ALTER TABLE requirements ADD COLUMN source_excerpt VARCHAR"))
            conn.execute(text("UPDATE requirements SET source_excerpt = '' WHERE source_excerpt IS NULL"))
        if "open_questions" not in columns:
            conn.execute(text("ALTER TABLE requirements ADD COLUMN open_questions JSON"))
            conn.execute(text("UPDATE requirements SET open_questions = '[]' WHERE open_questions IS NULL"))
        if "processing_complete" not in columns:
            conn.execute(text("ALTER TABLE requirements ADD COLUMN processing_complete BOOLEAN"))
            # Pre-existing rows were persisted by the old all-at-once flow, so
            # by definition they already finished the full per-requirement
            # agent loop — mark them complete rather than eligible for resume.
            conn.execute(
                text(
                    "UPDATE requirements SET processing_complete = 1 "
                    "WHERE processing_complete IS NULL"
                )
            )
        conn.commit()

    session = SessionLocal()
    try:
        has_legacy_requirements = (
            session.query(RequirementORM).filter_by(batch_id=LEGACY_BATCH_ID).first()
            is not None
        )
        if has_legacy_requirements and session.get(BatchORM, LEGACY_BATCH_ID) is None:
            session.add(
                BatchORM(
                    id=LEGACY_BATCH_ID,
                    transcript_preview="(ingested before batch tracking was added)",
                )
            )
            session.commit()
    finally:
        session.close()


def get_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session, closing it afterward."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def load_requirements(db_session: Session, batch_id: str | None = None) -> list[Requirement]:
    """Loads persisted requirements as Pydantic models, optionally scoped to
    a single batch."""
    query = db_session.query(RequirementORM)
    if batch_id is not None:
        query = query.filter_by(batch_id=batch_id)
    return [Requirement.model_validate(row, from_attributes=True) for row in query.all()]


def create_requirements(db_session: Session, requirements: list[Requirement]) -> None:
    """Inserts newly extracted requirements. Called right after classification
    — a checkpoint so a crash during the (expensive, per-requirement) agent
    loop that follows doesn't lose extraction/classification work too."""
    for requirement in requirements:
        db_session.add(RequirementORM(**requirement.model_dump(mode="json")))
    db_session.commit()


def update_requirement(db_session: Session, requirement: Requirement) -> None:
    """Writes one requirement's current state back to its existing row. Used
    to checkpoint progress after each requirement finishes the per-requirement
    agent loop, so Coordinator.resume() has an accurate picture of what's
    already done."""
    row = db_session.get(RequirementORM, requirement.id)
    if row is None:
        raise ValueError(f"Requirement {requirement.id} not found")
    for field, value in requirement.model_dump(mode="json").items():
        setattr(row, field, value)
    db_session.commit()


def create_batch(db_session: Session, batch_id: str, transcript_preview: str) -> None:
    """Records a new ingestion batch. Called once per transcript, before its
    requirements are persisted."""
    db_session.add(BatchORM(id=batch_id, transcript_preview=transcript_preview))
    db_session.commit()


def load_batches(db_session: Session) -> list[BatchORM]:
    """Returns every batch, most recently created first."""
    return db_session.query(BatchORM).order_by(BatchORM.created_at.desc()).all()


def get_batch(db_session: Session, batch_id: str) -> BatchORM | None:
    return db_session.get(BatchORM, batch_id)


def save_batch_sdlc_recommendation(
    db_session: Session, batch_id: str, recommendation: list[dict]
) -> None:
    """Persists a generated SDLC recommendation onto its batch, so it can be
    looked up again later instead of only existing until the session ends."""
    batch = db_session.get(BatchORM, batch_id)
    if batch is None:
        raise ValueError(f"Batch {batch_id} not found")
    batch.sdlc_recommendation = recommendation
    db_session.commit()
