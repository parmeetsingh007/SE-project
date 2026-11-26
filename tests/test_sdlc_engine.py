"""The SDLC engine must tell clearly different project situations apart."""

from src.models.requirement import Factor
from src.sdlc.engine import FACTOR_KEYS, MODELS, build_signals, extract_factors, rank_models
from src.sdlc.workflow import TEMPLATES, WorkflowContext, build_workflow
from src.models.requirement import Category, Requirement, RiskItem


def _factors(**scores: int) -> list[Factor]:
    return [Factor(key=k, label=k, score=scores[k], evidence="") for k in FACTOR_KEYS]


VAGUE_UNCERTAIN = dict(stability=1, regulatory=5, security=4, complexity=3, size=2, legacy=2, change=4, continuous_delivery=2,
                       stakeholder_availability=3, documentation=4, schedule=2, verification=4, failure_consequence=4, technical_uncertainty=5)
STABLE_REGULATED = dict(stability=5, regulatory=5, security=3, complexity=3, size=3, legacy=3, change=1, continuous_delivery=1,
                        stakeholder_availability=2, documentation=5, schedule=2, verification=5, failure_consequence=5, technical_uncertainty=1)
VOLATILE_LOW_REG = dict(stability=2, regulatory=2, security=2, complexity=3, size=3, legacy=1, change=5, continuous_delivery=4,
                        stakeholder_availability=5, documentation=2, schedule=4, verification=1, failure_consequence=2, technical_uncertainty=3)
REGULATED_EVOLVING = dict(stability=3, regulatory=5, security=4, complexity=4, size=4, legacy=3, change=5, continuous_delivery=3,
                          stakeholder_availability=4, documentation=4, schedule=3, verification=4, failure_consequence=4, technical_uncertainty=2)
SECURE_CD = dict(stability=3, regulatory=3, security=5, complexity=3, size=4, legacy=3, change=4, continuous_delivery=5,
                 stakeholder_availability=3, documentation=3, schedule=4, verification=3, failure_consequence=4, technical_uncertainty=3)


def test_vague_uncertain_project_gets_spiral() -> None:
    assert rank_models(_factors(**VAGUE_UNCERTAIN))[0].model == "Spiral"


def test_stable_regulated_project_gets_plan_driven_model() -> None:
    assert rank_models(_factors(**STABLE_REGULATED))[0].model in {"V-Model", "Waterfall"}


def test_volatile_low_regulation_project_gets_agile() -> None:
    assert rank_models(_factors(**VOLATILE_LOW_REG))[0].model == "Agile (Scrum/Kanban)"


def test_regulated_but_evolving_project_gets_a_hybrid() -> None:
    assert rank_models(_factors(**REGULATED_EVOLVING))[0].model in {"Agile-V hybrid", "Agile-DevSecOps hybrid"}


def test_secure_continuous_delivery_gets_devsecops_family() -> None:
    assert rank_models(_factors(**SECURE_CD))[0].model in {"DevSecOps", "Agile-DevSecOps hybrid"}


def test_ranking_is_complete_sorted_and_scores_are_distinct() -> None:
    ranked = rank_models(_factors(**VAGUE_UNCERTAIN))
    assert {o.model for o in ranked} == set(MODELS)
    scores = [o.score for o in ranked]
    assert scores == sorted(scores, reverse=True)
    assert len(set(scores)) > 3
    assert all(0 <= s <= 100 for s in scores)


def test_ranking_is_deterministic() -> None:
    assert rank_models(_factors(**VAGUE_UNCERTAIN)) == rank_models(_factors(**VAGUE_UNCERTAIN))


def test_extracted_factors_react_to_vagueness_in_the_inputs() -> None:
    def requirements(weak: bool) -> list[Requirement]:
        return [
            Requirement(statement=f"The system shall do thing {i}.", ref=f"FR-{i}", categories=[Category.FUNCTIONAL], is_weak=weak)
            for i in range(6)
        ]

    risks: list[RiskItem] = []
    vague_text = ["We are not sure what we want. Maybe a pilot, probably changes later, unknown feasibility, to be decided."]
    firm_text = ["The requirements are final and approved."]

    vague = {f.key: f.score for f in extract_factors(build_signals(requirements(True), [], [], risks, vague_text))}
    firm = {f.key: f.score for f in extract_factors(build_signals(requirements(False), [], [], risks, firm_text))}

    assert vague["stability"] < firm["stability"]
    assert vague["technical_uncertainty"] > firm["technical_uncertainty"]


def test_every_model_has_a_workflow_with_gates() -> None:
    ctx = WorkflowContext(open_questions=2, open_conflicts=1, control_gaps=["Sanctions screening"], jurisdictions=["IN"])
    for model in MODELS:
        assert model in TEMPLATES
        phases = build_workflow(model, ctx)
        assert len(phases) >= 4
        assert all(p.approval_gate and p.exit_criteria and p.activities for p in phases)
        assert any("Sanctions screening" in c for c in phases[0].compliance_checkpoints)
        assert any("open clarification" in a for a in phases[0].activities)


def test_explicit_finality_language_outweighs_vagueness_flags() -> None:
    """A signed-off business document is stable even if the quality agent wants more detail."""
    reqs = [Requirement(statement=f"The system shall do thing {i}.", ref=f"FR-{i}", categories=[Category.FUNCTIONAL, Category.REGULATORY], is_weak=(i % 2 == 0)) for i in range(10)]
    final_text = ["Policy version 3.1 is final and approved by the board. Scope was signed off by the steering committee and is fixed. The regulator's schedule is mandated and unchanged."]
    vague_text = ["We are not sure yet. Maybe later, probably changes, to be decided."]

    firm = {f.key: f.score for f in extract_factors(build_signals(reqs, [], [], [], final_text))}
    unsure = {f.key: f.score for f in extract_factors(build_signals(reqs, [], [], [], vague_text))}
    assert firm["stability"] >= 4 and unsure["stability"] <= 2
    assert rank_models(extract_factors(build_signals(reqs, [], [], [], final_text)))[0].model in {"Waterfall", "V-Model"}
