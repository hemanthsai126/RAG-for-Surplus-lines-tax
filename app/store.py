"""Persisted chunk store + FAISS + BM25."""

from __future__ import annotations

import json
import pickle
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from app.config import settings


def tokenize_bm25(text: str) -> list[str]:
    """Tokens for BM25: word pieces plus hyphenated statute-style citations (e.g. 40-2-124, 33-24-46, 59a-02).

    Plain ``[a-z0-9]+`` splits ``40-2-124`` into ``40``, ``2``, ``124`` (too weak for retrieval). We also emit
    full hyphen chains. Kansas often prints ``40-2,124``; a comma between digit groups is normalized to hyphens
    before extracting chains so queries like ``§40-2-124`` match indexed text.

    **Re-run** ``python -m app.ingest`` after changing this function so ``bm25.pkl`` is rebuilt.
    """
    t = text.lower()
    t_hyp = re.sub(r"\b(\d+)-(\d+),(\d+)\b", r"\1-\2-\3", t)
    tokens = re.findall(r"[a-z0-9]+", t)
    tokens.extend(re.findall(r"(?:\d+[a-z]?)(?:-\d+[a-z]?)+", t_hyp))
    return tokens


class VectorStore:
    def __init__(
        self,
        chunks: list[dict[str, Any]],
        bm25: BM25Okapi,
        faiss_index: faiss.Index,
        embedder: SentenceTransformer,
    ) -> None:
        self.chunks = chunks
        self.bm25 = bm25
        self.faiss_index = faiss_index
        self.embedder = embedder
        self._dim = faiss_index.d

    @classmethod
    def load(cls, vector_dir: Path | None = None) -> VectorStore | None:
        vd = vector_dir or settings.vector_dir
        chunks_path = vd / "chunks.json"
        faiss_path = vd / "faiss.index"
        bm25_path = vd / "bm25.pkl"
        meta_path = vd / "embedder.txt"

        if not all(p.exists() for p in (chunks_path, faiss_path, bm25_path, meta_path)):
            return None

        with open(chunks_path, encoding="utf-8") as f:
            chunks = json.load(f)
        with open(meta_path, encoding="utf-8") as f:
            emb_name = f.read().strip()
        embedder = SentenceTransformer(emb_name)
        index = faiss.read_index(str(faiss_path))
        with open(bm25_path, "rb") as f:
            bm25 = pickle.load(f)
        return cls(chunks=chunks, bm25=bm25, faiss_index=index, embedder=embedder)

    def save(self, vector_dir: Path | None = None) -> None:
        vd = vector_dir or settings.vector_dir
        vd.mkdir(parents=True, exist_ok=True)

        with open(vd / "chunks.json", "w", encoding="utf-8") as f:
            json.dump(self.chunks, f, ensure_ascii=False, indent=0)
        faiss.write_index(self.faiss_index, str(vd / "faiss.index"))
        with open(vd / "bm25.pkl", "wb") as f:
            pickle.dump(self.bm25, f)
        name = getattr(self.embedder, "model_name_or_path", None) or settings.embedding_model
        with open(vd / "embedder.txt", "w", encoding="utf-8") as f:
            f.write(str(name))

    def embed_query(self, query: str) -> np.ndarray:
        v = self.embedder.encode([query], convert_to_numpy=True, normalize_embeddings=True)
        return v.astype(np.float32)


def build_store_from_chunks(
    chunks: list[dict[str, Any]],
    embedder: SentenceTransformer,
    *,
    on_encode_progress: Callable[[int, int], None] | None = None,
    encode_batch_size: int = 256,
) -> VectorStore:
    texts = [c["text"] for c in chunks]
    tokenized = [tokenize_bm25(t) for t in texts]
    bm25 = BM25Okapi(tokenized)

    n = len(texts)
    if n == 0:
        raise ValueError("chunks must be non-empty")

    if on_encode_progress is not None:
        parts: list[np.ndarray] = []
        bs = min(encode_batch_size, n) if n > 0 else 1
        for start in range(0, n, bs):
            end = min(start + bs, n)
            batch = texts[start:end]
            part = embedder.encode(
                batch,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            ).astype(np.float32)
            parts.append(part)
            on_encode_progress(end, n)
        embeddings = np.vstack(parts)
    else:
        embeddings = embedder.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=len(texts) >= 32,
        ).astype(np.float32)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    return VectorStore(chunks=chunks, bm25=bm25, faiss_index=index, embedder=embedder)
