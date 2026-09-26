"""Security/privacy agent: JSON parsing/validation, Gemini call mocked out."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents.security_privacy import SecurityPrivacyAgent
from src.models.requirement import Requirement


def _fake_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text=response_text)
    return client


def test_security_privacy_agent_flags_implicit_encryption_need(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requirement = Requirement(
        statement="The system shall log the risk score for every declined "
        "transaction as a potential fraud event.",
        source_stakeholder="Marcus Webb (Security Lead)",
    )
    valid_json = json.dumps(
        {
            "flags": [
                {
                    "concern": "Fraud event logs may contain sensitive "
                    "transaction data that needs protection at rest.",
                    "recommended_requirement": "The system shall encrypt fraud "
                    "event logs at rest and restrict access to authorized "
                    "fraud-ops personnel.",
                    "rationale": "Logging risk/fraud events implies storing "
                    "data that must be protected per PCI-DSS.",
                }
            ]
        }
    )
    client = _fake_client(valid_json)
    monkeypatch.setattr("src.agents.llm_client.genai.Client", lambda **k: client)

    flags = SecurityPrivacyAgent().run(requirement)

    assert len(flags) == 1
    assert "encrypt" in flags[0].recommended_requirement.lower()


def test_security_privacy_agent_returns_empty_when_nothing_implied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requirement = Requirement(
        statement="The system shall display the current date in the footer.",
        source_stakeholder="Marcus Webb (Security Lead)",
    )
    client = _fake_client(json.dumps({"flags": []}))
    monkeypatch.setattr("src.agents.llm_client.genai.Client", lambda **k: client)

    flags = SecurityPrivacyAgent().run(requirement)

    assert flags == []
