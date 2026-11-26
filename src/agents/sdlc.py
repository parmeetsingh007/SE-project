"""Explains the SDLC ranking in plain language. It never changes a score."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.common import DOMAIN, JSON_ONLY, dumps
from src.agents.llm_client import call_agent_json
from src.models.requirement import Factor, SdlcOption

SYSTEM_PROMPT = f"""\
You are the SDLC advisor for {DOMAIN}. A deterministic engine has already scored 14 project \
factors (1-5, with evidence) and ranked lifecycle models. You will receive those factors, the \
ranking and a few project counts. Explain the result for a project manager.

Rules: use ONLY the numbers and evidence provided; never change, re-rank or invent scores. \
Write in plain language.

Return:
- explanation: 3-5 sentences on why the top model fits this project, citing the specific \
factors (e.g. "requirement stability is 2/5 because ...") and what the runner-up offers.
- tradeoffs: 2-4 short bullets on what the team gives up with the top choice.
- would_change_if: 2-3 short bullets naming what new information would change the \
recommendation (for example "if the regulator's guidance is finalised and requirements \
stabilise, V-Model overtakes Spiral").

{JSON_ONLY}
{{"explanation": str, "tradeoffs": [str], "would_change_if": [str]}}
"""


class SdlcNarrative(BaseModel):
    explanation: str
    tradeoffs: list[str] = Field(default_factory=list)
    would_change_if: list[str] = Field(default_factory=list)


class SdlcAdvisorAgent:
    def run(
        self,
        factors: list[Factor],
        ranking: list[SdlcOption],
        counts: dict,
        db_session: Session | None = None,
    ) -> SdlcNarrative:
        payload = {
            "factors": [{"factor": f.label, "score": f.score, "evidence": f.evidence} for f in factors],
            "ranking": [{"model": o.model, "suitability_percent": o.score} for o in ranking[:4]],
            "project": counts,
        }
        return call_agent_json(
            agent_name="sdlc_advisor",
            system_prompt=SYSTEM_PROMPT,
            user_content=dumps(payload),
            output_model=SdlcNarrative,
            db_session=db_session,
        )
