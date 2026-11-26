"""The coordinator: runs the agents in a fixed order and persists after every stage.

Control flow is plain code, never decided by the model. Each stage records which
requirements it has processed, so a re-run (new input, answered questions, or a retry
after a rate-limit failure) only does the work that is still outstanding.
"""

from __future__ import annotations

import re
import time
from collections import Counter
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from src.agents.acceptance_criteria import AcceptanceCriteriaAgent
from src.agents.classification import ClassificationAgent
from src.agents.compliance import ComplianceAgent, assess_controls
from src.agents.conflict_detection import ConflictDetectionAgent
from src.agents.extraction import ExtractionAgent
from src.agents.llm_client import AgentOutputError
from src.agents.quality import QualityAgent
from src.agents.refinement import RefinementAgent
from src.agents.risk_analysis import RiskAnalysisAgent
from src.agents.sdlc import SdlcAdvisorAgent
from src.agents.security_privacy import SecurityPrivacyAgent
from src.knowledge_base.kb import KnowledgeBase, get_kb
from src.models import audit
from src.models.db import (
    AuditORM,
    delete_open_questions,
    delete_requirements,
    get_project,
    list_documents,
    load_questions,
    load_requirements,
    save_analysis,
    save_gates,
    save_questions,
    save_requirements,
)
from src.models.requirement import (
    CATEGORY_PREFIX,
    ApprovalStatus,
    Category,
    Conflict,
    Priority,
    RegulationMapping,
    Requirement,
    RiskItem,
    now_iso,
)
from src.pipeline.approvals import ensure_gates, reset_gates
from src.pipeline.jobs import Job
from src.pipeline.validation import run_validation
from src.sdlc.engine import build_signals, extract_factors, rank_models
from src.sdlc.workflow import WorkflowContext, build_workflow

STEPS = [
    ("extract", "Reading inputs and extracting requirements"),
    ("classify", "Classifying across 13 dimensions"),
    ("quality", "Checking quality and drafting questions"),
    ("compliance", "Mapping to regulations"),
    ("controls", "Checking mandatory controls"),
    ("security", "Deriving security and privacy needs"),
    ("conflicts", "Detecting conflicts and duplicates"),
    ("criteria", "Writing acceptance criteria"),
    ("risk", "Scoring risks"),
    ("sdlc", "Recommending an SDLC"),
    ("validate", "Running quality gates"),
]

C = Category
CONTROL_CATEGORIES = {
    "C-CIP": [C.FUNCTIONAL, C.REGULATORY], "C-RISK": [C.FUNCTIONAL, C.REGULATORY],
    "C-SANCTIONS": [C.FUNCTIONAL, C.REGULATORY], "C-PEP": [C.FUNCTIONAL, C.REGULATORY],
    "C-UBO": [C.FUNCTIONAL, C.REGULATORY, C.DATA], "C-EDD": [C.FUNCTIONAL, C.REGULATORY],
    "C-CONSENT": [C.PRIVACY, C.REGULATORY], "C-MINIMISE": [C.PRIVACY, C.DATA],
    "C-RETENTION": [C.DATA, C.REGULATORY], "C-REKYC": [C.FUNCTIONAL, C.REGULATORY, C.OPERATIONAL],
    "C-MONITOR": [C.FUNCTIONAL, C.REGULATORY, C.OPERATIONAL], "C-STR": [C.FUNCTIONAL, C.REGULATORY, C.AUDIT],
    "C-LIVENESS": [C.SECURITY, C.FUNCTIONAL], "C-DOCFRAUD": [C.SECURITY, C.FUNCTIONAL],
    "C-CKYC": [C.INTEGRATION, C.REGULATORY], "C-AUDIT": [C.AUDIT, C.SECURITY],
    "C-ENCRYPT": [C.SECURITY, C.PRIVACY], "C-ACCESS": [C.SECURITY],
    "C-BREACH": [C.SECURITY, C.PRIVACY, C.OPERATIONAL], "C-RIGHTS": [C.PRIVACY, C.REGULATORY],
    "C-HUMAN-REVIEW": [C.FUNCTIONAL, C.USABILITY],
}
PRIVACY_WORDS = ("personal", "consent", "retention", "retain", "erasure", "pii", "biometric", "privacy")
REF_RE = re.compile(r"^KYC-([A-Z]+)-(\d+)$")
STAGES_PER_REQ = ("classified", "reviewed", "mapped", "criteria", "risked")


