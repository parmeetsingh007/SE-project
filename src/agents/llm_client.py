"""Shared helper for calling the Gemini API with validated JSON-only output.

Every agent asks Gemini for JSON-only output and validates it against a Pydantic
model before returning. This module centralizes that call + parse + audit-log
sequence so individual agent files stay focused on their own prompt and schema.
"""

from __future__ import annotations

import json
import os
from typing import TypeVar

from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from src.models.db import AuditLogORM

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

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
    client: genai.Client | None = None,
    db_session: Session | None = None,
    model: str = DEFAULT_MODEL,
) -> T:
    """Call Gemini with a JSON-only system prompt and validate the response.

    Logs every call (input, raw output, timestamp) to the audit_log table when
    ``db_session`` is provided. Raises ``AgentOutputError`` on parse/validation
    failure instead of silently dropping the bad output.
    """
    client = client or genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

    response = client.models.generate_content(
        model=model,
        contents=user_content,
        config=genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
        ),
    )
    raw_text = response.text

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
