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

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from contextlib import contextmanager

from src.agents.coordinator import Coordinator
from src.agents.doc_renderers import write_requirements_report
from src.agents.human_approval import ApprovalDecision, apply_approval_decision
from src.agents.llm_client import RateLimitedError, set_status_sink
from src.agents.sdlc_selection import SDLCRecommendation
from src.models.db import (
    BatchORM,
    SessionLocal,
    get_batch,
    init_db,
    load_batches,
    load_requirements,
)
from src.models.requirement import ApprovalStatus, Requirement
from src.orchestration.generate_docs import generate_documentation
from src.ui.theme import CSS, batch_badge, category_badges, risk_badge, status_badge

DEFAULT_TRANSCRIPT = "data/sample_inputs/transcript_step_up_auth.txt"
DOCS_OUTPUT_DIR = Path("docs/generated")


def _write_requirements_report(db_session, batch_id: str) -> Path:
    """(Re)writes the all-requirements report for one batch, grouped by
    current approval_status. Called after every ingestion and every
    approve/send-back/reject click so it always reflects the latest state."""
    batch = get_batch(db_session, batch_id)
    label = _batch_label(batch) if batch else batch_id
    requirements = load_requirements(db_session, batch_id=batch_id)
    DOCS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return write_requirements_report(DOCS_OUTPUT_DIR, batch_id, label, requirements)


@contextmanager
def _live_status(spinner_text: str):
    """Wraps a block of Gemini calls with a spinner plus a placeholder that
    llm_client updates in real time while it's rate-limit-pacing or retrying
    — so a long wait (expected on the free tier) shows what it's doing
    instead of looking like the app has frozen."""
    placeholder = st.empty()
    set_status_sink(lambda message: placeholder.info(message))
    try:
        with st.spinner(spinner_text):
            yield
    finally:
        set_status_sink(None)
        placeholder.empty()