def assign_refs(all_requirements: list[Requirement], targets: list[Requirement]) -> None:
    """Gives each target a readable id such as KYC-SEC-004, continuing existing numbering."""
    counters: Counter[str] = Counter()
    for r in all_requirements:
        match = REF_RE.match(r.ref or "")
        if match:
            counters[match.group(1)] = max(counters[match.group(1)], int(match.group(2)))
    for r in targets:
        prefix = CATEGORY_PREFIX[r.primary_category or Category.FUNCTIONAL]
        counters[prefix] += 1
        r.ref = f"KYC-{prefix}-{counters[prefix]:03d}"


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def _conflict_sig(ids: list[str], by_id: dict) -> str:
    return "|".join(sorted(f"{i}:{_norm(by_id[i].statement)}" for i in ids if i in by_id))


def _similar(a: str, b: str) -> bool:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio() >= 0.82


class Pipeline:
    def __init__(self, kb: KnowledgeBase | None = None, **agents) -> None:
        self.kb = kb or get_kb()
        self.extraction = agents.get("extraction") or ExtractionAgent()
        self.classification = agents.get("classification") or ClassificationAgent()
        self.quality = agents.get("quality") or QualityAgent()
        self.conflicts = agents.get("conflicts") or ConflictDetectionAgent()
        self.compliance = agents.get("compliance") or ComplianceAgent(self.kb)
        self.security = agents.get("security") or SecurityPrivacyAgent()
        self.criteria = agents.get("criteria") or AcceptanceCriteriaAgent()
        self.risk = agents.get("risk") or RiskAnalysisAgent()
        self.refinement = agents.get("refinement") or RefinementAgent()
        self.advisor = agents.get("advisor") or SdlcAdvisorAgent()

    # ------------------------------------------------------------------ entry points
    def analyse(self, project_id: str, db: Session, job: Job) -> None:
        job.set_steps(STEPS)
        self._run(project_id, db, job, kind="analyse")

    def apply_answers(self, project_id: str, db: Session, job: Job) -> None:
        """Folds answered questions into their requirements, then re-analyses what changed."""
        job.set_steps([("refine", "Folding your answers into the requirements"), *STEPS])
        questions = load_questions(db, project_id)
        fresh = [q for q in questions if q.status == "answered" and not q.applied and q.answer]
        if not fresh:
            raise ValueError("There are no new answers to apply.")

        job.begin("refine")
        requirements = load_requirements(db, project_id)
        answers: dict[str, list[dict]] = {}
        for q in questions:
            if q.status == "answered" and q.answer:
                answers.setdefault(q.requirement_id, []).append({"question": q.question, "answer": q.answer})
        changed = self.refinement.run(requirements, {rid: a for rid, a in answers.items() if rid in {q.requirement_id for q in fresh}}, db)
        for requirement in requirements:
            if requirement.id in changed:
                if requirement.approval_status != ApprovalStatus.PENDING:
                    requirement.history.append({"action": "status_reset_after_answer", "previous": requirement.approval_status.value, "at": now_iso()})
                requirement.approval_status = ApprovalStatus.PENDING
        for q in fresh:
            q.applied = True
        save_requirements(db, project_id, requirements)
        save_questions(db, project_id, fresh)

        project = get_project(db, project_id)
        done = self._done(project.analysis)
        for key in ("reviewed", "mapped", "criteria", "risked"):
            done[key] -= set(changed)
        save_analysis(db, project_id, done={k: sorted(v) for k, v in done.items()})
        audit.record(db, "agent:refinement", "answers_applied", {"requirements": len(changed), "answers": len(fresh)}, project_id)
        job.end("refine", f"Updated {len(changed)} requirement(s) from {len(fresh)} answer(s)")
        self._run(project_id, db, job, kind="apply_answers", force_reset=True)

    # --------------------------------------------------------------------- internals
    @staticmethod
    def _done(analysis: dict | None) -> dict[str, set[str]]:
        raw = (analysis or {}).get("done", {})
        return {key: set(raw.get(key, [])) for key in STAGES_PER_REQ}

    def _run(self, project_id: str, db: Session, job: Job, kind: str, force_reset: bool = False) -> None:
        started = time.time()
        first_audit = db.query(AuditORM.id).filter_by(project_id=project_id).order_by(AuditORM.id.desc()).first()
        audit_floor = first_audit[0] if first_audit else 0
        project = get_project(db, project_id)
        analysis = dict(project.analysis or {})
        jurisdictions = list(project.jurisdictions or ["IN", "GLOBAL"])
        done = self._done(analysis)
        guard = {"ungrounded_requirements": 0, "invalid_citations": 0, **analysis.get("guard", {})}
        docs = list_documents(db, project_id)
        guard["pii_masked"] = sum(sum(d.pii_found.values()) for d in docs)
        guard["injection_quarantined"] = sum(len(d.injection) for d in docs)
        changed = force_reset

        def checkpoint() -> None:
            save_analysis(db, project_id, done={k: sorted(v) for k, v in done.items()}, guard=guard)

        reqs = load_requirements(db, project_id)
        doc_texts = [d.masked_text for d in docs]

        # 1 --- extract (only inputs not analysed before) ---------------------------------
        job.begin("extract")
        analysed = set(analysis.get("analysed_docs", []))
        new_docs = [d for d in docs if d.id not in analysed]
        added = 0
        for doc in new_docs:
            result = self.extraction.run(doc.title, doc.masked_text, doc.role, db)
            guard["ungrounded_requirements"] += result.dropped_ungrounded
            for i, cand in enumerate(result.candidates, start=1):
                reqs.append(
                    Requirement(
                        project_id=project_id,
                        ref=f"NEW-{doc.id[:4]}-{i}",
                        statement=cand.statement.strip(),
                        source_stakeholder=cand.source_stakeholder.strip() or "Unspecified",
                        source_document=doc.title,
                        source_excerpt=cand.source_excerpt,
                        business_justification=cand.business_justification,
                        assumptions=cand.assumptions,
                        hints=cand.unclear,
                    )
                )
                added += 1
            analysed.add(doc.id)
            save_requirements(db, project_id, reqs)
            save_analysis(db, project_id, analysed_docs=sorted(analysed), guard=guard)
        changed = changed or added > 0
        job.end("extract", f"{added} requirement(s) from {len(new_docs)} new input(s)" if new_docs else "No new inputs", skipped=not new_docs)

        stated = [r for r in reqs if r.origin == "stated"]
        if not stated:
            for key, _ in STEPS[1:]:
                job.end(key, "Nothing to analyse yet", skipped=True)
            save_analysis(db, project_id, last_run={"at": now_iso(), "note": "No requirements were found in the inputs."}, guard=guard,
                          validation=run_validation([], [], [], [], guard))
            return

        # 2 --- classify --------------------------------------------------------------------
        job.begin("classify")
        targets = [r for r in stated if r.id not in done["classified"]]
        if targets:
            for i, r in enumerate(targets, start=1):
                r.ref = f"T{i}"
            self.classification.run(targets, db)
            assign_refs([r for r in reqs if r not in targets], targets)
            save_requirements(db, project_id, reqs)
            done["classified"] |= {r.id for r in targets}
            checkpoint()
        job.end("classify", f"{len(targets)} classified" if targets else "Up to date", skipped=not targets)

        # 3 --- quality + questions -----------------------------------------------------------
        job.begin("quality")
        targets = [r for r in stated if r.id not in done["reviewed"]]
        if targets:
            questions = self.quality.run(targets, db)
            delete_open_questions(db, project_id, [r.id for r in targets])
            save_questions(db, project_id, questions)
            save_requirements(db, project_id, reqs)
            done["reviewed"] |= {r.id for r in targets}
            checkpoint()
        weak = sum(1 for r in stated if r.is_weak)
        job.end("quality", f"{weak} weak requirement(s) flagged" if targets else "Up to date", skipped=not targets)

        # 5 --- compliance mapping ------------------------------------------------------------
        job.begin("compliance")
        targets = [r for r in reqs if r.id not in done["mapped"] and not r.derived_reason.startswith("[C-")]
        if targets:
            result = self.compliance.run(targets, jurisdictions, db)
            guard["invalid_citations"] += result.hallucinated_citations
            save_requirements(db, project_id, reqs)
            done["mapped"] |= {r.id for r in targets}
            checkpoint()
        job.end("compliance", f"{sum(len(r.regulations) for r in targets)} mapping(s) proposed" if targets else "Up to date", skipped=not targets)

        # 6 --- mandatory controls + derived requirements -------------------------------------
        job.begin("controls")
        coverage = assess_controls(reqs, jurisdictions, self.kb, doc_texts)
        derived_new = self._derive_from_gaps(project_id, reqs, coverage, jurisdictions)
        if derived_new:
            reqs.extend(derived_new)
            assign_refs([r for r in reqs if r not in derived_new], derived_new)
            save_requirements(db, project_id, reqs)
            for r in derived_new:
                done["classified"].add(r.id)
                done["mapped"].add(r.id)
                done["reviewed"].add(r.id)
            changed = True
            coverage = assess_controls(reqs, jurisdictions, self.kb, doc_texts)
        save_analysis(db, project_id, controls=[c.model_dump(mode="json") for c in coverage])
        checkpoint()
        gaps = sum(1 for c in coverage if c.status == "gap")
        job.end("controls", f"{len(derived_new)} requirement(s) derived from control gaps; {gaps} gap(s) remain")

        # 7 --- security / privacy derivation + threat model ----------------------------------
        job.begin("security")
        stated_sig = "|".join(sorted(f"{r.id}:{_norm(r.statement)}" for r in reqs if r.origin == "stated"))
        if analysis.get("security_sig") != stated_sig:
            live = [r for r in reqs if r.approval_status != ApprovalStatus.REJECTED]
            derived, threats = self.security.run(live, db)
            stale = [r.id for r in reqs if r.origin == "derived" and not r.derived_reason.startswith("[C-") and r.approval_status == ApprovalStatus.PENDING]
            if stale:
                delete_requirements(db, project_id, stale)
                reqs = [r for r in reqs if r.id not in stale]
            new_items: list[Requirement] = []
            ref_by_ref = {r.ref: r for r in reqs}
            for item in derived:
                if any(_similar(item.statement, r.statement) for r in [*reqs, *new_items]):
                    continue
                text = item.statement.lower()
                cats = [Category.SECURITY] + ([Category.PRIVACY] if any(w in text for w in PRIVACY_WORDS) else [])
                related = ref_by_ref.get(item.related_ref)
                new_items.append(
                    Requirement(
                        project_id=project_id, statement=item.statement.strip(), categories=cats, primary_category=cats[0],
                        source_stakeholder="System (security/privacy analysis)", origin="derived",
                        derived_reason=item.rationale or "Implied security/privacy need.",
                        business_justification=item.rationale or None, priority=Priority.HIGH,
                        dependencies=[related.ref] if related else [],
                    )
                )
            if new_items:
                assign_refs(reqs, new_items)
                result = self.compliance.run(new_items, jurisdictions, db)
                guard["invalid_citations"] += result.hallucinated_citations
                reqs.extend(new_items)
                for r in new_items:
                    done["classified"].add(r.id)
                    done["mapped"].add(r.id)
                    done["reviewed"].add(r.id)
                changed = True
            save_requirements(db, project_id, reqs)
            save_analysis(db, project_id, threats=[t.model_dump(mode="json") for t in threats], security_sig=stated_sig)
            checkpoint()
            job.end("security", f"{len(new_items)} derived requirement(s), {len(threats)} threat(s)")
        else:
            job.end("security", "Up to date", skipped=True)

        # 7b --- conflicts (after derivation, so derived requirements are checked too) ---------
        job.begin("conflicts")
        live = [r for r in reqs if r.approval_status != ApprovalStatus.REJECTED]
        signature = "|".join(sorted(f"{r.id}:{_norm(r.statement)}" for r in live))
        by_id = {r.id: r for r in live}
        # A conflict stays until one of its requirements changes or disappears: the model is not
        # deterministic, and a conflict that was real a minute ago must not vanish on a re-run.
        kept = [
            c for c in (analysis.get("conflicts") or [])
            if all(i in by_id for i in c["requirement_ids"]) and c.get("sig") == _conflict_sig(c["requirement_ids"], by_id)
        ]
        if analysis.get("conflict_sig") != signature:
            found = self.conflicts.run(live, db)
            have = {tuple(sorted(c["requirement_ids"])) for c in kept}
            added = []
            for c in found:
                if tuple(sorted(c.requirement_ids)) in have:
                    continue
                c.sig = _conflict_sig(c.requirement_ids, by_id)
                added.append(c.model_dump(mode="json"))
            conflicts = kept + added
            save_analysis(db, project_id, conflicts=conflicts, conflict_sig=signature)
            job.end("conflicts", f"{len(added)} new, {len(kept)} kept")
        else:
            conflicts = kept
            job.end("conflicts", "Up to date", skipped=True)

        # 8 --- acceptance criteria ------------------------------------------------------------
        job.begin("criteria")
        questions = load_questions(db, project_id)
        clar: dict[str, list[dict]] = {}
        for q in questions:
            if q.status == "answered" and q.answer:
                clar.setdefault(q.requirement_id, []).append({"question": q.question, "answer": q.answer})
        targets = [r for r in reqs if r.id not in done["criteria"]]
        if targets:
            self.criteria.run(targets, clar, db)
            save_requirements(db, project_id, reqs)
            done["criteria"] |= {r.id for r in targets}
            checkpoint()
        job.end("criteria", f"{len(targets)} written" if targets else "Up to date", skipped=not targets)

        # 9 --- risk ----------------------------------------------------------------------------
        job.begin("risk")
        targets = [r for r in reqs if r.id not in done["risked"]]
        risks = [RiskItem.model_validate(x) for x in analysis.get("risks", [])]
        if targets:
            fresh = self.risk.run(targets, db)
            target_ids = {r.id for r in targets}
            risks = [x for x in risks if x.requirement_id not in target_ids] + fresh
            save_requirements(db, project_id, reqs)
            save_analysis(db, project_id, risks=[x.model_dump(mode="json") for x in risks])
            done["risked"] |= target_ids
            checkpoint()
        job.end("risk", f"{len(targets)} scored" if targets else "Up to date", skipped=not targets)
        live_ids = {r.id for r in reqs}
        risks = [x for x in risks if x.requirement_id in live_ids]

        # 10 --- SDLC ---------------------------------------------------------------------------
        job.begin("sdlc")
        self._sdlc(project_id, db, reqs, [Conflict.model_validate(c) for c in conflicts], coverage, risks, docs, analysis, jurisdictions)
        job.end("sdlc", "Recommendation updated")

        # 11 --- validate -----------------------------------------------------------------------
        job.begin("validate")
        questions = load_questions(db, project_id)
        validation = run_validation(reqs, questions, [Conflict.model_validate(c) for c in conflicts], coverage, guard)
        llm_calls = db.query(AuditORM).filter(AuditORM.project_id == project_id, AuditORM.action == "llm_call", AuditORM.id > audit_floor).count()
        save_analysis(
            db, project_id, validation=validation, guard=guard, risks=[x.model_dump(mode="json") for x in risks],
            last_run={"at": now_iso(), "kind": kind, "seconds": round(time.time() - started, 1), "llm_calls": llm_calls, "model": _model_name()},
        )
        if changed:
            gates = reset_gates(ensure_gates(get_project(db, project_id).gates), ["baseline", "regulatory", "conflicts", "sdlc"],
                                "Requirements changed after the last sign-off.")
            save_gates(db, project_id, gates)
        audit.record(db, "system", "analysis_complete", {"kind": kind, "requirements": len(reqs), "llm_calls": llm_calls}, project_id)
        job.end("validate", "Baseline ready" if validation["metrics"]["baseline_ready"] else "Baseline blocked: see gates")

    # ----------------------------------------------------------------------------- helpers
    def _derive_from_gaps(self, project_id, reqs, coverage, jurisdictions) -> list[Requirement]:
        existing_tags = {r.derived_reason.split("]")[0] + "]" for r in reqs if r.derived_reason.startswith("[C-")}
        out: list[Requirement] = []
        by_id = {c.id: c for c in self.kb.controls}
        for item in coverage:
            if item.status != "gap" or f"[{item.control_id}]" in existing_tags:
                continue
            control = by_id[item.control_id]
            allowed = {j.upper() for j in jurisdictions} | {"GLOBAL"}
            clauses = [c for rid in control.regulations if (c := self.kb.get(rid)) and c.jurisdiction in allowed][:3]
            cats = CONTROL_CATEGORIES.get(control.id, [Category.REGULATORY])
            out.append(
                Requirement(
                    project_id=project_id,
                    statement=control.suggested_requirement,
                    categories=cats,
                    primary_category=cats[0],
                    source_stakeholder="System (mandatory control catalogue)",
                    origin="derived",
                    derived_reason=f"[{control.id}] Mandatory control with no covering requirement: {control.title}.",
                    business_justification="Required by " + ", ".join(sorted({c.source for c in clauses})) + ".",
                    priority=Priority.HIGH,
                    regulations=[
                        RegulationMapping(
                            regulation=c.source, clause_id=c.id, citation=c.citation, jurisdiction=c.jurisdiction,
                            confidence=0.9, rationale="Derived from the mandatory-control catalogue.", needs_legal_review=c.high_impact,
                        )
                        for c in clauses
                    ],
                )
            )
        return out

    def _sdlc(self, project_id, db, reqs, conflicts, coverage, risks, docs, analysis, jurisdictions) -> None:
        live = [r for r in reqs if r.approval_status != ApprovalStatus.REJECTED]
        signals = build_signals(live, conflicts, coverage, risks, [d.masked_text for d in docs])
        factors = extract_factors(signals)
        ranking = rank_models(factors)
        old = analysis.get("sdlc") or {}
        signature = "|".join(f"{f.key}{f.score}" for f in factors) + ranking[0].model
        questions = load_questions(db, project_id)
        counts = {
            "requirements": len(live),
            "weak_requirements": sum(1 for r in live if r.is_weak),
            "open_conflicts": sum(1 for c in conflicts if c.status == "open"),
            "uncovered_controls": sum(1 for c in coverage if c.status == "gap"),
            "open_questions": sum(1 for q in questions if q.status == "open"),
        }
        if old.get("signature") == signature and old.get("narrative"):
            narrative = old["narrative"]
        else:
            try:
                narrative = self.advisor.run(factors, ranking, counts, db).model_dump()
            except AgentOutputError:
                top = ranking[0]
                narrative = {
                    "explanation": f"{top.model} scores highest ({top.score:.0f}%) on the project's decision factors. See the factor table for the evidence.",
                    "tradeoffs": [], "would_change_if": [],
                }
        chosen = old.get("chosen") if old.get("chosen") in {o.model for o in ranking} else ranking[0].model
        ctx = WorkflowContext(
            open_questions=counts["open_questions"],
            open_conflicts=counts["open_conflicts"],
            control_gaps=[c.title for c in coverage if c.status == "gap"],
            top_risks=[x.risk for x in sorted(risks, key=lambda x: -x.score)[:3]],
            jurisdictions=jurisdictions,
            requirement_count=len(live),
        )
        workflow = build_workflow(chosen, ctx)
        save_analysis(
            db, project_id,
            sdlc={
                "signature": signature,
                "factors": [f.model_dump() for f in factors],
                "ranking": [o.model_dump() for o in ranking],
                "recommended": ranking[0].model,
                "chosen": chosen,
                "narrative": narrative,
                "workflow": [p.model_dump() for p in workflow],
            },
        )


