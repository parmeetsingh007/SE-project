"""Classification agent: JSON parsing/validation, with the Gemini call mocked out."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents.classification import ClassificationAgent
from src.models.requirement import Requirement


def _fake_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text=response_text)
    return client


def test_classification_agent_maps_categories_by_id(monkeypatch: pytest.MonkeyPatch) -> None:
    requirement = Requirement(
        statement="The system shall require step-up authentication above the "
        "risk threshold.",
        source_stakeholder="Marcus Webb (Security Lead)",
    )
    valid_json = json.dumps(
        {"classifications": [{"id": requirement.id, "category": ["security", "compliance"]}]}
    )
    client = _fake_client(valid_json)
    monkeypatch.setattr("src.agents.llm_client.genai.Client", lambda **k: client)

    categories_by_id = ClassificationAgent().run([requirement])

    assert categories_by_id[requirement.id] == ["security", "compliance"]
