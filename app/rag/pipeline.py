"""Retrieve → rerank → grounded generation with streaming."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings
from app.guards.domain import is_insurance_domain
from app.retrieval.hybrid import hybrid_retrieve
from app.retrieval.reranker import rerank
from app.rag.prompts import SYSTEM_INSURANCE_RAG, build_user_message, domain_rejection_message
from app.rag.risko import SYSTEM_RISKO_RAG
from app.store import VectorStore


def retrieve_and_pack_context(store: VectorStore, query: str) -> tuple[list[dict[str, Any]], list[str]]:
    fused = hybrid_retrieve(store, query)
    cand_indices = [i for i, _ in fused]
    texts = [store.chunks[i]["text"] for i in cand_indices]
    rr = rerank(query, texts, top_k=settings.rerank_top_k)
    selected: list[dict[str, Any]] = []
    blocks: list[str] = []
    for rank, (pos_in_cand, _score) in enumerate(rr, start=1):
        chunk_idx = cand_indices[pos_in_cand]
        ch = store.chunks[chunk_idx]
        # Plain text only — no [S1]/filenames in the LLM prompt (avoids leaking retrieval markup).
        blocks.append(ch["text"])
        selected.append({"rank": rank, **ch})
    return selected, blocks


def _ollama_troubleshoot_hint() -> str:
    return (
        f"Ollama is not usable at {settings.ollama_base_url!r}. "
        "Install from https://ollama.com, run the Ollama app (or `ollama serve`), then "
        f"`ollama pull <model>` and set OLLAMA_MODEL to a model you have (`ollama list`). "
        f"Currently OLLAMA_MODEL={settings.ollama_model!r}. "
        "Alternatively set OPENAI_BASE_URL + OPENAI_MODEL for a vLLM/OpenAI-compatible server."
    )


async def stream_ollama(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": True,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout_s) as client:
            async with client.stream("POST", url, json=payload) as resp:
                if resp.status_code == 404:
                    detail = ""
                    try:
                        body = await resp.aread()
                        err = json.loads(body.decode())
                        if isinstance(err.get("error"), str):
                            detail = err["error"].strip()
                    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
                        pass
                    if detail and "not found" in detail.lower():
                        yield (
                            f"Ollama: {detail}. Run `ollama pull {settings.ollama_model}` "
                            "(or pick a model from `ollama list` and set OLLAMA_MODEL). "
                        )
                    else:
                        yield (
                            "Ollama returned HTTP 404 for /api/chat — if the server is up, "
                            "the model may be missing (`ollama pull <name>`); otherwise "
                            "Ollama may not be running or another program is using the port. "
                        )
                    yield _ollama_troubleshoot_hint()
                    return
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    piece = data.get("message", {}).get("content")
                    if piece:
                        yield piece
                    if data.get("done"):
                        break
    except httpx.ConnectError:
        yield "Cannot connect to Ollama. " + _ollama_troubleshoot_hint()
    except httpx.HTTPStatusError as e:
        yield f"Ollama HTTP {e.response.status_code}. " + _ollama_troubleshoot_hint()


async def stream_openai_compatible(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    base = (settings.openai_base_url or "").rstrip("/")
    if not base or not settings.openai_model:
        raise RuntimeError("OpenAI-compatible URL/model not configured")
    url = f"{base}/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.openai_api_key:
        headers["Authorization"] = f"Bearer {settings.openai_api_key}"
    payload = {
        "model": settings.openai_model,
        "messages": messages,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=settings.ollama_timeout_s) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_s = line[6:].strip()
                if data_s == "[DONE]":
                    break
                try:
                    data = json.loads(data_s)
                except json.JSONDecodeError:
                    continue
                delta = data.get("choices", [{}])[0].get("delta", {})
                piece = delta.get("content")
                if piece:
                    yield piece


async def collect_answer(
    query: str,
    store: VectorStore,
    history: list[dict[str, str]] | None = None,
) -> str:
    parts: list[str] = []
    async for piece in stream_answer(query, store, history):
        parts.append(piece)
    return "".join(parts)


async def stream_answer(
    query: str,
    store: VectorStore,
    history: list[dict[str, str]] | None = None,
) -> AsyncIterator[str]:
    history = history or []
    if settings.strict_domain_guard and not is_insurance_domain(query):
        yield domain_rejection_message()
        return

    _meta, blocks = retrieve_and_pack_context(store, query)
    user_msg = build_user_message(query, blocks)
    system_content = SYSTEM_RISKO_RAG if settings.use_risko_persona else SYSTEM_INSURANCE_RAG
    messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]
    for m in history[-6:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_msg})

    if settings.openai_base_url and settings.openai_model:
        async for piece in stream_openai_compatible(messages):
            yield piece
    else:
        async for piece in stream_ollama(messages):
            yield piece
