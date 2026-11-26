"""Finds weak requirements and drafts optional clarification questions.

A requirement is weak when a developer could not build or test it without guessing.
The questions are suggestions: the user decides whether to answer or skip each one.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.common import DOMAIN, JSON_ONLY, dumps
from src.agents.llm_client import call_agent_json
from src.models.requirement import QualityFlag, Question, Requirement

FLAG_KINDS = [
    "ambiguity",
    "incomplete",
    "untestable",
    "non_atomic",
    "undefined_term",
    "infeasible",
    "missing_source",
]

SYSTEM_PROMPT = f"""\
You are the requirement-quality and clarification agent for {DOMAIN}. You receive a JSON \
list of requirements, each with a "ref", a "statement", optional "assumptions" and an \
"unclear" list noted by the extraction agent.

Check each requirement for these defects (use exactly these kinds):
- ambiguity: vague words with no measurable meaning ("fast", "secure", "easy", "soon", \
"high risk" without a definition)
- incomplete: a missing actor, condition, threshold, customer type, time limit, owner or \
failure behaviour that a developer needs
- untestable: no way to prove pass or fail
- non_atomic: bundles several obligations in one statement
- undefined_term: uses a term or acronym that is not defined
- infeasible: unrealistic or self-contradictory as written

Be fair: do NOT flag requirements that are already concrete. A requirement with no defect \
gets empty lists.

For each requirement that has defects, write up to 3 clarification questions that a \
business analyst could put to the stakeholder. Each question must be specific and answerable \
in a sentence. When there is a sensible set of common answers, include 2-4 short "options" \
(for example ["24 hours", "2 business days", "5 business days"]); otherwise leave options empty. \
Each question has a short "why" saying which defect it resolves.

{JSON_ONLY}
{{"reviews": [{{"ref": str, "flags": [{{"kind": str, "detail": str}}],
"questions": [{{"question": str, "why": str, "options": [str]}}]}}]}}
Every input "ref" must appear exactly once.
"""


class ReviewQuestion(BaseModel):
    question: str
    why: str = ""
    options: list[str] = Field(default_factory=list)


class ReviewFlag(BaseModel):
    kind: str
    detail: str


class Review(BaseModel):
    ref: str
    flags: list[ReviewFlag] = Field(default_factory=list)
    questions: list[ReviewQuestion] = Field(default_factory=list)


class QualityOutput(BaseModel):
    reviews: list[Review]


class QualityAgent:
    def run(
        self, requirements: list[Requirement], db_session: Session | None = None
    ) -> list[Question]:
        """Sets quality_flags / is_weak on each requirement in place and returns new questions."""
        payload = [
            {"ref": r.ref, "statement": r.statement, "assumptions": r.assumptions, "unclear": r.hints}
            for r in requirements
        ]
        result = call_agent_json(
            agent_name="quality",
            system_prompt=SYSTEM_PROMPT,
            user_content=dumps(payload),
            output_model=QualityOutput,
            db_session=db_session,
        )
        by_ref = {review.ref: review for review in result.reviews}
        questions: list[Question] = []
        for requirement in requirements:
            review = by_ref.get(requirement.ref)
            flags = [
                QualityFlag(kind=f.kind if f.kind in FLAG_KINDS else "ambiguity", detail=f.detail)
                for f in (review.flags if review else [])
            ]
            if not requirement.source_excerpt.strip():
                flags.append(QualityFlag(kind="missing_source", detail="No source quote is recorded."))
            requirement.quality_flags = flags
            requirement.is_weak = bool(flags)
            if review and flags:
                for q in review.questions[:3]:
                    questions.append(
                        Question(
                            requirement_id=requirement.id,
                            question=q.question.strip(),
                            why=q.why.strip(),
                            options=[o.strip() for o in q.options if o.strip()][:4],
                        )
                    )
        return questions
