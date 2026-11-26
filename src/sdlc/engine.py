"""Deterministic SDLC selection: decision factors -> hard rules -> weighted multi-criteria fit.

Scores never come from the language model. Every factor carries the evidence behind its
score, so the ranking can be audited and reproduced; the model only writes the narrative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.models.requirement import (
    Category,
    Conflict,
    ControlCoverage,
    Factor,
    Requirement,
    RiskItem,
    SdlcOption,
)

FACTOR_KEYS = [
    "stability",
    "regulatory",
    "security",
    "complexity",
    "size",
    "legacy",
    "change",
    "continuous_delivery",
    "stakeholder_availability",
    "documentation",
    "schedule",
    "verification",
    "failure_consequence",
    "technical_uncertainty",
]

LABELS = {
    "stability": "Requirement stability",
    "regulatory": "Regulatory criticality",
    "security": "Security risk",
    "complexity": "Project complexity",
    "size": "System size",
    "legacy": "Legacy-system dependence",
    "change": "Expected frequency of change",
    "continuous_delivery": "Need for continuous delivery",
    "stakeholder_availability": "Stakeholder availability",
    "documentation": "Documentation and testing demand",
    "schedule": "Budget and schedule pressure",
    "verification": "Need for formal verification",
    "failure_consequence": "Consequence of failure",
    "technical_uncertainty": "Technical uncertainty",
}

HEDGES = [
    "not sure", "unsure", "don't know", "do not know", "dont know", "tbd", "to be decided", "undecided",
    "haven't decided", "have not decided", "not decided", "maybe", "probably", "might", "we'll see",
    "figure out", "unknown", "depends", "not clear", "unclear", "no idea", "hard to say", "yet to",
    "not finalised", "not finalized", "still open", "we'll decide", "decide later",
]
CHANGE_WORDS = [
    "change", "evolv", "iterate", "iteration", "pilot", "experiment", "prototype", "feedback", "incremental",
    "phase", "mvp", "frequently", "revise", "adjust", "refine", "may change", "will change", "new regulation",
    "regulation changes", "learn as we",
]
LEGACY_WORDS = [
    "legacy", "core banking", "mainframe", "existing system", "integrate with", "integration with",
    "third-party", "third party", "vendor", "registry", "ckyc", "cbs", "batch job", "old system", "api",
]
CD_WORDS = [
    "continuous", "ci/cd", "release often", "frequent release", "weekly release", "deploy", "devops",
    "automated pipeline", "automation", "rapid release",
]
SCHEDULE_WORDS = [
    "deadline", "go-live", "go live", "launch", "urgent", "tight", "quarter", "budget", "weeks", "by march",
    "by june", "by december", "regulator deadline", "time to market", "asap",
]
TECH_UNCERTAINTY_WORDS = [
    "feasib", "prototype", "proof of concept", "poc", "can we", "not sure if", "unproven", "new technology",
    "experimental", "research", "vendor evaluation", "unknown performance", "scalab",
]
FIRM_WORDS = [
    "final", "approved", "signed off", "signed-off", "board-approved", "fixed", "unchanged", "baselined",
    "steering committee", "regulator's schedule", "mandated", "stable", "agreed",
]
REG_WORDS = [
    "regulator", "regulatory", "rbi", "compliance", "audit", "mandatory", "policy", "pmla", "gdpr", "fatf",
    "retain", "retention", "sanction", "kyc", "aml", "central kyc", "fiu",
]
AVAIL_LOW = ["unavailable", "hard to reach", "too busy", "not available", "limited availability"]
AVAIL_HIGH = ["available", "weekly meeting", "embedded", "daily stand", "product owner is", "readily"]
VERIFICATION_WORDS = ["formal", "certif", "assurance", "independent test", "penetration", "validation", "sign-off", "sign off"]


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _score(unit: float) -> int:
    """Maps a 0-1 intensity onto the 1-5 scale."""
    return 1 + round(4 * _clamp(unit))


def _hits(text: str, words: list[str]) -> list[str]:
    return [w for w in words if w in text]


def _count(text: str, words: list[str]) -> int:
    return sum(text.count(w) for w in words)


@dataclass
class ProjectSignals:
    """Everything the factor extractor needs, gathered once."""

    requirements: list[Requirement]
    conflicts: list[Conflict]
    controls: list[ControlCoverage]
    risks: list[RiskItem]
    corpus: str  # lower-cased masked text of all inputs + requirement statements
    words: int


def build_signals(
    requirements: list[Requirement],
    conflicts: list[Conflict],
    controls: list[ControlCoverage],
    risks: list[RiskItem],
    document_texts: list[str],
) -> ProjectSignals:
    statements = " ".join(r.statement for r in requirements)
    corpus = (" ".join(document_texts) + " " + statements).lower()
    return ProjectSignals(
        requirements=requirements,
        conflicts=conflicts,
        controls=controls,
        risks=risks,
        corpus=corpus,
        words=max(len(re.findall(r"\w+", corpus)), 1),
    )


def extract_factors(signals: ProjectSignals) -> list[Factor]:
    """Scores the 14 decision factors 1-5, each with its evidence."""
    stated = [r for r in signals.requirements if r.origin == "stated"] or signals.requirements
    n = max(len(stated), 1)
    corpus = signals.corpus

    weak = sum(1 for r in stated if r.is_weak)
    weak_ratio = weak / n
    open_conflicts = [c for c in signals.conflicts if c.status == "open"]
    conflict_ratio = len(open_conflicts) / n
    hedge_n = _count(corpus, HEDGES)
    hedge_norm = _clamp((hedge_n / signals.words * 1000) / 10)
    change_n = _count(corpus, CHANGE_WORDS)
    change_norm = _clamp((change_n / signals.words * 1000) / 12)
    firm_n = _count(corpus, FIRM_WORDS)
    firm_norm = _clamp((firm_n / signals.words * 1000) / 5)
    # explicit "final / approved / signed off" language discounts vagueness flags: the quality
    # agent asks for more detail than a finished business document naturally contains
    instability = _clamp(0.55 * weak_ratio * (1 - 0.6 * firm_norm) + 0.6 * conflict_ratio + 0.5 * hedge_norm + 0.25 * change_norm - 0.25 * firm_norm)

    mapped = sum(1 for r in stated if r.regulations)
    reg_cat = sum(1 for r in stated if {Category.REGULATORY, Category.PRIVACY, Category.AUDIT} & set(r.categories))
    reg_density = _clamp(max(mapped, reg_cat) / n)
    applicable = [c for c in signals.controls if c.status != "not_applicable"]
    needed_share = len(applicable) / max(len(signals.controls), 1)
    high_impact = sum(1 for r in stated if any(m.needs_legal_review for m in r.regulations)) / n
    reg_word_norm = _clamp((_count(corpus, REG_WORDS) / signals.words * 1000) / 25)
    regulatory = _score(0.4 * reg_density + 0.25 * needed_share + 0.15 * _clamp(high_impact * 2) + 0.2 * reg_word_norm)

    sec_share = sum(1 for r in stated if {Category.SECURITY, Category.PRIVACY} & set(r.categories)) / n
    high_risk = [r for r in stated if r.risk_level and r.risk_level.value == "high"]
    high_share = len(high_risk) / n
    security = _score(0.5 * sec_share + 0.5 * high_share + 0.1)

    integ = sum(1 for r in stated if Category.INTEGRATION in r.categories) / n
    complexity = _score(0.45 * _clamp(n / 28) + 0.3 * integ + 0.25 * _clamp(conflict_ratio * 3))
    size = _score(_clamp(n / 30))

    legacy_hits = _hits(corpus, LEGACY_WORDS)
    legacy = min(5, 1 + len(legacy_hits))
    change = _score(0.55 * change_norm + 0.45 * instability)
    cd_hits = _hits(corpus, CD_WORDS)
    cd = min(5, 1 + len(cd_hits)) if cd_hits else 2

    availability = 3
    availability_note = "No statement about stakeholder availability; assumed moderate."
    if _hits(corpus, AVAIL_LOW):
        availability, availability_note = 2, "Inputs mention limited stakeholder availability."
    elif _hits(corpus, AVAIL_HIGH):
        availability, availability_note = 4, "Inputs suggest stakeholders are available for ongoing involvement."

    audit_share = sum(1 for r in stated if Category.AUDIT in r.categories) / n
    documentation = _score(0.6 * (regulatory - 1) / 4 + 0.4 * _clamp(audit_share * 3))
    schedule_hits = _hits(corpus, SCHEDULE_WORDS)
    schedule = min(5, 1 + len(schedule_hits)) if schedule_hits else 2
    verification_hits = _hits(corpus, VERIFICATION_WORDS)
    verification = _score(0.55 * (regulatory - 1) / 4 + 0.25 * (security - 1) / 4 + 0.2 * _clamp(len(verification_hits) / 3))
    impacts = [x.impact for x in signals.risks] or [3]
    failure = _score(0.5 * high_share + 0.5 * ((sum(impacts) / len(impacts)) - 1) / 4)
    tech_hits = _hits(corpus, TECH_UNCERTAINTY_WORDS)
    technical = _score(0.45 * hedge_norm + 0.3 * weak_ratio + 0.25 * _clamp(len(tech_hits) / 3))

    evidence = {
        "stability": f"{weak} of {n} requirements are still vague, {len(open_conflicts)} open conflict(s), {hedge_n} hedging phrase(s) and {firm_n} finality phrase(s) (final, approved, signed off) in the inputs.",
        "regulatory": f"{mapped} of {n} requirements map to regulations; {len(applicable)} mandatory controls apply; {sum(1 for c in applicable if c.status == 'gap')} uncovered.",
        "security": f"{sec_share:.0%} of requirements are security/privacy; {len(high_risk)} rated high risk.",
        "complexity": f"{n} requirements, {integ:.0%} integration-related, {len(open_conflicts)} conflict(s).",
        "size": f"{n} stated requirements.",
        "legacy": f"Mentions: {', '.join(legacy_hits[:4]) or 'none found'}.",
        "change": f"{change_n} change/iteration phrase(s); instability index {instability:.2f}.",
        "continuous_delivery": f"Mentions: {', '.join(cd_hits[:4]) or 'no continuous-delivery language'}.",
        "stakeholder_availability": availability_note,
        "documentation": f"Regulatory criticality {regulatory}/5 and {audit_share:.0%} audit/reporting requirements demand traceable documentation.",
        "schedule": f"Mentions: {', '.join(schedule_hits[:4]) or 'no explicit deadline or budget pressure'}.",
        "verification": f"Derived from regulatory criticality ({regulatory}/5) and security risk ({security}/5); verification terms: {', '.join(verification_hits[:3]) or 'none'}.",
        "failure_consequence": f"{len(high_risk)} high-risk requirement(s); average impact {sum(impacts) / len(impacts):.1f}/5.",
        "technical_uncertainty": f"{hedge_n} hedging phrase(s), {weak_ratio:.0%} vague requirements; mentions: {', '.join(tech_hits[:3]) or 'none'}.",
    }
    stability = max(1, min(5, round(5 - 4 * instability)))
    values = {
        "stability": stability,
        "regulatory": regulatory,
        "security": security,
        "complexity": complexity,
        "size": size,
        "legacy": legacy,
        "change": change,
        "continuous_delivery": cd,
        "stakeholder_availability": availability,
        "documentation": documentation,
        "schedule": schedule,
        "verification": verification,
        "failure_consequence": failure,
        "technical_uncertainty": technical,
    }
    return [Factor(key=k, label=LABELS[k], score=values[k], evidence=evidence[k]) for k in FACTOR_KEYS]


# --------------------------------------------------------------------------- profiles
# ideal: the factor level at which this model fits best (1-5). weight: how much the factor matters.
MODELS: dict[str, dict] = {
    "Waterfall": {
        "ideal": dict(stability=5, regulatory=4, security=3, complexity=2, size=3, legacy=3, change=1, continuous_delivery=1,
                      stakeholder_availability=2, documentation=5, schedule=2, verification=3, failure_consequence=3, technical_uncertainty=1),
        "weight": dict(stability=2.5, change=2, technical_uncertainty=2, documentation=1.2),
    },
    "V-Model": {
        "ideal": dict(stability=4, regulatory=5, security=4, complexity=3, size=3, legacy=3, change=2, continuous_delivery=1,
                      stakeholder_availability=3, documentation=5, schedule=2, verification=5, failure_consequence=5, technical_uncertainty=2),
        "weight": dict(regulatory=2, verification=2, failure_consequence=1.5, documentation=1.5, stability=1.5),
    },
    "Spiral": {
        "ideal": dict(stability=1, regulatory=3, security=4, complexity=4, size=4, legacy=3, change=3, continuous_delivery=2,
                      stakeholder_availability=4, documentation=3, schedule=2, verification=3, failure_consequence=4, technical_uncertainty=5),
        "weight": dict(stability=2.5, technical_uncertainty=2.5, failure_consequence=1.5, stakeholder_availability=1.2),
    },
    "Agile (Scrum/Kanban)": {
        "ideal": dict(stability=2, regulatory=2, security=2, complexity=3, size=3, legacy=2, change=5, continuous_delivery=4,
                      stakeholder_availability=5, documentation=2, schedule=4, verification=1, failure_consequence=2, technical_uncertainty=3),
        "weight": dict(change=2, stakeholder_availability=1.5, regulatory=1.8, verification=1.5, failure_consequence=1.2),
    },
    "DevSecOps": {
        "ideal": dict(stability=3, regulatory=3, security=5, complexity=3, size=4, legacy=3, change=4, continuous_delivery=5,
                      stakeholder_availability=3, documentation=3, schedule=4, verification=3, failure_consequence=4, technical_uncertainty=3),
        "weight": dict(security=2, continuous_delivery=2.5, change=1.2),
    },
    "Agile-V hybrid": {
        "ideal": dict(stability=3, regulatory=5, security=4, complexity=4, size=4, legacy=3, change=4, continuous_delivery=3,
                      stakeholder_availability=4, documentation=4, schedule=3, verification=4, failure_consequence=4, technical_uncertainty=3),
        "weight": dict(regulatory=2, change=1.5, verification=1.5, documentation=1.2),
    },
    "Agile-DevSecOps hybrid": {
        "ideal": dict(stability=3, regulatory=4, security=5, complexity=4, size=4, legacy=3, change=4, continuous_delivery=4,
                      stakeholder_availability=4, documentation=3, schedule=4, verification=3, failure_consequence=4, technical_uncertainty=3),
        "weight": dict(security=2, regulatory=1.5, continuous_delivery=1.5, change=1.5),
    },
}


def _fit(scores: dict[str, int], model: dict) -> float:
    total_w = total_d = 0.0
    for key in FACTOR_KEYS:
        w = model["weight"].get(key, 1.0)
        total_w += w
        total_d += w * abs(scores[key] - model["ideal"][key]) / 4
    return 1 - total_d / total_w


def _hard_rules(s: dict[str, int]) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Returns (score adjustments in points, reasons per model)."""
    adj: dict[str, float] = {m: 0.0 for m in MODELS}
    why: dict[str, list[str]] = {m: [] for m in MODELS}

    def apply(models: dict[str, float], reason: str) -> None:
        for name, delta in models.items():
            adj[name] += delta
            why[name].append(("+" if delta > 0 else "") + f"{delta:g}: {reason}")

    if s["stability"] <= 2 and (s["technical_uncertainty"] >= 4 or s["failure_consequence"] >= 4):
        apply({"Spiral": 12, "Waterfall": -15, "V-Model": -8}, "unstable requirements with high uncertainty or failure cost need risk-driven iteration")
    if s["regulatory"] >= 4 and s["change"] >= 4:
        apply({"Agile-V hybrid": 8, "Agile-DevSecOps hybrid": 8, "Agile (Scrum/Kanban)": -10, "Waterfall": -8}, "high regulation combined with frequent change favours a regulated hybrid")
    if s["verification"] >= 4:
        apply({"Agile (Scrum/Kanban)": -12}, "strict verification needs rule out pure Agile")
    if s["stability"] >= 4 and s["change"] <= 2:
        apply({"Waterfall": 6, "V-Model": 5, "Spiral": -10, "Agile (Scrum/Kanban)": -10}, "stable requirements reward plan-driven models")
    if s["continuous_delivery"] >= 4 and s["security"] >= 4:
        apply({"DevSecOps": 6, "Agile-DevSecOps hybrid": 6}, "continuous delivery of a security-critical system needs pipeline security gates")
    if s["failure_consequence"] >= 4 and s["regulatory"] >= 4 and s["stability"] >= 3:
        apply({"V-Model": 4}, "costly failure under heavy regulation favours verification at every level")
    return adj, why


