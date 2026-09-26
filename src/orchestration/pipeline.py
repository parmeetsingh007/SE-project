"""End-to-end entry point: run the Coordinator on a transcript file.

Usage:
    python -m src.orchestration.pipeline data/sample_inputs/transcript_step_up_auth.txt
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from src.agents.coordinator import Coordinator
from src.models.db import SessionLocal, init_db


def run_pipeline(transcript_path: str) -> None:
    load_dotenv()
    init_db()

    with open(transcript_path, encoding="utf-8") as f:
        transcript_text = f.read()

    session = SessionLocal()
    try:
        coordinator = Coordinator()
        requirements = coordinator.run(transcript_text, session)
    finally:
        session.close()

    validation_issues_by_id = {
        issue.requirement_id: issue for issue in coordinator.validation_issues
    }

    if coordinator.stakeholder_follow_ups:
        print("Pre-extraction stakeholder follow-ups (simulated adaptive interviewing"
              " on the static transcript — see README):")
        for follow_up in coordinator.stakeholder_follow_ups:
            print(f'- "{follow_up.original_statement}"')
            print(f"    -> {follow_up.follow_up_question}")
        print()

    print(f"Processed {len(requirements)} requirements:\n")
    for req in requirements:
        categories = ", ".join(c.value for c in req.category) or "(uncategorized)"
        risk = req.risk_level.value if req.risk_level else "unscored"
        print(f"- [{categories}] ({req.approval_status.value}, risk={risk}) {req.statement}")
        print(f"  source: {req.source_stakeholder}")
        for citation in req.applicable_regulations:
            print(f"  regulation: {citation}")
        for issue in coordinator.clarification_issues.get(req.id, []):
            print(f"  needs clarification: {issue.issue}")
            print(f"    -> {issue.follow_up_question}")
        for flag in coordinator.security_flags.get(req.id, []):
            print(f"  implicit security/privacy need: {flag.concern}")
            print(f"    -> {flag.recommended_requirement}")
        if req.id in validation_issues_by_id:
            print(f"  validation: {', '.join(validation_issues_by_id[req.id].problems)}")

    if coordinator.conflicts:
        print("\nConflicts detected:")
        for conflict in coordinator.conflicts:
            print(
                f"- [{conflict.conflict_type}] {conflict.requirement_id_a} <-> "
                f"{conflict.requirement_id_b}: {conflict.explanation}"
            )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.orchestration.pipeline <transcript_path>")
        sys.exit(1)
    run_pipeline(sys.argv[1])
