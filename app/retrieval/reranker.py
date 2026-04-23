"""Cross-encoder reranking for high-precision selection."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from sentence_transformers import CrossEncoder

from app.config import settings


@lru_cache(maxsize=2)
def get_cross_encoder() -> CrossEncoder:
    return CrossEncoder(settings.cross_encoder_model)


def rerank(query: str, chunk_texts: list[str], top_k: int) -> list[tuple[int, float]]:
    if not chunk_texts:
        return []
    ce = get_cross_encoder()
    pairs = [[query, t] for t in chunk_texts]
    raw = ce.predict(pairs, show_progress_bar=False)
    scores = np.asarray(raw, dtype=float).reshape(-1)
    ranked = sorted(enumerate(scores), key=lambda x: -float(x[1]))
    return [(int(i), float(s)) for i, s in ranked[:top_k]]