def rank_models(factors: list[Factor]) -> list[SdlcOption]:
    scores = {f.key: f.score for f in factors}
    adjustments, rule_reasons = _hard_rules(scores)
    options: list[SdlcOption] = []
    for name, profile in MODELS.items():
        fit = _fit(scores, profile)
        base = 100 * _clamp((fit - 0.35) / 0.65)
        final = round(_clamp((base + adjustments[name]) / 100) * 100, 1)
        # strongest agreements / disagreements, weighted
        diffs = sorted(
            FACTOR_KEYS, key=lambda k: abs(scores[k] - profile["ideal"][k]) / max(profile["weight"].get(k, 1.0), 0.1)
        )
        close = [k for k in diffs if abs(scores[k] - profile["ideal"][k]) <= 1][:3]
        far = [k for k in reversed(diffs) if abs(scores[k] - profile["ideal"][k]) >= 2][:2]
        reasons = [f"Fits: {LABELS[k]} is {scores[k]}/5 (ideal {profile['ideal'][k]})." for k in close]
        reasons += [f"Tension: {LABELS[k]} is {scores[k]}/5 (ideal {profile['ideal'][k]})." for k in far]
        reasons += [f"Rule {r}" for r in rule_reasons[name]]
        options.append(SdlcOption(model=name, score=final, reasons=reasons))
    options.sort(key=lambda o: -o.score)
    return options
