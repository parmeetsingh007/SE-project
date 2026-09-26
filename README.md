# Agentic AI Requirement-Gathering & SDLC Recommendation System

A multi-agent system that ingests stakeholder input about a payment-processing
feature, extracts and validates structured software requirements, maps them to
payment regulations, and recommends an SDLC approach with a generated project
workflow. Built as a college course project — a working, demonstrable MVP
scoped to one financial sector (payment processing).

## Reference use case

> A bank wants to add step-up authentication for payments above a risk
> threshold, and needs requirements gathered from business, security, and
> compliance stakeholders, checked against payment regulations (PCI-DSS, RBI
> payment/authentication guidelines), and turned into an SRS with a
> recommended SDLC approach.

A sample stakeholder transcript and paraphrased PCI-DSS/RBI excerpts for this
scenario live in [`data/sample_inputs/`](data/sample_inputs/).

## Architecture

1. **Input layer** — sample transcripts, policy docs, regulation excerpts (`data/`)
2. **Multi-agent layer** — one agent per file in [`src/agents/`](src/agents/),
   orchestrated by [`src/agents/coordinator.py`](src/agents/coordinator.py)
3. **Knowledge & retrieval layer** — [`src/knowledge_base/`](src/knowledge_base/)
   (ChromaDB + retriever) holding PCI-DSS/RBI excerpts for RAG-based compliance mapping
4. **Human-in-the-loop layer** — approval gate in the Streamlit UI
   ([`src/ui/app.py`](src/ui/app.py)); nothing reaches `approved` status
   without an explicit click
5. **Output layer** — generated SRS, user stories, and traceability matrix
   written to [`docs/generated/`](docs/generated/)

### Agents

| Agent | Responsibility |
|---|---|
| `coordinator.py` | Orchestrates the pipeline, passes shared context between agents |
| `extraction.py` | Pulls candidate requirement statements from a transcript |
| `classification.py` | Multi-label tags: functional, security, compliance, performance, usability |
| `compliance.py` | Maps requirements to PCI-DSS/RBI clauses via RAG; proposes with citation + confidence, never a final legal call |
| `clarification.py` | Flags incomplete/ambiguous requirements with concrete follow-up questions |
| `conflict_detection.py` | Flags contradicting or duplicate requirements across a batch |
| `security_privacy.py` | Flags implicit security/privacy needs (encryption, retention, access control) |
| `risk_analysis.py` | Scores business/technical/compliance risk per requirement |
| `sdlc_selection.py` | Recommends SDLC model(s) with ranked confidence, from project characteristics |
| `documentation.py` | Generates SRS.md, user_stories.md, traceability_matrix.csv |
| `human_approval.py` | Data contract for a reviewer decision — not an LLM call |

Every LLM-calling agent requests JSON-only output from Gemini and validates it
against a Pydantic model before it's used downstream (see
[`src/agents/llm_client.py`](src/agents/llm_client.py)). Every call is logged
to the `audit_log` table for traceability.

## Tech stack

Python 3.11 · `google-genai` (Gemini Flash) · ChromaDB · SQLAlchemy + SQLite ·
FastAPI · Streamlit · Pydantic · pytest

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in GOOGLE_API_KEY
```

## Usage

**1. Ingest a transcript** (extraction → classification → compliance →
clarification → security/privacy → risk analysis → conflict detection →
persistence to SQLite):

```bash
python -m src.orchestration.pipeline data/sample_inputs/transcript_step_up_auth.txt
```

**2. Review and approve requirements** — the human-in-the-loop gate:

```bash
streamlit run src/ui/app.py
```

Use the **Ingest transcript** tab to run the pipeline from the browser, and
the **Review & approve** tab to inspect each requirement (category, risk,
regulations, clarification questions, security/privacy flags) and click
**Approve** / **Send back for revision** / **Reject**. Nothing is final until
approved here.

**3. Generate the final output** — SDLC recommendation + SRS, from *approved*
requirements only (also available as a button in the Streamlit Review tab):

```bash
python -m src.orchestration.generate_docs
```

Writes `SRS.md`, `user_stories.md`, and `traceability_matrix.csv` to
[`docs/generated/`](docs/generated/).

## Tests

```bash
pytest
```

All agent tests mock the Gemini client, so the suite runs offline with no API
key required. `tests/conftest.py` points the suite at its own SQLite file, so
running tests never touches the real ingested data in
`sdlc_requirements.db`.

## Data model

`Requirement` (Pydantic + SQLAlchemy, see
[`src/models/requirement.py`](src/models/requirement.py) /
[`src/models/db.py`](src/models/db.py)):

```
id, statement, category (list), source_stakeholder, business_justification,
priority, dependencies, assumptions, acceptance_criteria,
applicable_regulations, risk_level, confidence_score, approval_status
```

## Out of scope

- The other 7 financial sectors from the original course problem statement
- Real production security hardening (RBAC/MFA/encryption are a "describe in
  the report" item, not a "build a real auth system" item)
- Multi-tenant / multi-organization support