def rebuild_workflow(db: Session, project_id: str, chosen: str) -> None:
    """Re-generates the workflow when a reviewer picks a different model than the top one."""
    from src.sdlc.engine import MODELS

    project = get_project(db, project_id)
    sdlc = dict((project.analysis or {}).get("sdlc") or {})
    if not sdlc or chosen not in MODELS:
        raise ValueError("Unknown SDLC model or no recommendation yet.")
    analysis = project.analysis
    questions = load_questions(db, project_id)
    coverage = analysis.get("controls", [])
    risks = analysis.get("risks", [])
    ctx = WorkflowContext(
        open_questions=sum(1 for q in questions if q.status == "open"),
        open_conflicts=sum(1 for c in analysis.get("conflicts", []) if c["status"] == "open"),
        control_gaps=[c["title"] for c in coverage if c["status"] == "gap"],
        top_risks=[x["risk"] for x in sorted(risks, key=lambda x: -(x["likelihood"] * x["impact"]))[:3]],
        jurisdictions=list(project.jurisdictions or []),
    )
    sdlc["chosen"] = chosen
    sdlc["workflow"] = [p.model_dump() for p in build_workflow(chosen, ctx)]
    save_analysis(db, project_id, sdlc=sdlc)


def _model_name() -> str:
    from src.agents.llm_client import DEFAULT_MODEL

    return DEFAULT_MODEL
