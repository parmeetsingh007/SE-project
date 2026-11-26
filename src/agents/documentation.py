"""Generates user stories and use cases (the narrative artefacts) in one call.

The SRS, matrices and registers are rendered deterministically in src/artefacts so a
formal deliverable never depends on a model paraphrasing a requirement or citation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.common import DOMAIN, JSON_ONLY, dumps
from src.agents.llm_client import call_agent_json
from src.models.requirement import Requirement

MAX_USE_CASES = 6

SYSTEM_PROMPT = f"""\
You are the documentation agent for {DOMAIN}. You receive a JSON list of requirements with \
"ref", "statement", "justification" and "acceptance_criteria".

1. USER STORIES: for each requirement write one story "As a <role>, I want <capability>, \
so that <benefit>" from the point of view of whoever benefits (the customer, an onboarding \
agent, a compliance officer, a fraud analyst) - not the stakeholder who asked. Stay strictly \
within the statement; do not add functionality. Keep any "[TBD: ...]" gap visible.

2. USE CASES: write up to {MAX_USE_CASES} use cases covering the most important end-to-end \
flows. Each has a name, a primary actor, preconditions, a numbered main flow, alternate/failure \
flows, postconditions and the requirement refs it realises.

{JSON_ONLY}
{{"stories": [{{"ref": str, "as_a": str, "i_want": str, "so_that": str}}],
"use_cases": [{{"name": str, "actor": str, "pre": [str], "main": [str], "alt": [str],
"post": [str], "refs": [str]}}]}}
"""


class Story(BaseModel):
    ref: str
    as_a: str
    i_want: str
    so_that: str


class UseCase(BaseModel):
    name: str
    actor: str
    pre: list[str] = Field(default_factory=list)
    main: list[str] = Field(default_factory=list)
    alt: list[str] = Field(default_factory=list)
    post: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)


class DocumentationOutput(BaseModel):
    stories: list[Story] = Field(default_factory=list)
    use_cases: list[UseCase] = Field(default_factory=list)


class DocumentationAgent:
    def run(
        self, requirements: list[Requirement], db_session: Session | None = None
    ) -> DocumentationOutput:
        payload = [
            {
                "ref": r.ref,
                "statement": r.statement,
                "justification": r.business_justification,
                "acceptance_criteria": r.acceptance_criteria,
            }
            for r in requirements
        ]
        output = call_agent_json(
            agent_name="documentation",
            system_prompt=SYSTEM_PROMPT,
            user_content=dumps(payload),
            output_model=DocumentationOutput,
            db_session=db_session,
        )
        known = {r.ref for r in requirements}
        output.stories = [s for s in output.stories if s.ref in known]
        for use_case in output.use_cases:
            use_case.refs = [ref for ref in use_case.refs if ref in known]
        output.use_cases = output.use_cases[:MAX_USE_CASES]
        return output
