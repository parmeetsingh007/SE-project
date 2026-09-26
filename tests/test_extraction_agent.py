"""Extraction agent: JSON parsing/validation, with the Gemini call mocked out."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents.extraction import ExtractionAgent
from src.agents.llm_client import AgentOutputError


def _fake_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text=response_text)
    return client


def test_extraction_agent_parses_valid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    valid_json = json.dumps(
        {
            "requirements": [
                {
                    "statement": "The system shall require biometric step-up "
                    "authentication for app payments above the risk threshold.",
                    "source_stakeholder": "Marcus Webb (Security Lead)",
                    "source_excerpt": "For app users we'd want biometric — "
                    "fingerprint or face, whatever the phone supports.",
                    "business_justification": "Reduce fraud on high-risk payments.",
                    "assumptions": ["Phone supports biometric hardware."],
                    "open_questions": ["What is the web fallback method?"],
                }
            ]
        }
    )
    client = _fake_client(valid_json)
    monkeypatch.setattr("src.agents.llm_client.genai.Client", lambda **k: client)

    candidates = ExtractionAgent().run("some transcript text")

    assert len(candidates) == 1
    assert candidates[0].source_stakeholder == "Marcus Webb (Security Lead)"
    assert candidates[0].open_questions == ["What is the web fallback method?"]


def test_extraction_agent_raises_on_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _fake_client("not valid json at all")
    monkeypatch.setattr("src.agents.llm_client.genai.Client", lambda **k: client)

    with pytest.raises(AgentOutputError):
        ExtractionAgent().run("some transcript text")
