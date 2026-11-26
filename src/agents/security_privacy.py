"""Derives implicit security/privacy requirements and a STRIDE-style threat model."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.common import DOMAIN, JSON_ONLY, dumps
from src.agents.llm_client import call_agent_json
from src.models.requirement import Requirement, Threat

MAX_DERIVED = 8

SYSTEM_PROMPT = f"""\
You are the security-and-privacy agent for {DOMAIN}. You receive the project's requirements \
as a JSON list with "ref", "statement" and "categories".

1. DERIVED REQUIREMENTS. Find security or privacy needs that the requirements imply but never \
state (for example: a requirement that stores identity documents implies encryption at rest, \
retention limits and access logging). Propose at most {MAX_DERIVED} new requirements written \
as "The system shall ...". Each must be genuinely implied by a specific stated requirement \
(give its "related_ref") and must NOT repeat something already stated. Do not pad with \
generic advice.

2. THREAT MODEL. List up to 8 realistic threats to this system using STRIDE (Spoofing, \
Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege), \
for example forged identity documents, deepfake selfies, tampering with screening results, \
leaking identity documents. For each threat name the asset at risk and which existing \
requirement refs mitigate it (empty list if none do - that is an important finding).

{JSON_ONLY}
{{"derived": [{{"statement": str, "rationale": str, "related_ref": str}}],
"threats": [{{"stride": str, "threat": str, "asset": str, "mitigated_by": [str]}}]}}
"""


class DerivedItem(BaseModel):
    statement: str
    rationale: str = ""
    related_ref: str = ""


class ThreatItem(BaseModel):
    stride: str
    threat: str
    asset: str = ""
    mitigated_by: list[str] = Field(default_factory=list)


class SecurityOutput(BaseModel):
    derived: list[DerivedItem] = Field(default_factory=list)
    threats: list[ThreatItem] = Field(default_factory=list)


class SecurityPrivacyAgent:
    def run(
        self, requirements: list[Requirement], db_session: Session | None = None
    ) -> tuple[list[DerivedItem], list[Threat]]:
        payload = [
            {"ref": r.ref, "statement": r.statement, "categories": [c.value for c in r.categories]}
            for r in requirements
        ]
        output = call_agent_json(
            agent_name="security_privacy",
            system_prompt=SYSTEM_PROMPT,
            user_content=dumps(payload),
            output_model=SecurityOutput,
            db_session=db_session,
        )
        id_by_ref = {r.ref: r.id for r in requirements}
        threats = [
            Threat(
                stride=t.stride,
                threat=t.threat,
                asset=t.asset,
                mitigated_by=[id_by_ref[ref] for ref in t.mitigated_by if ref in id_by_ref],
            )
            for t in output.threats[:8]
        ]
        return output.derived[:MAX_DERIVED], threats
