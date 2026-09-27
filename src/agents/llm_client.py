"""Shared helper for calling the Gemini API with validated JSON-only output.

Every agent asks Gemini for JSON-only output and validates it against a Pydantic
model before returning. This module centralizes that call + parse + audit-log
sequence so individual agent files stay focused on their own prompt and schema.
"""

from __future__ import annotations

import json
import os
import time
from typing import TypeVar

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from src.models.db import AuditLogORM

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

# The free tier's 15 requests/minute limit is easily hit mid-run now that the
# pipeline makes ~5 calls per requirement — retry transient rate-limit (429)
# and overload (503) errors with backoff instead of losing the whole batch
# (Coordinator only commits requirements at the very end of run()).
MAX_RATE_LIMIT_RETRIES = 6
DEFAULT_RETRY_DELAY_SECONDS = 20.0
MAX_RETRY_DELAY_SECONDS = 65.0
RETRYABLE_STATUS_CODES = {429, 503}

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

    response = _generate_with_retry(client, model, user_content, system_prompt)
    raw_text = response.text

    try:
        data = json.loads(raw_text)
        parsed = output_model.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        _log_call(db_session, agent_name, user_content, f"PARSE_ERROR: {exc}\n{raw_text}")
        raise AgentOutputError(f"{agent_name} returned invalid JSON output: {exc}") from exc

    _log_call(db_session, agent_name, user_content, raw_text)
    return parsed


def _generate_with_retry(
    client: genai.Client, model: str, user_content: str, system_prompt: str
) -> genai_types.GenerateContentResponse:
    """Calls generate_content, retrying rate-limit/overload errors with the
    delay Gemini itself suggests (falling back to a fixed default)."""
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        try:
            return client.models.generate_content(
                model=model,
                contents=user_content,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                ),
            )
        except genai_errors.APIError as exc:
            if exc.code not in RETRYABLE_STATUS_CODES or attempt >= MAX_RATE_LIMIT_RETRIES:
                raise
            delay = _retry_delay_seconds(exc)
            print(
                f"[llm_client] Gemini returned {exc.code}, retrying in {delay:.0f}s "
                f"(attempt {attempt + 1}/{MAX_RATE_LIMIT_RETRIES})..."
            )
            time.sleep(delay)
    raise AssertionError("unreachable")  # loop always returns or raises


def _retry_delay_seconds(exc: genai_errors.APIError) -> float:
    """Parses the server-suggested retry delay (e.g. RetryInfo.retryDelay =
    "56s") out of a Gemini error, falling back to a fixed default."""
    try:
        details = exc.details.get("error", {}).get("details", [])
        for item in details:
            if str(item.get("@type", "")).endswith("RetryInfo"):
                raw = str(item.get("retryDelay", ""))
                if raw.endswith("s"):
                    return min(float(raw[:-1]) + 2, MAX_RETRY_DELAY_SECONDS)
    except (AttributeError, TypeError, ValueError):
        pass
    return DEFAULT_RETRY_DELAY_SECONDS


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
