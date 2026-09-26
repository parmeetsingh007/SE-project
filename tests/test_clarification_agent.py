"""Clarification agent: JSON parsing/validation, with the Gemini call mocked out."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents.clarification import ClarificationAgent
from src.models.requirement import Requirement


def _fake_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text=response_text)
    return client


def test_clarification_agent_flags_incomplete_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requirement = Requirement(
        statement="The system shall provide a fallback authentication method for "
        "web users.",
        source_stakeholder="Marcus Webb (Security Lead)",
    )
    valid_json = json.dumps(
        {
            "is_complete": False,
            "issues": [
                {
                    "issue": "The fallback method for web isn't specified.",
                    "follow_up_question": "What authentication method should web "
                    "users see when step-up auth triggers?",
                }
            ],
        }
    )
    client = _fake_client(valid_json)
    monkeypatch.setattr("src.agents.llm_client.genai.Client", lambda **k: client)

    result = ClarificationAgent().run(
        requirement, open_questions=["What is the web fallback method?"]
    )

    assert result.is_complete is False
    assert len(result.issues) == 1
    assert "web" in result.issues[0].follow_up_question.lower()


def test_clarification_agent_marks_complete_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requirement = Requirement(
        statement="The system shall lock the customer's account after 3 "
        "consecutive failed step-up authentication attempts.",
        source_stakeholder="Marcus Webb (Security Lead)",
    )
    valid_json = json.dumps({"is_complete": True, "issues": []})
    client = _fake_client(valid_json)
    monkeypatch.setattr("src.agents.llm_client.genai.Client", lambda **k: client)

    result = ClarificationAgent().run(requirement)

    assert result.is_complete is True
    assert result.issues == []
