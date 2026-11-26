"""Deterministic stand-ins for the LLM agents so pipeline behaviour can be tested offline."""

from __future__ import annotations

from src.agents.compliance import ComplianceResult
from src.agents.extraction import Candidate, ExtractionResult
from src.agents.sdlc import SdlcNarrative
from src.agents.security_privacy import DerivedItem
from src.models.requirement import Category, Question, RegulationMapping, RiskItem, Threat


class Calls:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def hit(self, name: str) -> None:
        self.counts[name] = self.counts.get(name, 0) + 1

    def __getitem__(self, name: str) -> int:
        return self.counts.get(name, 0)


class FakeExtraction:
    def __init__(self, calls: Calls, candidates: list[Candidate]) -> None:
        self.calls, self.candidates = calls, candidates

    def run(self, title, text, role="", db_session=None):
        self.calls.hit("extraction")
        return ExtractionResult(candidates=[c.model_copy() for c in self.candidates], dropped_ungrounded=1)


class FakeClassification:
    def __init__(self, calls: Calls) -> None:
        self.calls = calls

    def run(self, requirements, db_session=None):
        self.calls.hit("classification")
        for r in requirements:
            text = r.statement.lower()
            r.categories = [Category.SECURITY] if "encrypt" in text else [Category.FUNCTIONAL, Category.REGULATORY]
            r.primary_category = r.categories[0]


class FakeQuality:
    """Flags any statement containing 'fast' as vague and asks one question about it."""

    def __init__(self, calls: Calls) -> None:
        self.calls = calls

    def run(self, requirements, db_session=None):
        self.calls.hit("quality")
        questions = []
        for r in requirements:
            vague = "fast" in r.statement.lower() or "quickly" in r.statement.lower()
            r.is_weak = vague
            r.quality_flags = []
            if vague:
                questions.append(Question(requirement_id=r.id, question="How fast, in seconds?", why="No measurable target", options=["5 s", "60 s"]))
        return questions


class FakeConflicts:
    def __init__(self, calls: Calls) -> None:
        self.calls = calls

    def run(self, requirements, db_session=None):
        self.calls.hit("conflicts")
        return []


class FakeCompliance:
    def __init__(self, calls: Calls, hallucinated: int = 0) -> None:
        self.calls, self.hallucinated = calls, hallucinated

    def run(self, requirements, jurisdictions, db_session=None, top_k=5):
        self.calls.hit("compliance")
        for r in requirements:
            if "identity" in r.statement.lower():
                r.regulations = [
                    RegulationMapping(regulation="RBI KYC Master Direction", clause_id="RBI-KYC-CIP", citation="RBI KYC Master Direction: Customer identification and verification",
                                      jurisdiction="IN", confidence=0.9, rationale="Identity verification at onboarding.")
                ]
        return ComplianceResult(hallucinated_citations=self.hallucinated, mapped=1)


class FakeSecurity:
    def __init__(self, calls: Calls) -> None:
        self.calls = calls

    def run(self, requirements, db_session=None):
        self.calls.hit("security")
        return (
            [DerivedItem(statement="The system shall encrypt stored identity documents at rest.", rationale="Documents are stored.", related_ref=requirements[0].ref)],
            [Threat(stride="Spoofing", threat="Forged identity documents", asset="Identity documents", mitigated_by=[requirements[0].id])],
        )


class FakeCriteria:
    def __init__(self, calls: Calls) -> None:
        self.calls = calls

    def run(self, requirements, clarifications=None, db_session=None):
        self.calls.hit("criteria")
        for r in requirements:
            note = " ".join(a["answer"] for a in (clarifications or {}).get(r.id, []))
            r.acceptance_criteria = [f"Given the requirement, when tested, then it passes. {note}".strip()]


class FakeRisk:
    def __init__(self, calls: Calls, fail_first: bool = False) -> None:
        self.calls, self.fail_first = calls, fail_first

    def run(self, requirements, db_session=None):
        self.calls.hit("risk")
        if self.fail_first and self.calls["risk"] == 1:
            from src.agents.llm_client import RateLimitedError

            raise RateLimitedError("quota exhausted")
        items = []
        for r in requirements:
            item = RiskItem(requirement_id=r.id, risk=f"Risk for {r.ref}", likelihood=4 if r.is_weak else 2, impact=4, mitigation="Mitigate", confidence=0.7)
            r.risk_level, r.confidence_score = item.level, 0.7
            r.risk_scores = {"likelihood": item.likelihood, "impact": item.impact, "score": item.score}
            items.append(item)
        return items


class FakeRefinement:
    def __init__(self, calls: Calls) -> None:
        self.calls = calls

    def run(self, requirements, answers, db_session=None):
        self.calls.hit("refinement")
        changed = []
        for r in requirements:
            if answers.get(r.id):
                r.statement = r.statement.replace("fast", "within 5 seconds")
                changed.append(r.id)
        return changed


class FakeAdvisor:
    def __init__(self, calls: Calls) -> None:
        self.calls = calls

    def run(self, factors, ranking, counts, db_session=None):
        self.calls.hit("advisor")
        return SdlcNarrative(explanation=f"{ranking[0].model} fits.", tradeoffs=["t"], would_change_if=["c"])


class FakeConflictsFirstRunOnly:
    """Reports one conflict between the first two requirements the first time, then nothing
    (simulating a non-deterministic model that fails to repeat a finding)."""

    def __init__(self, calls: Calls) -> None:
        self.calls = calls

    def run(self, requirements, db_session=None):
        from src.models.requirement import Conflict

        self.calls.hit("conflicts")
        if self.calls["conflicts"] > 1 or len(requirements) < 2:
            return []
        stated = [r for r in requirements if r.origin == "stated"][:2]
        return [Conflict(requirement_ids=[r.id for r in stated], kind="contradiction", explanation="They disagree.", confidence=0.8)]
