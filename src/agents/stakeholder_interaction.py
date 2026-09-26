"""Pre-processing pass over a raw transcript, run before extraction.

Scope cut, deliberate: transcripts here are pre-written, not live interviews,
so this agent cannot actually ask a stakeholder a question and get a reply.
It simulates the "notice a vague answer, draft a follow-up" half of adaptive
interviewing on static text — surfacing what a human interviewer would have
asked in the room, without a live conversational loop. See the README for
the same note in context.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.llm_client import call_agent_json

SYSTEM_PROMPT = """\
You are the stakeholder-interaction agent in a requirements-gathering pipeline \
for a bank's payment-processing feature. You will be given a raw interview \
transcript, before any requirement extraction has happened.

Find stakeholder statements that are vague, hedge ("I think", "probably", "I'd \
need to check", "don't quote me on that"), or leave a concrete detail unstated \
(a threshold, a policy, an owner). For each one, quote the original statement \
and draft a concrete follow-up question an interviewer would ask in the room to \
pin it down. Only flag genuinely vague/incomplete statements — do not flag \
statements that are already concrete and complete.

Respond with ONLY valid JSON matching this schema, no prose before or after:
{"follow_ups": [{"original_statement": str, "follow_up_question": str}]}
If nothing is vague or incomplete, return {"follow_ups": []}.
"""


class FollowUpItem(BaseModel):
    original_statement: str
    follow_up_question: str


class StakeholderInteractionOutput(BaseModel):
    follow_ups: list[FollowUpItem] = Field(default_factory=list)


class StakeholderInteractionAgent:
    """Flags vague/incomplete stakeholder statements before extraction runs."""

    def run(
        self, transcript_text: str, db_session: Session | None = None
    ) -> list[FollowUpItem]:
        result = call_agent_json(
            agent_name="stakeholder_interaction",
            system_prompt=SYSTEM_PROMPT,
            user_content=transcript_text,
            output_model=StakeholderInteractionOutput,
            db_session=db_session,
        )
        return result.follow_ups
