"""Orchestrates the pipeline: passes shared context between agents.

Not itself an LLM call — it owns the sequencing and hands each agent exactly
what it needs, then persists the result. Milestone 2 wired extraction and
classification; Milestone 3 added compliance mapping; Milestone 4 added
clarification, conflict detection, security/privacy, and risk analysis;
acceptance_criteria populates the field validation.py checks for;
validation runs last, right before persistence; stakeholder_interaction runs
first, as a pre-processing pass over the raw transcript before extraction.

Progress is checkpointed to the DB as it goes (create_requirements right
after classification, update_requirement after each requirement finishes the
per-requirement agent loop), so a Gemini quota failure partway through
doesn't lose everything done before it — resume() picks up where run() left
off, skipping requirements already marked processing_complete.

Findings that don't have a dedicated field in the fixed Requirement schema
(clarification issues, security/privacy flags, conflicts, validation issues,
stakeholder follow-ups) are logged to the audit table via each agent's own
call, and also kept on the coordinator instance after run()/resume() for the
UI/CLI to display.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from src.agents.acceptance_criteria import AcceptanceCriteriaAgent
from src.agents.classification import ClassificationAgent
from src.agents.clarification import ClarificationAgent, ClarificationIssue
from src.agents.compliance import ComplianceAgent
from src.agents.conflict_detection import ConflictDetectionAgent, ConflictFinding
from src.agents.extraction import ExtractionAgent
from src.agents.risk_analysis import RiskAnalysisAgent
from src.agents.security_privacy import SecurityPrivacyAgent, SecurityPrivacyFlag
from src.agents.stakeholder_interaction import FollowUpItem, StakeholderInteractionAgent
from src.agents.validation import ValidationAgent, ValidationIssue
from src.models.db import create_batch, create_requirements, load_requirements, update_requirement
from src.models.requirement import ApprovalStatus, Requirement

TRANSCRIPT_PREVIEW_LENGTH = 300


class Coordinator:
    """Runs a transcript through the full agent sequence and persists the
    result, checkpointing as it goes so a failure partway through is
    resumable instead of a total loss."""

    def __init__(
        self,
        stakeholder_interaction_agent: StakeholderInteractionAgent | None = None,
        extraction_agent: ExtractionAgent | None = None,
        classification_agent: ClassificationAgent | None = None,
        compliance_agent: ComplianceAgent | None = None,
        clarification_agent: ClarificationAgent | None = None,
        security_privacy_agent: SecurityPrivacyAgent | None = None,
        acceptance_criteria_agent: AcceptanceCriteriaAgent | None = None,
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
        self.acceptance_criteria_agent = acceptance_criteria_agent or AcceptanceCriteriaAgent()
        self.risk_analysis_agent = risk_analysis_agent or RiskAnalysisAgent()
        self.conflict_detection_agent = conflict_detection_agent or ConflictDetectionAgent()
        self.validation_agent = validation_agent or ValidationAgent()

        self.last_batch_id: str | None = None
        self.stakeholder_follow_ups: list[FollowUpItem] = []
        self.clarification_issues: dict[str, list[ClarificationIssue]] = {}
        self.security_flags: dict[str, list[SecurityPrivacyFlag]] = {}
        self.conflicts: list[ConflictFinding] = []
        self.validation_issues: list[ValidationIssue] = []

    def run(self, transcript_text: str, db_session: Session) -> list[Requirement]:
        """Runs one transcript through the full agent pipeline, all stamped
        with one new batch_id so a later SDLC recommendation can be scoped
        to just this ingestion."""
        batch_id = str(uuid.uuid4())
        self.last_batch_id = batch_id
        preview = transcript_text.strip().replace("\n", " ")[:TRANSCRIPT_PREVIEW_LENGTH]
        if len(transcript_text.strip()) > TRANSCRIPT_PREVIEW_LENGTH:
            preview += "..."
        create_batch(db_session, batch_id, preview)

        self.stakeholder_follow_ups = self.stakeholder_interaction_agent.run(
            transcript_text, db_session=db_session
        )

        candidates = self.extraction_agent.run(transcript_text, db_session=db_session)

        requirements = [
            Requirement(
                batch_id=batch_id,
                statement=candidate.statement,
                source_stakeholder=candidate.source_stakeholder,
                business_justification=candidate.business_justification,
                assumptions=candidate.assumptions,
                source_excerpt=candidate.source_excerpt,
                open_questions=candidate.open_questions,
            )
            for candidate in candidates
        ]

        categories_by_id = self.classification_agent.run(requirements, db_session=db_session)
        for requirement in requirements:
            requirement.category = categories_by_id.get(requirement.id, [])

        # Checkpoint: extraction + classification are done. A failure
        # anywhere in the per-requirement loop that follows (the expensive
        # part — 5 calls per requirement) won't lose this.
        create_requirements(db_session, requirements)

        return self._process_and_finalize(requirements, db_session)

    def resume(self, batch_id: str, db_session: Session) -> list[Requirement]:
        """Continues a batch that previously failed partway through the
        per-requirement agent loop (e.g. the Gemini quota ran out),
        re-processing only requirements a prior attempt didn't finish.

        Note: clarification/security findings on the coordinator after this
        call cover only requirements (re)processed in *this* resume —
        findings for requirements a prior attempt already completed are
        still in the audit_log table but aren't re-summarized here.
        """
        self.last_batch_id = batch_id
        requirements = load_requirements(db_session, batch_id=batch_id)
        if not requirements:
            raise ValueError(f"No requirements found for batch {batch_id} — nothing to resume")
        return self._process_and_finalize(requirements, db_session)

    def _process_and_finalize(
        self, requirements: list[Requirement], db_session: Session
    ) -> list[Requirement]:
        """Runs the per-requirement agent loop (skipping requirements already
        marked processing_complete), then batch-level conflict detection and
        validation, persisting each requirement's final state."""
        open_questions_by_id = {r.id: r.open_questions for r in requirements}
        source_excerpts_by_id = {r.id: r.source_excerpt for r in requirements}

        self.clarification_issues = {}
        self.security_flags = {}
        needs_revision_ids = {
            r.id for r in requirements if r.approval_status == ApprovalStatus.NEEDS_REVISION
        }

        for requirement in requirements:
            if requirement.processing_complete:
                continue

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

            requirement.acceptance_criteria = self.acceptance_criteria_agent.run(
                requirement, db_session=db_session
            )

            risk = self.risk_analysis_agent.run(requirement, db_session=db_session)
            requirement.risk_level = risk.overall_risk_level
            requirement.confidence_score = risk.confidence

            requirement.processing_complete = True
            update_requirement(db_session, requirement)  # checkpoint: this one's done

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
            update_requirement(db_session, requirement)

        return requirements
