"""Pre-analysed demo projects: export a finished analysis to JSON, import it with no model calls.

Lets a reviewer open a fully analysed project instantly (no API key, no quota, no waiting).
Imported projects get fresh ids, so a demo can be opened as many times as you like.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from src.models import audit
from src.models.db import (
    ProjectORM,
    add_document,
    get_project,
    list_documents,
    load_questions,
    load_requirements,
    save_gates,
    save_questions,
    save_requirements,
)
from src.models.requirement import ApprovalStatus, Question, Requirement
from src.pipeline.approvals import blank_gates

DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demos"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def export_demo(db: Session, project_id: str, demo_id: str) -> Path:
    """Writes a clean (nothing approved, nothing answered) snapshot of an analysed project."""
    project = get_project(db, project_id)
    if project is None:
        raise ValueError("Project not found")
    requirements = load_requirements(db, project_id)
    for r in requirements:
        r.approval_status = ApprovalStatus.PENDING
        r.history = []
    questions = load_questions(db, project_id)
    for q in questions:
        q.status, q.answer, q.applied, q.answered_at = "open", None, False, None
    payload = {
        "demo_id": demo_id,
        "project": {"name": project.name, "description": project.description, "jurisdictions": project.jurisdictions},
        "documents": [
            {"title": d.title, "source_type": d.source_type, "role": d.role, "masked_text": d.masked_text, "pii_found": d.pii_found, "injection": d.injection}
            for d in list_documents(db, project_id)
        ],
        "requirements": [r.model_dump(mode="json") for r in requirements],
        "questions": [q.model_dump(mode="json") for q in questions],
        "analysis": {k: v for k, v in (project.analysis or {}).items() if k != "artefacts"},
    }
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    path = DEMO_DIR / f"{demo_id}.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def list_demos() -> list[dict]:
    out = []
    for path in sorted(DEMO_DIR.glob("*.json")) if DEMO_DIR.exists() else []:
        data = json.loads(path.read_text(encoding="utf-8"))
        sdlc = (data.get("analysis") or {}).get("sdlc") or {}
        out.append({
            "id": data["demo_id"],
            "name": data["project"]["name"],
            "description": data["project"]["description"],
            "requirements": len(data["requirements"]),
            "questions": len(data["questions"]),
            "inputs": len(data["documents"]),
            "sdlc": sdlc.get("recommended"),
        })
    return out


def import_demo(db: Session, demo_id: str) -> ProjectORM:
    path = DEMO_DIR / f"{re.sub(r'[^A-Za-z0-9_-]', '', demo_id)}.json"
    if not path.exists():
        raise KeyError(demo_id)
    text = path.read_text(encoding="utf-8")
    remap: dict[str, str] = {}
    fresh = UUID_RE.sub(lambda m: remap.setdefault(m.group(0), str(uuid.uuid4())), text)
    data = json.loads(fresh)

    project = ProjectORM(
        name=f"{data['project']['name']} (demo)",
        description=data["project"]["description"],
        jurisdictions=data["project"]["jurisdictions"],
        analysis=data["analysis"],
        gates={},
    )
    db.add(project)
    db.commit()

    new_doc_ids = []
    for d in data["documents"]:
        doc = add_document(db, project.id, d["title"], d["masked_text"], d["source_type"], d["role"], d["pii_found"], d["injection"])
        new_doc_ids.append(doc.id)
    # documents get their own ids at insert time: mark them analysed under those ids
    analysis = dict(project.analysis)
    analysis["analysed_docs"] = new_doc_ids
    project.analysis = analysis
    db.commit()

    save_requirements(db, project.id, [Requirement.model_validate(r) for r in data["requirements"]])
    save_questions(db, project.id, [Question.model_validate(q) for q in data["questions"]])
    save_gates(db, project.id, blank_gates())
    audit.record(db, "system", "demo_imported", {"demo": demo_id, "requirements": len(data["requirements"])}, project.id)
    return project


def build_demo(sample_id: str) -> Path:
    """Runs the REAL pipeline (live model, uses API quota) on a bundled sample and exports it
    as a demo. The temporary project is deleted afterwards so the working database stays clean."""
    from dotenv import load_dotenv

    load_dotenv()
    from src.agents.llm_client import set_status_sink
    from src.models.db import SessionLocal, delete_project, init_db
    from src.pipeline.jobs import Job
    from src.pipeline.runner import Pipeline
    from src.samples import create_from_sample

    init_db()
    db = SessionLocal()
    try:
        project = create_from_sample(db, sample_id)
        audit.set_audit_project(project.id)
        set_status_sink(lambda message: print("  ", message))
        job = Job(id="build", project_id=project.id, kind="analyse")
        Pipeline().analyse(project.id, db, job)
        for step in job.steps:
            print(f"  {step.status:8s} {step.key:11s} {step.detail}")
        path = export_demo(db, project.id, sample_id)
        delete_project(db, project.id)
        return path
    finally:
        set_status_sink(None)
        db.close()


def main(argv: list[str] | None = None) -> None:
    import argparse

    from src.samples import sample_dirs

    parser = argparse.ArgumentParser(description="Build pre-analysed demo projects from the bundled samples.")
    parser.add_argument("command", choices=["build"])
    parser.add_argument("sample", nargs="?", help="sample id, or omit with --all")
    parser.add_argument("--all", action="store_true", help="build every sample")
    args = parser.parse_args(argv)
    targets = [p.name for p in sample_dirs()] if args.all else [args.sample]
    if not all(targets):
        parser.error("give a sample id or --all")
    for sample_id in targets:
        print(f"Building demo '{sample_id}' with the live model...")
        print("  wrote", build_demo(sample_id))


if __name__ == "__main__":
    main()
