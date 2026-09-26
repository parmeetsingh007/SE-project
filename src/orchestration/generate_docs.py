"""Generates the SRS, user stories, and traceability matrix from *approved*
requirements — the final step of "raw transcript in -> approved SRS + SDLC
recommendation out".

Run on demand after human review in the Streamlit UI, not automatically at
the end of every ingestion — nothing gets documented as final output until
a reviewer has explicitly approved it.

Usage:
    python -m src.orchestration.generate_docs
"""

from __future__ import annotations

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from src.agents.documentation import DocumentationAgent, DocumentationOutput
from src.agents.sdlc_selection import SDLCRecommendation, SDLCSelectionAgent
from src.models.db import SessionLocal, init_db, load_requirements
from src.models.requirement import ApprovalStatus, Requirement


def generate_documentation(
    approved_requirements: list[Requirement], db_session: Session
) -> tuple[list[SDLCRecommendation], DocumentationOutput]:
    """Runs SDLC selection + documentation for an already-approved requirement set."""
    recommendations = SDLCSelectionAgent().run(approved_requirements, db_session=db_session)
    output = DocumentationAgent().run(approved_requirements, recommendations, db_session=db_session)
    return recommendations, output


def generate_docs() -> None:
    load_dotenv()
    init_db()

    session = SessionLocal()
    try:
        all_requirements = load_requirements(session)
        approved = [r for r in all_requirements if r.approval_status == ApprovalStatus.APPROVED]
        if not approved:
            print(
                f"{len(all_requirements)} requirement(s) persisted, 0 approved — "
                "approve some in the Streamlit UI (Review & approve tab) first."
            )
            return

        recommendations, output = generate_documentation(approved, session)
    finally:
        session.close()

    print(f"Documented {len(approved)} approved requirement(s) (of {len(all_requirements)} total):")
    print(f"  SRS: {output.srs_path}")
    print(f"  User stories: {output.user_stories_path}")
    print(f"  Traceability matrix: {output.traceability_csv_path}")
    print("\nRecommended SDLC approach:")
    for i, rec in enumerate(recommendations, start=1):
        print(f"  {i}. {rec.model} (confidence: {rec.confidence:.0%}) — {rec.rationale}")


if __name__ == "__main__":
    generate_docs()
