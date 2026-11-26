"""Versioned KYC/AML knowledge base with jurisdiction-aware retrieval.

Retrieval order: Chroma (semantic) when available, otherwise a built-in BM25-style
lexical ranker. The compliance agent may only cite clause ids this module returned.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
PERSIST_DIR = os.environ.get("CHROMA_DIR", "chroma_db")
STOPWORDS = set(
    "a an and are as at be by for from has have in is it its of on or that the their this to was were will with shall must should may can not".split()
)


@dataclass
class Clause:
    id: str
    source: str
    jurisdiction: str
    title: str
    text: str
    effective: str = ""
    version: str = ""
    applicability: list[str] = field(default_factory=list)
    high_impact: bool = False
    distance: float | None = None

    @property
    def citation(self) -> str:
        return f"{self.source}: {self.title}"


@dataclass
class Control:
    id: str
    title: str
    regulations: list[str]
    keywords: list[str]
    applies_if: list[str]
    suggested_requirement: str


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS and len(t) > 1]


class KnowledgeBase:
    def __init__(self, backend: str | None = None, persist_dir: str | None = None) -> None:
        raw = json.loads((DATA_DIR / "regulations.json").read_text(encoding="utf-8"))
        self.version: str = raw["kb_version"]
        self.clauses: dict[str, Clause] = {
            item["id"]: Clause(
                id=item["id"],
                source=item["source"],
                jurisdiction=item["jurisdiction"],
                title=item["title"],
                text=item["text"],
                effective=item.get("effective", ""),
                version=item.get("version", ""),
                applicability=item.get("applicability", []),
                high_impact=item.get("high_impact", False),
            )
            for item in raw["items"]
        }
        ctrl = json.loads((DATA_DIR / "controls.json").read_text(encoding="utf-8"))
        self.controls: list[Control] = [Control(**c) for c in ctrl["controls"]]

        self.backend = (backend or os.environ.get("KB_BACKEND", "chroma")).lower()
        self._collection = None
        if self.backend == "chroma":
            try:
                self._collection = self._open_collection(persist_dir or PERSIST_DIR)
            except Exception as exc:  # noqa: BLE001 - any chroma failure falls back to lexical
                log.warning("Chroma unavailable (%s); using lexical retrieval", exc)
                self.backend = "lexical"
        self._build_lexical_index()

    # ------------------------------------------------------------------ chroma
    def _open_collection(self, persist_dir: str):
        import chromadb

        client = chromadb.PersistentClient(path=persist_dir)
        name = "kyc_" + re.sub(r"[^A-Za-z0-9]+", "_", self.version)
        collection = client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})
        if collection.count() != len(self.clauses):
            collection.upsert(
                ids=list(self.clauses),
                documents=[f"{c.title}. {c.text}" for c in self.clauses.values()],
                metadatas=[{"source": c.source, "jurisdiction": c.jurisdiction} for c in self.clauses.values()],
            )
        return collection

    # ----------------------------------------------------------------- lexical
    def _build_lexical_index(self) -> None:
        self._doc_tokens: dict[str, Counter[str]] = {}
        df: Counter[str] = Counter()
        for clause in self.clauses.values():
            weighted = _tokens(clause.title) * 2 + _tokens(clause.text) + _tokens(" ".join(clause.applicability)) * 2
            counts = Counter(weighted)
            self._doc_tokens[clause.id] = counts
            df.update(counts.keys())
        n = len(self.clauses)
        self._idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self._avg_len = sum(sum(c.values()) for c in self._doc_tokens.values()) / max(n, 1)

    def _lexical(self, query: str, allowed: set[str], top_k: int) -> list[Clause]:
        q = _tokens(query)
        scored: list[tuple[float, Clause]] = []
        for cid, counts in self._doc_tokens.items():
            clause = self.clauses[cid]
            if clause.jurisdiction not in allowed:
                continue
            length = sum(counts.values())
            score = 0.0
            for term in q:
                tf = counts.get(term, 0)
                if tf:
                    score += self._idf.get(term, 0.0) * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * length / self._avg_len))
            if score > 0:
                scored.append((score, clause))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        out = []
        for rank, (score, clause) in enumerate(scored[:top_k]):
            out.append(Clause(**{**clause.__dict__, "distance": round(1 / (1 + score), 3)}))
        return out

    # ------------------------------------------------------------------ public
    def get(self, clause_id: str) -> Clause | None:
        return self.clauses.get(clause_id)

    def retrieve(self, query: str, jurisdictions: list[str], top_k: int = 5) -> list[Clause]:
        """Top clauses for ``query`` among the project's jurisdictions (plus GLOBAL)."""
        allowed = {j.upper() for j in jurisdictions} | {"GLOBAL"}
        if self._collection is not None:
            try:
                result = self._collection.query(
                    query_texts=[query],
                    n_results=min(top_k, self._collection.count()),
                    where={"jurisdiction": {"$in": sorted(allowed)}},
                )
                clauses = []
                for cid, dist in zip(result["ids"][0], result["distances"][0]):
                    clause = self.clauses[cid]
                    clauses.append(Clause(**{**clause.__dict__, "distance": round(float(dist), 3)}))
                return clauses
            except Exception as exc:  # noqa: BLE001
                log.warning("Chroma query failed (%s); falling back to lexical", exc)
        return self._lexical(query, allowed, top_k)

    def controls_for(self, jurisdictions: list[str]) -> list[Control]:
        """Controls that have at least one regulation in the project's jurisdictions."""
        allowed = {j.upper() for j in jurisdictions} | {"GLOBAL"}
        out = []
        for control in self.controls:
            regs = [self.clauses[r] for r in control.regulations if r in self.clauses]
            if any(r.jurisdiction in allowed for r in regs):
                out.append(control)
        return out

    def manifest(self) -> dict:
        by_jurisdiction = Counter(c.jurisdiction for c in self.clauses.values())
        return {
            "version": self.version,
            "backend": self.backend,
            "clauses": len(self.clauses),
            "controls": len(self.controls),
            "by_jurisdiction": dict(by_jurisdiction),
        }


_default: KnowledgeBase | None = None


def get_kb() -> KnowledgeBase:
    global _default
    if _default is None:
        _default = KnowledgeBase()
    return _default
