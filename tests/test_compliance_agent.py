"""Compliance agent: real Chroma retrieval + mocked Gemini call."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents.compliance import ComplianceAgent
from src.knowledge_base.ingest import ingest_regulations
from src.knowledge_base.retriever import RegulationRetriever
from src.models.requirement import Requirement


@pytest.fixture
def retriever(tmp_path) -> RegulationRetriever:
    r = RegulationRetriever(persist_dir=str(tmp_path / "chroma_test"))
    ingest_regulations(retriever=r)
    return r


def _fake_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text=response_text)
    return client


def test_compliance_agent_proposes_grounded_citation(
    monkeypatch: pytest.MonkeyPatch, retriever: RegulationRetriever
) -> None:
    requirement = Requirement(
        statement="The system shall trigger step-up authentication automatically "
        "when a payment receives a high risk score.",
        source_stakeholder="Marcus Webb (Security Lead)",
    )
    valid_json = json.dumps(
        {
            "proposals": [
                {
                    "regulation": "RBI",
                    "clause_id": "AFA-2",
                    "citation": "RBI AFA-2 - Risk-Based Step-Up Authentication",
                    "confidence": 0.85,
                    "rationale": "The requirement matches automatic risk-based "
                    "step-up authentication described in this clause.",
                }
            ]
        }
    )
    client = _fake_client(valid_json)
    monkeypatch.setattr("src.agents.llm_client.genai.Client", lambda **k: client)

    proposals = ComplianceAgent(retriever=retriever).run(requirement)

    assert len(proposals) == 1
    assert proposals[0].regulation == "RBI"
    assert proposals[0].clause_id == "AFA-2"
    assert 0.0 <= proposals[0].confidence <= 1.0


def test_compliance_agent_empty_kb_returns_no_proposals(tmp_path) -> None:
    empty_retriever = RegulationRetriever(persist_dir=str(tmp_path / "chroma_empty"))
    requirement = Requirement(
        statement="The system shall log all authentication attempts.",
        source_stakeholder="Marcus Webb (Security Lead)",
    )

    proposals = ComplianceAgent(retriever=empty_retriever).run(requirement)

    assert proposals == []
