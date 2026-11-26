# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

**KYCompass**: an agentic AI system for requirement gathering, analysis and SDLC recommendation in
**customer onboarding and KYC**. It takes vague stakeholder input (pasted text or `.txt .md .eml
.docx .pdf`), extracts requirements, maps them to KYC / AML / data-protection regulations, scores
risk, asks *optional* clarification questions about weak requirements, recommends an SDLC with a
project-specific workflow, and produces an SRS and related artefacts behind human approval gates.

This is a college course project (problem statement: "Agentic AI ... requirement gathering,
analysis and SDLC identification in the financial sector"). Favour a working, demonstrable
product over production hardening. Scope is one sector: KYC / onboarding.

The previous incarnation (payment-processing, Streamlit) lives on `main` / earlier history; this
codebase replaced it on the `kyc-redesign` branch.

## Run, test

```bash
.venv/bin/uvicorn src.api.main:app --port 8000     # website + API at http://localhost:8000
.venv/bin/python -m pytest -q                       # fully offline; fake agents stand in for Gemini
```

`GOOGLE_API_KEY` goes in `.env` (see `.env.example`). Never hardcode or print it.

## Architecture

```
web (src/web, plain HTML/CSS/JS)  ->  FastAPI (src/api/main.py)  ->  Pipeline (src/pipeline/runner.py)
                                                                       -> agents (src/agents) -> Gemini
                                                                       -> SQLite (src/models/db.py)
```

* **Control flow is code, never the model.** `Pipeline._run` runs eleven stages in a fixed order:
  extract, classify, quality, compliance, controls, security, conflicts, criteria, risk, sdlc,
  validate. Each per-requirement stage records processed ids in `project.analysis["done"]`, so
  re-runs, answered questions, edits and retries after a quota error only do outstanding work.
* **Batch agents.** One model call handles the whole project per stage (about 12 calls per
  analysis) because Gemini's free tier allows 15 requests/minute. Do not reintroduce per-requirement
  calls without a reason.
* **Every agent** has a system prompt that forces JSON-only output, validates it against a Pydantic
  model (`call_agent_json` in `src/agents/llm_client.py`), and raises `AgentOutputError` on bad
  output. Never pass raw model text downstream, never swallow a parse failure.
* **Rate limiting and retry** live in `llm_client.py` (process-wide sliding window plus backoff
  that honours Google's `retryDelay`). A quota failure raises `RateLimitedError`; the job fails but
  finished stages are saved and **Resume analysis** continues.
* **Background jobs** (`src/pipeline/jobs.py`) run on a thread; the UI polls `/api/projects/{id}/job`.

### Anti-hallucination guards (keep them)

* Extraction must quote the source **verbatim**; an ungrounded quote drops the requirement and is
  counted (`find_grounding`).
* Compliance may only cite clause ids the retriever returned **for that requirement**; others are
  dropped and counted. High-impact clauses and confidence < 0.6 set `needs_legal_review`.
* SDLC scores come from the deterministic engine (`src/sdlc/engine.py`). The model only writes the
  explanation and must not change scores.
* The compliance agent never makes a legal determination.

### Security controls (keep them)

* `src/security/gate.py::secure_input` quarantines prompt-injection text and masks PII **before**
  anything is stored or sent to the model. Raw text is never persisted.
* Stakeholder text is wrapped in `<untrusted_document>` tags and never placed in a system prompt.
* Roles and gates are in `src/pipeline/approvals.py`. Sensitive requirements (high risk and
  security/privacy/regulatory, or needing legal review) need a security, compliance or architect role.
  Auth is a demo (client-stated name and role); real roles must come from an identity provider.
* `src/models/audit.py` is a hash-chained append-only log. `record()` for actions,
  `record_llm_call()` for model calls, `verify_chain()` to detect tampering.

## Data model

`src/models/requirement.py` holds the contracts: `Requirement` (id, readable `ref` like
`KYC-SEC-004`, statement, 13-way multi-label `categories`, `primary_category`, source stakeholder /
document / verbatim excerpt, justification, priority, dependencies, assumptions, acceptance
criteria, `regulations`, risk level and scores, `confidence_score`, `approval_status`, `origin`
(`stated` or `derived`), quality flags, `is_weak`, history), `Question` (optional, status
open/answered/skipped, `applied`), `Conflict`, `ControlCoverage`, `RiskItem`, `Threat`, `Factor`,
`SdlcOption`, `WorkflowPhase`.

Persistence (`src/models/db.py`): projects (with `analysis` and `gates` JSON), documents (masked
text only), requirements, questions, audit. Derived project-level results (conflicts, controls,
risks, threats, SDLC, validation, guard counters) live in `project.analysis`.

**Derived requirements** are added by the system from control gaps (`derived_reason` starts with
`[C-...]`) and from security analysis. They are pending until a human decides.

## Knowledge base

`src/knowledge_base/data/regulations.json` (50 versioned, paraphrased clauses with source,
jurisdiction, effective date, version, applicability, `high_impact`) and `controls.json` (21
mandatory controls with keywords and suggested requirements). Retrieval is Chroma with a lexical
fallback; tests force `KB_BACKEND=lexical`. Control applicability uses **whole-word** matching and
only the stakeholders' own words (never derived text), which keeps re-runs stable.

## Conventions

* Python 3.11, type hints, docstrings on public classes/functions. Keep modules focused.
* Tests must run offline: use the fakes in `tests/fakes.py`; never call Gemini from a test.
* Front end is plain HTML/CSS/JS with no build step. Escape all dynamic text with `esc()`.
  Static assets are served with `Cache-Control: no-cache` so browsers revalidate.
* No emojis in the UI or docs. Comments only when the *why* is non-obvious.
* Do not add the Claude co-author trailer to commits in this repo (owner's preference).

## Out of scope

* Other financial sectors; multi-tenant support; real RBAC/MFA/encryption-at-rest (documented as
  deployment concerns in the README); a gold-annotated evaluation harness (not built).
