"""SQLAlchemy models and SQLite session setup for requirements + audit log."""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from src.models.requirement import Requirement

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./sdlc_requirements.db")

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
    """Create all tables if they don't already exist."""
    Base.metadata.create_all(bind=engine)


def get_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session, closing it afterward."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def load_requirements(db_session: Session) -> list[Requirement]:
    """Loads every persisted requirement as its Pydantic model."""
    rows = db_session.query(RequirementORM).all()
    return [Requirement.model_validate(row, from_attributes=True) for row in rows]
