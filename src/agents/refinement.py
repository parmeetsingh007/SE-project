"""Folds the user's answers to clarification questions back into the requirements."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.common import DOMAIN, JSON_ONLY, dumps
from src.agents.llm_client import call_agent_json
from src.models.requirement import Requirement

SYSTEM_PROMPT = f"""\
You are the requirement-refinement agent for {DOMAIN}. You receive a JSON list. Each item has \
a requirement "ref", its current "statement", its "assumptions", and "answers": questions a \
reviewer put to a stakeholder together with the answers they gave.

Rewrite each requirement so it incorporates the answers, still as one atomic statement \
beginning "The system shall ...". Use ONLY facts present in the answers. Do not add anything \
the answers do not say. If an answer is itself vague, keep the requirement at that level and \
list what is still unclear in "still_unclear". Add any new assumption an answer reveals to \
"new_assumptions".

{JSON_ONLY}
{{"updates": [{{"ref": str, "statement": str, "new_assumptions": [str], "still_unclear": [str]}}]}}
"""


class UpdateItem(BaseModel):
    ref: str
    statement: str
    new_assumptions: list[str] = Field(default_factory=list)
    still_unclear: list[str] = Field(default_factory=list)


class RefinementOutput(BaseModel):
    updates: list[UpdateItem]


class RefinementAgent:
    def run(
        self,
        requirements: list[Requirement],
        answers: dict[str, list[dict]],
        db_session: Session | None = None,
    ) -> list[str]:
        """Updates statement/assumptions/hints in place; returns ids of requirements changed."""
        targets = [r for r in requirements if answers.get(r.id)]
        if not targets:
            return []
        payload = [
            {"ref": r.ref, "statement": r.statement, "assumptions": r.assumptions, "answers": answers[r.id]}
            for r in targets
        ]
        output = call_agent_json(
            agent_name="refinement",
            system_prompt=SYSTEM_PROMPT,
            user_content=dumps(payload),
            output_model=RefinementOutput,
            db_session=db_session,
        )
        by_ref = {item.ref: item for item in output.updates}
        changed: list[str] = []
        for requirement in targets:
            item = by_ref.get(requirement.ref)
            if item is None or not item.statement.strip():
                continue
            if item.statement.strip() != requirement.statement:
                requirement.history.append({"action": "refined_from_answers", "previous": requirement.statement})
                requirement.statement = item.statement.strip()
            for assumption in item.new_assumptions:
                if assumption not in requirement.assumptions:
                    requirement.assumptions.append(assumption)
            requirement.hints = item.still_unclear
            changed.append(requirement.id)
        return changed
