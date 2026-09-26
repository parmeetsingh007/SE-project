"""Classification agent: JSON parsing/validation, with the Anthropic call mocked out."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents.classification import ClassificationAgent
from src.models.requirement import Requirement


def _fake_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=response_text)]
    )
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
    monkeypatch.setattr("src.agents.base.anthropic.Anthropic", lambda: client)

    categories_by_id = ClassificationAgent().run([requirement])

    assert categories_by_id[requirement.id] == ["security", "compliance"]
