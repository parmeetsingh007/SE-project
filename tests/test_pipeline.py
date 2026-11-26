import pytest

from src.agents.extraction import Candidate
from src.agents.llm_client import RateLimitedError
from src.knowledge_base.kb import KnowledgeBase
from src.models.db import (
    Base,
    SessionLocal,
    add_document,
    create_project,
    engine,
    get_project,
    load_questions,
    load_requirements,
)
from src.pipeline.jobs import Job
from src.pipeline.runner import Pipeline
from tests.fakes import (
    Calls,
    FakeAdvisor,
    FakeClassification,
    FakeCompliance,
    FakeConflicts,
    FakeCriteria,
    FakeExtraction,
    FakeQuality,
    FakeRefinement,
    FakeRisk,
    FakeSecurity,
)

CANDIDATES = [
    Candidate(statement="The system shall verify customer identity before account opening.", source_stakeholder="Product owner",
              source_excerpt="we must verify who the customer is", business_justification="Regulatory duty", unclear=["which documents"]),
    Candidate(statement="The system shall complete onboarding fast.", source_stakeholder="Sales head",
              source_excerpt="it should be fast", assumptions=["Customers are impatient"], unclear=["no target time"]),
]


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def make(db, *, risk_fail=False):
    calls = Calls()
    pipeline = Pipeline(
        kb=KnowledgeBase(backend="lexical"),
        extraction=FakeExtraction(calls, CANDIDATES),
        classification=FakeClassification(calls),
        quality=FakeQuality(calls),
        conflicts=FakeConflicts(calls),
        compliance=FakeCompliance(calls),
        security=FakeSecurity(calls),
        criteria=FakeCriteria(calls),
        risk=FakeRisk(calls, fail_first=risk_fail),
        refinement=FakeRefinement(calls),
        advisor=FakeAdvisor(calls),
    )
    project = create_project(db, "Test KYC project", jurisdictions=["IN", "GLOBAL"])
    add_document(db, project.id, "Interview", "we must verify who the customer is. it should be fast.")
    return pipeline, calls, project.id


def test_full_analysis_produces_every_artefact(db) -> None:
    pipeline, calls, pid = make(db)
    job = Job(id="j", project_id=pid, kind="analyse")
    pipeline.analyse(pid, db, job)

    requirements = load_requirements(db, pid)
    stated = [r for r in requirements if r.origin == "stated"]
    derived = [r for r in requirements if r.origin == "derived"]
    assert len(stated) == 2
    assert all(r.ref.startswith("KYC-") for r in requirements)
    assert len({r.ref for r in requirements}) == len(requirements)
    assert derived, "control gaps and security analysis should add derived requirements"
    assert all(r.acceptance_criteria and r.risk_level for r in requirements)

    weak = [r for r in stated if r.is_weak]
    questions = load_questions(db, pid)
    assert len(weak) == 1 and len(questions) == 1 and questions[0].requirement_id == weak[0].id

    analysis = get_project(db, pid).analysis
    assert analysis["sdlc"]["ranking"] and analysis["sdlc"]["workflow"]
    assert len(analysis["sdlc"]["factors"]) == 14
    assert analysis["controls"] and analysis["risks"] and analysis["threats"]
    assert analysis["guard"]["ungrounded_requirements"] == 1
    assert analysis["validation"]["gates"]
    assert all(step.status in {"done", "skipped"} for step in job.steps)


def test_rerun_with_nothing_new_makes_no_model_calls(db) -> None:
    pipeline, calls, pid = make(db)
    pipeline.analyse(pid, db, Job(id="j1", project_id=pid, kind="analyse"))
    before = dict(calls.counts)

    pipeline.analyse(pid, db, Job(id="j2", project_id=pid, kind="analyse"))
    assert calls.counts == before


def test_answering_a_question_refines_and_rechecks_only_that_requirement(db) -> None:
    pipeline, calls, pid = make(db)
    pipeline.analyse(pid, db, Job(id="j1", project_id=pid, kind="analyse"))

    question = load_questions(db, pid)[0]
    from src.models.db import get_question

    row = get_question(db, pid, question.id)
    row.status, row.answer = "answered", "Within 5 seconds for 95% of customers"
    db.commit()

    extraction_before = calls["extraction"]
    pipeline.apply_answers(pid, db, Job(id="j2", project_id=pid, kind="apply_answers"))

    assert calls["refinement"] == 1
    assert calls["extraction"] == extraction_before, "answering must not re-extract"
    updated = next(r for r in load_requirements(db, pid) if r.id == question.requirement_id)
    assert "within 5 seconds" in updated.statement
    assert not updated.is_weak
    assert "Within 5 seconds" in updated.acceptance_criteria[0], "answers feed the acceptance criteria"
    reloaded = load_questions(db, pid)[0]
    assert reloaded.applied and reloaded.status == "answered"


