"""Pulls candidate requirement statements out of a raw stakeholder transcript."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.base import call_agent_json

SYSTEM_PROMPT = """\
You are the extraction agent in a requirements-gathering pipeline for a bank's \
payment-processing feature. You will be given a raw interview transcript between \
stakeholders (e.g. a business analyst and a security lead) discussing a feature.

Pull out every candidate software requirement implied by the conversation, even if \
it was stated informally. For each one, capture:
- statement: a single clear requirement sentence, phrased as "The system shall ..."
- source_stakeholder: whoever raised or owns this requirement (name + role)
- business_justification: why it's needed, if stated or clearly implied; else null
- assumptions: things the speakers assumed but did not confirm
- open_questions: anything left vague, unresolved, or explicitly flagged as
  "needs follow-up" in the transcript

Do not invent requirements that aren't grounded in the transcript. Do not resolve
ambiguity yourself — capture it in open_questions instead, a later agent handles it.

Respond with ONLY valid JSON matching this schema, no prose before or after:
{"requirements": [{"statement": str, "source_stakeholder": str,
"business_justification": str | null, "assumptions": [str], "open_questions": [str]}]}
"""


class ExtractedRequirementCandidate(BaseModel):
    """A raw candidate requirement, before classification/risk/compliance tagging."""

    statement: str
    source_stakeholder: str
    business_justification: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class ExtractionOutput(BaseModel):
    requirements: list[ExtractedRequirementCandidate]


class ExtractionAgent:
    """Turns a stakeholder transcript into a list of candidate requirements."""

    def run(
        self, transcript_text: str, db_session: Session | None = None
    ) -> list[ExtractedRequirementCandidate]:
        result = call_agent_json(
            agent_name="extraction",
            system_prompt=SYSTEM_PROMPT,
            user_content=transcript_text,
            output_model=ExtractionOutput,
            db_session=db_session,
        )
        return result.requirements
