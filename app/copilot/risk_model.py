"""XGBoost risk model with SHAP; trains on synthetic data or user CSV in data/."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.model_selection import train_test_split

from app.copilot.industry_risk import INDUSTRY_RISK
from app.copilot.location_risk import location_risk_features
from app.copilot.naics_2012 import blended_industry_risk_for_model

FEATURE_NAMES = [
    "industry_risk",
    "log_revenue",
    "log_employees",
    "log_sqft",
    "location_composite",
    "flood_proxy",
    "crime_proxy",
    "building_owned",
    "stores_pii",
    "kitchen_flag",
]

_COPILOT = Path(__file__).resolve().parent
DATA_DIR = _COPILOT / "data"
MODEL_PATH = DATA_DIR / "risk_xgb.joblib"


def _industry_key(industry: str) -> float:
    return INDUSTRY_RISK.get(industry, 0.5)


def featurize_row(
    industry: str,
    annual_revenue_usd: float,
    employee_count: int,
    zip_code: Optional[str],
    property_sqft: float,
    building_owned: bool,
    stores_customer_pii: bool,
    has_kitchen_or_food_prep: Optional[bool],
    industry_override: Optional[str],
    *,
    industry_risk_value: Optional[float] = None,
    full_address: Optional[str] = None,
    use_nfhl: bool = False,
    loc_floats: Optional[Dict[str, float]] = None,
) -> np.ndarray:
    if loc_floats is not None:
        loc = loc_floats
    else:
        loc, _ = location_risk_features(
            zip_code=zip_code,
            full_address=full_address,
            use_nfhl=use_nfhl,
        )
    rev = max(annual_revenue_usd, 1.0)
    emp = max(employee_count, 1)
    sqft = max(property_sqft, 1.0)
    kitchen = 1.0 if (has_kitchen_or_food_prep if has_kitchen_or_food_prep is not None else industry == "restaurant") else 0.0
    if industry_risk_value is not None:
        base = float(np.clip(industry_risk_value, 0.0, 1.0))
    elif industry_override:
        base = _industry_key(industry_override)
    else:
        base = _industry_key(industry)
    return np.array(
        [
            base,
            np.log10(rev),
            np.log10(emp),
            np.log10(sqft),
            loc["location_composite"],
            loc["flood_proxy"],
            loc["crime_proxy"],
            float(building_owned),
            float(stores_customer_pii),
            kitchen,
        ],
        dtype=np.float32,
    )


def _synthetic_frame(n: int = 8000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    industries = list(INDUSTRY_RISK.keys())
    rows = []
    for _ in range(n):
        ind = industries[int(rng.integers(0, len(industries)))]
        rev = float(10 ** rng.uniform(4.5, 7.2))
        emp = int(rng.integers(3, 250))
        sqft = float(rng.uniform(800, 80_000))
        z = f"{rng.integers(10000, 99999):05d}"
        owned = bool(rng.random() < 0.45)
        pii = bool(rng.random() < 0.35)
        kitchen = 1.0 if ind == "restaurant" else float(rng.random() < 0.08)
        vec = featurize_row(
            ind,
            rev,
            emp,
            z,
            sqft,
            owned,
            pii,
            bool(kitchen),
            None,
            industry_risk_value=None,
            full_address=None,
            use_nfhl=False,
        )
        # Synthetic label: smooth function + noise
        score = (
            0.35 * vec[0]
            + 0.12 * (vec[4] + vec[5]) / 2
            + 0.08 * vec[1] / 7.5
            + 0.1 * vec[7]
            + 0.12 * vec[8]
            + 0.06 * vec[9]
            + float(rng.normal(0, 0.06))
        )
        score = float(np.clip(score + rng.normal(0, 0.04), 0.02, 0.98))
        claim_p = float(np.clip(0.15 + 0.55 * score + rng.normal(0, 0.05), 0.01, 0.95))
        rows.append(
            {
                **{FEATURE_NAMES[i]: vec[i] for i in range(len(FEATURE_NAMES))},
                "risk_score": score,
                "claim_probability": claim_p,
            }
        )
    return pd.DataFrame(rows)


def _load_user_csv() -> Optional[pd.DataFrame]:
    """If user drops Allstate-style CSV in backend/data/, merge or replace."""
    candidates = list(DATA_DIR.glob("*.csv")) if DATA_DIR.exists() else []
    if not candidates:
        return None
    # Prefer a file named training.csv or use first csv
    preferred = DATA_DIR / "training.csv"
    path = preferred if preferred.exists() else sorted(candidates)[0]
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    required = set(FEATURE_NAMES) | {"risk_score"}
    if not required.issubset(set(df.columns)):
        return None
    return df


def ensure_model() -> tuple[xgb.XGBRegressor, list[str]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if MODEL_PATH.exists():
        bundle = joblib.load(MODEL_PATH)
        return bundle["model"], bundle["feature_names"]

    df_user = _load_user_csv()
    df = df_user if df_user is not None else _synthetic_frame()
    X = df[FEATURE_NAMES]
    y = df["risk_score"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.15, random_state=42)
    model = xgb.XGBRegressor(
        n_estimators=220,
        max_depth=5,
        learning_rate=0.06,
        subsample=0.9,
        colsample_bytree=0.85,
        reg_lambda=1.2,
        random_state=42,
    )
    model.fit(X_train, y_train)
    joblib.dump({"model": model, "feature_names": FEATURE_NAMES}, MODEL_PATH)
    meta = {"source": "user_csv" if df_user is not None else "synthetic", "n_rows": len(df)}
    (DATA_DIR / "model_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return model, FEATURE_NAMES


_explainer: Optional[shap.TreeExplainer] = None


def _get_explainer(model: xgb.XGBRegressor) -> "shap.TreeExplainer":
    global _explainer
    if _explainer is None:
        _explainer = shap.TreeExplainer(model)
    return _explainer


def predict_with_shap(
    industry: str,
    annual_revenue_usd: float,
    employee_count: int,
    zip_code: Optional[str],
    full_address: Optional[str],
    property_sqft: float,
    building_owned: bool,
    stores_customer_pii: bool,
    has_kitchen_or_food_prep: Optional[bool],
    naics_code: Optional[str] = None,
) -> Tuple[float, float, dict[str, float], list[str], Dict[str, Any], Dict[str, Any]]:
    model, names = ensure_model()
    loc_floats, location_evidence = location_risk_features(
        zip_code=zip_code,
        full_address=full_address,
        use_nfhl=True,
    )
    blended_risk, naics_info = blended_industry_risk_for_model(industry, naics_code)
    vec = featurize_row(
        industry,
        annual_revenue_usd,
        employee_count,
        zip_code,
        property_sqft,
        building_owned,
        stores_customer_pii,
        has_kitchen_or_food_prep,
        None,
        industry_risk_value=blended_risk,
        full_address=full_address,
        use_nfhl=True,
        loc_floats=loc_floats,
    )
    X = pd.DataFrame([vec], columns=names)
    risk_raw = float(model.predict(X)[0])
    risk = float(np.clip(risk_raw, 0.0, 1.0))
    claim_p = float(np.clip(0.12 + 0.65 * risk, 0.01, 0.95))

    explainer = _get_explainer(model)
    sv = explainer.shap_values(X)[0]
    pairs = sorted(zip(names, np.abs(sv)), key=lambda x: -x[1])
    total = sum(w for _, w in pairs) or 1.0
    shap_pct = {n: round(100 * w / total, 1) for n, w in pairs}
    top_drivers = [f"{n.replace('_', ' ')} contributed about {shap_pct[n]:.0f}% of this prediction's magnitude" for n, _ in pairs[:4]]

    return risk, claim_p, shap_pct, top_drivers, location_evidence, naics_info
