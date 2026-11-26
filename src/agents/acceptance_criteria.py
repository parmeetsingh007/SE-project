"""Drafts testable acceptance criteria for every requirement in one call."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.common import DOMAIN, JSON_ONLY, dumps
from src.agents.llm_client import call_agent_json
from src.models.requirement import Requirement

SYSTEM_PROMPT = f"""\
You are the acceptance-criteria agent for {DOMAIN}. You receive a JSON list of requirements \
with "ref", "statement", "assumptions" and (when the stakeholder answered clarification \
questions) "clarifications".

Write 2-4 concrete, testable acceptance criteria per requirement. Each is a specific \
pass/fail condition a QA engineer could verify, preferably Given/When/Then. Ground every \
criterion strictly in the statement and clarifications. Do NOT invent numbers or rules that \
were not given: if the requirement is vague, write the criterion around what is stated and \
use "[TBD: ...]" for the missing value so the gap stays visible.

{JSON_ONLY}
{{"criteria": [{{"ref": str, "acceptance_criteria": [str]}}]}}
Every input "ref" must appear exactly once.
"""


class CriteriaItem(BaseModel):
    ref: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class CriteriaOutput(BaseModel):
    criteria: list[CriteriaItem]


class AcceptanceCriteriaAgent:
    def run(
        self,
        requirements: list[Requirement],
        clarifications: dict[str, list[dict]] | None = None,
        db_session: Session | None = None,
    ) -> None:
        """Sets acceptance_criteria on each requirement in place."""
        clarifications = clarifications or {}
        payload = [
            {
                "ref": r.ref,
                "statement": r.statement,
                "assumptions": r.assumptions,
                **({"clarifications": clarifications[r.id]} if clarifications.get(r.id) else {}),
            }
            for r in requirements
        ]
        output = call_agent_json(
            agent_name="acceptance_criteria",
            system_prompt=SYSTEM_PROMPT,
            user_content=dumps(payload),
            output_model=CriteriaOutput,
            db_session=db_session,
        )
        by_ref = {item.ref: item.acceptance_criteria for item in output.criteria}
        for requirement in requirements:
            criteria = [c.strip() for c in by_ref.get(requirement.ref, []) if c.strip()]
            if criteria:
                requirement.acceptance_criteria = criteria
