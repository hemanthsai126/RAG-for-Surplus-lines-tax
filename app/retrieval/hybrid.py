"""BM25 + dense FAISS with reciprocal rank fusion."""

from __future__ import annotations

import numpy as np

from app.config import settings
from app.store import VectorStore, tokenize_bm25


def _bm25_top_indices(store: VectorStore, query: str, k: int) -> list[int]:
    tokens = tokenize_bm25(query)
    if not tokens:
        return []
    scores = store.bm25.get_scores(tokens)
    order = np.argsort(scores)[::-1][:k]
    return [int(i) for i in order]


def _faiss_top_indices(store: VectorStore, query: str, k: int) -> list[int]:
    q = store.embed_query(query)
    scores, idx = store.faiss_index.search(q, min(k, len(store.chunks)))
    return [int(i) for i in idx[0] if i >= 0]


def reciprocal_rank_fusion(rank_lists: list[list[int]], k: int | None = None) -> list[tuple[int, float]]:
    k = k if k is not None else settings.rrf_k
    scores: dict[int, float] = {}
    for ranks in rank_lists:
        for rank, doc_idx in enumerate(ranks):
            scores[doc_idx] = scores.get(doc_idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


def _path_substring_bonus(store: VectorStore, doc_idx: int) -> float:
    raw = (settings.retrieval_path_bonus_substrings or "").strip()
    if not raw or not float(settings.retrieval_path_rrf_bonus):
        return 0.0
    hints = [h.strip().lower() for h in raw.split(",") if h.strip()]
    if not hints:
        return 0.0
    src = (store.chunks[doc_idx].get("source") or "").replace("\\", "/").lower()
    if any(h in src for h in hints):
        return float(settings.retrieval_path_rrf_bonus)
    return 0.0


def hybrid_retrieve(store: VectorStore, query: str) -> list[tuple[int, float]]:
    bm25_idx = _bm25_top_indices(store, query, settings.bm25_top_k)
    faiss_idx = _faiss_top_indices(store, query, settings.faiss_top_k)
    fused = reciprocal_rank_fusion([bm25_idx, faiss_idx])
    if settings.retrieval_path_bonus_substrings.strip():
        boosted = [(idx, score + _path_substring_bonus(store, idx)) for idx, score in fused]
        boosted.sort(key=lambda x: -x[1])
        fused = boosted
    return fused[: settings.fuse_top_n]
