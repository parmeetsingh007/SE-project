"""Conflict-detection agent: JSON parsing/validation, Gemini call mocked out."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents.conflict_detection import ConflictDetectionAgent
from src.models.requirement import Requirement


def _fake_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text=response_text)
    return client


def test_conflict_detection_agent_finds_contradiction(monkeypatch: pytest.MonkeyPatch) -> None:
    req_a = Requirement(
        statement="The system shall lock the account after 3 failed attempts.",
        source_stakeholder="Marcus Webb (Security Lead)",
    )
    req_b = Requirement(
        statement="The system shall never lock the account regardless of failed "
        "attempts.",
        source_stakeholder="Marcus Webb (Security Lead)",
    )
    valid_json = json.dumps(
        {
            "conflicts": [
                {
                    "requirement_id_a": req_a.id,
                    "requirement_id_b": req_b.id,
                    "conflict_type": "contradiction",
                    "explanation": "One mandates lockout, the other forbids it.",
                    "confidence": 0.9,
                }
            ]
        }
    )
    client = _fake_client(valid_json)
    monkeypatch.setattr("src.agents.llm_client.genai.Client", lambda **k: client)

    conflicts = ConflictDetectionAgent().run([req_a, req_b])

    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "contradiction"
    assert {conflicts[0].requirement_id_a, conflicts[0].requirement_id_b} == {
        req_a.id,
        req_b.id,
    }


def test_conflict_detection_agent_skips_single_requirement() -> None:
    req = Requirement(
        statement="The system shall lock the account after 3 failed attempts.",
        source_stakeholder="Marcus Webb (Security Lead)",
    )

    conflicts = ConflictDetectionAgent().run([req])

    assert conflicts == []
