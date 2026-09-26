# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

**Agentic AI Requirement-Gathering & SDLC Recommendation System — Payment Processing**

A multi-agent system that ingests stakeholder input (interviews, policy docs, regulatory
text) about a payment-processing feature, extracts and validates structured software
requirements, maps them to payment regulations, and recommends an SDLC approach with a
generated project workflow. This is a college course project — favor a working,
demonstrable MVP over production hardening. Scope is deliberately narrowed to ONE
financial sector (payment processing) out of the eight named in the original problem
statement.

## Reference use case

Anchor all sample data, prompts, and demos on this scenario unless told otherwise:

> A bank wants to add step-up authentication for payments above a risk threshold, and
> needs requirements gathered from business, security, and compliance stakeholders,
> checked against payment regulations (PCI-DSS, RBI payment/authentication guidelines),
> and turned into an SRS with a recommended SDLC approach.

Sample stakeholder transcripts, policy snippets, and regulation excerpts for this
scenario live in `data/sample_inputs/`. Add more scenarios later only after this one
works end-to-end.

## Architecture (5 layers, per the course problem statement)

1. **Input layer** — sample transcripts / policy docs / regulation text (`data/`)
2. **Multi-agent layer** — `src/agents/`, one file per agent, orchestrated by `src/orchestration/pipeline.py`
3. **Knowledge & retrieval layer** — `src/knowledge_base/` (ChromaDB + retriever), holds
   payment regulations, bank policies, requirement templates
4. **Human-in-the-loop layer** — approval gate in the Streamlit UI (`src/ui/app.py`);
   nothing reaches "approved" status without an explicit click
5. **Output layer** — generated SRS, user stories, traceability matrix, SDLC workflow
   written to `docs/generated/`

## Agents to implement (`src/agents/`)

Each agent is a small class/function with a single `run(input) -> output` interface,
calling the Anthropic API with a system prompt that forces structured JSON output.
Log every agent call (input, output, timestamp) to the audit table for traceability.

| File | Responsibility |
|---|---|
| `coordinator.py` | Orchestrates the pipeline, passes shared context between agents |
| `stakeholder_interaction.py` | Turns a raw transcript into structured Q&A; asks a follow-up question when an answer is vague |
| `extraction.py` | Pulls candidate requirement statements from transcripts/docs |
| `clarification.py` | Flags incomplete/ambiguous requirements, sends them back |
| `classification.py` | Multi-label tags: functional, security, compliance, performance, etc. |
| `conflict_detection.py` | Flags contradicting or duplicate requirements |
| `compliance.py` | Maps requirements to PCI-DSS / RBI clauses via the retriever; never makes a final legal call, only proposes with citation + confidence |
| `security_privacy.py` | Flags implicit security/privacy needs (encryption, auth, data retention) |
| `risk_analysis.py` | Scores business/technical/compliance risk per requirement |
| `sdlc_selection.py` | Recommends SDLC model(s) with ranked confidence, from project characteristics |
| `documentation.py` | Generates SRS.md, user_stories.md, traceability_matrix.csv |
| `validation.py` | Final completeness/consistency check before human review |
| `human_approval.py` | Not an LLM call — just the data contract for what the UI needs to render an approval decision |

## Data model

Requirement fields (see `src/models/requirement.py`, Pydantic + SQLAlchemy):
`id, statement, category (list), source_stakeholder, business_justification, priority,
dependencies, assumptions, acceptance_criteria, applicable_regulations, risk_level,
confidence_score, approval_status`.

Store requirements and the audit log in SQLite (`src/models/db.py`) — no need for
Postgres at this scale.

## Tech stack (decided — don't re-litigate unless asked)

- Python 3.11, `anthropic` SDK for all agent LLM calls
- ChromaDB (local, persistent) for the knowledge base / RAG
- SQLite via SQLAlchemy for structured requirements + audit log
- FastAPI for the backend API (`src/api/main.py`)
- Streamlit for the demo UI (`src/ui/app.py`) — fast to build, good enough for a course
  demo; not React, don't suggest rewriting it
- Pydantic for all structured LLM outputs and data contracts
- pytest for tests

## Conventions

- Type hints everywhere; docstrings on every public function/class
- Every agent's LLM call must request JSON-only output and validate it against a
  Pydantic model before returning — never pass raw LLM text downstream
- No agent silently drops data on a parse failure — log it and raise, don't swallow
- Secrets in `.env` (see `.env.example`), never hardcoded
- Keep each agent file under ~150 lines; if an agent is doing too much, that's a sign
  it should be two agents

## Build order (milestones — build and demo each before moving to the next)

1. Data model + SQLite + one sample transcript ingested manually
2. Coordinator + extraction + classification agents working on that one transcript
3. Knowledge base populated with PCI-DSS/RBI excerpts + compliance agent doing RAG lookups
4. Clarification, conflict-detection, security/privacy, risk-analysis agents
5. SDLC selection agent + documentation agent (SRS/user stories/traceability output)
6. Streamlit UI with the human-approval gate wired to the SQLite approval_status field
7. End-to-end demo: raw transcript in → approved SRS + SDLC recommendation out

## Out of scope for this project

- The other 7 financial sectors from the original problem statement
- Real production security hardening (RBAC/MFA/encryption are a "describe in the report"
  item, not a "build a real auth system" item, unless explicitly asked to implement them)
- Multi-tenant / multi-organization support
