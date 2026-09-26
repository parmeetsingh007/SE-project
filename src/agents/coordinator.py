"""Orchestrates the pipeline: passes shared context between agents.

Not itself an LLM call — it owns the sequencing and hands each agent exactly
what it needs, then persists the result. Milestone 2 wired extraction and
classification; Milestone 3 added compliance mapping; Milestone 4 added
clarification, conflict detection, security/privacy, and risk analysis;
validation runs last, right before persistence; stakeholder_interaction runs
first, as a pre-processing pass over the raw transcript before extraction.

Findings that don't have a dedicated field in the fixed Requirement schema
(clarification issues, security/privacy flags, conflicts, validation issues,
stakeholder follow-ups) are logged to the audit table via each agent's own
call, and also kept on the coordinator instance after run() for the pipeline
CLI to display.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.agents.classification import ClassificationAgent
from src.agents.clarification import ClarificationAgent, ClarificationIssue
from src.agents.compliance import ComplianceAgent
from src.agents.conflict_detection import ConflictDetectionAgent, ConflictFinding
from src.agents.extraction import ExtractionAgent
from src.agents.risk_analysis import RiskAnalysisAgent
from src.agents.security_privacy import SecurityPrivacyAgent, SecurityPrivacyFlag
from src.agents.stakeholder_interaction import FollowUpItem, StakeholderInteractionAgent
from src.agents.validation import ValidationAgent, ValidationIssue
from src.models.db import RequirementORM
from src.models.requirement import ApprovalStatus, Requirement


class Coordinator:
    """Runs a transcript through the full agent sequence and persists the
    result."""

    def __init__(
        self,
        stakeholder_interaction_agent: StakeholderInteractionAgent | None = None,
        extraction_agent: ExtractionAgent | None = None,
        classification_agent: ClassificationAgent | None = None,
        compliance_agent: ComplianceAgent | None = None,
        clarification_agent: ClarificationAgent | None = None,
        security_privacy_agent: SecurityPrivacyAgent | None = None,
        risk_analysis_agent: RiskAnalysisAgent | None = None,
        conflict_detection_agent: ConflictDetectionAgent | None = None,
        validation_agent: ValidationAgent | None = None,
    ) -> None:
        self.stakeholder_interaction_agent = (
            stakeholder_interaction_agent or StakeholderInteractionAgent()
        )
        self.extraction_agent = extraction_agent or ExtractionAgent()
        self.classification_agent = classification_agent or ClassificationAgent()
        self.compliance_agent = compliance_agent or ComplianceAgent()
        self.clarification_agent = clarification_agent or ClarificationAgent()
        self.security_privacy_agent = security_privacy_agent or SecurityPrivacyAgent()
        self.risk_analysis_agent = risk_analysis_agent or RiskAnalysisAgent()
        self.conflict_detection_agent = conflict_detection_agent or ConflictDetectionAgent()
        self.validation_agent = validation_agent or ValidationAgent()

        self.stakeholder_follow_ups: list[FollowUpItem] = []
        self.clarification_issues: dict[str, list[ClarificationIssue]] = {}
        self.security_flags: dict[str, list[SecurityPrivacyFlag]] = {}
        self.conflicts: list[ConflictFinding] = []
        self.validation_issues: list[ValidationIssue] = []

    def run(self, transcript_text: str, db_session: Session) -> list[Requirement]:
        """Runs one transcript through the full agent pipeline and persists
        the resulting requirements."""
        self.stakeholder_follow_ups = self.stakeholder_interaction_agent.run(
            transcript_text, db_session=db_session
        )

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
        open_questions_by_id = {
            requirement.id: candidate.open_questions
            for requirement, candidate in zip(requirements, candidates)
        }
        source_excerpts_by_id = {
            requirement.id: candidate.source_excerpt
            for requirement, candidate in zip(requirements, candidates)
        }

        categories_by_id = self.classification_agent.run(requirements, db_session=db_session)
        for requirement in requirements:
            requirement.category = categories_by_id.get(requirement.id, [])

        self.clarification_issues = {}
        self.security_flags = {}
        needs_revision_ids: set[str] = set()

        for requirement in requirements:
            proposals = self.compliance_agent.run(requirement, db_session=db_session)
            requirement.applicable_regulations = [p.citation for p in proposals]

            clarification = self.clarification_agent.run(
                requirement,
                open_questions=open_questions_by_id.get(requirement.id),
                db_session=db_session,
            )
            if not clarification.is_complete:
                self.clarification_issues[requirement.id] = clarification.issues
                needs_revision_ids.add(requirement.id)

            flags = self.security_privacy_agent.run(requirement, db_session=db_session)
            if flags:
                self.security_flags[requirement.id] = flags

            risk = self.risk_analysis_agent.run(requirement, db_session=db_session)
            requirement.risk_level = risk.overall_risk_level
            requirement.confidence_score = risk.confidence

        self.conflicts = self.conflict_detection_agent.run(requirements, db_session=db_session)
        for conflict in self.conflicts:
            needs_revision_ids.add(conflict.requirement_id_a)
            needs_revision_ids.add(conflict.requirement_id_b)

        self.validation_issues = self.validation_agent.run(
            requirements, source_excerpts=source_excerpts_by_id, db_session=db_session
        )
        for issue in self.validation_issues:
            needs_revision_ids.add(issue.requirement_id)

        for requirement in requirements:
            if requirement.id in needs_revision_ids:
                requirement.approval_status = ApprovalStatus.NEEDS_REVISION

        for requirement in requirements:
            db_session.add(RequirementORM(**requirement.model_dump(mode="json")))
        db_session.commit()

        return requirements
