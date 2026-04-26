"""
Forward structured applicant data to a configured insurer / MGA / aggregator **HTTPS quote API**.

Live premiums require a **contracted API** — set ``INSURANCE_QUOTES_API_URL`` (and optional key).
This module does not scrape consumer websites (ToS, reliability, compliance).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import uuid
from typing import Any, List, Optional

import httpx

from app.copilot.schemas import QuoteCompareRequest, QuoteCompareResponse, QuoteOffer

logger = logging.getLogger(__name__)

# Partner quote calls: separate connect vs read so a bad host fails fast (not 120s on connect).
def _quote_http_timeout() -> httpx.Timeout:
    def _f(name: str, default: float) -> float:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return default
        try:
            return max(1.0, float(raw))
        except ValueError:
            return default

    return httpx.Timeout(
        connect=_f("INSURANCE_QUOTES_TIMEOUT_CONNECT", 8.0),
        read=_f("INSURANCE_QUOTES_TIMEOUT_READ", 60.0),
        write=20.0,
        pool=10.0,
    )


# Reuse one client so repeated partner calls avoid new TLS handshakes (faster after first request).
_quote_http_client: Optional[httpx.AsyncClient] = None


def _partner_http_client() -> httpx.AsyncClient:
    global _quote_http_client
    if _quote_http_client is None:
        _quote_http_client = httpx.AsyncClient(timeout=_quote_http_timeout())
    return _quote_http_client


def _submission_echo(payload: dict[str, Any], *, mock: bool) -> dict[str, Any]:
    """Full echo is optional: large JSON slows the browser on slow links. Mock defaults to minimal."""
    full = os.environ.get("QUOTES_DEBUG_PAYLOAD", "").strip().lower() in ("1", "true", "yes")
    if full:
        return payload
    if mock:
        return {"submission_id": payload.get("submission_id")}
    return payload


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _name(row: dict[str, Any]) -> Optional[str]:
    for k in ("company_name", "carrier_name", "insurer", "carrier", "name", "provider"):
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def _premium(row: dict[str, Any]) -> Optional[float]:
    for k in ("premium_annual_usd", "annual_premium_usd", "annual_premium", "premium", "price", "quote_amount"):
        n = _num(row.get(k))
        if n is not None and n >= 0:
            return n
    return None


def _rows_from_payload(data: Any) -> List[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("offers", "quotes", "results", "carriers", "data"):
        v = data.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    return []


def parse_partner_offers(data: Any) -> List[QuoteOffer]:
    """Normalize common partner JSON shapes into ``QuoteOffer`` list."""
    rows = _rows_from_payload(data)
    out: List[QuoteOffer] = []
    for row in rows:
        name = _name(row)
        prem = _premium(row)
        if not name or prem is None:
            continue
        out.append(
            QuoteOffer(
                company_name=name,
                premium_annual_usd=prem,
                plan_name=(str(row["plan_name"]) if row.get("plan_name") else None)
                or (str(row["product"]) if row.get("product") else None),
                notes=str(row["notes"])[:500] if row.get("notes") else None,
            )
        )
    return out


# Fictional composite names for demo quotes only (not real carriers).
_MOCK_PREFIXES = (
    "Apex",
    "Harborline",
    "Meridian",
    "Summit",
    "Northfield",
    "Cedar",
    "Granite",
    "Silvergate",
    "Bluewater",
    "Ironwood",
)
_MOCK_SUFFIXES = (
    "Mutual",
    "Specialty",
    "Risk Partners",
    "Coverage Group",
    "Advantage",
    "Shield",
    "Underwriters",
    "Insurance Co.",
)


def _mock_rng(submission_id: str, applicant: dict[str, Any]) -> random.Random:
    raw = f"{submission_id}:{json.dumps(applicant, sort_keys=True, default=str)}"
    seed = int(hashlib.sha256(raw.encode()).hexdigest()[:16], 16)
    return random.Random(seed)


def build_mock_offers(applicant: dict[str, Any], submission_id: str) -> List[QuoteOffer]:
    """Deterministic-but-varied demo offers from applicant fields (not real rates)."""
    rng = _mock_rng(submission_id, applicant)
    names: List[str] = []
    while len(names) < 8:
        n = f"{rng.choice(_MOCK_PREFIXES)} {rng.choice(_MOCK_SUFFIXES)}"
        if n not in names:
            names.append(n)
    rng.shuffle(names)
    n_offers = rng.randint(4, 6)
    names = names[:n_offers]

    rev = float(applicant.get("annual_revenue_usd") or 0)
    emp = int(applicant.get("employee_count") or 0)
    sqft = float(applicant.get("property_sqft") or 0)
    cov = applicant.get("coverages_requested") or []
    cov_n = len(cov) if isinstance(cov, list) else 0
    claims = applicant.get("claims_in_last_5_years") is True
    wc = applicant.get("workers_comp_needed") is True
    cyber = applicant.get("cyber_needed") is True

    base = rev * 0.0018 + emp * 95.0 + sqft * 0.11
    base *= 1.0 + 0.07 * cov_n
    if claims:
        base *= 1.32
    if wc:
        base *= 1.18
    if cyber:
        base *= 1.12
    base = max(base, 800.0)

    plans = (
        "BOP — standard",
        "GL + property bundle",
        "Commercial package",
        "Industry-tailored",
        "Preferred tier",
    )

    offers: List[QuoteOffer] = []
    for i, company_name in enumerate(names):
        jitter = rng.uniform(0.82, 1.28) * (1.0 + i * 0.03)
        prem = round(base * jitter, -1)  # nearest $10
        prem = max(500.0, prem)
        offers.append(
            QuoteOffer(
                company_name=company_name,
                premium_annual_usd=prem,
                plan_name=rng.choice(plans),
                notes="Illustrative demo quote — not from a live carrier.",
            )
        )
    offers.sort(key=lambda o: o.premium_annual_usd)
    return offers


async def fetch_quote_offers(req: QuoteCompareRequest) -> QuoteCompareResponse:
    url = (os.environ.get("INSURANCE_QUOTES_API_URL") or "").strip()
    payload: dict[str, Any] = {
        "submission_id": str(uuid.uuid4()),
        "applicant": req.applicant.model_dump(exclude_none=True),
    }

    if not url:
        offers = build_mock_offers(payload["applicant"], payload["submission_id"])
        return QuoteCompareResponse(
            offers=offers,
            configured=False,
            mock_mode=True,
            message=(
                "Demonstration mode: carrier names and premiums below are randomly generated from your "
                "inputs for UI preview. Set INSURANCE_QUOTES_API_URL (and optional INSURANCE_QUOTES_API_KEY) "
                "for live partner quotes."
            ),
            submission_payload_echo=_submission_echo(payload, mock=True),
        )

    key = (os.environ.get("INSURANCE_QUOTES_API_KEY") or "").strip()
    headers: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    extra = (os.environ.get("INSURANCE_QUOTES_API_HEADERS") or "").strip()
    if extra:
        for part in extra.split(","):
            if ":" in part:
                k, v = part.split(":", 1)
                headers[k.strip()] = v.strip()

    try:
        r = await _partner_http_client().post(url, json=payload, headers=headers)
    except httpx.ConnectError as e:
        logger.warning("Quote API connect error: %s", e)
        raise RuntimeError(f"Could not reach quote API at {url}: {e}") from e

    if r.status_code >= 400:
        detail = r.text[:2000]
        try:
            detail = str(r.json())[:2000]
        except Exception:
            pass
        raise RuntimeError(f"Quote API returned {r.status_code}: {detail}")

    try:
        data = r.json()
    except Exception as e:
        raise RuntimeError(f"Quote API did not return JSON: {e}") from e

    offers = parse_partner_offers(data)
    return QuoteCompareResponse(
        offers=offers,
        configured=True,
        mock_mode=False,
        message=None if offers else "Partner API returned 200 but no offers could be parsed. Check response shape (offers[].company_name + premium).",
        submission_payload_echo=_submission_echo(payload, mock=False),
    )
