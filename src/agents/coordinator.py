"""Orchestrates the pipeline: passes shared context between agents.

Not itself an LLM call — it owns the sequencing and hands each agent exactly
what it needs, then persists the result. Milestone 2 wires extraction and
classification only; later milestones add clarification, conflict detection,
compliance, security/privacy, and risk analysis to this same sequence.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.agents.classification import ClassificationAgent
from src.agents.extraction import ExtractionAgent
from src.models.db import RequirementORM
from src.models.requirement import Requirement


class Coordinator:
    """Runs a transcript through extraction -> classification -> persistence."""

    def __init__(
        self,
        extraction_agent: ExtractionAgent | None = None,
        classification_agent: ClassificationAgent | None = None,
    ) -> None:
        self.extraction_agent = extraction_agent or ExtractionAgent()
        self.classification_agent = classification_agent or ClassificationAgent()

    def run(self, transcript_text: str, db_session: Session) -> list[Requirement]:
        """Extracts, classifies, and persists requirements from one transcript."""
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
            db_session.add(RequirementORM(**requirement.model_dump(mode="json")))
        db_session.commit()

        return requirements
