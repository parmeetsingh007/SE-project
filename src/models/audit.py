"""Hash-chained, append-only audit log.

Each entry's hash covers the previous entry's hash, so editing or deleting any
row breaks every hash after it. ``verify_chain`` recomputes the chain.
"""

from __future__ import annotations

import hashlib
import json
import threading
from contextvars import ContextVar
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.models.db import AuditORM

_lock = threading.Lock()

# Lets low-level code (the LLM client) log against the right project without
# every agent having to pass a project id around.
_current_project: ContextVar[str] = ContextVar("audit_current_project", default="")


def set_audit_project(project_id: str) -> None:
    _current_project.set(project_id)


def current_project() -> str:
    return _current_project.get()


def _digest(prev_hash: str, ts: str, actor: str, action: str, detail: str) -> str:
    body = json.dumps([prev_hash, ts, actor, action, detail], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def record(
    db: Session, actor: str, action: str, detail: dict | str | None = None, project_id: str | None = None
) -> AuditORM:
    """Appends one entry to the project's chain."""
    project_id = project_id if project_id is not None else current_project()
    detail_text = detail if isinstance(detail, str) else json.dumps(detail or {}, ensure_ascii=False, default=str)
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    with _lock:
        last = (
            db.query(AuditORM).filter_by(project_id=project_id).order_by(AuditORM.id.desc()).first()
        )
        prev_hash = last.hash if last else ""
        entry = AuditORM(
            project_id=project_id,
            ts=ts,
            actor=actor,
            action=action,
            detail=detail_text,
            prev_hash=prev_hash,
            hash=_digest(prev_hash, ts, actor, action, detail_text),
        )
        db.add(entry)
        db.commit()
    return entry


def record_llm_call(db: Session | None, agent_name: str, prompt: str, output: str, model: str) -> None:
    """Logs one model call: which agent, which model, a hash of the prompt (the prompt
    text itself is already PII-masked at ingestion) and the raw output."""
    if db is None:
        return
    record(
        db,
        actor=f"agent:{agent_name}",
        action="llm_call",
        detail={
            "model": model,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "prompt_chars": len(prompt),
            "output": output,
        },
    )


def list_entries(db: Session, project_id: str, limit: int | None = None, newest_first: bool = True) -> list[AuditORM]:
    query = db.query(AuditORM).filter_by(project_id=project_id)
    query = query.order_by(AuditORM.id.desc() if newest_first else AuditORM.id.asc())
    return query.limit(limit).all() if limit else query.all()


def verify_chain(db: Session, project_id: str) -> tuple[bool, int, int | None]:
    """Returns (is_valid, entries_checked, first_bad_entry_id)."""
    prev_hash = ""
    checked = 0
    for entry in list_entries(db, project_id, newest_first=False):
        expected = _digest(prev_hash, entry.ts, entry.actor, entry.action, entry.detail)
        if entry.prev_hash != prev_hash or entry.hash != expected:
            return False, checked, entry.id
        prev_hash = entry.hash
        checked += 1
    return True, checked, None
