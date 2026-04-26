"""
Resolve user NAICS input using `backend/data/2012 Industry Data by Industry and State.csv`
(2012 NAICS sector titles at US level from Census-style industry tables).

Maps 2–6 digit NAICS codes to sector keys in that file and provides underwriting-style
`industry_risk` proxies (0–1) aligned with sector hazard.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from app.copilot.industry_risk import INDUSTRY_RISK

_COPILOT = Path(__file__).resolve().parent
DATA_CSV = _COPILOT / "data" / "2012 Industry Data by Industry and State.csv"

# Sector-level risk priors (underwriting-style; not empirical loss costs).
NAICS_SECTOR_RISK: Dict[str, float] = {
    "21": 0.88,
    "22": 0.48,
    "23": 0.72,
    "31-33": 0.78,
    "42": 0.58,
    "44-45": 0.55,
    "48-49 (104)": 0.65,
    "51": 0.42,
    "52": 0.38,
    "53": 0.45,
    "54": 0.35,
    "55": 0.40,
    "56": 0.52,
    "61": 0.42,
    "62": 0.48,
    "71": 0.58,
    "72": 0.90,
    "81": 0.50,
}


def _digits_only(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


def _map_numeric_naics_to_sector_key(digits: str) -> Optional[str]:
    """Map leading digits of a NAICS code to a sector key present in the CSV."""
    if len(digits) < 2:
        return None
    n2 = int(digits[:2])
    if n2 == 11:
        return None  # Agriculture — not in this extract
    if 21 <= n2 <= 23:
        return str(n2)
    if 31 <= n2 <= 33:
        return "31-33"
    if n2 == 42:
        return "42"
    if 44 <= n2 <= 45:
        return "44-45"
    if 48 <= n2 <= 49:
        return "48-49 (104)"
    if 51 <= n2 <= 56:
        return str(n2)
    if n2 in (61, 62, 71, 72, 81):
        return str(n2)
    if n2 == 92:
        return None  # Public admin — not modeled as commercial P&C SMB here
    return None


@lru_cache(maxsize=1)
def _sector_titles_from_csv() -> Dict[str, str]:
    """US-level canonical sector title per NAICS sector code in the file."""
    if not DATA_CSV.exists():
        return {}
    df = pd.read_csv(DATA_CSV)
    us = df[df["Geographic area name"].astype(str).str.strip() == "United States"]
    col_op = "Meaning of Type of operation or tax status code"
    titles: Dict[str, str] = {}
    for code in us["2012 NAICS code"].unique():
        rows = us[us["2012 NAICS code"] == code]
        pref = rows[rows[col_op].astype(str).str.strip() == "Total"]
        pick = pref if len(pref) else rows
        r = pick.iloc[0]
        key = str(code).strip()
        titles[key] = str(r["Meaning of 2012 NAICS code"]).strip()
    return titles


def _normalize_sector_key(raw: str) -> Optional[str]:
    """Match user-typed sector codes like 31-33 or 48-49 (104) to catalog keys."""
    t = raw.strip()
    if not t:
        return None
    titles = _sector_titles_from_csv()
    for k in titles:
        if k.lower() == t.lower():
            return k
    # Loose match: ignore spaces
    compact = re.sub(r"\s+", "", t.lower())
    for k in titles:
        if re.sub(r"\s+", "", k.lower()) == compact:
            return k
    return None


def resolve_naics_input(naics_code: Optional[str]) -> Dict[str, Any]:
    """
    Returns a dict suitable for NaicsResolution:
    matched, input_raw, normalized_input, sector_code, industry_title, industry_risk, note
    """
    raw = (naics_code or "").strip()
    if not raw:
        return {
            "matched": False,
            "input_raw": None,
            "normalized_input": None,
            "sector_code": None,
            "industry_title": None,
            "industry_risk": None,
            "note": None,
        }

    titles = _sector_titles_from_csv()
    if not titles:
        return {
            "matched": False,
            "input_raw": raw,
            "normalized_input": raw,
            "sector_code": None,
            "industry_title": None,
            "industry_risk": None,
            "note": "Industry CSV not found on server.",
        }

    sector_key: Optional[str] = _normalize_sector_key(raw)
    normalized = raw

    if sector_key is None:
        d = _digits_only(raw)
        if d:
            sector_key = _map_numeric_naics_to_sector_key(d)
            normalized = d
        else:
            sector_key = None

    if sector_key is None or sector_key not in titles:
        return {
            "matched": False,
            "input_raw": raw,
            "normalized_input": normalized,
            "sector_code": None,
            "industry_title": None,
            "industry_risk": None,
            "note": "Could not map to a 2012 NAICS sector in the loaded Census industry extract (try a 2–6 digit NAICS).",
        }

    title = titles[sector_key]
    risk = NAICS_SECTOR_RISK.get(sector_key, 0.5)
    return {
        "matched": True,
        "input_raw": raw,
        "normalized_input": normalized,
        "sector_code": sector_key,
        "industry_title": title,
        "industry_risk": risk,
        "note": None,
    }


def blended_industry_risk_for_model(
    industry_bucket: str,
    naics_code: Optional[str],
) -> Tuple[float, Dict[str, Any]]:
    """
    Combine NAICS sector risk with the UI industry bucket (0.65 / 0.35) for the ML feature row.
    """
    bucket = INDUSTRY_RISK.get(industry_bucket, 0.5)
    info = resolve_naics_input(naics_code)
    if not info["matched"] or info.get("industry_risk") is None:
        return float(bucket), info
    nr = float(info["industry_risk"])
    blended = float(0.65 * nr + 0.35 * bucket)
    return blended, info
