"""Generates the SRS, user stories, and traceability matrix from *approved*
requirements in *one* batch — the final step of "raw transcript in ->
approved SRS + SDLC recommendation out".

Scoped to a single batch (one transcript ingestion) so approving requirements
from a new transcript doesn't pollute the SDLC recommendation with old,
unrelated requirements from earlier ingestions.

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
from src.models.db import (
    SessionLocal,
    init_db,
    load_batches,
    load_requirements,
    save_batch_sdlc_recommendation,
)
from src.models.requirement import ApprovalStatus, Requirement


def generate_documentation(
    approved_requirements: list[Requirement],
    db_session: Session,
    batch_id: str | None = None,
    all_batch_requirements: list[Requirement] | None = None,
) -> tuple[list[SDLCRecommendation], DocumentationOutput]:
    """Runs SDLC selection + documentation for an already-approved requirement
    set. When batch_id is given, the recommendation is also persisted onto
    that batch so it can be looked up again later (see the History tab).

    SDLC selection reasons over ``all_batch_requirements`` (falling back to
    just the approved set if not given) rather than only the approved subset:
    "approved" and "needs revision" are mutually exclusive statuses, so an
    approved-only view always reports zero requirements needing revision and
    can never surface the batch's real gathering-time uncertainty — the
    signal the Spiral/high-uncertainty recommendation depends on. The SRS
    itself is still built strictly from approved_requirements, since that's
    the actual reviewed output."""
    sdlc_characteristics_source = (
        all_batch_requirements if all_batch_requirements is not None else approved_requirements
    )
    recommendations = SDLCSelectionAgent().run(sdlc_characteristics_source, db_session=db_session)
    output = DocumentationAgent().run(approved_requirements, recommendations, db_session=db_session)
    if batch_id is not None:
        save_batch_sdlc_recommendation(
            db_session, batch_id, [rec.model_dump(mode="json") for rec in recommendations]
        )
    return recommendations, output


def generate_docs() -> None:
    """Generates docs for the most recently ingested batch that has at least
    one approved requirement."""
    load_dotenv()
    init_db()

    session = SessionLocal()
    try:
        target_batch = None
        approved: list[Requirement] = []
        for batch in load_batches(session):
            batch_requirements = load_requirements(session, batch_id=batch.id)
            batch_approved = [
                r for r in batch_requirements if r.approval_status == ApprovalStatus.APPROVED
            ]
            if batch_approved:
                target_batch = batch
                approved = batch_approved
                break

        if target_batch is None:
            print(
                "No batch with approved requirements found — approve some in "
                "the Streamlit UI (Review & approve tab) first."
            )
            return

        recommendations, output = generate_documentation(
            approved, session, batch_id=target_batch.id, all_batch_requirements=batch_requirements
        )
    finally:
        session.close()

    print(f"Batch: {target_batch.transcript_preview}")
    print(f"Documented {len(approved)} approved requirement(s) from this batch:")
    print(f"  SRS: {output.srs_path}")
    print(f"  User stories: {output.user_stories_path}")
    print(f"  Traceability matrix: {output.traceability_csv_path}")
    print("\nRecommended SDLC approach:")
    for i, rec in enumerate(recommendations, start=1):
        print(f"  {i}. {rec.model} (confidence: {rec.confidence:.0%}) — {rec.rationale}")


if __name__ == "__main__":
    generate_docs()
