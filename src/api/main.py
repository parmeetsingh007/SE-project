"""REST API and static web app for KYCompass.

Run:  .venv/bin/uvicorn src.api.main:app --port 8000
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

load_dotenv()

from src.agents.documentation import DocumentationAgent  # noqa: E402
from src.agents.llm_client import DEFAULT_MODEL  # noqa: E402
from src.artefacts import writers  # noqa: E402
from src.demos import import_demo, list_demos  # noqa: E402
from src.ingest.extract_text import UnsupportedFileError, extract_text  # noqa: E402
from src.knowledge_base.kb import get_kb  # noqa: E402
from src.models import audit  # noqa: E402
from src.models.db import (  # noqa: E402
    DocumentORM,
    SessionLocal,
    add_document,
    create_project,
    delete_document,
    delete_project,
    get_project,
    get_question,
    init_db,
    list_documents,
    list_projects,
    load_questions,
    load_requirements,
    save_analysis,
    save_gates,
    save_requirements,
)
from src.models.requirement import now_iso  # noqa: E402
from src.pipeline import approvals  # noqa: E402
from src.pipeline.jobs import registry  # noqa: E402
from src.pipeline.runner import Pipeline, rebuild_workflow  # noqa: E402
from src.samples import SOURCE_TYPES, add_masked_document, create_from_sample, list_samples  # noqa: E402
from src.security.gate import secure_input  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
JURISDICTIONS = {"IN": "India", "EU": "European Union", "US": "United States", "GLOBAL": "Global standards"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="KYCompass", version="1.0", lifespan=lifespan)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Identity(BaseModel):
    user: str = "Anonymous"
    role: str = "business_analyst"


def identity(x_user: str = Header(default="Anonymous"), x_role: str = Header(default="business_analyst")) -> Identity:
    return Identity(user=x_user.strip()[:60] or "Anonymous", role=x_role.strip())


@app.exception_handler(PermissionError)
async def _forbidden(_request, exc: PermissionError):
    return JSONResponse({"detail": str(exc)}, status_code=403)


@app.exception_handler(KeyError)
async def _missing(_request, exc: KeyError):
    return JSONResponse({"detail": f"Not found: {exc.args[0] if exc.args else ''}"}, status_code=404)


@app.exception_handler(ValueError)
async def _bad(_request, exc: ValueError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


def _project_or_404(db: Session, project_id: str):
    project = get_project(db, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


# --------------------------------------------------------------------------- system
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "model": DEFAULT_MODEL,
        "llm_configured": bool(os.environ.get("GOOGLE_API_KEY")),
        "kb": get_kb().manifest(),
        "jurisdictions": JURISDICTIONS,
        "source_types": SOURCE_TYPES,
        "roles": approvals.ROLES,
        "gates": {k: {"title": v["title"], "description": v["description"], "roles": v["roles"]} for k, v in approvals.GATES.items()},
    }


@app.get("/api/kb")
def kb_items():
    kb = get_kb()
    return {
        **kb.manifest(),
        "clauses": [
            {"id": c.id, "source": c.source, "jurisdiction": c.jurisdiction, "title": c.title, "text": c.text,
             "effective": c.effective, "version": c.version, "high_impact": c.high_impact}
            for c in kb.clauses.values()
        ],
    }


# -------------------------------------------------------------------------- samples
@app.get("/api/samples")
def samples():
    return list_samples()


@app.post("/api/projects/from-sample/{sample_id}")
def project_from_sample(sample_id: str, db: Session = Depends(get_db), who: Identity = Depends(identity)):
    project = create_from_sample(db, sample_id)
    audit.record(db, f"user:{who.user}", "project_created_from_sample", {"sample": sample_id}, project.id)
    return {"id": project.id}


@app.get("/api/demos")
def demos():
    return list_demos()


@app.post("/api/demos/{demo_id}")
def open_demo(demo_id: str, db: Session = Depends(get_db)):
    """Imports a pre-analysed project: instant, and makes no model calls."""
    return {"id": import_demo(db, demo_id).id}


# -------------------------------------------------------------------------- projects
class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    jurisdictions: list[str] = Field(default_factory=lambda: ["IN", "GLOBAL"])


def _clean_jurisdictions(values: list[str]) -> list[str]:
    cleaned = [v.upper() for v in values if v.upper() in JURISDICTIONS]
    if "GLOBAL" not in cleaned:
        cleaned.append("GLOBAL")
    return cleaned


def _summary(db: Session, project) -> dict:
    reqs = load_requirements(db, project.id)
    return {
        "id": project.id, "name": project.name, "description": project.description, "jurisdictions": project.jurisdictions,
        "created_at": project.created_at.isoformat(), "updated_at": project.updated_at.isoformat(),
        "requirements": len(reqs), "approved": sum(1 for r in reqs if r.approval_status.value == "approved"),
        "documents": len(list_documents(db, project.id)),
        "sdlc": ((project.analysis or {}).get("sdlc") or {}).get("chosen"),
        "running": registry.is_running(project.id),
    }


@app.get("/api/projects")
def projects(db: Session = Depends(get_db)):
    return [_summary(db, p) for p in list_projects(db)]


@app.post("/api/projects")
def new_project(body: ProjectIn, db: Session = Depends(get_db), who: Identity = Depends(identity)):
    project = create_project(db, body.name, body.description, _clean_jurisdictions(body.jurisdictions))
    audit.record(db, f"user:{who.user}", "project_created", {"name": project.name}, project.id)
    return _summary(db, project)


@app.patch("/api/projects/{project_id}")
def edit_project(project_id: str, body: ProjectIn, db: Session = Depends(get_db), who: Identity = Depends(identity)):
    project = _project_or_404(db, project_id)
    project.name, project.description = body.name.strip(), body.description.strip()
    project.jurisdictions = _clean_jurisdictions(body.jurisdictions)
    db.commit()
    audit.record(db, f"user:{who.user}", "project_edited", {"jurisdictions": project.jurisdictions}, project_id)
    return _summary(db, project)


@app.delete("/api/projects/{project_id}")
def remove_project(project_id: str, db: Session = Depends(get_db)):
    _project_or_404(db, project_id)
    if registry.is_running(project_id):
        raise HTTPException(409, "Wait for the running analysis to finish.")
    delete_project(db, project_id)
    return {"ok": True}


def _doc_dict(d: DocumentORM, full: bool = False) -> dict:
    out = {
        "id": d.id, "title": d.title, "source_type": d.source_type, "role": d.role, "chars": len(d.masked_text),
        "words": len(d.masked_text.split()), "pii_found": d.pii_found, "injection": d.injection,
        "preview": d.masked_text[:240], "created_at": d.created_at.isoformat(),
    }
    if full:
        out["text"] = d.masked_text
    return out


def _state(db: Session, project_id: str) -> dict:
    project = _project_or_404(db, project_id)
    analysis = project.analysis or {}
    job = registry.latest(project_id)
    gates = approvals.ensure_gates(project.gates)
    analysed = set(analysis.get("analysed_docs", []))
    return {
        "project": _summary(db, project),
        "documents": [{**_doc_dict(d), "analysed": d.id in analysed} for d in list_documents(db, project_id)],
        "requirements": [r.model_dump(mode="json") for r in load_requirements(db, project_id)],
        "questions": [q.model_dump(mode="json") for q in load_questions(db, project_id)],
        "conflicts": analysis.get("conflicts", []),
        "controls": analysis.get("controls", []),
        "risks": analysis.get("risks", []),
        "threats": analysis.get("threats", []),
        "sdlc": analysis.get("sdlc"),
        "validation": analysis.get("validation"),
        "guard": analysis.get("guard", {}),
        "artefacts": analysis.get("artefacts"),
        "last_run": analysis.get("last_run"),
        "gates": {gid: {**state, "title": approvals.GATES[gid]["title"], "roles": approvals.GATES[gid]["roles"], "description": approvals.GATES[gid]["description"]} for gid, state in gates.items()},
        "job": job.snapshot() if job else None,
    }


@app.get("/api/projects/{project_id}")
def project_state(project_id: str, db: Session = Depends(get_db)):
    return _state(db, project_id)


# ------------------------------------------------------------------------ documents
_add_text = add_masked_document


class DocumentIn(BaseModel):
    title: str = "Pasted notes"
    text: str
    source_type: str = "notes"
    role: str = ""


@app.post("/api/projects/{project_id}/documents")
def add_text_document(project_id: str, body: DocumentIn, db: Session = Depends(get_db)):
    _project_or_404(db, project_id)
    return _doc_dict(_add_text(db, project_id, body.title, body.text, body.source_type, body.role))


@app.post("/api/projects/{project_id}/documents/upload")
async def upload_documents(
    project_id: str,
    files: list[UploadFile] = File(...),
    role: str = Form(""),
    source_type: str = Form("notes"),
    db: Session = Depends(get_db),
):
    _project_or_404(db, project_id)
    added, errors = [], []
    for upload in files:
        try:
            text = extract_text(upload.filename or "upload", await upload.read())
            added.append(_doc_dict(_add_text(db, project_id, upload.filename or "Upload", text, source_type, role)))
        except (UnsupportedFileError, ValueError) as exc:
            errors.append({"file": upload.filename, "error": str(exc)})
    return {"added": added, "errors": errors}


@app.get("/api/projects/{project_id}/documents/{document_id}")
def document_text(project_id: str, document_id: str, db: Session = Depends(get_db)):
    doc = db.get(DocumentORM, document_id)
    if doc is None or doc.project_id != project_id:
        raise HTTPException(404, "Document not found")
    return _doc_dict(doc, full=True)


@app.delete("/api/projects/{project_id}/documents/{document_id}")
def remove_document(project_id: str, document_id: str, db: Session = Depends(get_db)):
    project = _project_or_404(db, project_id)
    if document_id in (project.analysis or {}).get("analysed_docs", []):
        raise HTTPException(409, "This input has already been analysed; its requirements keep tracing to it, so it cannot be removed.")
    if not delete_document(db, project_id, document_id):
        raise HTTPException(404, "Document not found")
    return {"ok": True}


def _not_running(project_id: str) -> None:
    """Decisions and edits are refused mid-analysis: the pipeline holds an in-memory copy of the
    requirements and would overwrite them when it saves, silently losing a human decision."""
    if registry.is_running(project_id):
        raise HTTPException(409, "An analysis is running. Try again when it finishes (usually a minute or two).")


# --------------------------------------------------------------------------- analysis
def _start(project_id: str, kind: str, work):
    try:
        return registry.start(project_id, kind, work).snapshot()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


def _with_session(fn):
    def work(job):
        db = SessionLocal()
        try:
            fn(db, job)
        finally:
            db.close()

    return work


@app.post("/api/projects/{project_id}/analyse")
def analyse(project_id: str, db: Session = Depends(get_db), who: Identity = Depends(identity)):
    _project_or_404(db, project_id)
    if not list_documents(db, project_id):
        raise HTTPException(400, "Add at least one input (paste text or upload a file) first.")
    if not os.environ.get("GOOGLE_API_KEY"):
        raise HTTPException(400, "GOOGLE_API_KEY is not set, so the language model cannot be reached. Add it to .env and restart.")
    audit.record(db, f"user:{who.user}", "analysis_requested", {"role": who.role}, project_id)
    return _start(project_id, "analyse", _with_session(lambda s, job: Pipeline().analyse(project_id, s, job)))


@app.post("/api/projects/{project_id}/apply-answers")
def apply_answers(project_id: str, db: Session = Depends(get_db), who: Identity = Depends(identity)):
    _project_or_404(db, project_id)
    if not any(q.status == "answered" and not q.applied for q in load_questions(db, project_id)):
        raise HTTPException(400, "There are no new answers to apply.")
    audit.record(db, f"user:{who.user}", "answers_apply_requested", {}, project_id)
    return _start(project_id, "apply_answers", _with_session(lambda s, job: Pipeline().apply_answers(project_id, s, job)))


@app.get("/api/projects/{project_id}/job")
def job_status(project_id: str):
    job = registry.latest(project_id)
    return job.snapshot() if job else None


# -------------------------------------------------------------------------- questions
class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)


def _question(db: Session, project_id: str, question_id: str):
    row = get_question(db, project_id, question_id)
    if row is None:
        raise HTTPException(404, "Question not found")
    return row


@app.post("/api/projects/{project_id}/questions/{question_id}/answer")
def answer_question(project_id: str, question_id: str, body: AnswerIn, db: Session = Depends(get_db), who: Identity = Depends(identity)):
    row = _question(db, project_id, question_id)
    masked = secure_input(body.answer).text
    row.status, row.answer, row.applied, row.answered_at = "answered", masked, False, now_iso()
    db.commit()
    audit.record(db, f"user:{who.user}", "question_answered", {"question": row.question, "answer": masked}, project_id)
    return {"ok": True}


@app.post("/api/projects/{project_id}/questions/{question_id}/skip")
def skip_question(project_id: str, question_id: str, db: Session = Depends(get_db), who: Identity = Depends(identity)):
    row = _question(db, project_id, question_id)
    row.status, row.answer, row.answered_at = "skipped", None, now_iso()
    db.commit()
    audit.record(db, f"user:{who.user}", "question_skipped", {"question": row.question}, project_id)
    return {"ok": True}


@app.post("/api/projects/{project_id}/questions/{question_id}/reopen")
def reopen_question(project_id: str, question_id: str, db: Session = Depends(get_db)):
    row = _question(db, project_id, question_id)
    if row.applied:
        raise HTTPException(409, "This answer has already been folded into the requirement.")
    row.status, row.answer, row.answered_at = "open", None, None
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------------ requirements
class DecisionIn(BaseModel):
    decision: str
    note: str = ""


def _requirement(db: Session, project_id: str, requirement_id: str):
    requirements = load_requirements(db, project_id)
    found = next((r for r in requirements if r.id == requirement_id), None)
    if found is None:
        raise HTTPException(404, "Requirement not found")
    return requirements, found


@app.post("/api/projects/{project_id}/requirements/{requirement_id}/decision")
def decide(project_id: str, requirement_id: str, body: DecisionIn, db: Session = Depends(get_db), who: Identity = Depends(identity)):
    _not_running(project_id)
    requirements, requirement = _requirement(db, project_id, requirement_id)
    status = approvals.decision_to_status(body.decision)
    approvals.check_can_decide(who.role, requirement)
    requirement.history.append({"action": f"decision:{status.value}", "by": f"{who.user} ({who.role})", "note": body.note, "at": now_iso(), "previous": requirement.approval_status.value})
    requirement.approval_status = status
    save_requirements(db, project_id, requirements)
    project = get_project(db, project_id)
    save_gates(db, project_id, approvals.reset_gates(project.gates, ["baseline"], f"{requirement.ref} was re-decided."))
    audit.record(db, f"user:{who.user}", "requirement_decision", {"ref": requirement.ref, "decision": status.value, "role": who.role, "note": body.note}, project_id)
    return requirement.model_dump(mode="json")


class EditIn(BaseModel):
    statement: str = Field(min_length=5, max_length=1500)
    priority: str | None = None
    note: str = ""


@app.patch("/api/projects/{project_id}/requirements/{requirement_id}")
def edit_requirement(project_id: str, requirement_id: str, body: EditIn, db: Session = Depends(get_db), who: Identity = Depends(identity)):
    _not_running(project_id)
    requirements, requirement = _requirement(db, project_id, requirement_id)
    approvals.check_can_decide(who.role, requirement)
    statement = secure_input(body.statement).text.strip()
    if statement != requirement.statement:
        requirement.history.append({"action": "edited", "by": f"{who.user} ({who.role})", "previous": requirement.statement, "at": now_iso(), "note": body.note})
        requirement.statement = statement
    if body.priority:
        from src.models.requirement import Priority

        requirement.priority = Priority(body.priority)
    requirement.approval_status = approvals.decision_to_status("pending")
    save_requirements(db, project_id, requirements)
    project = get_project(db, project_id)
    done = {k: [i for i in v if i != requirement_id] for k, v in (project.analysis or {}).get("done", {}).items()}
    save_analysis(db, project_id, done=done)
    save_gates(db, project_id, approvals.reset_gates(project.gates, ["baseline", "regulatory", "sdlc"], f"{requirement.ref} was edited."))
    audit.record(db, f"user:{who.user}", "requirement_edited", {"ref": requirement.ref, "role": who.role}, project_id)
    return {**requirement.model_dump(mode="json"), "needs_reanalysis": True}


# --------------------------------------------------------------------------- conflicts
class ResolveIn(BaseModel):
    resolution: str = Field(min_length=3, max_length=1000)


@app.post("/api/projects/{project_id}/conflicts/{conflict_id}/resolve")
def resolve_conflict(project_id: str, conflict_id: str, body: ResolveIn, db: Session = Depends(get_db), who: Identity = Depends(identity)):
    _not_running(project_id)
    if who.role not in ("product_owner", "compliance", "project_manager", "architect"):
        raise PermissionError("Only a product owner, project manager, architect or compliance officer can resolve a conflict.")
    project = _project_or_404(db, project_id)
    conflicts = [dict(c) for c in (project.analysis or {}).get("conflicts", [])]
    target = next((c for c in conflicts if c["id"] == conflict_id), None)
    if target is None:
        raise HTTPException(404, "Conflict not found")
    target["status"], target["resolution"] = "resolved", secure_input(body.resolution).text
    save_analysis(db, project_id, conflicts=conflicts)
    save_gates(db, project_id, approvals.reset_gates(project.gates, ["conflicts"], "A conflict resolution changed."))
    audit.record(db, f"user:{who.user}", "conflict_resolved", {"conflict": conflict_id, "resolution": target["resolution"], "role": who.role}, project_id)
    return target


# ------------------------------------------------------------------------------ gates
class SignoffIn(BaseModel):
    decision: str
    note: str = ""


@app.post("/api/projects/{project_id}/gates/{gate_id}/signoff")
def signoff(project_id: str, gate_id: str, body: SignoffIn, db: Session = Depends(get_db), who: Identity = Depends(identity)):
    _not_running(project_id)
    project = _project_or_404(db, project_id)
    analysis = project.analysis or {}
    if body.decision == "approved":
        if gate_id == "baseline" and not (analysis.get("validation") or {}).get("metrics", {}).get("baseline_ready"):
            raise HTTPException(409, "The baseline is blocked: fix the failing quality gates first.")
        if gate_id == "sdlc" and not analysis.get("sdlc"):
            raise HTTPException(409, "There is no SDLC recommendation to approve yet.")
    gates = approvals.sign_off(project.gates, gate_id, who.role, who.user, body.decision, body.note)
    save_gates(db, project_id, gates)
    audit.record(db, f"user:{who.user}", "gate_signoff", {"gate": gate_id, "decision": body.decision, "role": who.role, "note": body.note}, project_id)
    return gates[gate_id]


class SdlcChoiceIn(BaseModel):
    model: str


@app.post("/api/projects/{project_id}/sdlc/choose")
def choose_sdlc(project_id: str, body: SdlcChoiceIn, db: Session = Depends(get_db), who: Identity = Depends(identity)):
    _not_running(project_id)
    if who.role not in ("project_manager", "architect", "security", "compliance"):
        raise PermissionError("Only a project manager, architect, security or compliance officer can change the SDLC choice.")
    project = _project_or_404(db, project_id)
    rebuild_workflow(db, project_id, body.model)
    save_gates(db, project_id, approvals.reset_gates(project.gates, ["sdlc"], f"SDLC changed to {body.model}."))
    audit.record(db, f"user:{who.user}", "sdlc_chosen", {"model": body.model, "role": who.role}, project_id)
    return {"ok": True}


# ----------------------------------------------------------------------------- export
def _bundle(db: Session, project_id: str) -> writers.Bundle:
    project = _project_or_404(db, project_id)
    entries = audit.list_entries(db, project_id, newest_first=False)
    return writers.Bundle(
        project={"id": project.id, "name": project.name, "description": project.description, "jurisdictions": project.jurisdictions},
        requirements=load_requirements(db, project_id),
        questions=load_questions(db, project_id),
        analysis=project.analysis or {},
        gates=approvals.ensure_gates(project.gates),
        documents=[{"title": d.title, "source_type": d.source_type, "role": d.role} for d in list_documents(db, project_id)],
        audit=[{"id": e.id, "ts": e.ts, "actor": e.actor, "action": e.action, "detail": e.detail, "prev_hash": e.prev_hash, "hash": e.hash} for e in entries],
        kb_version=get_kb().version,
        model=DEFAULT_MODEL,
    )


@app.post("/api/projects/{project_id}/documents-generate")
def generate_documents(project_id: str, db: Session = Depends(get_db), who: Identity = Depends(identity)):
    _project_or_404(db, project_id)
    if not load_requirements(db, project_id):
        raise HTTPException(400, "Analyse some inputs first.")

    def work(session: Session, job) -> None:
        job.set_steps([("docs", "Writing user stories and use cases")])
        job.begin("docs")
        live = [r for r in load_requirements(session, project_id) if r.approval_status.value != "rejected"]
        output = DocumentationAgent().run(live, session)
        save_analysis(session, project_id, artefacts={**output.model_dump(), "generated_at": now_iso()})
        audit.record(session, "agent:documentation", "artefacts_generated", {"stories": len(output.stories), "use_cases": len(output.use_cases)}, project_id)
        job.end("docs", f"{len(output.stories)} stories, {len(output.use_cases)} use cases")

    audit.record(db, f"user:{who.user}", "documents_requested", {}, project_id)
    return _start(project_id, "documents", _with_session(work))


EXPORT_TYPES = {".md": "text/markdown", ".csv": "text/csv", ".json": "application/json", ".jsonl": "application/x-ndjson",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


@app.get("/api/projects/{project_id}/export")
def export_zip(project_id: str, db: Session = Depends(get_db)):
    bundle = _bundle(db, project_id)
    safe = "".join(c if c.isalnum() else "_" for c in bundle.project["name"])[:40] or "project"
    return Response(writers.build_zip(bundle), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{safe}_kycompass.zip"'})


@app.get("/api/projects/{project_id}/export/{filename}")
def export_file(project_id: str, filename: str, db: Session = Depends(get_db)):
    files = writers.build_files(_bundle(db, project_id))
    if filename not in files:
        raise HTTPException(404, "Unknown file")
    content = files[filename]
    media = EXPORT_TYPES.get(Path(filename).suffix, "text/plain")
    disposition = "inline" if media.startswith("text/") or media.startswith("application/json") else "attachment"
    return Response(content, media_type=media + ("; charset=utf-8" if isinstance(content, str) else ""), headers={"Content-Disposition": f'{disposition}; filename="{filename}"'})


@app.get("/api/projects/{project_id}/audit")
def audit_log(project_id: str, limit: int = 300, include_llm: bool = True, db: Session = Depends(get_db)):
    _project_or_404(db, project_id)
    valid, checked, bad = audit.verify_chain(db, project_id)
    entries = audit.list_entries(db, project_id, limit=limit)
    out = []
    for e in entries:
        if not include_llm and e.action == "llm_call":
            continue
        detail = e.detail
        try:
            parsed = json.loads(detail)
            if e.action == "llm_call" and isinstance(parsed, dict):
                parsed = {k: v for k, v in parsed.items() if k != "output"} | {"output_chars": len(str(parsed.get("output", "")))}
            detail = parsed
        except json.JSONDecodeError:
            pass
        out.append({"id": e.id, "ts": e.ts, "actor": e.actor, "action": e.action, "detail": detail, "hash": e.hash[:12]})
    return {"chain_valid": valid, "entries_checked": checked, "first_bad_entry": bad, "entries": out}


# ---------------------------------------------------------------------------- web app
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-store"})


class RevalidatingStatic(StaticFiles):
    """Static assets are small and change with every release, so make browsers revalidate
    (cheap thanks to ETags) instead of mixing a cached old script with a new one."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", RevalidatingStatic(directory=WEB_DIR), name="static")
