"""The anti-hallucination guards: ungrounded quotes and invented citations are dropped."""

from unittest.mock import patch

from src.agents.compliance import ComplianceAgent, MappingItem, MappingOutput, assess_controls
from src.agents.extraction import Candidate, ExtractionAgent, ExtractionOutput, find_grounding
from src.knowledge_base.kb import KnowledgeBase
from src.models.requirement import Category, RegulationMapping, Requirement

SOURCE = "Priya: We want people to open an account on their phone. It must feel easy and secure."


def test_grounding_accepts_verbatim_and_near_verbatim_quotes() -> None:
    assert find_grounding(SOURCE, "open an account on their phone") is not None
    assert find_grounding(SOURCE, "We want people to open an account on their phone") is not None
    near = find_grounding(SOURCE, "It must feel easy and secure")  # punctuation differs
    assert near is not None


def test_grounding_rejects_a_quote_that_is_not_in_the_source() -> None:
    assert find_grounding(SOURCE, "The system must support biometric login with a retina scan") is None
    assert find_grounding(SOURCE, "") is None


def test_extraction_drops_and_counts_ungrounded_requirements() -> None:
    output = ExtractionOutput(requirements=[
        Candidate(statement="The system shall support mobile onboarding.", source_excerpt="open an account on their phone"),
        Candidate(statement="The system shall use retina scans.", source_excerpt="retina scan login was approved by the board"),
    ])
    with patch("src.agents.extraction.call_agent_json", return_value=output):
        result = ExtractionAgent().run("Interview", SOURCE)
    assert [c.statement for c in result.candidates] == ["The system shall support mobile onboarding."]
    assert result.dropped_ungrounded == 1


def test_compliance_only_keeps_clauses_the_retriever_offered() -> None:
    kb = KnowledgeBase(backend="lexical")
    requirement = Requirement(statement="The system shall retain customer identity records for five years.", ref="KYC-DATA-001")
    offered = [c.id for c in kb.retrieve(requirement.statement, ["IN"], 5)]
    good = offered[0]
    not_offered = next(cid for cid in kb.clauses if cid not in offered)
    output = MappingOutput(mappings=[
        MappingItem(ref="KYC-DATA-001", clause_id=good, confidence=0.9, rationale="Retention."),
        MappingItem(ref="KYC-DATA-001", clause_id=not_offered, confidence=0.9, rationale="Real clause but never retrieved."),
        MappingItem(ref="KYC-DATA-001", clause_id="MADE-UP-123", confidence=0.9, rationale="Invented."),
    ])
    with patch("src.agents.compliance.call_agent_json", return_value=output):
        result = ComplianceAgent(kb).run([requirement], ["IN"])

    assert [m.clause_id for m in requirement.regulations] == [good]
    assert result.hallucinated_citations == 2


def test_high_impact_or_low_confidence_mappings_are_flagged_for_legal_review() -> None:
    kb = KnowledgeBase(backend="lexical")
    requirement = Requirement(statement="The system shall approve politically exposed persons only with senior approval.", ref="KYC-REG-001")
    offered = [c.id for c in kb.retrieve(requirement.statement, ["GLOBAL"], 5)]
    assert "FATF-R12" in offered
    output = MappingOutput(mappings=[MappingItem(ref="KYC-REG-001", clause_id="FATF-R12", confidence=0.95, rationale="PEP.")])
    with patch("src.agents.compliance.call_agent_json", return_value=output):
        ComplianceAgent(kb).run([requirement], ["GLOBAL"])
    assert requirement.regulations[0].needs_legal_review is True  # high-impact clause, despite high confidence


def _req(statement: str, *clause_ids: str, origin: str = "stated") -> Requirement:
    return Requirement(
        statement=statement, ref="R", origin=origin, categories=[Category.FUNCTIONAL],
        regulations=[RegulationMapping(regulation="x", clause_id=c, citation=c, confidence=0.9) for c in clause_ids],
    )


def test_control_is_covered_partial_or_gap() -> None:
    kb = KnowledgeBase(backend="lexical")
    cov = {c.control_id: c for c in assess_controls(
        [_req("The system shall retain identity records for five years.", "RBI-KYC-RETAIN"),
         _req("The system shall screen customers against sanctions lists."),
         ], ["IN"], kb)}
    assert cov["C-RETENTION"].status == "covered"      # cites the regulation and states its substance
    assert cov["C-SANCTIONS"].status == "partial"      # states the substance but cites nothing
    assert cov["C-STR"].status == "gap"                # nothing mentions it


def test_applicability_uses_whole_words_and_ignores_derived_text() -> None:
    kb = KnowledgeBase(backend="lexical")
    # "approved" contains "app"; it must not make the mobile/liveness control apply
    stated = [_req("The design must be approved by the committee.")]
    assert {c.control_id: c.status for c in assess_controls(stated, ["IN"], kb)}["C-LIVENESS"] == "not_applicable"

    # a system-derived requirement mentioning "mobile" must not switch the control on either
    derived = stated + [_req("The system shall protect mobile sessions.", origin="derived")]
    assert {c.control_id: c.status for c in assess_controls(derived, ["IN"], kb)}["C-LIVENESS"] == "not_applicable"

    # but when the stakeholders themselves talk about selfies, it applies
    selfie = [_req("The customer shall take a selfie in the app.")]
    assert {c.control_id: c.status for c in assess_controls(selfie, ["IN"], kb)}["C-LIVENESS"] != "not_applicable"


def test_controls_are_filtered_by_jurisdiction() -> None:
    kb = KnowledgeBase(backend="lexical")
    india = {c.control_id for c in assess_controls([], ["IN"], kb)}
    us = {c.control_id for c in assess_controls([], ["US"], kb)}
    assert "C-CKYC" in india and "C-CKYC" not in us   # the Indian central KYC registry only applies in India
