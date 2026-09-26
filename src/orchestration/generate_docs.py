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
from src.models.db import RequirementORM, SessionLocal, init_db
from src.models.requirement import Requirement


def _load_requirements(db_session) -> list[Requirement]:
    rows = db_session.query(RequirementORM).all()
    return [
        Requirement(
            id=row.id,
            statement=row.statement,
            category=row.category,
            source_stakeholder=row.source_stakeholder,
            business_justification=row.business_justification,
            priority=row.priority,
            dependencies=row.dependencies,
            assumptions=row.assumptions,
            acceptance_criteria=row.acceptance_criteria,
            applicable_regulations=row.applicable_regulations,
            risk_level=row.risk_level,
            confidence_score=row.confidence_score,
            approval_status=row.approval_status,
        )
        for row in rows
    ]


def generate_docs() -> None:
    load_dotenv()
    init_db()

    session = SessionLocal()
    try:
        requirements = _load_requirements(session)
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
