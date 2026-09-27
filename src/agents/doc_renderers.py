"""Deterministic file renderers for the documentation agent's output.

Pure formatting, no LLM calls — a formal SRS deliverable can't afford an LLM
paraphrasing or dropping a requirement, citation, or risk score.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from src.agents.sdlc_selection import SDLCRecommendation
from src.models.requirement import Requirement


def write_srs(
    output_dir: Path,
    requirements: list[Requirement],
    sdlc_recommendations: list[SDLCRecommendation],
    summary: str,
) -> Path:
    lines = [
        "# Software Requirements Specification — Step-Up Authentication for Payments",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()}_",
        "",
        "## Executive Summary",
        "",
        summary,
        "",
        "## Recommended SDLC Approach",
        "",
    ]
    for i, rec in enumerate(sdlc_recommendations, start=1):
        lines.append(f"{i}. **{rec.model}** (confidence: {rec.confidence:.0%}) — {rec.rationale}")

    lines += [
        "",
        "## Requirements",
        "",
        "| ID | Statement | Category | Priority | Risk | Regulations | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in requirements:
        categories = ", ".join(c.value for c in r.category) or "—"
        regs = "; ".join(r.applicable_regulations) or "—"
        risk = r.risk_level.value if r.risk_level else "—"
        lines.append(
            f"| {r.id[:8]} | {r.statement} | {categories} | {r.priority.value} | "
            f"{risk} | {regs} | {r.approval_status.value} |"
        )

    path = output_dir / "SRS.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_user_stories(output_dir: Path, stories: list) -> Path:
    lines = ["# User Stories", ""]
    for i, story in enumerate(stories, start=1):
        lines.append(f"**US-{i}** (requirement `{story.requirement_id[:8]}`)")
        so_that = story.so_that.rstrip(".")
        lines.append(f"> As a {story.as_a}, I want {story.i_want}, so that {so_that}.")
        lines.append("")

    path = output_dir / "user_stories.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_requirements_report(
    output_dir: Path, batch_id: str, batch_label: str, requirements: list[Requirement]
) -> Path:
    """Writes every requirement extracted from one transcript ingestion,
    grouped by current approval_status — unlike the SRS, which only ever
    lists approved requirements. Regenerated after every ingestion and every
    approve/send-back/reject click so it always reflects the batch's current
    review state, not just a point-in-time snapshot."""
    groups: dict[str, list[Requirement]] = {"approved": [], "needs_revision": [], "pending": [], "rejected": []}
    for r in requirements:
        groups.setdefault(r.approval_status.value, []).append(r)

    lines = [
        f"# Requirements Report — {batch_label}",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()}_",
        "",
        f"Total: {len(requirements)} — "
        f"Approved: {len(groups['approved'])}, "
        f"Needs revision: {len(groups['needs_revision'])}, "
        f"Pending: {len(groups['pending'])}, "
        f"Rejected: {len(groups['rejected'])}",
        "",
    ]

    section_titles = {
        "approved": "## Approved",
        "needs_revision": "## Needs Revision",
        "pending": "## Pending Review",
        "rejected": "## Rejected",
    }
    for status, title in section_titles.items():
        lines.append(title)
        lines.append("")
        if not groups[status]:
            lines.append("_None._")
            lines.append("")
            continue
        for r in groups[status]:
            categories = ", ".join(c.value for c in r.category) or "—"
            risk = r.risk_level.value if r.risk_level else "—"
            lines.append(f"- **{r.id[:8]}** ({categories}, risk: {risk}) — {r.statement}")
            if r.open_questions:
                for q in r.open_questions:
                    lines.append(f"  - _Open question:_ {q}")
        lines.append("")

    path = output_dir / f"requirements_report_{batch_id[:8]}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_traceability_csv(output_dir: Path, requirements: list[Requirement]) -> Path:
    path = output_dir / "traceability_matrix.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "requirement_id",
                "statement",
                "category",
                "priority",
                "risk_level",
                "confidence_score",
                "applicable_regulations",
                "approval_status",
                "source_stakeholder",
            ]
        )
        for r in requirements:
            writer.writerow(
                [
                    r.id,
                    r.statement,
                    "|".join(c.value for c in r.category),
                    r.priority.value,
                    r.risk_level.value if r.risk_level else "",
                    r.confidence_score,
                    "|".join(r.applicable_regulations),
                    r.approval_status.value,
                    r.source_stakeholder,
                ]
            )
    return path
