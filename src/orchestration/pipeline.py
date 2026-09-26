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

    print(f"Extracted and classified {len(requirements)} requirements:\n")
    for req in requirements:
        categories = ", ".join(c.value for c in req.category) or "(uncategorized)"
        print(f"- [{categories}] {req.statement}")
        print(f"  source: {req.source_stakeholder}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.orchestration.pipeline <transcript_path>")
        sys.exit(1)
    run_pipeline(sys.argv[1])
