"""Acceptance-criteria agent: JSON parsing/validation, Gemini call mocked out."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents.acceptance_criteria import AcceptanceCriteriaAgent
from src.models.requirement import Requirement, RequirementCategory


def _fake_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text=response_text)
    return client


def test_acceptance_criteria_agent_returns_criteria(monkeypatch: pytest.MonkeyPatch) -> None:
    requirement = Requirement(
        statement="The system shall lock the customer's account after 3 "
        "consecutive failed step-up authentication attempts.",
        source_stakeholder="Marcus Webb (Security Lead)",
        category=[RequirementCategory.SECURITY],
    )
    valid_json = json.dumps(
        {
            "acceptance_criteria": [
                "Given 3 consecutive failed step-up attempts, when the third "
                "failure is recorded, then the account is locked.",
                "Given a locked account, when the customer attempts another "
                "payment, then the transaction is declined without a fourth "
                "authentication prompt.",
            ]
        }
    )
    client = _fake_client(valid_json)
    monkeypatch.setattr("src.agents.llm_client.genai.Client", lambda **k: client)

    criteria = AcceptanceCriteriaAgent().run(requirement)

    assert len(criteria) == 2
    assert "locked" in criteria[0]