load_dotenv()
init_db()
st.set_page_config(page_title="Payment Requirements Review", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
st.markdown(
    """
    <div class="app-header">
        <h1>Payment-Processing Requirements</h1>
        <p>Multi-agent requirement gathering, compliance mapping &amp; the human approval gate</p>
    </div>
    """,
    unsafe_allow_html=True,
)


def _batch_label(batch: BatchORM) -> str:
    return f"{batch.created_at:%Y-%m-%d %H:%M} — {batch.transcript_preview[:40]}"


def _snapshot_run(coordinator: Coordinator, requirements: list[Requirement]) -> dict:
    """Captures one run()/resume() call's results for session_state, so the
    ingest tab's "just-processed" section works the same after either."""
    return {
        "batch_id": coordinator.last_batch_id,
        "requirements": requirements,
        "stakeholder_follow_ups": coordinator.stakeholder_follow_ups,
        "clarification": coordinator.clarification_issues,
        "security": coordinator.security_flags,
        "conflicts": coordinator.conflicts,
        "validation": {issue.requirement_id: issue for issue in coordinator.validation_issues},
    }


def _render_requirement_card(
    req: Requirement,
    key_prefix: str,
    clarification_issues: list | None = None,
    security_flags: list | None = None,
    validation_issue=None,
    batch_label: str | None = None,
    read_only: bool = False,
) -> None:
    with st.container(border=True):
        risk = req.risk_level.value if req.risk_level else "unscored"
        badges = (
            status_badge(req.approval_status.value)
            + risk_badge(risk)
            + category_badges([c.value for c in req.category])
        )
        if batch_label:
            badges += batch_badge(batch_label)
        st.markdown(badges, unsafe_allow_html=True)
        st.markdown(f'<div class="req-statement">{req.statement}</div>', unsafe_allow_html=True)

        with st.expander("Details"):
            st.write(f"**Source:** {req.source_stakeholder}")
            if req.business_justification:
                st.write(f"**Business justification:** {req.business_justification}")
            if req.applicable_regulations:
                st.write("**Applicable regulations:**")
                for citation in req.applicable_regulations:
                    st.write(f"- {citation}")
            if req.acceptance_criteria:
                st.write("**Acceptance criteria:**")
                for criterion in req.acceptance_criteria:
                    st.write(f"- {criterion}")
            if req.confidence_score:
                st.write(f"**Risk confidence:** {req.confidence_score:.0%}")
            if req.open_questions:
                st.write("**Open questions from extraction:**")
                for question in req.open_questions:
                    st.write(f"- {question}")
            for issue in clarification_issues or []:
                st.warning(
                    f"**Needs clarification:** {issue.issue}\n\n"
                    f"_Follow-up:_ {issue.follow_up_question}"
                )
            for flag in security_flags or []:
                st.info(
                    f"**Implicit security/privacy need:** {flag.concern}\n\n"
                    f"_Recommended:_ {flag.recommended_requirement}"
                )
            if validation_issue is not None:
                st.error("**Validation:** " + "; ".join(validation_issue.problems))

        if read_only:
            return

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
                    if req.batch_id:
                        _write_requirements_report(session, req.batch_id)
                finally:
                    session.close()
                # keep the in-memory "just processed" snapshot from the ingest
                # tab consistent with the DB, since it isn't reloaded on rerun
                last_run = st.session_state.get("last_run")
                if last_run:
                    for r in last_run["requirements"]:
                        if r.id == req.id:
                            r.approval_status = status
                st.rerun()


def _render_sdlc_cards(recommendations: list[SDLCRecommendation]) -> None:
    for i, rec in enumerate(recommendations, start=1):
        st.markdown(
            f"""
            <div class="sdlc-card">
                <h4>{i}. {rec.model} — <span class="confidence">{rec.confidence:.0%}</span></h4>
                <p>{rec.rationale}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_results(recommendations, output, approved_count: int, total: int) -> None:
    st.success(f"Documented {approved_count} approved requirement(s).")

    m1, m2, m3 = st.columns(3)
    m1.metric("Total requirements", total)
    m2.metric("Approved", approved_count)
    m3.metric("Approval rate", f"{approved_count / total:.0%}" if total else "0%")

    st.markdown("#### Recommended SDLC approach")
    _render_sdlc_cards(recommendations)

    with st.expander("View full SRS (Markdown)"):
        st.markdown(Path(output.srs_path).read_text(encoding="utf-8"))

    st.markdown("#### Traceability matrix")
    st.dataframe(pd.read_csv(output.traceability_csv_path), use_container_width=True)

    st.markdown("##### Download files (also written to `docs/generated/`)")
    for label, path in [
        ("Download SRS.md", output.srs_path),
        ("Download user_stories.md", output.user_stories_path),
        ("Download traceability_matrix.csv", output.traceability_csv_path),
    ]:
        with open(path, "rb") as f:
            st.download_button(label, f.read(), file_name=Path(path).name)


tab_ingest, tab_review, tab_history = st.tabs(
    ["Ingest transcript", "Review & approve", "History"]
)

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

        coordinator = Coordinator()
        with _live_status("Running the agent pipeline (this calls the Gemini API several times)..."):
            session = SessionLocal()
            try:
                requirements = coordinator.run(transcript_text, session)
            except RateLimitedError:
                st.session_state["failed_batch_id"] = coordinator.last_batch_id
                st.session_state.pop("last_run", None)
            else:
                st.session_state["last_run"] = _snapshot_run(coordinator, requirements)
                st.session_state.pop("failed_batch_id", None)
                report_path = _write_requirements_report(session, coordinator.last_batch_id)
                st.success(
                    f"Extracted {len(requirements)} requirements into a new batch. "
                    f"Requirements report: `{report_path}`"
                )
            finally:
                session.close()

    failed_batch_id = st.session_state.get("failed_batch_id")
    if failed_batch_id:
        st.error(
            "Gemini's free-tier quota (15 requests/minute) was exhausted and retries "
            "didn't recover in time. Progress up to this point has already been saved "
            "— click below to continue this batch once the quota resets (usually "
            "within a minute), rather than re-ingesting from scratch."
        )
        st.caption(f"Batch ID: `{failed_batch_id}`")
        if st.button("Resume ingestion"):
            coordinator = Coordinator()
            with _live_status("Resuming from the last completed requirement..."):
                session = SessionLocal()
                try:
                    requirements = coordinator.resume(failed_batch_id, session)
                except RateLimitedError:
                    st.error("Still rate-limited — wait a little longer and try Resume again.")
                else:
                    st.session_state["last_run"] = _snapshot_run(coordinator, requirements)
                    st.session_state.pop("failed_batch_id", None)
                    report_path = _write_requirements_report(session, failed_batch_id)
                    st.success(
                        f"Resumed and finished {len(requirements)} requirement(s). "
                        f"Requirements report: `{report_path}`"
                    )
                finally:
                    session.close()

    last_run = st.session_state.get("last_run")
    if last_run:
        st.caption(f"Batch ID: `{last_run['batch_id']}`")

        if last_run["stakeholder_follow_ups"]:
            with st.expander(
                f"Pre-extraction stakeholder follow-ups "
                f"({len(last_run['stakeholder_follow_ups'])}) — simulated adaptive "
                f"interviewing on the static transcript"
            ):
                for follow_up in last_run["stakeholder_follow_ups"]:
                    st.write(f'*"{follow_up.original_statement}"*')
                    st.write(f"→ {follow_up.follow_up_question}")
                    st.divider()

        st.markdown("### Just-processed requirements")
        for req in last_run["requirements"]:
            _render_requirement_card(
                req,
                key_prefix="ingest",
                clarification_issues=last_run["clarification"].get(req.id),
                security_flags=last_run["security"].get(req.id),
                validation_issue=last_run["validation"].get(req.id),
            )

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
        batches = load_batches(session)
    finally:
        session.close()

    batches_by_id = {batch.id: batch for batch in batches}

    if not all_requirements:
        st.info("No requirements yet — ingest a transcript first.")
    else:
        status_options = [s.value for s in ApprovalStatus]
        status_filter = st.multiselect("Filter by status", status_options, default=status_options)
        visible = [r for r in all_requirements if r.approval_status.value in status_filter]

        for req in visible:
            batch = batches_by_id.get(req.batch_id)
            _render_requirement_card(
                req, key_prefix="review", batch_label=_batch_label(batch) if batch else None
            )

        st.divider()
        st.subheader("Generate final output")
        st.caption("Scoped to one batch, so an old ingestion never pollutes a new one's SDLC recommendation.")

        batch_groups = []
        for batch in batches:  # already most-recent-first
            batch_reqs = [r for r in all_requirements if r.batch_id == batch.id]
            batch_approved = [r for r in batch_reqs if r.approval_status == ApprovalStatus.APPROVED]
            if batch_approved:
                batch_groups.append((batch, batch_reqs, batch_approved))

        if not batch_groups:
            st.write("No batch has an approved requirement yet.")
        else:
            labels = [
                f"{_batch_label(b)} — {len(appr)} approved / {len(reqs)} total"
                for b, reqs, appr in batch_groups
            ]
            chosen_i = st.selectbox(
                "Batch to generate for", range(len(batch_groups)), format_func=lambda i: labels[i]
            )
            chosen_batch, chosen_reqs, chosen_approved = batch_groups[chosen_i]

            session = SessionLocal()
            try:
                report_path = _write_requirements_report(session, chosen_batch.id)
            finally:
                session.close()
            st.download_button(
                "Download requirements report (all statuses)",
                data=report_path.read_text(encoding="utf-8"),
                file_name=report_path.name,
                mime="text/markdown",
            )

            if st.button("Generate & view results", type="primary"):
                with _live_status("Recommending an SDLC approach and drafting the SRS..."):
                    session = SessionLocal()
                    try:
                        recommendations, output = generate_documentation(
                            chosen_approved,
                            session,
                            batch_id=chosen_batch.id,
                            all_batch_requirements=chosen_reqs,
                        )
                    except RateLimitedError:
                        st.error(
                            "Gemini's free-tier quota (15 requests/minute) was exhausted "
                            "while generating this. Nothing was lost — wait a minute and "
                            "click 'Generate & view results' again."
                        )
                    else:
                        st.session_state["last_docs"] = {
                            "recommendations": recommendations,
                            "output": output,
                            "approved_count": len(chosen_approved),
                            "total": len(chosen_reqs),
                        }
                    finally:
                        session.close()

            last_docs = st.session_state.get("last_docs")
            if last_docs:
                _render_results(**last_docs)

with tab_history:
    st.subheader("Past ingestion batches")
    session = SessionLocal()
    try:
        batches = load_batches(session)
        all_requirements = load_requirements(session)
    finally:
        session.close()

    if not batches:
        st.info("No batches yet — ingest a transcript first.")
    else:
        for batch in batches:
            batch_reqs = [r for r in all_requirements if r.batch_id == batch.id]
            batch_approved = [r for r in batch_reqs if r.approval_status == ApprovalStatus.APPROVED]
            header = (
                f"{batch.created_at:%Y-%m-%d %H:%M} — {len(batch_approved)} approved / "
                f"{len(batch_reqs)} total — {batch.transcript_preview[:60]}"
            )
            with st.expander(header):
                st.write(f"**Transcript preview:** {batch.transcript_preview}")

                if batch.sdlc_recommendation:
                    st.markdown("**SDLC recommendation:**")
                    recs = [SDLCRecommendation.model_validate(d) for d in batch.sdlc_recommendation]
                    _render_sdlc_cards(recs)
                else:
                    st.caption("No SDLC recommendation generated yet for this batch.")

                st.markdown("**Requirements:**")
                for req in batch_reqs:
                    _render_requirement_card(
                        req, key_prefix=f"history-{batch.id}", read_only=True
                    )
