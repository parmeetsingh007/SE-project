"""Documentation agent: mocked Gemini calls, real file rendering to a tmp dir."""

import csv
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents.documentation import DocumentationAgent
from src.agents.sdlc_selection import SDLCRecommendation
from src.models.requirement import Requirement, RequirementCategory


def _fake_client(summary_json: str, stories_json: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.side_effect = [
        SimpleNamespace(text=summary_json),
        SimpleNamespace(text=stories_json),
    ]
    return client


def test_documentation_agent_writes_all_three_outputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    requirement = Requirement(
        statement="The system shall trigger step-up authentication above the "
        "risk threshold.",
        source_stakeholder="Marcus Webb (Security Lead)",
        category=[RequirementCategory.SECURITY],
        applicable_regulations=["RBI AFA-2 - Risk-Based Step-Up Authentication"],
    )
    summary_json = json.dumps(
        {"summary": "This project covers one high-risk, RBI-cited requirement."}
    )
    stories_json = json.dumps(
        {
            "stories": [
                {
                    "requirement_id": requirement.id,
                    "as_a": "customer making a high-risk payment",
                    "i_want": "to be prompted for step-up authentication",
                    "so_that": "my transaction is protected from fraud",
                }
            ]
        }
    )
    client = _fake_client(summary_json, stories_json)
    monkeypatch.setattr("src.agents.llm_client.genai.Client", lambda **k: client)

    recommendations = [
        SDLCRecommendation(model="V-Model", confidence=0.8, rationale="Formal gates.")
    ]
    agent = DocumentationAgent(output_dir=str(tmp_path / "generated"))
    output = agent.run([requirement], recommendations)

    srs_text = open(output.srs_path, encoding="utf-8").read()
    assert "Executive Summary" in srs_text
    assert "V-Model" in srs_text
    assert requirement.id[:8] in srs_text

    stories_text = open(output.user_stories_path, encoding="utf-8").read()
    assert "As a customer making a high-risk payment" in stories_text

    with open(output.traceability_csv_path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["requirement_id"] == requirement.id
    assert rows[0]["applicable_regulations"] == "RBI AFA-2 - Risk-Based Step-Up Authentication"
