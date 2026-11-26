"""SQLAlchemy models and helpers (SQLite). One project = one analysis workspace."""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from src.models.requirement import Question, Requirement, new_id

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./kycompass.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record) -> None:  # pragma: no cover - trivial
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ProjectORM(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    jurisdictions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    # Everything derived by the pipeline that isn't a requirement row: conflicts,
    # control coverage, risks, threats, SDLC factors/ranking/workflow, metrics ...
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    # Human-approval gates: {gate_id: {"signoffs": [...], "status": ...}}
    gates: Mapped[dict] = mapped_column(JSON, default=dict)


class DocumentORM(Base):
    """A stakeholder input. Only the PII-masked text is ever stored."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, default="notes")
    role: Mapped[str] = mapped_column(String, default="")
    masked_text: Mapped[str] = mapped_column(Text, nullable=False)
    pii_found: Mapped[dict] = mapped_column(JSON, default=dict)
    injection: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class RequirementORM(Base):
    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    ref: Mapped[str] = mapped_column(String, default="")
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    categories: Mapped[list] = mapped_column(JSON, default=list)
    primary_category: Mapped[str | None] = mapped_column(String, nullable=True)
    source_stakeholder: Mapped[str] = mapped_column(String, default="Unspecified")
    source_document: Mapped[str] = mapped_column(String, default="")
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    business_justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String, default="medium")
    dependencies: Mapped[list] = mapped_column(JSON, default=list)
    assumptions: Mapped[list] = mapped_column(JSON, default=list)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    regulations: Mapped[list] = mapped_column(JSON, default=list)
    risk_level: Mapped[str | None] = mapped_column(String, nullable=True)
    risk_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    approval_status: Mapped[str] = mapped_column(String, default="pending")
    origin: Mapped[str] = mapped_column(String, default="stated")
    derived_reason: Mapped[str] = mapped_column(Text, default="")
    quality_flags: Mapped[list] = mapped_column(JSON, default=list)
    is_weak: Mapped[bool] = mapped_column(Boolean, default=False)
    hints: Mapped[list] = mapped_column(JSON, default=list)
    history: Mapped[list] = mapped_column(JSON, default=list)


class QuestionORM(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    requirement_id: Mapped[str] = mapped_column(String, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    why: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="open")
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String, default="")
    answered_at: Mapped[str | None] = mapped_column(String, nullable=True)


class AuditORM(Base):
    """Append-only, hash-chained log (one chain per project)."""

    __tablename__ = "audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String, index=True, default="")
    ts: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="")
    prev_hash: Mapped[str] = mapped_column(String, default="")
    hash: Mapped[str] = mapped_column(String, default="")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------- projects


def create_project(
    db: Session, name: str, description: str = "", jurisdictions: list[str] | None = None
) -> ProjectORM:
    project = ProjectORM(
        name=name.strip() or "Untitled project",
        description=description.strip(),
        jurisdictions=jurisdictions or ["IN", "GLOBAL"],
        analysis={},
        gates={},
    )
    db.add(project)
    db.commit()
    return project


def get_project(db: Session, project_id: str) -> ProjectORM | None:
    return db.get(ProjectORM, project_id)


def list_projects(db: Session) -> list[ProjectORM]:
    return db.query(ProjectORM).order_by(ProjectORM.created_at.desc()).all()


def delete_project(db: Session, project_id: str) -> None:
    for model in (DocumentORM, RequirementORM, QuestionORM, AuditORM):
        db.query(model).filter_by(project_id=project_id).delete()
    project = db.get(ProjectORM, project_id)
    if project is not None:
        db.delete(project)
    db.commit()


def save_analysis(db: Session, project_id: str, **updates) -> dict:
    """Merges keys into project.analysis (always assigns a fresh dict so SQLAlchemy
    notices the JSON change) and returns the new value."""
    project = db.get(ProjectORM, project_id)
    if project is None:
        raise ValueError(f"Project {project_id} not found")
    analysis = dict(project.analysis or {})
    analysis.update(updates)
    project.analysis = analysis
    project.updated_at = _utcnow()
    db.commit()
    return analysis


def save_gates(db: Session, project_id: str, gates: dict) -> None:
    project = db.get(ProjectORM, project_id)
    if project is None:
        raise ValueError(f"Project {project_id} not found")
    project.gates = gates
    project.updated_at = _utcnow()
    db.commit()


# --------------------------------------------------------------- documents


def add_document(
    db: Session,
    project_id: str,
    title: str,
    masked_text: str,
    source_type: str = "notes",
    role: str = "",
    pii_found: dict | None = None,
    injection: list | None = None,
) -> DocumentORM:
    doc = DocumentORM(
        project_id=project_id,
        title=title.strip() or "Untitled input",
        source_type=source_type,
        role=role,
        masked_text=masked_text,
        pii_found=pii_found or {},
        injection=injection or [],
    )
    db.add(doc)
    db.commit()
    return doc


def list_documents(db: Session, project_id: str) -> list[DocumentORM]:
    return db.query(DocumentORM).filter_by(project_id=project_id).order_by(DocumentORM.created_at).all()


def delete_document(db: Session, project_id: str, document_id: str) -> bool:
    doc = db.get(DocumentORM, document_id)
    if doc is None or doc.project_id != project_id:
        return False
    db.delete(doc)
    db.commit()
    return True


# ------------------------------------------------------------ requirements


def load_requirements(db: Session, project_id: str) -> list[Requirement]:
    rows = (
        db.query(RequirementORM)
        .filter_by(project_id=project_id)
        .order_by(RequirementORM.position, RequirementORM.ref)
        .all()
    )
    return [Requirement.model_validate(row, from_attributes=True) for row in rows]


def save_requirements(
    db: Session, project_id: str, requirements: list[Requirement], replace: bool = False
) -> None:
    """Upserts requirements (keeping the given order). With replace=True any stored
    requirement of this project that is not in ``requirements`` is deleted."""
    keep = {r.id for r in requirements}
    if replace:
        for row in db.query(RequirementORM).filter_by(project_id=project_id).all():
            if row.id not in keep:
                db.delete(row)
    for position, requirement in enumerate(requirements):
        requirement.project_id = project_id
        data = requirement.model_dump(mode="json")
        row = db.get(RequirementORM, requirement.id)
        if row is None:
            row = RequirementORM(id=requirement.id)
            db.add(row)
        for field, value in data.items():
            if field == "id":
                continue
            setattr(row, field, value)
        row.position = position
    db.commit()


def update_requirement(db: Session, requirement: Requirement) -> None:
    row = db.get(RequirementORM, requirement.id)
    if row is None:
        raise ValueError(f"Requirement {requirement.id} not found")
    for field, value in requirement.model_dump(mode="json").items():
        if field == "id":
            continue
        setattr(row, field, value)
    db.commit()


# --------------------------------------------------------------- questions


def load_questions(db: Session, project_id: str) -> list[Question]:
    rows = db.query(QuestionORM).filter_by(project_id=project_id).order_by(QuestionORM.created_at).all()
    return [Question.model_validate(row, from_attributes=True) for row in rows]


def save_questions(db: Session, project_id: str, questions: list[Question], replace_open: bool = False) -> None:
    """Inserts/updates questions. With replace_open=True, existing *open* questions that
    are not in ``questions`` are deleted (answered/skipped ones are history and kept)."""
    keep = {q.id for q in questions}
    if replace_open:
        for row in db.query(QuestionORM).filter_by(project_id=project_id, status="open").all():
            if row.id not in keep:
                db.delete(row)
    for question in questions:
        question.project_id = project_id
        data = question.model_dump(mode="json")
        row = db.get(QuestionORM, question.id)
        if row is None:
            row = QuestionORM(id=question.id)
            db.add(row)
        for field, value in data.items():
            if field == "id":
                continue
            setattr(row, field, value)
    db.commit()


def delete_open_questions(db: Session, project_id: str, requirement_ids: list[str]) -> None:
    """Removes still-open questions for these requirements (answered/skipped ones are history)."""
    if not requirement_ids:
        return
    for row in db.query(QuestionORM).filter_by(project_id=project_id, status="open").all():
        if row.requirement_id in requirement_ids:
            db.delete(row)
    db.commit()


def delete_requirements(db: Session, project_id: str, requirement_ids: list[str]) -> None:
    for row in db.query(RequirementORM).filter_by(project_id=project_id).all():
        if row.id in requirement_ids:
            db.delete(row)
    db.commit()


def get_question(db: Session, project_id: str, question_id: str) -> QuestionORM | None:
    row = db.get(QuestionORM, question_id)
    if row is None or row.project_id != project_id:
        return None
    return row
