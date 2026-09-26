"""Parses regulation excerpt files and upserts them into the Chroma collection.

Excerpt files use a simple clause-header format:

    ### <source> | <clause_id> | <title>
    <clause body text, until the next "### " header or end of file>

Run directly to (re-)populate the knowledge base:
    python -m src.knowledge_base.ingest
"""

from __future__ import annotations

import re
from pathlib import Path

from src.knowledge_base.retriever import RegulationRetriever

CLAUSE_HEADER = re.compile(r"^###\s*(?P<source>[^|]+)\|(?P<clause_id>[^|]+)\|(?P<title>.+)$")

DEFAULT_FILES = [
    "data/sample_inputs/pci_dss_excerpts.txt",
    "data/sample_inputs/rbi_payment_auth_excerpts.txt",
]


def parse_excerpt_file(path: str) -> list[dict]:
    """Splits one excerpt file into clause dicts: source, clause_id, title, text."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    clauses: list[dict] = []
    current: dict | None = None
    body_lines: list[str] = []

    for line in lines:
        match = CLAUSE_HEADER.match(line.strip())
        if match:
            if current is not None:
                current["text"] = "\n".join(body_lines).strip()
                clauses.append(current)
            current = {
                "source": match.group("source").strip(),
                "clause_id": match.group("clause_id").strip(),
                "title": match.group("title").strip(),
            }
            body_lines = []
        elif current is not None:
            body_lines.append(line)

    if current is not None:
        current["text"] = "\n".join(body_lines).strip()
        clauses.append(current)

    if not clauses:
        raise ValueError(f"No clauses found in {path} — check the '### source | id | title' format")
    return clauses


def ingest_regulations(
    file_paths: list[str] | None = None, retriever: RegulationRetriever | None = None
) -> int:
    """Parses each excerpt file and upserts its clauses into the knowledge base.

    Upserts are keyed by "<source>::<clause_id>", so re-running is idempotent.
    Returns the number of clauses ingested.
    """
    retriever = retriever or RegulationRetriever()
    all_clauses: list[dict] = []
    for path in file_paths or DEFAULT_FILES:
        all_clauses.extend(parse_excerpt_file(path))

    retriever.collection.upsert(
        ids=[f"{c['source']}::{c['clause_id']}" for c in all_clauses],
        documents=[c["text"] for c in all_clauses],
        metadatas=[
            {"source": c["source"], "clause_id": c["clause_id"], "title": c["title"]}
            for c in all_clauses
        ],
    )
    return len(all_clauses)


if __name__ == "__main__":
    count = ingest_regulations()
    print(f"Ingested {count} regulation clauses into the '{RegulationRetriever().collection.name}' collection.")
