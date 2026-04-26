"""Risko: insurance-only chat via an open-source local model (Ollama) or optional OpenAI-compatible API."""

from __future__ import annotations

import logging
import os
from typing import Any, List

import httpx

from app.copilot.schemas import RiskoMessage

logger = logging.getLogger(__name__)

RISKO_SYSTEM = """You are **Risko**, an articulate assistant that discusses **only insurance** and closely related risk-finance topics.

**Scope (allowed):** property & casualty, commercial lines, personal lines, life, health, disability, reinsurance, captives, underwriting, pricing, claims, loss adjusting, policy forms, endorsements, exclusions, deductibles, limits, surplus lines, brokers & agents, insurtech, solvency/regulation at a high level, actuarial concepts, risk management, and insurance vocabulary.

**Not allowed:** topics with no meaningful insurance angle (general programming, recipes, sports trivia, unrelated politics, etc.). If asked, briefly decline and suggest an insurance-related question instead.

**Safety:** Do not provide personalized insurance advice, binding coverage decisions, or legal counsel. Always remind users that real purchase, claims, and compliance decisions require licensed professionals in their jurisdiction.

Be concise unless the user asks for depth. Use clear structure when helpful.

**Formatting:** Reply in GitHub-flavored Markdown. Use `###` headings, **bold**, bullet or numbered lists, and **tables** (pipe syntax) when comparing products, coverages, or options — not plain text with visible `###` or `**` markers left uninterpreted."""

# Default: open-weight models via Ollama (https://ollama.com — Llama, Mistral, Qwen, etc.)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5")

# Optional: RISKO_LLM_BACKEND=openai for proprietary APIs (requires OPENAI_API_KEY)
RISKO_LLM_BACKEND = (os.environ.get("RISKO_LLM_BACKEND") or "ollama").strip().lower()

OPENAI_URL = os.environ.get("OPENAI_CHAT_COMPLETIONS_URL", "https://api.openai.com/v1/chat/completions")
OPENAI_DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def _messages_to_api(turns: List[RiskoMessage]) -> List[dict[str, str]]:
    out: List[dict[str, str]] = []
    for m in turns:
        out.append({"role": m.role, "content": m.content})
    while out and out[0]["role"] == "assistant":
        out.pop(0)
    return out


async def _ollama_chat(openai_msgs: List[dict[str, str]]) -> tuple[str, str]:
    base = OLLAMA_BASE_URL.rstrip("/")
    model = OLLAMA_MODEL.strip() or "qwen2.5"
    url = f"{base}/api/chat"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": RISKO_SYSTEM}] + openai_msgs,
        "stream": False,
        "options": {"temperature": 0.65, "num_predict": 1400},
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            r = await client.post(url, json=payload)
    except httpx.ConnectError as e:
        raise RuntimeError(
            f"Cannot reach Ollama at {base}. Install Ollama (https://ollama.com), run the app, "
            f"then: `ollama pull {model}` and ensure the server is listening (default port 11434). "
            f"Original error: {e}",
        ) from e

    if r.status_code >= 400:
        detail = r.text
        try:
            detail = str((r.json().get("error") or r.text))[:800]
        except Exception:
            pass
        logger.warning("Ollama error %s: %s", r.status_code, detail)
        raise RuntimeError(
            f"Ollama returned {r.status_code}: {detail}. If the model is missing, run: ollama pull {model}",
        )

    data = r.json()
    content = (data.get("message") or {}).get("content") or ""
    used = str(data.get("model") or model)
    return content.strip() or "…", used


async def _openai_chat(openai_msgs: List[dict[str, str]]) -> tuple[str, str]:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "RISKO_LLM_BACKEND=openai but OPENAI_API_KEY is not set. "
            "Set the key, or use the default open-source path: unset RISKO_LLM_BACKEND, install Ollama, and "
            "`ollama pull` a model (e.g. qwen2.5).",
        )

    model = (os.environ.get("OPENAI_MODEL") or OPENAI_DEFAULT_MODEL).strip() or OPENAI_DEFAULT_MODEL
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": RISKO_SYSTEM}] + openai_msgs,
        "temperature": 0.65,
        "max_tokens": 1400,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        r = await client.post(OPENAI_URL, headers=headers, json=payload)

    if r.status_code >= 400:
        try:
            err_body = r.json()
            detail = err_body.get("error", {}).get("message", r.text)
        except Exception:
            detail = r.text or r.reason_phrase
        logger.warning("OpenAI error %s: %s", r.status_code, detail[:500])
        raise RuntimeError(f"Upstream model error ({r.status_code}): {detail}")

    data = r.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Empty response from model.")
    msg = (choices[0].get("message") or {}).get("content") or ""
    used_model = str(data.get("model") or model)
    return msg.strip() or "…", used_model


async def risko_chat_completion(messages: List[RiskoMessage]) -> tuple[str, str]:
    openai_msgs = _messages_to_api(messages)
    if not openai_msgs:
        raise RuntimeError("No user messages to send after stripping UI welcome text.")

    if RISKO_LLM_BACKEND in ("openai", "gpt", "cloud"):
        return await _openai_chat(openai_msgs)
    # Default: Ollama (open-source weights, local inference)
    return await _ollama_chat(openai_msgs)
