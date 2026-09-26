"""SDLC-selection agent: JSON parsing/validation, with the Gemini call mocked out."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents.sdlc_selection import SDLCSelectionAgent, summarize_requirements
from src.models.requirement import ApprovalStatus, Requirement, RequirementCategory, RiskLevel


def _fake_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text=response_text)
    return client


def _sample_requirements() -> list[Requirement]:
    return [
        Requirement(
            statement="The system shall trigger step-up authentication above the "
            "risk threshold.",
            source_stakeholder="Marcus Webb (Security Lead)",
            category=[RequirementCategory.SECURITY, RequirementCategory.COMPLIANCE],
            applicable_regulations=["RBI AFA-2 - Risk-Based Step-Up Authentication"],
            risk_level=RiskLevel.HIGH,
            approval_status=ApprovalStatus.NEEDS_REVISION,
        ),
        Requirement(
            statement="The system shall log fraud events.",
            source_stakeholder="Marcus Webb (Security Lead)",
            category=[RequirementCategory.COMPLIANCE],
            risk_level=RiskLevel.MEDIUM,
        ),
    ]


def test_summarize_requirements_computes_deterministic_characteristics() -> None:
    characteristics = summarize_requirements(_sample_requirements())

    assert characteristics["total_requirements"] == 2
    assert characteristics["num_needing_revision"] == 1
    assert characteristics["num_high_risk"] == 1
    assert characteristics["num_citing_regulations"] == 1
    assert characteristics["category_counts"]["compliance"] == 2


def test_sdlc_selection_agent_returns_ranked_recommendations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid_json = json.dumps(
        {
            "recommendations": [
                {
                    "model": "V-Model",
                    "confidence": 0.8,
                    "rationale": "High compliance density favors formal sign-off gates.",
                },
                {
                    "model": "Agile (Scrum)",
                    "confidence": 0.5,
                    "rationale": "Some requirements still need revision.",
                },
            ]
        }
    )
    client = _fake_client(valid_json)
    monkeypatch.setattr("src.agents.llm_client.genai.Client", lambda **k: client)

    recommendations = SDLCSelectionAgent().run(_sample_requirements())

    assert len(recommendations) == 2
    assert recommendations[0].model == "V-Model"
    assert recommendations[0].confidence > recommendations[1].confidence
