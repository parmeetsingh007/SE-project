"""Maps a requirement to candidate PCI-DSS / RBI clauses via the retriever.

Never makes a final legal determination — only proposes citations with a
confidence score and rationale, grounded strictly in retrieved clause text.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.llm_client import call_agent_json
from src.knowledge_base.retriever import RegulationRetriever
from src.models.requirement import Requirement

SYSTEM_PROMPT = """\
You are the compliance-mapping agent in a requirements-gathering pipeline for a \
bank's payment-processing feature. You will be given one requirement statement \
and a list of candidate regulation clauses retrieved from a knowledge base of \
PCI-DSS and RBI payment/authentication excerpts.

Decide which of the candidate clauses (if any) genuinely apply to the requirement.
You are proposing citations for a human compliance reviewer, not making a final
legal determination — be conservative, and never cite a clause_id that was not
given to you in the candidates list.

The retriever selects candidates by topical similarity, not correctness — it will
often hand you clauses that are merely thematically adjacent (same general area,
e.g. "cardholder data protection") without actually governing the specific
mechanism the requirement describes. Apply this test before citing a clause: the
clause must impose a concrete, checkable obligation that the requirement's
statement would satisfy or violate. A shared topic, keyword, or general subject
area is NOT enough on its own — "both are about card data" or "both are about
authentication" does not make a clause applicable unless the clause's actual
mechanism (what it requires you to encrypt, log, verify, retain, disclose, etc.)
matches what the requirement actually does. When in doubt, do not cite it.

For each clause that applies, give:
- regulation: the "source" value from that candidate (e.g. "PCI-DSS" or "RBI")
- clause_id: the "clause_id" value from that candidate
- citation: a short human-readable citation, e.g. "PCI-DSS 8.4.2 - Multi-Factor
  Authentication for All CDE Access"
- confidence: your confidence this clause applies, from 0.0 to 1.0
- rationale: one or two sentences naming the SPECIFIC mechanism in the requirement
  that the clause governs — not just the shared topic. If you cannot name a
  specific matching mechanism, don't cite the clause.

If none of the candidates apply, return an empty "proposals" list rather than
forcing a match. An empty list is a normal, expected, and correct result for many
requirements — most requirements in a transcript will not be compliance-relevant.

Respond with ONLY valid JSON matching this schema, no prose before or after:
{"proposals": [{"regulation": str, "clause_id": str, "citation": str,
"confidence": float, "rationale": str}]}
"""


class ComplianceProposal(BaseModel):
    regulation: str
    clause_id: str
    citation: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class ComplianceMappingOutput(BaseModel):
    proposals: list[ComplianceProposal]


class ComplianceAgent:
    """Proposes regulation citations for a requirement via RAG over the KB."""

    def __init__(self, retriever: RegulationRetriever | None = None) -> None:
        self.retriever = retriever or RegulationRetriever()

    def run(
        self,
        requirement: Requirement,
        top_k: int = 3,
        db_session: Session | None = None,
    ) -> list[ComplianceProposal]:
        candidates = self.retriever.query(requirement.statement, top_k=top_k)
        if not candidates:
            return []

        payload = {
            "requirement_statement": requirement.statement,
            "candidates": [
                {
                    "source": c.source,
                    "clause_id": c.clause_id,
                    "title": c.title,
                    "text": c.text,
                }
                for c in candidates
            ],
        }

        result = call_agent_json(
            agent_name="compliance",
            system_prompt=SYSTEM_PROMPT,
            user_content=json.dumps(payload),
            output_model=ComplianceMappingOutput,
            db_session=db_session,
        )
        return result.proposals
