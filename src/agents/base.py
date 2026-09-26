"""Shared helper for calling the Anthropic API with validated JSON-only output.

Every agent asks Claude for JSON-only output and validates it against a Pydantic
model before returning. This module centralizes that call + parse + audit-log
sequence so individual agent files stay focused on their own prompt and schema.
"""

from __future__ import annotations

import json
import os
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from src.models.db import AuditLogORM

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

T = TypeVar("T", bound=BaseModel)


class AgentOutputError(ValueError):
    """Raised when an agent's LLM call returns output that fails JSON parsing
    or Pydantic validation. Never swallowed — always logged and re-raised."""


def call_agent_json(
    *,
    agent_name: str,
    system_prompt: str,
    user_content: str,
    output_model: type[T],
    client: anthropic.Anthropic | None = None,
    db_session: Session | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
) -> T:
    """Call Claude with a JSON-only system prompt and validate the response.

    Logs every call (input, raw output, timestamp) to the audit_log table when
    ``db_session`` is provided. Raises ``AgentOutputError`` on parse/validation
    failure instead of silently dropping the bad output.
    """
    client = client or anthropic.Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    raw_text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    )

    try:
        data = json.loads(raw_text)
        parsed = output_model.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        _log_call(db_session, agent_name, user_content, f"PARSE_ERROR: {exc}\n{raw_text}")
        raise AgentOutputError(f"{agent_name} returned invalid JSON output: {exc}") from exc

    _log_call(db_session, agent_name, user_content, raw_text)
    return parsed


def _log_call(
    db_session: Session | None, agent_name: str, input_payload: str, output_payload: str
) -> None:
    if db_session is None:
        return
    db_session.add(
        AuditLogORM(
            agent_name=agent_name,
            input_payload=input_payload,
            output_payload=output_payload,
        )
    )
    db_session.commit()
