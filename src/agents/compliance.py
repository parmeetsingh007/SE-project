"""Maps requirements to regulation clauses (retrieval-grounded) and checks control coverage.

The model may only choose among clauses the retriever returned for that requirement. Any
other clause id is dropped and counted as a hallucination. It never makes a final legal
determination: low-confidence or high-impact mappings are flagged for legal review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.common import DOMAIN, JSON_ONLY, dumps
from src.agents.llm_client import call_agent_json
from src.knowledge_base.kb import KnowledgeBase, get_kb
from src.models.requirement import ControlCoverage, RegulationMapping, Requirement

LEGAL_REVIEW_BELOW = 0.6

SYSTEM_PROMPT = f"""\
You are the compliance-mapping agent for {DOMAIN}. You receive a JSON list. Each item has a \
requirement "ref" and "statement" plus "candidates": regulation or standard clauses retrieved \
from the knowledge base.

For each requirement decide which candidates, if any, genuinely apply. A clause applies only \
if it imposes a concrete obligation that the requirement would satisfy or violate. Sharing a \
topic or keyword is NOT enough. Be conservative; an empty list is a normal, correct answer. \
You propose citations for a human compliance officer; you never make a final legal decision. \
Only use "clause_id" values that appear in that requirement's own candidates.

For each applicable clause give a confidence from 0.0 to 1.0 and a one-sentence rationale \
that names the specific obligation matched.

{JSON_ONLY}
{{"mappings": [{{"ref": str, "clause_id": str, "confidence": float, "rationale": str}}]}}
"""


class MappingItem(BaseModel):
    ref: str
    clause_id: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str = ""


class MappingOutput(BaseModel):
    mappings: list[MappingItem] = Field(default_factory=list)


@dataclass
class ComplianceResult:
    hallucinated_citations: int = 0
    mapped: int = 0
    candidates_offered: dict[str, list[str]] = field(default_factory=dict)


class ComplianceAgent:
    def __init__(self, kb: KnowledgeBase | None = None) -> None:
        self.kb = kb or get_kb()

    def run(
        self,
        requirements: list[Requirement],
        jurisdictions: list[str],
        db_session: Session | None = None,
        top_k: int = 5,
    ) -> ComplianceResult:
        """Replaces ``regulations`` on each requirement in place."""
        result = ComplianceResult()
        payload = []
        for requirement in requirements:
            clauses = self.kb.retrieve(requirement.statement, jurisdictions, top_k=top_k)
            result.candidates_offered[requirement.ref] = [c.id for c in clauses]
            payload.append(
                {
                    "ref": requirement.ref,
                    "statement": requirement.statement,
                    "candidates": [
                        {"clause_id": c.id, "source": c.source, "title": c.title, "text": c.text}
                        for c in clauses
                    ],
                }
            )

        output = call_agent_json(
            agent_name="compliance",
            system_prompt=SYSTEM_PROMPT,
            user_content=dumps(payload),
            output_model=MappingOutput,
            db_session=db_session,
        )

        by_ref: dict[str, list[RegulationMapping]] = {r.ref: [] for r in requirements}
        for item in output.mappings:
            if item.ref not in by_ref:
                continue
            offered = result.candidates_offered.get(item.ref, [])
            clause = self.kb.get(item.clause_id)
            if clause is None or item.clause_id not in offered:
                result.hallucinated_citations += 1
                continue
            if any(m.clause_id == clause.id for m in by_ref[item.ref]):
                continue
            by_ref[item.ref].append(
                RegulationMapping(
                    regulation=clause.source,
                    clause_id=clause.id,
                    citation=clause.citation,
                    jurisdiction=clause.jurisdiction,
                    confidence=item.confidence,
                    rationale=item.rationale,
                    needs_legal_review=clause.high_impact or item.confidence < LEGAL_REVIEW_BELOW,
                )
            )
            result.mapped += 1

        for requirement in requirements:
            requirement.regulations = sorted(by_ref[requirement.ref], key=lambda m: -m.confidence)
        return result


def _mentions(text: str, word: str) -> bool:
    """Whole-word match for short words (so 'app' does not match 'approved'); prefix
    match for longer ones (so 'biometric' matches 'biometrics')."""
    pattern = rf"\b{re.escape(word)}\b" if len(word) <= 4 else rf"\b{re.escape(word)}"
    return re.search(pattern, text) is not None


def assess_controls(
    requirements: list[Requirement],
    jurisdictions: list[str],
    kb: KnowledgeBase | None = None,
    document_texts: list[str] | None = None,
) -> list[ControlCoverage]:
    """Rule-based coverage of the mandatory-control catalogue.

    covered  = some requirement cites one of the control's regulations AND mentions its keywords
    partial  = only one of those holds
    gap      = neither
    not_applicable = the control only applies to features the inputs never mention
    """
    kb = kb or get_kb()
    # Applicability is judged only from what the stakeholders themselves said, never from
    # requirements the system derived, so derived text cannot make more controls "apply".
    corpus = " ".join(
        [
            *(document_texts or []),
            *(f"{r.statement} {r.business_justification or ''} {' '.join(r.assumptions)}" for r in requirements if r.origin == "stated"),
        ]
    ).lower()
    coverage: list[ControlCoverage] = []
    for control in kb.controls_for(jurisdictions):
        regs = [kb.get(r) for r in control.regulations if kb.get(r)]
        reg_names = sorted({r.source for r in regs})
        applicable = not control.applies_if or any(_mentions(corpus, word) for word in control.applies_if)
        if not applicable:
            status, covered_by = "not_applicable", []
        else:
            mapped = {r.ref for r in requirements if any(m.clause_id in control.regulations for m in r.regulations)}
            keyword = {
                r.ref
                for r in requirements
                if any(k in f"{r.statement} {' '.join(r.assumptions)}".lower() for k in control.keywords)
            }
            covered_by = sorted(mapped | keyword)
            if mapped and keyword:
                status = "covered"
            elif mapped or keyword:
                status = "partial"
            else:
                status = "gap"
        coverage.append(
            ControlCoverage(
                control_id=control.id,
                title=control.title,
                description=next((c.text for c in regs[:1]), ""),
                regulations=reg_names,
                status=status,
                covered_by=covered_by,
                suggested_requirement=control.suggested_requirement if status in ("gap", "partial") else "",
            )
        )
    return coverage
