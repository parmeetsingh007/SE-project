"""Multi-label classification across the 13 requirement dimensions, plus a priority."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.agents.common import DOMAIN, JSON_ONLY, dumps
from src.agents.llm_client import call_agent_json
from src.models.requirement import Category, Priority, Requirement

CATEGORY_HELP = {
    "business": "business goals, products, customer journeys",
    "stakeholder": "expectations of a specific stakeholder group",
    "functional": "what the system does",
    "security": "authentication, access control, fraud and attack resistance, encryption",
    "privacy": "personal data, consent, minimisation, rights",
    "regulatory": "obligations from KYC/AML/data-protection law or regulator guidance",
    "performance": "speed, throughput, turnaround time",
    "availability": "uptime, resilience, recovery",
    "usability": "customer or staff experience, accessibility, friction",
    "data": "data quality, retention, storage, lineage",
    "integration": "external or legacy systems, registries, vendors, APIs",
    "audit": "logging, evidence, reporting, traceability",
    "operational": "support, monitoring, maintenance, deployment",
}

SYSTEM_PROMPT = f"""\
You are the classification agent for {DOMAIN}. You receive a JSON list of requirements, \
each with a "ref" and a "statement".

For each requirement assign ONE OR MORE categories from this fixed set (multi-label is \
expected - e.g. a consent requirement is usually "privacy" and "regulatory"):
{chr(10).join(f"- {k}: {v}" for k, v in CATEGORY_HELP.items())}

Also give a "primary" category (the single best fit, one of the assigned ones) and a \
"priority": "critical" (legal obligation or blocks launch), "high", "medium" or "low".

{JSON_ONLY}
{{"classifications": [{{"ref": str, "categories": [str], "primary": str, "priority": str}}]}}
Every input "ref" must appear exactly once.
"""


class ClassificationItem(BaseModel):
    ref: str
    categories: list[str] = Field(default_factory=list)
    primary: str = ""
    priority: str = "medium"


class ClassificationOutput(BaseModel):
    classifications: list[ClassificationItem]


def _valid_categories(values: list[str]) -> list[Category]:
    out: list[Category] = []
    for value in values:
        try:
            category = Category(value.strip().lower())
        except ValueError:
            continue
        if category not in out:
            out.append(category)
    return out


class ClassificationAgent:
    def run(self, requirements: list[Requirement], db_session: Session | None = None) -> None:
        """Sets categories, primary_category and priority on each requirement in place."""
        payload = [{"ref": r.ref, "statement": r.statement} for r in requirements]
        result = call_agent_json(
            agent_name="classification",
            system_prompt=SYSTEM_PROMPT,
            user_content=dumps(payload),
            output_model=ClassificationOutput,
            db_session=db_session,
        )
        by_ref = {item.ref: item for item in result.classifications}
        for requirement in requirements:
            item = by_ref.get(requirement.ref)
            categories = _valid_categories(item.categories) if item else []
            if not categories:
                categories = [Category.FUNCTIONAL]
            primary = _valid_categories([item.primary]) if item else []
            requirement.categories = categories
            requirement.primary_category = primary[0] if primary and primary[0] in categories else categories[0]
            if item:
                try:
                    requirement.priority = Priority(item.priority.strip().lower())
                except ValueError:
                    pass
