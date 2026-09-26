"""Streamlit UI: ingestion plus the human-in-the-loop review/approval gate.

This is the only place in the system allowed to set approval_status to
APPROVED (or REJECTED) — every write to it here comes from an explicit
button click, never automatically.
"""

from __future__ import annotations

import sys
from pathlib import Path

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
from dotenv import load_dotenv

from src.agents.coordinator import Coordinator
from src.agents.human_approval import ApprovalDecision, apply_approval_decision
from src.models.db import SessionLocal, init_db, load_requirements
from src.models.requirement import ApprovalStatus, Requirement

DEFAULT_TRANSCRIPT = "data/sample_inputs/transcript_step_up_auth.txt"

load_dotenv()
init_db()
st.set_page_config(page_title="Payment Requirements Review", layout="wide")
st.title("Payment-Processing Requirements — Review & Approval")


def _render_requirement_header(req: Requirement) -> str:
    categories = ", ".join(c.value for c in req.category) or "uncategorized"
    risk = req.risk_level.value if req.risk_level else "unscored"
    return f"[{req.approval_status.value}] ({categories}, risk={risk}) {req.statement}"


def _render_requirement_body(
    req: Requirement,
    clarification_issues: list | None = None,
    security_flags: list | None = None,
) -> None:
    st.write(f"**Source:** {req.source_stakeholder}")
    if req.business_justification:
        st.write(f"**Business justification:** {req.business_justification}")
    if req.applicable_regulations:
        st.write("**Applicable regulations:**")
        for citation in req.applicable_regulations:
            st.write(f"- {citation}")
    if req.confidence_score:
        st.write(f"**Risk confidence:** {req.confidence_score:.0%}")
    for issue in clarification_issues or []:
        st.warning(f"**Needs clarification:** {issue.issue}\n\n_Follow-up:_ {issue.follow_up_question}")
    for flag in security_flags or []:
        st.info(f"**Implicit security/privacy need:** {flag.concern}\n\n_Recommended:_ {flag.recommended_requirement}")


def _render_approval_controls(req: Requirement, key_prefix: str) -> None:
    cols = st.columns(3)
    actions = [
        ("Approve", ApprovalStatus.APPROVED, cols[0]),
        ("Send back for revision", ApprovalStatus.NEEDS_REVISION, cols[1]),
        ("Reject", ApprovalStatus.REJECTED, cols[2]),
    ]
    for label, status, col in actions:
        if col.button(label, key=f"{key_prefix}-{status.value}-{req.id}"):
            session = SessionLocal()
            try:
                apply_approval_decision(
                    ApprovalDecision(requirement_id=req.id, decision=status), session
                )
            finally:
                session.close()
            st.rerun()


tab_ingest, tab_review = st.tabs(["Ingest transcript", "Review & approve"])

with tab_ingest:
    st.subheader("Run the pipeline on a stakeholder transcript")
    uploaded = st.file_uploader("Upload a transcript (.txt)", type=["txt"])
    pasted = st.text_area("...or paste transcript text", height=200)

    if st.button("Run pipeline", type="primary"):
        if uploaded is not None:
            transcript_text = uploaded.read().decode("utf-8")
        elif pasted.strip():
            transcript_text = pasted
        else:
            with open(DEFAULT_TRANSCRIPT, encoding="utf-8") as f:
                transcript_text = f.read()

        with st.spinner("Running the agent pipeline (this calls the Gemini API several times)..."):
            session = SessionLocal()
            try:
                coordinator = Coordinator()
                requirements = coordinator.run(transcript_text, session)
            finally:
                session.close()

        st.session_state["last_run"] = {
            "requirements": requirements,
            "clarification": coordinator.clarification_issues,
            "security": coordinator.security_flags,
            "conflicts": coordinator.conflicts,
        }
        st.success(f"Extracted {len(requirements)} requirements.")

    last_run = st.session_state.get("last_run")
    if last_run:
        st.markdown("### Just-processed requirements")
        for req in last_run["requirements"]:
            with st.expander(_render_requirement_header(req)):
                _render_requirement_body(
                    req,
                    last_run["clarification"].get(req.id),
                    last_run["security"].get(req.id),
                )
                _render_approval_controls(req, key_prefix="ingest")

        if last_run["conflicts"]:
            st.markdown("### Conflicts detected")
            for conflict in last_run["conflicts"]:
                st.warning(
                    f"[{conflict.conflict_type}] {conflict.requirement_id_a[:8]} <-> "
                    f"{conflict.requirement_id_b[:8]}: {conflict.explanation}"
                )

with tab_review:
    st.subheader("All persisted requirements")
    session = SessionLocal()
    try:
        all_requirements = load_requirements(session)
    finally:
        session.close()

    if not all_requirements:
        st.info("No requirements yet — ingest a transcript first.")
    else:
        status_options = [s.value for s in ApprovalStatus]
        status_filter = st.multiselect("Filter by status", status_options, default=status_options)
        visible = [r for r in all_requirements if r.approval_status.value in status_filter]

        for req in visible:
            with st.expander(_render_requirement_header(req)):
                _render_requirement_body(req)
                _render_approval_controls(req, key_prefix="review")
