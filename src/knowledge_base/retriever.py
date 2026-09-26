"""Chroma-backed retriever over the regulation knowledge base (PCI-DSS / RBI)."""

from __future__ import annotations

import chromadb
from pydantic import BaseModel

COLLECTION_NAME = "regulations"
PERSIST_DIR = "chroma_db"


class RegulationClause(BaseModel):
    """One retrieved regulation clause, with its similarity distance."""

    source: str
    clause_id: str
    title: str
    text: str
    distance: float | None = None


class RegulationRetriever:
    """Thin wrapper over a persistent Chroma collection of regulation clauses."""

    def __init__(self, persist_dir: str = PERSIST_DIR) -> None:
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(COLLECTION_NAME)

    def query(self, text: str, top_k: int = 3) -> list[RegulationClause]:
        """Returns the top_k regulation clauses most relevant to ``text``."""
        if self.collection.count() == 0:
            return []

        results = self.collection.query(
            query_texts=[text], n_results=min(top_k, self.collection.count())
        )
        clauses = []
        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results.get("distances", [[None] * len(ids)])[0]

        for doc, meta, dist in zip(documents, metadatas, distances):
            clauses.append(
                RegulationClause(
                    source=meta["source"],
                    clause_id=meta["clause_id"],
                    title=meta["title"],
                    text=doc,
                    distance=dist,
                )
            )
        return clauses
