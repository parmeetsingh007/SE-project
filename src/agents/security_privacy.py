"""Flags implicit security/privacy needs a requirement doesn't state outright.

E.g. a requirement that mentions storing a risk score or an authentication
result implies an encryption-at-rest and retention-period need, even if nobody
said "encrypt" or "retain" out loud.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.llm_client import call_agent_json
from src.models.requirement import Requirement

SYSTEM_PROMPT = """\
You are the security/privacy agent in a requirements-gathering pipeline for a \
bank's payment-processing feature. You will be given one requirement statement.

Identify security or privacy needs that are implied by this requirement but not \
explicitly stated — think encryption at rest/in transit, data retention and \
deletion, access control/least privilege, secure logging (never logging secrets \
or full card data), key management, or consent/PII handling. Only flag a concern \
that is genuinely implied by what this requirement does; do not pad the list with \
generic security advice unrelated to it.

For each concern, propose a candidate new requirement statement that would address \
it, phrased as "The system shall ...".

If nothing is meaningfully implied beyond what's already stated, return an empty \
"flags" list.

Respond with ONLY valid JSON matching this schema, no prose before or after:
{"flags": [{"concern": str, "recommended_requirement": str, "rationale": str}]}
"""


class SecurityPrivacyFlag(BaseModel):
    concern: str
    recommended_requirement: str
    rationale: str


class SecurityPrivacyOutput(BaseModel):
    flags: list[SecurityPrivacyFlag] = Field(default_factory=list)


class SecurityPrivacyAgent:
    """Flags implicit security/privacy needs for a single requirement."""

    def run(
        self, requirement: Requirement, db_session: Session | None = None
    ) -> list[SecurityPrivacyFlag]:
        result = call_agent_json(
            agent_name="security_privacy",
            system_prompt=SYSTEM_PROMPT,
            user_content=json.dumps({"statement": requirement.statement}),
            output_model=SecurityPrivacyOutput,
            db_session=db_session,
        )
        return result.flags