def test_failure_midway_resumes_without_redoing_earlier_stages(db) -> None:
    pipeline, calls, pid = make(db, risk_fail=True)
    with pytest.raises(RateLimitedError):
        pipeline.analyse(pid, db, Job(id="j1", project_id=pid, kind="analyse"))
    assert calls["extraction"] == 1 and calls["risk"] == 1

    pipeline.analyse(pid, db, Job(id="j2", project_id=pid, kind="analyse"))
    assert calls["extraction"] == 1, "extraction must not repeat after a later stage failed"
    assert calls["classification"] == 1 and calls["compliance"] >= 1
    assert all(r.risk_level for r in load_requirements(db, pid))


def test_applying_answers_without_any_answer_is_an_error(db) -> None:
    pipeline, _, pid = make(db)
    pipeline.analyse(pid, db, Job(id="j1", project_id=pid, kind="analyse"))
    with pytest.raises(ValueError):
        pipeline.apply_answers(pid, db, Job(id="j2", project_id=pid, kind="apply_answers"))


def test_audit_chain_records_the_run_and_verifies(db) -> None:
    from src.models import audit

    pipeline, _, pid = make(db)
    pipeline.analyse(pid, db, Job(id="j1", project_id=pid, kind="analyse"))
    ok, checked, bad = audit.verify_chain(db, pid)
    assert ok and checked >= 1 and bad is None


def test_conflicts_survive_reruns_until_an_involved_requirement_changes(db) -> None:
    from src.models.db import get_question
    from tests.fakes import FakeConflictsFirstRunOnly

    pipeline, calls, pid = make(db)
    pipeline.conflicts = FakeConflictsFirstRunOnly(calls)
    pipeline.analyse(pid, db, Job(id="j1", project_id=pid, kind="analyse"))
    first = get_project(db, pid).analysis["conflicts"]
    assert len(first) == 1

    # an unrelated re-run (the model now reports nothing) must not erase the conflict
    from src.models.db import add_document

    add_document(db, pid, "More notes", "we must verify who the customer is.")
    pipeline.analyse(pid, db, Job(id="j2", project_id=pid, kind="analyse"))
    assert [c["id"] for c in get_project(db, pid).analysis["conflicts"]] == [first[0]["id"]]

    # changing a requirement that is part of the conflict drops it (it must be re-judged)
    weak = next(q for q in load_questions(db, pid))
    row = get_question(db, pid, weak.id)
    row.status, row.answer = "answered", "Within 5 seconds"
    db.commit()
    involved = set(first[0]["requirement_ids"])
    if weak.requirement_id in involved:
        pipeline.apply_answers(pid, db, Job(id="j3", project_id=pid, kind="apply_answers"))
        assert get_project(db, pid).analysis["conflicts"] == []


def test_demo_export_and_import_roundtrip_makes_no_model_calls(db, tmp_path, monkeypatch) -> None:
    from src import demos
    from src.models.db import get_question

    monkeypatch.setattr(demos, "DEMO_DIR", tmp_path)
    pipeline, calls, pid = make(db)
    pipeline.analyse(pid, db, Job(id="j1", project_id=pid, kind="analyse"))
    # human state must not leak into the demo
    reqs = load_requirements(db, pid)
    reqs[0].approval_status = __import__("src.models.requirement", fromlist=["ApprovalStatus"]).ApprovalStatus.APPROVED
    from src.models.db import save_requirements

    save_requirements(db, pid, reqs)
    q = load_questions(db, pid)[0]
    row = get_question(db, pid, q.id)
    row.status, row.answer = "answered", "x"
    db.commit()

    demos.export_demo(db, pid, "sample")
    before = dict(calls.counts)
    imported = demos.import_demo(db, "sample")
    imported_again = demos.import_demo(db, "sample")

    assert imported.id not in (pid, imported_again.id)
    new_reqs = load_requirements(db, imported.id)
    assert len(new_reqs) == len(reqs) and all(r.approval_status.value == "pending" for r in new_reqs)
    assert {r.id for r in new_reqs}.isdisjoint({r.id for r in reqs}), "ids must be fresh"
    assert all(q.status == "open" for q in load_questions(db, imported.id))
    a = get_project(db, imported.id).analysis
    assert a["sdlc"]["ranking"] and a["controls"]
    new_ids = {r.id for r in new_reqs}
    assert all(x["requirement_id"] in new_ids for x in a["risks"]), "analysis references must point at the new ids"
    assert calls.counts == before, "importing a demo must not call any model"
    assert demos.list_demos()[0]["id"] == "sample"


def test_risk_rows_of_replaced_requirements_do_not_linger(db) -> None:
    """When a requirement changes, the system's pending derived requirements are regenerated;
    risk rows that pointed at the deleted ones must not stay behind."""
    from src.models.db import get_question

    pipeline, calls, pid = make(db)
    pipeline.analyse(pid, db, Job(id="j1", project_id=pid, kind="analyse"))
    q = load_questions(db, pid)[0]
    row = get_question(db, pid, q.id)
    row.status, row.answer = "answered", "Within 5 seconds"
    db.commit()
    pipeline.apply_answers(pid, db, Job(id="j2", project_id=pid, kind="apply_answers"))

    live_ids = {r.id for r in load_requirements(db, pid)}
    risks = get_project(db, pid).analysis["risks"]
    assert risks and all(x["requirement_id"] in live_ids for x in risks)
