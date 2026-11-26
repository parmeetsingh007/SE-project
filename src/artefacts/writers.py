"""Renders every deliverable from the analysed project.

Deterministic formatting only: a formal document must never depend on a model
paraphrasing a requirement, citation or risk score. (The narrative user stories and use
cases are generated earlier and stored; this module only lays them out.)
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.models.requirement import ApprovalStatus, Question, Requirement


@dataclass
class Bundle:
    project: dict  # id, name, description, jurisdictions
    requirements: list[Requirement]
    questions: list[Question]
    analysis: dict
    gates: dict
    documents: list[dict]  # title, source_type, role
    audit: list[dict] = field(default_factory=list)
    kb_version: str = ""
    model: str = ""

    @property
    def live(self) -> list[Requirement]:
        return [r for r in self.requirements if r.approval_status != ApprovalStatus.REJECTED]

    def ref_of(self, requirement_id: str) -> str:
        return next((r.ref for r in self.requirements if r.id == requirement_id), requirement_id[:8])


def _cell(text: object) -> str:
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ").strip() or "-"


def _strip_numbering(step: str) -> str:
    """The model often numbers flow steps itself; remove that so we do not number twice."""
    return re.sub(r"^\s*(?:step\s*)?\d+\s*[.):-]\s*", "", step, flags=re.I).strip()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


STATUS_LABEL = {"approved": "Approved", "pending": "Pending review", "needs_revision": "Needs revision", "rejected": "Rejected"}


def _by_status(bundle: Bundle) -> dict[str, list[Requirement]]:
    groups: dict[str, list[Requirement]] = {"approved": [], "needs_revision": [], "pending": []}
    for r in bundle.live:
        groups.setdefault(r.approval_status.value, []).append(r)
    return groups


# ------------------------------------------------------------------------------- SRS
def srs_markdown(b: Bundle) -> str:
    a, m = b.analysis, (b.analysis.get("validation") or {}).get("metrics", {})
    groups = _by_status(b)
    sdlc = a.get("sdlc") or {}
    out = [
        f"# Software Requirements Specification - {b.project['name']}",
        "",
        f"_Generated {_now()} | Knowledge base {b.kb_version} | Model {b.model}_",
        f"_Jurisdictions: {', '.join(b.project.get('jurisdictions', [])) or '-'}_",
        "",
        "> Advisory output. Regulatory mappings are proposals for a compliance officer, not legal determinations.",
        "",
        "## 1. Summary",
        "",
        b.project.get("description") or "No description provided.",
        "",
        f"This specification covers **{len(b.live)} requirements** extracted from {len(b.documents)} stakeholder input(s): "
        f"{len(groups['approved'])} approved, {len(groups['needs_revision'])} needing revision and {len(groups['pending'])} pending review. "
        f"{m.get('derived', 0)} were derived by the system from mandatory controls and security analysis. "
        f"{m.get('open_questions', 0)} clarification question(s) remain open and {m.get('open_conflicts', 0)} conflict(s) are unresolved.",
        "",
        "## 2. Stakeholder inputs",
        "",
        "| Input | Type | Declared role |",
        "|---|---|---|",
        *(f"| {_cell(d['title'])} | {_cell(d['source_type'])} | {_cell(d['role'])} |" for d in b.documents),
        "",
        "## 3. Requirements",
        "",
    ]
    for status, title in (("approved", "3.1 Approved baseline"), ("needs_revision", "3.2 Needs revision"), ("pending", "3.3 Pending review")):
        items = groups[status]
        out += [f"### {title} ({len(items)})", ""]
        if not items:
            out += ["_None._", ""]
            continue
        out += ["| Ref | Statement | Categories | Priority | Risk | Source |", "|---|---|---|---|---|---|"]
        for r in items:
            out.append(
                f"| {r.ref} | {_cell(r.statement)} | {_cell(', '.join(c.value for c in r.categories))} | {r.priority.value} | "
                f"{r.risk_level.value if r.risk_level else '-'} | {_cell(r.source_stakeholder)} |"
            )
        out.append("")

    out += ["## 4. Requirement details", ""]
    for r in b.live:
        out += [f"### {r.ref} - {STATUS_LABEL[r.approval_status.value]}", "", f"**{r.statement}**", ""]
        out.append(f"- Origin: {r.origin}" + (f" ({r.derived_reason})" if r.derived_reason else ""))
        out.append(f"- Source: {r.source_stakeholder}" + (f", {r.source_document}" if r.source_document else ""))
        if r.source_excerpt:
            out.append(f'- Evidence: "{r.source_excerpt}"')
        if r.business_justification:
            out.append(f"- Justification: {r.business_justification}")
        out.append(f"- Confidence: {r.confidence_score:.0%}")
        if r.assumptions:
            out.append("- Assumptions: " + "; ".join(r.assumptions))
        if r.acceptance_criteria:
            out.append("- Acceptance criteria:")
            out += [f"  - {c}" for c in r.acceptance_criteria]
        if r.regulations:
            out.append("- Regulations:")
            out += [
                f"  - {mp.citation} ({mp.jurisdiction}, confidence {mp.confidence:.0%})" + (" - needs legal review" if mp.needs_legal_review else "")
                for mp in r.regulations
            ]
        out.append("")

    out += ["## 5. Regulatory control coverage", "", "| Control | Status | Regulations | Covered by |", "|---|---|---|---|"]
    for c in a.get("controls", []):
        out.append(f"| {_cell(c['title'])} | {c['status']} | {_cell('; '.join(c['regulations']))} | {_cell(', '.join(c['covered_by']))} |")
    out += ["", "## 6. Risk register (top 10)", "", "| Requirement | Risk | Type | L | I | Score | Mitigation |", "|---|---|---|---|---|---|---|"]
    for x in sorted(a.get("risks", []), key=lambda x: -(x["likelihood"] * x["impact"]))[:10]:
        out.append(f"| {b.ref_of(x['requirement_id'])} | {_cell(x['risk'])} | {x['risk_type']} | {x['likelihood']} | {x['impact']} | {x['likelihood'] * x['impact']} | {_cell(x['mitigation'])} |")

    out += ["", "## 7. Recommended SDLC", ""]
    if sdlc:
        out += [f"**Recommended: {sdlc.get('recommended')}**" + (f" (selected: {sdlc.get('chosen')})" if sdlc.get("chosen") != sdlc.get("recommended") else ""), "", (sdlc.get("narrative") or {}).get("explanation", ""), ""]
        out += ["| Rank | Model | Suitability |", "|---|---|---|"]
        out += [f"| {i} | {o['model']} | {o['score']:.0f}% |" for i, o in enumerate(sdlc.get("ranking", []), 1)]
        out += ["", "See `sdlc_workflow.md` for the project-specific phases, gates and checkpoints.", ""]
    out += ["## 8. Assumptions, dependencies and open issues", ""]
    issues = open_issues_markdown(b).split("\n")[2:]  # drop the document's own title
    out += [("#" + line) if line.startswith("## ") else line for line in issues]
    out += ["", "## 9. Approval record", ""]
    out += approvals_markdown(b)
    out += ["", "## 10. Limitations", "",
            "- Regulatory text in the knowledge base is paraphrased for prototyping; verify against official sources.",
            "- Name and address detection in PII masking is out of scope (identifiers only).",
            "- Confidence scores combine model confidence, requirement clarity and regulatory support; they are not probabilities."]
    return "\n".join(out) + "\n"


def approvals_markdown(b: Bundle) -> list[str]:
    from src.pipeline.approvals import GATES, ROLES

    lines = ["| Gate | Status | Sign-offs |", "|---|---|---|"]
    for gid, gate in GATES.items():
        state = b.gates.get(gid, {"status": "pending", "signoffs": []})
        latest = {s["role"]: s for s in state["signoffs"]}
        signed = "; ".join(f"{ROLES[r]}: {e['user']} ({e['decision']})" for r, e in latest.items()) or "none yet"
        lines.append(f"| {gate['title']} | {state['status']} | {_cell(signed)} |")
    return lines


# ---------------------------------------------------------------------- other documents
def open_issues_markdown(b: Bundle) -> str:
    refs = {r.id: r.ref for r in b.requirements}
    out = ["# Assumptions, dependencies and open issues", ""]
    out += ["## Open and skipped clarification questions", ""]
    pending = [q for q in b.questions if q.status != "answered"]
    out += [f"- **{refs.get(q.requirement_id, '?')}** ({'skipped by reviewer' if q.status == 'skipped' else 'open'}): {q.question}" for q in pending] or ["_None._"]
    out += ["", "## Answered questions", ""]
    out += [f"- **{refs.get(q.requirement_id, '?')}**: {q.question} -> {q.answer}" for q in b.questions if q.status == "answered"] or ["_None._"]
    out += ["", "## Unresolved conflicts", ""]
    conflicts = [c for c in b.analysis.get("conflicts", []) if c["status"] == "open"]
    out += [f"- {c['kind']}: {', '.join(refs.get(i, '?') for i in c['requirement_ids'])} - {c['explanation']}" for c in conflicts] or ["_None._"]
    out += ["", "## Assumptions", ""]
    assumptions = [f"- **{r.ref}**: {a}" for r in b.live for a in r.assumptions]
    out += assumptions or ["_None recorded._"]
    out += ["", "## Dependencies", ""]
    deps = [f"- **{r.ref}** depends on {', '.join(r.dependencies)}" for r in b.live if r.dependencies]
    out += deps or ["_None recorded._"]
    out += ["", "## Mandatory controls not yet covered", ""]
    gaps = [c for c in b.analysis.get("controls", []) if c["status"] == "gap"]
    out += [f"- {c['title']} ({', '.join(c['regulations'])})" for c in gaps] or ["_None._"]
    return "\n".join(out) + "\n"


def user_stories_markdown(b: Bundle) -> str:
    docs = b.analysis.get("artefacts") or {}
    stories = docs.get("stories")
    if not stories:
        return "# User stories\n\n_Not generated yet. Use **Generate stories and use cases** on the Export page._\n"
    out = ["# User stories", ""]
    for s in stories:
        out += [f"**{s['ref']}**", f"> As a {s['as_a']}, I want {s['i_want']}, so that {s['so_that'].rstrip('.')}.", ""]
    return "\n".join(out) + "\n"


def use_cases_markdown(b: Bundle) -> str:
    cases = (b.analysis.get("artefacts") or {}).get("use_cases")
    if not cases:
        return "# Use cases\n\n_Not generated yet. Use **Generate stories and use cases** on the Export page._\n"
    out = ["# Use cases", ""]
    for i, u in enumerate(cases, 1):
        out += [f"## UC-{i:02d} {u['name']}", "", f"**Actor:** {u['actor']}", ""]
        for title, key, numbered in (("Preconditions", "pre", False), ("Main flow", "main", True), ("Alternate and failure flows", "alt", False), ("Postconditions", "post", False)):
            if u.get(key):
                out += [f"**{title}**", ""] + [f"{n}. {_strip_numbering(x)}" if numbered else f"- {_strip_numbering(x)}" for n, x in enumerate(u[key], 1)] + [""]
        if u.get("refs"):
            out += ["**Realises:** " + ", ".join(u["refs"]), ""]
    return "\n".join(out) + "\n"


def sdlc_workflow_markdown(b: Bundle) -> str:
    sdlc = b.analysis.get("sdlc")
    if not sdlc:
        return "# SDLC workflow\n\n_No recommendation yet._\n"
    out = [f"# SDLC workflow - {sdlc['chosen']}", "", (sdlc.get("narrative") or {}).get("explanation", ""), "", "## Decision factors", "",
           "| Factor | Score | Evidence |", "|---|---|---|"]
    out += [f"| {f['label']} | {f['score']}/5 | {_cell(f['evidence'])} |" for f in sdlc["factors"]]
    out += ["", "## Phases", ""]
    for i, p in enumerate(sdlc["workflow"], 1):
        out += [f"### {i}. {p['name']}", "", f"_{p['goal']}_", ""]
        for title, key in (("Activities", "activities"), ("Roles", "roles"), ("Deliverables", "deliverables"), ("Security activities", "security_activities"),
                           ("Testing", "testing"), ("Compliance checkpoints", "compliance_checkpoints"), ("Entry criteria", "entry_criteria"), ("Exit criteria", "exit_criteria")):
            if p[key]:
                out += [f"**{title}**", ""] + [f"- {x}" for x in p[key]] + [""]
        out += [f"**Approval gate:** {p['approval_gate']}", ""]
    return "\n".join(out) + "\n"


def requirements_report_markdown(b: Bundle) -> str:
    """Every requirement from the inputs grouped by current review status, with open questions."""
    groups = _by_status(b)
    open_q: dict[str, list[str]] = {}
    for q in b.questions:
        if q.status == "open":
            open_q.setdefault(q.requirement_id, []).append(q.question)
    rejected = [r for r in b.requirements if r.approval_status == ApprovalStatus.REJECTED]
    out = [f"# Requirements report - {b.project['name']}", "", f"_Generated {_now()}_", "",
           f"Total {len(b.requirements)}: approved {len(groups['approved'])}, needs revision {len(groups['needs_revision'])}, "
           f"pending {len(groups['pending'])}, rejected {len(rejected)}", ""]
    for status, title in (("approved", "Approved"), ("needs_revision", "Needs revision"), ("pending", "Pending review")):
        out += [f"## {title}", ""]
        for r in groups[status]:
            out.append(f"- **{r.ref}** ({', '.join(c.value for c in r.categories)}; risk {r.risk_level.value if r.risk_level else '-'}) - {r.statement}")
            out += [f"  - _Open question:_ {q}" for q in open_q.get(r.id, [])]
        if not groups[status]:
            out.append("_None._")
        out.append("")
    out += ["## Rejected", ""] + ([f"- **{r.ref}** - {r.statement}" for r in rejected] or ["_None._"]) + [""]
    return "\n".join(out)


# --------------------------------------------------------------------------------- CSV
def _csv(rows: list[list], header: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def traceability_csv(b: Bundle) -> str:
    risks = {x["requirement_id"]: x for x in b.analysis.get("risks", [])}
    stories = {s["ref"]: s for s in (b.analysis.get("artefacts") or {}).get("stories", [])}
    cases = (b.analysis.get("artefacts") or {}).get("use_cases", [])
    rows = []
    for r in b.live:
        case_ids = [f"UC-{i:02d}" for i, u in enumerate(cases, 1) if r.ref in u.get("refs", [])]
        rows.append([
            r.ref, r.statement, r.origin, r.source_stakeholder, r.source_document, r.source_excerpt,
            "|".join(c.value for c in r.categories), r.priority.value,
            "|".join(m.clause_id for m in r.regulations), "|".join(m.citation for m in r.regulations),
            "yes" if stories.get(r.ref) else "no", "|".join(case_ids), len(r.acceptance_criteria),
            risks.get(r.id, {}).get("risk", ""), r.risk_level.value if r.risk_level else "", r.confidence_score, r.approval_status.value,
        ])
    return _csv(rows, ["ref", "statement", "origin", "stakeholder", "source_document", "source_quote", "categories", "priority", "clause_ids", "regulations",
                       "user_story", "use_cases", "acceptance_criteria_count", "risk", "risk_level", "confidence", "status"])


def compliance_matrix_csv(b: Bundle) -> str:
    rows = [
        [r.ref, r.statement, m.regulation, m.clause_id, m.jurisdiction, m.confidence, "yes" if m.needs_legal_review else "no", m.rationale]
        for r in b.live for m in r.regulations
    ]
    return _csv(rows, ["ref", "statement", "regulation", "clause_id", "jurisdiction", "confidence", "needs_legal_review", "rationale"])


def control_coverage_csv(b: Bundle) -> str:
    rows = [[c["control_id"], c["title"], c["status"], "; ".join(c["regulations"]), ", ".join(c["covered_by"]), c.get("suggested_requirement", "")] for c in b.analysis.get("controls", [])]
    return _csv(rows, ["control_id", "title", "status", "regulations", "covered_by", "suggested_requirement"])


def risk_register_csv(b: Bundle) -> str:
    rows = [
        [b.ref_of(x["requirement_id"]), x["risk"], x["risk_type"], x["likelihood"], x["impact"], x["likelihood"] * x["impact"], x["mitigation"], x["confidence"]]
        for x in sorted(b.analysis.get("risks", []), key=lambda x: -(x["likelihood"] * x["impact"]))
    ]
    return _csv(rows, ["ref", "risk", "type", "likelihood", "impact", "score", "mitigation", "confidence"])


# -------------------------------------------------------------------------------- DOCX
def srs_docx(b: Bundle) -> bytes:
    import docx
    from docx.shared import Pt

    d = docx.Document()
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(10.5)
    d.add_heading(f"Software Requirements Specification - {b.project['name']}", 0)
    d.add_paragraph(f"Generated {_now()} | Knowledge base {b.kb_version} | Model {b.model}")
    d.add_paragraph("Advisory output. Regulatory mappings are proposals for a compliance officer, not legal determinations.").italic = True
    m = (b.analysis.get("validation") or {}).get("metrics", {})
    groups = _by_status(b)
    d.add_heading("1. Summary", 1)
    d.add_paragraph(b.project.get("description") or "No description provided.")
    d.add_paragraph(
        f"{len(b.live)} requirements from {len(b.documents)} input(s): {len(groups['approved'])} approved, "
        f"{len(groups['needs_revision'])} need revision, {len(groups['pending'])} pending. "
        f"{m.get('open_questions', 0)} open question(s), {m.get('open_conflicts', 0)} unresolved conflict(s)."
    )
    d.add_heading("2. Requirements", 1)
    table = d.add_table(rows=1, cols=6)
    table.style = "Light Grid Accent 1"
    for cell, text in zip(table.rows[0].cells, ["Ref", "Statement", "Categories", "Priority", "Risk", "Status"]):
        cell.text = text
    for r in b.live:
        row = table.add_row().cells
        row[0].text, row[1].text = r.ref, r.statement
        row[2].text, row[3].text = ", ".join(c.value for c in r.categories), r.priority.value
        row[4].text, row[5].text = (r.risk_level.value if r.risk_level else "-"), STATUS_LABEL[r.approval_status.value]
    d.add_heading("3. Requirement details", 1)
    for r in b.live:
        d.add_heading(f"{r.ref} ({STATUS_LABEL[r.approval_status.value]})", 3)
        d.add_paragraph(r.statement).runs[0].bold = True
        for label, value in (("Source", f"{r.source_stakeholder} {('- ' + r.source_document) if r.source_document else ''}"), ("Evidence", f'"{r.source_excerpt}"' if r.source_excerpt else ""),
                             ("Justification", r.business_justification or ""), ("Confidence", f"{r.confidence_score:.0%}")):
            if value.strip():
                d.add_paragraph(f"{label}: {value}")
        for c in r.acceptance_criteria:
            d.add_paragraph(c, style="List Bullet")
        for mp in r.regulations:
            d.add_paragraph(f"{mp.citation} ({mp.jurisdiction}, {mp.confidence:.0%})" + (" - needs legal review" if mp.needs_legal_review else ""), style="List Bullet 2")
    d.add_heading("4. Regulatory control coverage", 1)
    t = d.add_table(rows=1, cols=3)
    t.style = "Light Grid Accent 1"
    for cell, text in zip(t.rows[0].cells, ["Control", "Status", "Regulations"]):
        cell.text = text
    for c in b.analysis.get("controls", []):
        row = t.add_row().cells
        row[0].text, row[1].text, row[2].text = c["title"], c["status"], "; ".join(c["regulations"])
    sdlc = b.analysis.get("sdlc")
    if sdlc:
        d.add_heading("5. Recommended SDLC", 1)
        d.add_paragraph(f"{sdlc['chosen']}: " + (sdlc.get("narrative") or {}).get("explanation", ""))
        for i, o in enumerate(sdlc["ranking"], 1):
            d.add_paragraph(f"{i}. {o['model']} - {o['score']:.0f}%", style="List Number")
    d.add_heading("6. Open issues", 1)
    for line in open_issues_markdown(b).split("\n"):
        if line.startswith("- "):
            d.add_paragraph(line[2:].replace("**", ""), style="List Bullet")
    buffer = io.BytesIO()
    d.save(buffer)
    return buffer.getvalue()


# --------------------------------------------------------------------------------- ZIP
def build_files(b: Bundle) -> dict[str, bytes | str]:
    state = {
        "project": b.project,
        "requirements": [r.model_dump(mode="json") for r in b.requirements],
        "questions": [q.model_dump(mode="json") for q in b.questions],
        "analysis": b.analysis,
        "gates": b.gates,
    }
    return {
        "SRS.docx": srs_docx(b),
        "SRS.md": srs_markdown(b),
        "requirements_report.md": requirements_report_markdown(b),
        "user_stories.md": user_stories_markdown(b),
        "use_cases.md": use_cases_markdown(b),
        "sdlc_workflow.md": sdlc_workflow_markdown(b),
        "assumptions_dependencies_open_issues.md": open_issues_markdown(b),
        "requirements_traceability_matrix.csv": traceability_csv(b),
        "compliance_control_matrix.csv": compliance_matrix_csv(b),
        "control_coverage.csv": control_coverage_csv(b),
        "risk_register.csv": risk_register_csv(b),
        "audit_log.jsonl": "\n".join(json.dumps(e, ensure_ascii=False) for e in b.audit) + "\n",
        "project_state.json": json.dumps(state, indent=2, ensure_ascii=False, default=str),
    }


def build_zip(b: Bundle) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in build_files(b).items():
            z.writestr(name, content)
    return buffer.getvalue()
