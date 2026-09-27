"""llm_client's retry-on-rate-limit behavior: transient 429/503 errors from
Gemini shouldn't crash a whole pipeline run, since Coordinator only commits
requirements at the very end.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.genai import errors as genai_errors
from pydantic import BaseModel

from src.agents.llm_client import (
    AgentOutputError,
    RateLimitedError,
    call_agent_json,
    set_status_sink,
)


class _Echo(BaseModel):
    ok: bool


def _rate_limit_error(code: int = 429) -> genai_errors.APIError:
    error_cls = genai_errors.ClientError if code == 429 else genai_errors.ServerError
    return error_cls(
        code,
        {
            "error": {
                "code": code,
                "message": "rate limited",
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "0s",
                    }
                ],
            }
        },
    )


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("src.agents.llm_client.time.sleep", lambda _seconds: None)


def test_retries_transient_rate_limit_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    client.models.generate_content.side_effect = [
        _rate_limit_error(429),
        SimpleNamespace(text='{"ok": true}'),
    ]

    result = call_agent_json(
        agent_name="test",
        system_prompt="prompt",
        user_content="content",
        output_model=_Echo,
        client=client,
    )

    assert result.ok is True
    assert client.models.generate_content.call_count == 2


def test_retries_server_overload_then_succeeds() -> None:
    client = MagicMock()
    client.models.generate_content.side_effect = [
        _rate_limit_error(503),
        SimpleNamespace(text='{"ok": true}'),
    ]

    result = call_agent_json(
        agent_name="test",
        system_prompt="prompt",
        user_content="content",
        output_model=_Echo,
        client=client,
    )

    assert result.ok is True


def test_gives_up_after_max_retries() -> None:
    client = MagicMock()
    client.models.generate_content.side_effect = _rate_limit_error(429)

    with pytest.raises(RateLimitedError):
        call_agent_json(
            agent_name="test",
            system_prompt="prompt",
            user_content="content",
            output_model=_Echo,
            client=client,
        )


def test_non_retryable_error_raises_immediately() -> None:
    client = MagicMock()
    client.models.generate_content.side_effect = genai_errors.ClientError(
        400, {"error": {"code": 400, "message": "bad request", "status": "INVALID_ARGUMENT"}}
    )

    with pytest.raises(genai_errors.ClientError):
        call_agent_json(
            agent_name="test",
            system_prompt="prompt",
            user_content="content",
            output_model=_Echo,
            client=client,
        )

    assert client.models.generate_content.call_count == 1


def test_exponential_backoff_grows_without_server_hint() -> None:
    """A 503 with no RetryInfo (the common case) should back off
    exponentially by attempt number, not use a flat delay every time."""
    from src.agents.llm_client import _retry_delay_seconds

    exc = genai_errors.ServerError(
        503, {"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}}
    )

    delays = [_retry_delay_seconds(exc, attempt) for attempt in range(4)]

    assert delays == sorted(delays)
    assert delays[0] < delays[-1]


def test_retry_delay_respects_server_suggested_value() -> None:
    from src.agents.llm_client import _retry_delay_seconds

    exc = _rate_limit_error(429)  # retryDelay: "0s" in the fixture

    # Server said 0s (+2s buffer) — should not fall through to the much
    # larger exponential-backoff default.
    assert _retry_delay_seconds(exc, attempt=5) == pytest.approx(2.0)


def test_retry_backoff_reports_to_the_status_sink() -> None:
    """The UI needs to know *why* a call is taking a while (rate-limit
    pacing, a retry) instead of a silent wait that looks like a hang."""
    client = MagicMock()
    client.models.generate_content.side_effect = [
        _rate_limit_error(429),
        SimpleNamespace(text='{"ok": true}'),
    ]
    messages: list[str] = []
    set_status_sink(messages.append)
    try:
        call_agent_json(
            agent_name="test",
            system_prompt="prompt",
            user_content="content",
            output_model=_Echo,
            client=client,
        )
    finally:
        set_status_sink(None)

    assert any("429" in m and "retrying" in m for m in messages)


def test_malformed_json_still_raises_agent_output_error() -> None:
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text="not json")

    with pytest.raises(AgentOutputError):
        call_agent_json(
            agent_name="test",
            system_prompt="prompt",
            user_content="content",
            output_model=_Echo,
            client=client,
        )
