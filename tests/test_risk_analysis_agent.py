"""Risk-analysis agent: JSON parsing/validation, with the Gemini call mocked out."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents.risk_analysis import RiskAnalysisAgent
from src.models.requirement import Requirement, RequirementCategory


def _fake_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text=response_text)
    return client


def test_risk_analysis_agent_scores_requirement(monkeypatch: pytest.MonkeyPatch) -> None:
    requirement = Requirement(
        statement="The system shall trigger step-up authentication automatically "
        "above the risk threshold.",
        source_stakeholder="Marcus Webb (Security Lead)",
        category=[RequirementCategory.SECURITY, RequirementCategory.COMPLIANCE],
    )
    valid_json = json.dumps(
        {
            "business_risk": 0.6,
            "technical_risk": 0.4,
            "compliance_risk": 0.7,
            "overall_risk_level": "high",
            "confidence": 0.75,
            "rationale": "High compliance exposure given RBI/PCI-DSS overlap.",
        }
    )
    client = _fake_client(valid_json)
    monkeypatch.setattr("src.agents.llm_client.genai.Client", lambda **k: client)

    scores = RiskAnalysisAgent().run(requirement)

    assert scores.overall_risk_level.value == "high"
    assert 0.0 <= scores.confidence <= 1.0
    assert scores.business_risk == pytest.approx(0.6)
