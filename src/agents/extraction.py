"""Extracts candidate requirements from vague, informal stakeholder input.

Every candidate must quote the source verbatim; a quote that cannot be found in the
document is treated as a hallucination and the candidate is dropped (and counted).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.common import DOMAIN, JSON_ONLY, UNTRUSTED_NOTE, wrap_document
from src.agents.llm_client import call_agent_json

SYSTEM_PROMPT = f"""\
You are the requirement-extraction agent for {DOMAIN}. {UNTRUSTED_NOTE}

You will receive ONE stakeholder input: an interview transcript, email, meeting notes, a \
policy extract or an audit finding. It may be vague, informal or incomplete. Pull out \
every software requirement it states or clearly implies, including non-functional ones \
(security, privacy, performance, availability, audit, data retention, integration).

For each requirement return:
- statement: one clear, single requirement written as "The system shall ..." Keep it \
atomic (one obligation per statement). If the stakeholder was vague, write the requirement \
at the level of detail they actually gave. NEVER invent numbers, thresholds, products or \
rules they did not say.
- source_stakeholder: the person or role who said it (name and role if known; otherwise \
the declared role; otherwise "Unspecified").
- source_excerpt: a short quote copied VERBATIM from the input that this requirement \
comes from. It must appear word for word in the input.
- business_justification: why they want it, if said or clearly implied; otherwise null.
- assumptions: things the speaker took for granted without confirming.
- unclear: the things left vague, undecided, contradictory or missing for THIS requirement \
(e.g. "no threshold given", "unclear which customers", "not decided between X and Y"). \
Do not resolve them yourself.

Also extract stated constraints such as deadlines, budgets and legacy systems as \
requirements only if they are phrased as something the system must do or respect.

{JSON_ONLY}
{{"requirements": [{{"statement": str, "source_stakeholder": str, "source_excerpt": str,
"business_justification": str | null, "assumptions": [str], "unclear": [str]}}]}}
If the input contains no requirement at all, return {{"requirements": []}}.
"""


class Candidate(BaseModel):
    statement: str
    source_stakeholder: str = "Unspecified"
    source_excerpt: str
    business_justification: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    unclear: list[str] = Field(default_factory=list)


class ExtractionOutput(BaseModel):
    requirements: list[Candidate]


@dataclass
class ExtractionResult:
    candidates: list[Candidate] = field(default_factory=list)
    dropped_ungrounded: int = 0


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def find_grounding(source_text: str, excerpt: str) -> str | None:
    """Returns the matching verbatim span of the source, or None if the quote is not there.

    Exact (whitespace/case-insensitive) matches pass; otherwise the closest sentence is
    accepted when it is very similar (the model sometimes drops punctuation)."""
    if not excerpt.strip():
        return None
    haystack, needle = _norm(source_text), _norm(excerpt)
    if needle in haystack:
        return excerpt.strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", source_text) if s.strip()]
    best, best_ratio = None, 0.0
    for sentence in sentences:
        ratio = SequenceMatcher(None, _norm(sentence), needle).ratio()
        if ratio > best_ratio:
            best, best_ratio = sentence, ratio
    return best if best is not None and best_ratio >= 0.8 else None


class ExtractionAgent:
    def run(
        self, title: str, text: str, role: str = "", db_session: Session | None = None
    ) -> ExtractionResult:
        output = call_agent_json(
            agent_name="extraction",
            system_prompt=SYSTEM_PROMPT,
            user_content=wrap_document(title, text, role),
            output_model=ExtractionOutput,
            db_session=db_session,
        )
        result = ExtractionResult()
        for candidate in output.requirements:
            grounded = find_grounding(text, candidate.source_excerpt)
            if grounded is None:
                result.dropped_ungrounded += 1
                continue
            candidate.source_excerpt = grounded
            result.candidates.append(candidate)
        return result
