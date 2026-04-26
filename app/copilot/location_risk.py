"""
Location risk features.

- **Flood**: [FEMA NFHL MapServer](https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer)
  layer `28` (Flood Hazard Zones), queried at a point from geocoded address or ZIP.
- **Geocoding**: OpenStreetMap Nominatim — full US address or ZIP → lat/lon. Per
  https://operations.osmfoundation.org/policies/nominatim/ — valid User-Agent required.
- **Crime**: `backend/data/crime_proxy_by_zip.csv` (ZIP → `crime_proxy` from homicide-based notebook); hash fallback if ZIP missing.
- **Weather**: [Open-Meteo Archive](https://open-meteo.com/) **historical daily** aggregates at geocoded lat/lon
  (multi-year heavy-precipitation and wind exposure — **not** a “today’s forecast”).

Training uses `use_nfhl=False` (no HTTP, hash-only crime/weather for stable synthetic training).
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import math
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent / "data"
_CRIME_CSV = _DATA_DIR / "crime_proxy_by_zip.csv"
_crime_by_zip: Optional[Dict[str, Dict[str, Any]]] = None

NFHL_MAPSERVER = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
NFHL_FLOOD_HAZARD_ZONES_LAYER = 28

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Zprojects-InsuranceCopilot/1.0 (commercial P&C demo; local dev)"

# Multi-year historical daily weather at a point (location / climate-style exposure, not current conditions).
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_ARCHIVE_START = "2014-01-01"
WEATHER_ARCHIVE_END = "2023-12-31"

_HTTP_TIMEOUT = 25.0
_WEATHER_HTTP_TIMEOUT = 22.0


def _zip_key_for_hash(zip_code: Optional[str], full_address: Optional[str]) -> str:
    """Five-digit key for hash-based crime/weather when no ZIP is known."""
    z = "".join(c for c in (zip_code or "") if c.isdigit())[:5]
    if len(z) >= 5:
        return z.ljust(5, "0")[:5]
    s = (full_address or "").strip().lower()
    if s:
        h = int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)
        return f"{h % 100000:05d}"
    return "00000"


def _load_crime_table() -> Dict[str, Dict[str, Any]]:
    """Lazy-load ZIP → {crime_proxy, murder_rate_per_100k_annual, city_ascii, ...}."""
    global _crime_by_zip
    if _crime_by_zip is not None:
        return _crime_by_zip
    _crime_by_zip = {}
    if not _CRIME_CSV.exists():
        logger.warning("Crime CSV not found at %s — using hash fallback for crime_proxy", _CRIME_CSV)
        return _crime_by_zip
    try:
        df = pd.read_csv(_CRIME_CSV, dtype={"zip_code": str})
        df["zip_code"] = df["zip_code"].astype(str).str.strip().str.zfill(5)
        for _, row in df.iterrows():
            z = row["zip_code"]
            if len(z) == 5:
                _crime_by_zip[z] = {
                    "crime_proxy": float(row["crime_proxy"]),
                    "murder_rate_per_100k_annual": float(row["murder_rate_per_100k_annual"]),
                    "city_ascii": row.get("city_ascii"),
                    "state_id": row.get("state_id"),
                }
    except Exception as e:
        logger.warning("Could not load crime CSV: %s", e)
        _crime_by_zip = {}
    return _crime_by_zip


def _zip5_from_digits(raw: Optional[str]) -> str:
    d = "".join(c for c in (raw or "") if c.isdigit())
    if len(d) >= 5:
        return d[:5]
    return ""


def _apply_crime_proxy(
    zip_for_lookup: str,
    hash_crime: float,
    *,
    use_csv: bool,
) -> Tuple[float, Dict[str, Any]]:
    """Return crime_proxy and evidence keys."""
    ev: Dict[str, Any] = {"crime_proxy_source": "hash_fallback"}
    if not use_csv or len(zip_for_lookup) != 5:
        return hash_crime, ev
    table = _load_crime_table()
    row = table.get(zip_for_lookup)
    if row is None:
        ev["crime_csv_miss"] = True
        return hash_crime, ev
    ev["crime_proxy_source"] = "csv_homicide_index"
    ev["crime_csv_path"] = str(_CRIME_CSV.name)
    ev["crime_murder_rate_per_100k_annual"] = row["murder_rate_per_100k_annual"]
    ev["crime_matched_city"] = row.get("city_ascii")
    ev["crime_matched_state_id"] = row.get("state_id")
    return float(row["crime_proxy"]), ev


def _hash_proxies(zip_key: str) -> Dict[str, float]:
    z = zip_key.ljust(5, "0")[:5]
    h = int(hashlib.sha256(z.encode()).hexdigest()[:8], 16)
    flood = (h % 1000) / 1000.0
    crime = ((h >> 10) % 1000) / 1000.0
    weather = ((h >> 20) % 1000) / 1000.0
    composite = 0.5 * flood + 0.3 * crime + 0.2 * weather
    return {
        "flood_proxy": flood,
        "crime_proxy": crime,
        "weather_proxy": weather,
        "location_composite": composite,
    }


def _geocode_zip_nominatim(zip5: str) -> Tuple[float, float]:
    """Return (longitude, latitude) for US ZIP using Nominatim."""
    params = {
        "postalcode": zip5,
        "country": "United States",
        "format": "json",
        "limit": "1",
        "addressdetails": "1",
    }
    url = NOMINATIM_SEARCH + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    if not data:
        raise ValueError(f"No geocode result for ZIP {zip5}")
    lon = float(data[0]["lon"])
    lat = float(data[0]["lat"])
    return lon, lat


def _geocode_address_nominatim(query: str) -> Tuple[float, float, Optional[str]]:
    """
    Free-form US address → (lon, lat, postcode if present in response).
    """
    params = {
        "q": query,
        "countrycodes": "us",
        "format": "json",
        "limit": "1",
        "addressdetails": "1",
    }
    url = NOMINATIM_SEARCH + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    if not data:
        raise ValueError(f"No geocode result for address: {query[:80]}...")
    lon = float(data[0]["lon"])
    lat = float(data[0]["lat"])
    addr = data[0].get("address") or {}
    pc = addr.get("postcode")
    if pc:
        digits = "".join(c for c in str(pc) if c.isdigit())[:5]
        postcode = digits if len(digits) >= 5 else None
    else:
        postcode = None
    return lon, lat, postcode


def _query_nfhl_zone(lon: float, lat: float) -> Optional[Dict[str, Any]]:
    geom = json.dumps(
        {"x": lon, "y": lat, "spatialReference": {"wkid": 4326}},
    )
    params = {
        "f": "json",
        "geometry": geom,
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "false",
    }
    base = f"{NFHL_MAPSERVER}/{NFHL_FLOOD_HAZARD_ZONES_LAYER}/query"
    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        payload = json.loads(resp.read().decode())
    feats = payload.get("features") or []
    if not feats:
        return None
    return feats[0].get("attributes") or {}


def _sfha_bool(sfha_tf: Optional[str]) -> Optional[bool]:
    if not sfha_tf:
        return None
    v = str(sfha_tf).strip().upper()
    if v == "T":
        return True
    if v == "F":
        return False
    return None


def _flood_proxy_from_nfhl_attrs(attrs: Dict[str, Any]) -> float:
    fld = str(attrs.get("FLD_ZONE") or "").strip().upper()
    sub = str(attrs.get("ZONE_SUBTY") or "").upper()
    sfha = _sfha_bool(attrs.get("SFHA_TF"))

    coastal = {"V", "VE", "VB"}
    sfha_zones = {"A", "AE", "AO", "AH", "AR", "A99", "V", "VE", "VB"}

    if fld in coastal:
        return 0.95
    if fld in sfha_zones or sfha is True:
        return 0.9 if fld not in coastal else 0.95
    if fld == "D":
        return 0.52
    if fld == "X":
        if "SHADED" in sub or "0.2%" in sub:
            return 0.33
        return 0.14
    if sfha is False and fld:
        return 0.2
    return 0.45


def _norm_clip(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.5
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def _percentile_linear(sorted_vals: list[float], q: float) -> float:
    """q in [0, 1]."""
    if not sorted_vals:
        return float("nan")
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    pos = (n - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _openmeteo_historical_weather_hazard(lat: float, lon: float) -> Tuple[float, Dict[str, Any]]:
    """
    Long-baseline severe-weather / climate exposure proxy (not a forecast).

    Uses Open-Meteo Archive daily series: heavy precipitation days and high wind days,
    aggregated over a fixed window, mapped to [0, 1].
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": WEATHER_ARCHIVE_START,
        "end_date": WEATHER_ARCHIVE_END,
        "daily": "precipitation_sum,wind_speed_10m_max",
    }
    url = OPEN_METEO_ARCHIVE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=_WEATHER_HTTP_TIMEOUT) as resp:
        payload = json.loads(resp.read().decode())
    daily = payload.get("daily") or {}
    times: list = daily.get("time") or []
    prec_raw = daily.get("precipitation_sum") or []
    wind_raw = daily.get("wind_speed_10m_max") or []
    if len(times) < 200:
        raise ValueError("Insufficient weather archive rows")

    prec: list[float] = []
    wind: list[float] = []
    for i in range(len(times)):
        p = prec_raw[i] if i < len(prec_raw) else None
        w = wind_raw[i] if i < len(wind_raw) else None
        prec.append(float(p) if p is not None else float("nan"))
        wind.append(float(w) if w is not None else float("nan"))

    years = {str(t)[:4] for t in times if isinstance(t, str) and len(t) >= 4}
    n_years = max(len(years), 1)

    heavy_days = sum(1 for p in prec if not math.isnan(p) and p >= 25.0)
    heavy_per_year = heavy_days / float(n_years)

    w_valid = sorted(w for w in wind if not math.isnan(w))
    if len(w_valid) < 100:
        raise ValueError("Insufficient wind samples")
    wind_p95 = _percentile_linear(w_valid, 0.95)

    heavy_score = _norm_clip(heavy_per_year, 0.0, 42.0)
    wind_score = _norm_clip(wind_p95, 8.0, 88.0)
    weather_proxy = 0.55 * heavy_score + 0.45 * wind_score

    ev: Dict[str, Any] = {
        "weather_proxy_source": "open_meteo_archive",
        "weather_exposure_note": (
            "Multi-year historical daily aggregates at this point (heavy rain + wind tail); "
            "not a current-conditions forecast."
        ),
        "weather_archive_start": WEATHER_ARCHIVE_START,
        "weather_archive_end": WEATHER_ARCHIVE_END,
        "weather_heavy_rain_days_ge_25mm_per_year_avg": round(heavy_per_year, 2),
        "weather_wind_daily_max_p95_kmh": round(wind_p95, 1),
        "weather_attribution": "Historical weather via Open-Meteo (https://open-meteo.com)",
    }
    return float(weather_proxy), ev


