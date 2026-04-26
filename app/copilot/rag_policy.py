"""Lightweight RAG: chunk policy text, TF-IDF retrieval (no large model download)."""

from __future__ import annotations

import re
from typing import Optional, Tuple
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.copilot.policy_parse import extract_from_text
from app.copilot.schemas import PolicyExtraction


def _chunks(text: str, max_chunk: int = 900, overlap: int = 120) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    out: list[str] = []
    i = 0
    while i < len(text):
        out.append(text[i : i + max_chunk])
        i += max_chunk - overlap
    return out


class PolicyRAG:
    def __init__(self) -> None:
        self._chunks: list[str] = []
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._matrix = None

    def ingest(self, full_text: str) -> None:
        self._chunks = _chunks(full_text)
        if not self._chunks:
            self._vectorizer = None
            self._matrix = None
            return
        self._vectorizer = TfidfVectorizer(max_features=4096, ngram_range=(1, 2), stop_words="english")
        self._matrix = self._vectorizer.fit_transform(self._chunks)

    def retrieve(self, query: str, k: int = 5) -> list[str]:
        if not self._chunks or self._vectorizer is None or self._matrix is None:
            return []
        qv = self._vectorizer.transform([query])
        sims = cosine_similarity(qv, self._matrix).ravel()
        idx = sims.argsort()[::-1][:k]
        return [self._chunks[i] for i in idx if sims[i] > 0.01]

    def analyze_policy(self, full_text: str) -> Tuple[PolicyExtraction, list[str]]:
        self.ingest(full_text)
        queries = [
            "general liability limit each occurrence",
            "property coverage building personal property",
            "deductible",
            "exclusions flood earthquake",
            "business interruption extra expense",
            "cyber data breach",
        ]
        citations: list[str] = []
        for q in queries:
            citations.extend(self.retrieve(q, k=2))
        # dedupe preserve order
        seen = set()
        uniq: list[str] = []
        for c in citations:
            key = c[:120]
            if key not in seen:
                seen.add(key)
                uniq.append(c)
        extraction = extract_from_text(full_text, uniq[:10])
        return extraction, uniq[:8]


def load_sample_policy_text() -> str:
    """Embedded sample policy prose for RAG demo when user uploads nothing."""
    p = Path(__file__).resolve().parent / "sample_policy.txt"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return _FALLBACK_POLICY


_FALLBACK_POLICY = """
COMMERCIAL PACKAGE POLICY — SAMPLE (SYNTHETIC)
Named Insured: Demo Bistro LLC
Policy Period: 01/01/2026 to 01/01/2027

COVERAGE A — GENERAL LIABILITY
Each Occurrence Limit: $1,000,000
Personal & Advertising Injury: $1,000,000
General Aggregate: $2,000,000
Products/Completed Operations Aggregate: $2,000,000

COVERAGE B — COMMERCIAL PROPERTY
Building Limit: $350,000
Business Personal Property: $75,000
Causes of Loss: Special Form
Deductible: $2,500 per occurrence

EXCLUSIONS
Flood damage is excluded unless Flood Coverage is endorsed.
Earth movement is excluded except as provided by endorsement.

BUSINESS INTERRUPTION
Business Income and Extra Expense: Not included unless endorsed.

CYBER LIABILITY
Network Security and Privacy Liability: Not included.
"""

