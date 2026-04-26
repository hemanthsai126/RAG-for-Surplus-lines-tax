"""Heuristic extraction from policy text (RAG snippets + regex)."""

import re
from typing import Optional

from app.copilot.schemas import PolicyExtraction


_LIMIT_PATTERNS = [
    (re.compile(r"general\s+liability.*?(\$[\d,]+(?:\.\d{2})?)", re.I), "gl"),
    (re.compile(r"each\s+occurrence.*?(\$[\d,]+(?:\.\d{2})?)", re.I), "gl"),
    (re.compile(r"property\s+coverage.*?(\$[\d,]+(?:\.\d{2})?)", re.I), "prop"),
    (re.compile(r"building\s+limit.*?(\$[\d,]+(?:\.\d{2})?)", re.I), "prop"),
]

_DEDUCTIBLE = re.compile(r"deductible.*?(\$[\d,]+(?:\.\d{2})?)", re.I)


def _parse_money(s: str) -> Optional[float]:
    s = s.replace(",", "").replace("$", "")
    try:
        return float(s)
    except ValueError:
        return None


def extract_from_text(text: str, snippets: list[str]) -> PolicyExtraction:
    blob = (text or "")[:200_000]
    gl = None
    prop = None
    ded = None
    for rx, kind in _LIMIT_PATTERNS:
        m = rx.search(blob)
        if m:
            val = _parse_money(m.group(1))
            if kind == "gl" and gl is None:
                gl = val
            if kind == "prop" and prop is None:
                prop = val
    dm = _DEDUCTIBLE.search(blob)
    if dm:
        ded = _parse_money(dm.group(1))

    flood_excluded = bool(re.search(r"flood\s+(is\s+)?excluded|exclusion.*?flood", blob, re.I))
    bi_mentioned = bool(re.search(r"business\s+interruption|time\s+element|income\s+loss", blob, re.I))
    bi_neg = bool(
        re.search(
            r"business\s+(interruption|income).{0,80}not\s+included|not\s+included.{0,40}business",
            blob,
            re.I | re.DOTALL,
        )
    )
    bi = bi_mentioned and not bi_neg
    cyber_mentioned = bool(re.search(r"cyber|data\s+breach|network\s+security", blob, re.I))
    cyber_neg = bool(re.search(r"cyber.{0,60}not\s+included|network\s+security.{0,60}not\s+included", blob, re.I))
    cyber = cyber_mentioned and not cyber_neg

    return PolicyExtraction(
        general_liability_limit_usd=gl,
        property_limit_usd=prop,
        business_interruption=bi,
        cyber_coverage=cyber,
        deductible_usd=ded,
        flood_excluded=flood_excluded if flood_excluded or "flood" in blob.lower() else None,
        raw_snippets=(snippets or [])[:12],
    )
