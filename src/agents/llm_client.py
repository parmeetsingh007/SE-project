"""Shared helper for calling the Gemini API with validated JSON-only output.

Every agent asks Gemini for JSON-only output and validates it against a Pydantic
model before returning. This module centralizes that call + parse + audit-log
sequence so individual agent files stay focused on their own prompt and schema.

Every call also goes through one process-wide rate limiter and retry policy,
since the free tier's 15 requests/minute limit is shared across the whole
app, not per-agent.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from collections.abc import Callable
from contextvars import ContextVar
from typing import TypeVar

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from src.models.db import AuditLogORM

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

# The pipeline makes ~5-6 calls per requirement now, which for a real
# multi-requirement transcript easily exceeds the free tier's 15 req/min on
# its own. Two layers guard against that: a proactive limiter that paces
# calls so the app itself never bursts past the quota, and reactive retry
# with backoff for the 429/503s that still happen (another process sharing
# the same key, a slightly-off window boundary, etc).
GEMINI_RPM_LIMIT = int(os.environ.get("GEMINI_RPM_LIMIT", "15"))
RATE_LIMIT_WINDOW_SECONDS = 60.0

MAX_RATE_LIMIT_RETRIES = 6
DEFAULT_RETRY_DELAY_SECONDS = 20.0
MAX_RETRY_DELAY_SECONDS = 65.0
RETRYABLE_STATUS_CODES = {429, 503}

# Every agent's job here is "follow the instructions precisely" (extract only
# what's grounded, flag ambiguity, don't invent) — none of them want creative
# variety. Left unset, Gemini's default temperature (~1.0) is tuned for the
# opposite of that, and produces real run-to-run inconsistency: the same
# prompt on the same transcript can either correctly flag an unresolved
# conflict or silently smooth it into a clean-sounding sentence. A low
# temperature trades away creativity we never wanted for the rule-following
# consistency every agent here actually needs.
DEFAULT_TEMPERATURE = float(os.environ.get("GEMINI_TEMPERATURE", "0.2"))

T = TypeVar("T", bound=BaseModel)

# Lets a UI show *why* a call is taking a while (rate-limit pacing, a 429/503
# retry) instead of a bare, silent spinner — long waits are expected on the
# free tier and easily look like a hang without this. A contextvar rather
# than a parameter threaded through every agent's run() signature, since
# dozens of call sites would otherwise need to change for a purely cosmetic
# concern. Always defaults to None (no UI attached); set via set_status_sink.
_status_sink: ContextVar[Callable[[str], None] | None] = ContextVar(
    "llm_client_status_sink", default=None
)


def set_status_sink(callback: Callable[[str], None] | None) -> None:
    """Registers a callback invoked with a human-readable string whenever
    llm_client is waiting (rate-limit pacing or a retry backoff). Pass None
    to stop reporting. The Streamlit UI uses this to show live progress."""
    _status_sink.set(callback)


def _report_status(message: str) -> None:
    print(f"[llm_client] {message}")
    sink = _status_sink.get()
    if sink is not None:
        sink(message)


class AgentOutputError(ValueError):
    """Raised when an agent's LLM call returns output that fails JSON parsing
    or Pydantic validation. Never swallowed — always logged and re-raised."""


class RateLimitedError(RuntimeError):
    """Raised when Gemini kept returning 429/503 after every retry was
    exhausted. A distinct type so callers (the Streamlit UI) can catch just
    this and show a clear message instead of a raw traceback."""


class _RateLimiter:
    """Sliding-window limiter shared by every Gemini call in the process, so
    pacing is enforced app-wide rather than per-agent."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._call_times: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            self._evict_expired()
            if len(self._call_times) >= self.limit:
                wait_for = self.window_seconds - (time.monotonic() - self._call_times[0])
                if wait_for > 0:
                    _report_status(
                        f"At the {self.limit}/{self.window_seconds:.0f}s Gemini rate "
                        f"limit, pacing — waiting {wait_for:.0f}s before the next call..."
                    )
                    time.sleep(wait_for + 0.05)
                self._evict_expired()
            self._call_times.append(time.monotonic())

    def _evict_expired(self) -> None:
        cutoff = time.monotonic() - self.window_seconds
        while self._call_times and self._call_times[0] < cutoff:
            self._call_times.popleft()


_rate_limiter = _RateLimiter(GEMINI_RPM_LIMIT, RATE_LIMIT_WINDOW_SECONDS)


def call_agent_json(
    *,
    agent_name: str,
    system_prompt: str,
    user_content: str,
    output_model: type[T],
    client: genai.Client | None = None,
    db_session: Session | None = None,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
) -> T:
    """Call Gemini with a JSON-only system prompt and validate the response.

    Logs every call (input, raw output, timestamp) to the audit_log table when
    ``db_session`` is provided. Raises ``AgentOutputError`` on parse/validation
    failure instead of silently dropping the bad output, and ``RateLimitedError``
    if the quota is still exhausted after every retry.
    """
    client = client or genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

    response = _generate_with_retry(client, model, user_content, system_prompt, temperature)
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
    client: genai.Client, model: str, user_content: str, system_prompt: str, temperature: float
) -> genai_types.GenerateContentResponse:
    """Calls generate_content, pacing every attempt through the shared rate
    limiter and retrying rate-limit/overload errors with backoff: the delay
    Gemini itself suggests when given, otherwise growing exponentially."""
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        _rate_limiter.acquire()
        try:
            return client.models.generate_content(
                model=model,
                contents=user_content,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    temperature=temperature,
                ),
            )
        except genai_errors.APIError as exc:
            if exc.code not in RETRYABLE_STATUS_CODES:
                raise
            if attempt >= MAX_RATE_LIMIT_RETRIES:
                raise RateLimitedError(
                    f"Gemini kept returning {exc.code} after {MAX_RATE_LIMIT_RETRIES} "
                    "retries. The free-tier quota is likely still exhausted — wait a "
                    "minute and try again."
                ) from exc
            delay = _retry_delay_seconds(exc, attempt)
            _report_status(
                f"Gemini returned {exc.code}, retrying in {delay:.0f}s "
                f"(attempt {attempt + 1}/{MAX_RATE_LIMIT_RETRIES})..."
            )
            time.sleep(delay)
    raise AssertionError("unreachable")  # loop always returns or raises


def _retry_delay_seconds(exc: genai_errors.APIError, attempt: int) -> float:
    """Uses the server-suggested retry delay (RetryInfo.retryDelay, e.g.
    "56s") when Gemini provides one — that's an exact answer, no need to
    guess. Otherwise backs off exponentially, since a 503 overload rarely
    comes with a RetryInfo hint."""
    try:
        details = exc.details.get("error", {}).get("details", [])
        for item in details:
            if str(item.get("@type", "")).endswith("RetryInfo"):
                raw = str(item.get("retryDelay", ""))
                if raw.endswith("s"):
                    return min(float(raw[:-1]) + 2, MAX_RETRY_DELAY_SECONDS)
    except (AttributeError, TypeError, ValueError):
        pass
    return min(DEFAULT_RETRY_DELAY_SECONDS * (2**attempt), MAX_RETRY_DELAY_SECONDS)


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
