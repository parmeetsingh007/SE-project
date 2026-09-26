"""Generates SRS.md, user_stories.md, and traceability_matrix.csv.

Only the prose (executive summary, user stories) comes from Gemini, and it's
grounded strictly in the given requirements/characteristics — no invented
facts. See doc_renderers.py for the deterministic file rendering.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.agents.doc_renderers import write_srs, write_traceability_csv, write_user_stories
from src.agents.llm_client import call_agent_json
from src.agents.sdlc_selection import SDLCRecommendation, summarize_requirements
from src.models.requirement import Requirement

SUMMARY_PROMPT = """\
You are drafting the executive summary of a Software Requirements Specification \
for a bank's payment-processing feature. You will be given aggregate \
characteristics of the gathered requirements (counts, category/risk distribution). \
Write a 2-4 sentence summary grounded strictly in these numbers — do not invent \
facts, deadlines, or figures not given to you.

Respond with ONLY valid JSON: {"summary": str}
"""

STORIES_PROMPT = """\
You are converting system-level requirements into user stories for a bank's \
payment-processing feature. You will be given a list of requirements, each with \
an "id", "statement", and optional "business_justification".

For each one, write a user story in "As a <role>, I want <capability>, so that \
<benefit>" form, from the perspective of whoever benefits (often the paying \
customer, sometimes a fraud analyst or compliance reviewer) — not the stakeholder \
who dictated it. Ground the capability and benefit strictly in the given \
statement/justification; do not invent new functionality.

Respond with ONLY valid JSON matching this schema, no prose before or after:
{"stories": [{"requirement_id": str, "as_a": str, "i_want": str, "so_that": str}]}
"""


class ExecutiveSummary(BaseModel):
    summary: str


class UserStory(BaseModel):
    requirement_id: str
    as_a: str
    i_want: str
    so_that: str


class UserStoriesOutput(BaseModel):
    stories: list[UserStory]


class DocumentationOutput(BaseModel):
    srs_path: str
    user_stories_path: str
    traceability_csv_path: str


class DocumentationAgent:
    """Writes the SRS, user stories, and traceability matrix to docs/generated/."""

    def __init__(self, output_dir: str = "docs/generated") -> None:
        self.output_dir = Path(output_dir)

    def run(
        self,
        requirements: list[Requirement],
        sdlc_recommendations: list[SDLCRecommendation],
        db_session: Session | None = None,
    ) -> DocumentationOutput:
        characteristics = summarize_requirements(requirements)
        summary = call_agent_json(
            agent_name="documentation_summary",
            system_prompt=SUMMARY_PROMPT,
            user_content=json.dumps(characteristics),
            output_model=ExecutiveSummary,
            db_session=db_session,
        ).summary

        payload = [
            {
                "id": r.id,
                "statement": r.statement,
                "business_justification": r.business_justification,
            }
            for r in requirements
        ]
        stories = call_agent_json(
            agent_name="documentation_user_stories",
            system_prompt=STORIES_PROMPT,
            user_content=json.dumps(payload),
            output_model=UserStoriesOutput,
            db_session=db_session,
        ).stories

        self.output_dir.mkdir(parents=True, exist_ok=True)
        srs_path = write_srs(self.output_dir, requirements, sdlc_recommendations, summary)
        stories_path = write_user_stories(self.output_dir, stories)
        csv_path = write_traceability_csv(self.output_dir, requirements)

        return DocumentationOutput(
            srs_path=str(srs_path),
            user_stories_path=str(stories_path),
            traceability_csv_path=str(csv_path),
        )
