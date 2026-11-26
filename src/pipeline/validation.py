"""Deterministic quality gates and metrics over the analysed project.

No model is involved: a gate either passes or it does not, so the baseline cannot be
approved on the strength of a model's opinion.
"""

from __future__ import annotations

from src.models.requirement import (
    ApprovalStatus,
    Conflict,
    ControlCoverage,
    Question,
    Requirement,
)


def _pct(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 100.0


def run_validation(
    requirements: list[Requirement],
    questions: list[Question],
    conflicts: list[Conflict],
    controls: list[ControlCoverage],
    guard_stats: dict,
) -> dict:
    live = [r for r in requirements if r.approval_status != ApprovalStatus.REJECTED]
    stated = [r for r in live if r.origin == "stated"]
    open_q_by_req: dict[str, int] = {}
    for q in questions:
        if q.status == "open":
            open_q_by_req[q.requirement_id] = open_q_by_req.get(q.requirement_id, 0) + 1

    no_source = [r.ref for r in stated if not r.source_excerpt.strip()]
    no_criteria = [r.ref for r in live if not r.acceptance_criteria]
    unresolved_weak = [r.ref for r in live if r.is_weak and open_q_by_req.get(r.id)]
    open_conflicts = [c for c in conflicts if c.status == "open"]
    applicable = [c for c in controls if c.status != "not_applicable"]
    gaps = [c for c in applicable if c.status == "gap"]
    legal = [r.ref for r in live if any(m.needs_legal_review for m in r.regulations)]

    gates = [
        {"id": "traceability", "title": "Every stated requirement traces to a source quote",
         "passed": not no_source, "detail": f"{len(no_source)} without a source quote" if no_source else "All traceable."},
        {"id": "criteria", "title": "Every requirement has acceptance criteria",
         "passed": not no_criteria, "detail": f"{len(no_criteria)} missing criteria" if no_criteria else "All have criteria."},
        {"id": "clarity", "title": "Weak requirements are answered or consciously skipped",
         "passed": not unresolved_weak, "detail": f"{len(unresolved_weak)} still have open questions" if unresolved_weak else "No open questions block the baseline."},
        {"id": "conflicts", "title": "No unresolved stakeholder conflicts",
         "passed": not open_conflicts, "detail": f"{len(open_conflicts)} open" if open_conflicts else "None open."},
        {"id": "controls", "title": "No mandatory control is left uncovered",
         "passed": not gaps, "detail": f"{len(gaps)} uncovered: " + ", ".join(c.title for c in gaps[:3]) if gaps else "All applicable controls have a requirement."},
    ]

    covered = sum(1 for c in applicable if c.status == "covered")
    partial = sum(1 for c in applicable if c.status == "partial")
    complete = [
        r for r in live
        if r.acceptance_criteria and (r.source_excerpt.strip() or r.origin == "derived") and r.categories and r.risk_level
    ]
    metrics = {
        "requirements": len(live),
        "stated": len(stated),
        "derived": len(live) - len(stated),
        "weak": sum(1 for r in live if r.is_weak),
        "open_questions": sum(open_q_by_req.values()),
        "open_conflicts": len(open_conflicts),
        "completeness_pct": _pct(len(complete), len(live)),
        "traceability_pct": _pct(len(stated) - len(no_source), len(stated)),
        "control_coverage_pct": _pct(covered, len(applicable)),
        "controls_partial": partial,
        "controls_gap": len(gaps),
        "needs_legal_review": len(legal),
        "avg_confidence": round(sum(r.confidence_score for r in live) / len(live), 2) if live else 0.0,
        "hallucinations_dropped": guard_stats.get("ungrounded_requirements", 0) + guard_stats.get("invalid_citations", 0),
        "baseline_ready": all(g["passed"] for g in gates),
    }
    return {"gates": gates, "metrics": metrics}
