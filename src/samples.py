"""Creates a project from one of the bundled sample scenarios in data/samples/."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from src.models import audit
from src.models.db import ProjectORM, add_document, create_project
from src.security.gate import secure_input

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"
SOURCE_TYPES = ["interview", "email", "meeting notes", "policy", "regulation", "audit finding", "requirements doc", "notes"]


def sample_dirs() -> list[Path]:
    return sorted(p for p in SAMPLES_DIR.iterdir() if (p / "project.json").exists()) if SAMPLES_DIR.exists() else []


def list_samples() -> list[dict]:
    out = []
    for folder in sample_dirs():
        meta = json.loads((folder / "project.json").read_text(encoding="utf-8"))
        out.append({"id": folder.name, "name": meta["name"], "description": meta["description"], "inputs": len(list((folder / "inputs").glob("*.txt")))})
    return out


def add_masked_document(db: Session, project_id: str, title: str, text: str, source_type: str, role: str):
    """Runs text through the security gate and stores only the masked result."""
    if not text.strip():
        raise ValueError("The input is empty.")
    gate = secure_input(text)
    doc = add_document(db, project_id, title, gate.text, source_type if source_type in SOURCE_TYPES else "notes", role.strip()[:60], gate.pii_found, gate.injection)
    audit.record(db, "system:security_gate", "input_secured", {"document": title, "pii_masked": gate.pii_found, "injection_findings": gate.injection}, project_id)
    return doc


def create_from_sample(db: Session, sample_id: str) -> ProjectORM:
    folder = SAMPLES_DIR / Path(sample_id).name
    if not (folder / "project.json").exists():
        raise KeyError(sample_id)
    meta = json.loads((folder / "project.json").read_text(encoding="utf-8"))
    project = create_project(db, meta["name"], meta["description"], meta.get("jurisdictions"))
    for path in sorted((folder / "inputs").glob("*.txt")):
        add_masked_document(
            db, project.id, path.stem.replace("_", " ").title(), path.read_text(encoding="utf-8"),
            meta.get("source_types", {}).get(path.name, "notes"), meta.get("roles", {}).get(path.name, ""),
        )
    return project
