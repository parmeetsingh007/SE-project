"""Generates the SRS, user stories, and traceability matrix from persisted
requirements.

This is the Output layer, run on demand rather than automatically at the end
of every ingestion — Milestone 6 wires it to a UI action after human review.
For now it documents every persisted requirement regardless of approval_status,
since the approval gate doesn't exist yet.

Usage:
    python -m src.orchestration.generate_docs
"""

from __future__ import annotations

from dotenv import load_dotenv

from src.agents.documentation import DocumentationAgent
from src.agents.sdlc_selection import SDLCSelectionAgent
from src.models.db import SessionLocal, init_db, load_requirements


def generate_docs() -> None:
    load_dotenv()
    init_db()

    session = SessionLocal()
    try:
        requirements = load_requirements(session)
        if not requirements:
            print("No persisted requirements found — run the pipeline first.")
            return

        recommendations = SDLCSelectionAgent().run(requirements, db_session=session)
        output = DocumentationAgent().run(requirements, recommendations, db_session=session)
    finally:
        session.close()

    print(f"Documented {len(requirements)} requirements:")
    print(f"  SRS: {output.srs_path}")
    print(f"  User stories: {output.user_stories_path}")
    print(f"  Traceability matrix: {output.traceability_csv_path}")
    print("\nRecommended SDLC approach:")
    for i, rec in enumerate(recommendations, start=1):
        print(f"  {i}. {rec.model} (confidence: {rec.confidence:.0%}) — {rec.rationale}")


if __name__ == "__main__":
    generate_docs()