@functools.lru_cache(maxsize=512)
def _openmeteo_historical_weather_hazard_cached(lat_key: str, lon_key: str) -> Tuple[float, Dict[str, Any]]:
    return _openmeteo_historical_weather_hazard(float(lat_key), float(lon_key))


def location_risk_features(
    zip_code: Optional[str] = None,
    full_address: Optional[str] = None,
    *,
    use_nfhl: bool = True,
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """
    Returns (feature_floats, evidence_dict).

    Prefers **full_address** for geocoding (building-level point); falls back to **zip_code**.
    """
    fa = (full_address or "").strip()
    z_raw = (zip_code or "").strip()
    z_digits = "".join(c for c in z_raw if c.isdigit())
    zip5 = z_digits[:5].ljust(5, "0") if len(z_digits) >= 5 else ""

    zip_key = _zip_key_for_hash(zip_code, full_address)
    evidence: Dict[str, Any] = {
        "zip_normalized": zip5 or None,
        "full_address_input": fa or None,
        "nfhl_mapserver": NFHL_MAPSERVER,
        "nfhl_layer_id": NFHL_FLOOD_HAZARD_ZONES_LAYER,
        "flood_proxy_source": "hash_fallback",
    }

    if not use_nfhl:
        h = _hash_proxies(zip_key)
        evidence["note"] = "Synthetic training path: hash proxies only (no HTTP)."
        return h, evidence

    h_fallback = _hash_proxies(zip_key)
    weather_proxy = h_fallback["weather_proxy"]
    postcode_from_geo: Optional[str] = None

    try:
        lon: float
        lat: float

        if fa:
            q = fa if "," in fa or len(fa) > 10 else f"{fa}, United States"
            evidence["geocode_mode"] = "full_address"
            evidence["geocode_query"] = q
            try:
                lon, lat, postcode_from_geo = _geocode_address_nominatim(q)
            except (ValueError, urllib.error.URLError, OSError) as e1:
                if len(z_digits) >= 5:
                    logger.info("Address geocode failed, using ZIP: %s", e1)
                    lon, lat = _geocode_zip_nominatim(z_digits[:5])
                    postcode_from_geo = z_digits[:5]
                    evidence["geocode_mode"] = "zip_fallback"
                    evidence["geocode_fallback_reason"] = str(e1)
                else:
                    raise
        elif len(z_digits) >= 5:
            evidence["geocode_mode"] = "zip_only"
            lon, lat = _geocode_zip_nominatim(z_digits[:5])
            postcode_from_geo = z_digits[:5]
        else:
            raise ValueError("No geocodable address or ZIP")

        if postcode_from_geo:
            evidence["postcode_from_geocoder"] = postcode_from_geo
        evidence["geocoder"] = "nominatim_openstreetmap"
        evidence["geocoder_notice"] = "Data © OpenStreetMap contributors, ODbL 1.0"
        evidence["longitude"] = lon
        evidence["latitude"] = lat

        try:
            wp, w_ev = _openmeteo_historical_weather_hazard_cached(f"{lat:.2f}", f"{lon:.2f}")
            weather_proxy = wp
            evidence.update(w_ev)
        except Exception as e_w:
            logger.info("Historical weather hazard (Open-Meteo archive) failed: %s", e_w)
            evidence["weather_proxy_source"] = "hash_fallback"
            evidence["weather_error"] = str(e_w)

        attrs = _query_nfhl_zone(lon, lat)
        if attrs:
            flood_proxy = _flood_proxy_from_nfhl_attrs(attrs)
            evidence["flood_proxy_source"] = "nfhl"
            evidence["nfhl_fld_zone"] = attrs.get("FLD_ZONE")
            evidence["nfhl_zone_subty"] = attrs.get("ZONE_SUBTY")
            evidence["nfhl_sfha_tf"] = attrs.get("SFHA_TF")
            evidence["nfhl_sfha"] = _sfha_bool(attrs.get("SFHA_TF"))
        else:
            flood_proxy = h_fallback["flood_proxy"]
            evidence["flood_proxy_source"] = "hash_fallback"
            evidence["nfhl_miss_reason"] = (
                "No intersecting flood zone feature at this point (or outside NFHL coverage)."
            )

    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, json.JSONDecodeError, TimeoutError, OSError) as e:
        logger.warning("NFHL location pipeline failed: %s", e)
        flood_proxy = h_fallback["flood_proxy"]
        evidence["flood_proxy_source"] = "hash_fallback"
        evidence["error"] = str(e)
        if evidence.get("weather_proxy_source") is None:
            evidence["weather_proxy_source"] = "hash_fallback"
            evidence["weather_note"] = "Geocoding or upstream step failed before weather archive."

    zip_for_crime = _zip5_from_digits(postcode_from_geo or "") or _zip5_from_digits(z_raw)
    crime_proxy, crime_ev = _apply_crime_proxy(
        zip_for_crime,
        h_fallback["crime_proxy"],
        use_csv=True,
    )
    evidence.update(crime_ev)
    if zip_for_crime:
        evidence["zip_used_for_crime_lookup"] = zip_for_crime

    location_composite = 0.5 * flood_proxy + 0.3 * crime_proxy + 0.2 * weather_proxy

    floats = {
        "flood_proxy": flood_proxy,
        "crime_proxy": crime_proxy,
        "weather_proxy": weather_proxy,
        "location_composite": location_composite,
    }
    return floats, evidence


# Back-compat alias
zip_risk_features = location_risk_features
