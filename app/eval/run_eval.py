"""Benchmark retrieval overlap, answer substance, and optional LLM answers."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from app.config import settings
from app.rag.pipeline import collect_answer, retrieve_and_pack_context
from app.store import VectorStore

_ROOT = Path(__file__).resolve().parents[2]


def _load_benchmark(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def retrieval_hit(store: VectorStore, question: str, must_appear: list[str]) -> bool:
    meta, _blocks = retrieve_and_pack_context(store, question)
    blob = " ".join(m.get("text", "") for m in meta).lower()
    return all(k.lower() in blob for k in must_appear)


def substantive_answer_score(answer: str) -> float:
    """Answers no longer include [S#] tags (user-facing); score non-trivial length instead."""
    return 1.0 if len(answer.strip()) >= 40 else 0.0


async def run_async(benchmark_path: Path, skip_llm: bool) -> dict[str, Any]:
    store = VectorStore.load(settings.vector_dir)
    if store is None:
        return {"ok": True, "skipped": True, "reason": "No vector index — run POST /api/ingest after adding PDFs."}

    cases = _load_benchmark(benchmark_path)
    ret_hits = 0
    substance_scores: list[float] = []
    faith_scores: list[float] = []

    for row in cases:
        q = row["question"]
        keys = row.get("retrieval_must_contain", [])
        if keys and retrieval_hit(store, q, keys):
            ret_hits += 1

        if skip_llm:
            continue

        ans = await collect_answer(q, store)
        substance_scores.append(substantive_answer_score(ans))
        must = row.get("answer_must_mention", [])
        if must:
            low = ans.lower()
            faith_scores.append(1.0 if all(m.lower() in low for m in must) else 0.0)

    n = len(cases)
    keyed = [row for row in cases if row.get("retrieval_must_contain")]
    ret_denom = len(keyed)
    out: dict[str, Any] = {
        "ok": True,
        "cases": n,
        "retrieval_recall_proxy": (ret_hits / ret_denom) if ret_denom else None,
    }
    if not skip_llm:
        out["substantive_answer_rate"] = (
            sum(substance_scores) / len(substance_scores) if substance_scores else 0.0
        )
        out["answer_keyword_faithfulness"] = (
            sum(faith_scores) / len(faith_scores) if faith_scores else None
        )
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--benchmark",
        type=Path,
        default=_ROOT / "benchmarks" / "qa_sample.json",
    )
    args = p.parse_args()
    skip = os.environ.get("SKIP_LLM", "").lower() in ("1", "true", "yes")
    result = asyncio.run(run_async(args.benchmark, skip_llm=skip))
    print(json.dumps(result, indent=2))
    if result.get("skipped"):
        return
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
