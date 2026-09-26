"""Stakeholder-interaction agent: JSON parsing/validation, Gemini call mocked out."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents.stakeholder_interaction import StakeholderInteractionAgent


def _fake_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text=response_text)
    return client


def test_stakeholder_interaction_agent_flags_vague_statement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid_json = json.dumps(
        {
            "follow_ups": [
                {
                    "original_statement": "I don't have a hard number handed "
                    "down from anywhere, but personally I'd say under two "
                    "seconds.",
                    "follow_up_question": "Is the two-second figure an official "
                    "SLA, or does it still need sign-off?",
                }
            ]
        }
    )
    client = _fake_client(valid_json)
    monkeypatch.setattr("src.agents.llm_client.genai.Client", lambda **k: client)

    follow_ups = StakeholderInteractionAgent().run("some raw transcript text")

    assert len(follow_ups) == 1
    assert "sign-off" in follow_ups[0].follow_up_question


def test_stakeholder_interaction_agent_returns_empty_when_nothing_vague(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _fake_client(json.dumps({"follow_ups": []}))
    monkeypatch.setattr("src.agents.llm_client.genai.Client", lambda **k: client)

    follow_ups = StakeholderInteractionAgent().run("a fully precise transcript")

    assert follow_ups == []
