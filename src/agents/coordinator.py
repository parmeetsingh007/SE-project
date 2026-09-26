"""Orchestrates the pipeline: passes shared context between agents.

Not itself an LLM call — it owns the sequencing and hands each agent exactly
what it needs, then persists the result. Milestone 2 wired extraction and
classification; Milestone 3 adds compliance mapping. Later milestones add
clarification, conflict detection, security/privacy, and risk analysis to
this same sequence.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.agents.classification import ClassificationAgent
from src.agents.compliance import ComplianceAgent
from src.agents.extraction import ExtractionAgent
from src.models.db import RequirementORM
from src.models.requirement import Requirement


class Coordinator:
    """Runs a transcript through extraction -> classification -> compliance ->
    persistence."""

    def __init__(
        self,
        extraction_agent: ExtractionAgent | None = None,
        classification_agent: ClassificationAgent | None = None,
        compliance_agent: ComplianceAgent | None = None,
    ) -> None:
        self.extraction_agent = extraction_agent or ExtractionAgent()
        self.classification_agent = classification_agent or ClassificationAgent()
        self.compliance_agent = compliance_agent or ComplianceAgent()

    def run(self, transcript_text: str, db_session: Session) -> list[Requirement]:
        """Extracts, classifies, compliance-maps, and persists a transcript's
        requirements."""
        candidates = self.extraction_agent.run(transcript_text, db_session=db_session)

        requirements = [
            Requirement(
                statement=candidate.statement,
                source_stakeholder=candidate.source_stakeholder,
                business_justification=candidate.business_justification,
                assumptions=candidate.assumptions,
            )
            for candidate in candidates
        ]

        categories_by_id = self.classification_agent.run(requirements, db_session=db_session)
        for requirement in requirements:
            requirement.category = categories_by_id.get(requirement.id, [])

        for requirement in requirements:
            proposals = self.compliance_agent.run(requirement, db_session=db_session)
            requirement.applicable_regulations = [p.citation for p in proposals]

        for requirement in requirements:
            db_session.add(RequirementORM(**requirement.model_dump(mode="json")))
        db_session.commit()

        return requirements
