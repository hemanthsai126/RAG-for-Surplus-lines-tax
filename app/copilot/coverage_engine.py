"""Rule-based coverage mapping + gap detection vs extracted policy."""

from __future__ import annotations

from typing import Optional

from app.copilot.industry_risk import INDUSTRY_LABELS
from app.copilot.schemas import (
    BusinessProfile,
    CoverageGap,
    NaicsResolution,
    PolicyExtraction,
    PremiumEstimate,
    Recommendation,
)


def _needs_property(profile: BusinessProfile) -> bool:
    return profile.property_sqft > 400


def _needs_bi(profile: BusinessProfile) -> bool:
    return profile.annual_revenue_usd > 400_000 or profile.employee_count > 15


def _needs_cyber(profile: BusinessProfile) -> bool:
    return profile.stores_customer_pii


def recommended_coverages(
    profile: BusinessProfile,
    naics: Optional[NaicsResolution] = None,
) -> list[str]:
    out: list[str] = ["General Liability"]
    if _needs_property(profile):
        out.append("Commercial Property")
    if _needs_bi(profile):
        out.append("Business Interruption")
    if _needs_cyber(profile):
        out.append("Cyber Liability")
    if profile.industry in ("restaurant", "manufacturing"):
        out.append("Equipment Breakdown (optional)")
    if naics and naics.matched and naics.sector_code == "72":
        if "Equipment Breakdown (optional)" not in out:
            out.append("Equipment Breakdown (optional)")
        out.append("Food spoilage / equipment (review)")
    if naics and naics.matched and naics.sector_code == "31-33":
        if "Equipment Breakdown (optional)" not in out:
            out.append("Equipment Breakdown (optional)")
    return out


def _naics_sector_risk_bullets(naics: Optional[NaicsResolution]) -> list[str]:
    if not naics or not naics.matched or not naics.sector_code:
        return []
    c = naics.sector_code
    title = (naics.industry_title or "")[:80]
    if c == "21":
        return [f"NAICS {c} ({title}): heavy equipment, environmental, and safety exposure."]
    if c == "23":
        return [f"NAICS {c} ({title}): job-site injury, subcontractor, and builders risk exposure."]
    if c == "31-33":
        return [f"NAICS {c} ({title}): product liability, machinery, and supply chain exposure."]
    if c in ("48-49 (104)",):
        return [f"NAICS sector ({title}): fleet, cargo, and warehouse liability exposure."]
    if c == "52":
        return [f"NAICS {c} ({title}): E&O and financial lines exposure (review specialty)."]
    if c == "62":
        return [f"NAICS {c} ({title}): professional / medical malpractice & GL exposure."]
    if c == "72":
        return [f"NAICS {c} ({title}): fire, food safety, liquor, and guest safety exposure."]
    if c == "54":
        return [f"NAICS {c} ({title}): professional liability / E&O exposure."]
    return [f"NAICS sector {c}: {title}."]

def key_risks(profile: BusinessProfile, naics: Optional[NaicsResolution] = None) -> list[str]:
    risks: list[str] = []
    risks.extend(_naics_sector_risk_bullets(naics))
    if profile.industry == "restaurant":
        risks.append("Kitchen fire and equipment hazards")
        risks.append("Slip-and-fall / customer injury exposure")
    elif profile.industry == "retail":
        risks.append("Customer injury on premises")
        risks.append("Theft and inventory loss")
    elif profile.industry == "warehouse":
        risks.append("Forklift and loading dock injuries")
        risks.append("Property damage to stock")
    else:
        risks.append("General premises liability")
    loc_note = "Location-driven flood/crime/weather proxies elevate baseline hazard."
    risks.append(loc_note)
    if profile.stores_customer_pii:
        risks.append("Data breach / privacy exposure (PII)")
    # Dedupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for r in risks:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out[:8]


def detect_gaps(
    profile: BusinessProfile,
    risk_score: float,
    policy: Optional[PolicyExtraction],
    recommended: list[str],
) -> list[CoverageGap]:
    gaps: list[CoverageGap] = []
    pol = policy

    def has_bi() -> bool:
        if pol is None:
            return False
        return pol.business_interruption

    def has_cyber() -> bool:
        if pol is None:
            return False
        return pol.cyber_coverage

    gl_limit = pol.general_liability_limit_usd if pol else None

    if "Business Interruption" in recommended and not has_bi():
        gaps.append(
            CoverageGap(
                severity="high",
                title="Missing Business Interruption",
                detail="Revenue and headcount suggest income dependency; BI is not evident in the policy text.",
            )
        )
    if _needs_cyber(profile) and not has_cyber():
        gaps.append(
            CoverageGap(
                severity="high",
                title="Missing Cyber coverage",
                detail="You indicated customer PII is stored; cyber/network security coverage is not evident.",
            )
        )
    if gl_limit is not None and gl_limit < 1_000_000 and risk_score > 0.45:
        gaps.append(
            CoverageGap(
                severity="medium",
                title="General liability limit may be low",
                detail=f"Each-occurrence limit around ${gl_limit:,.0f} vs typical $1M+ for this exposure profile.",
            )
        )
    if pol and pol.flood_excluded and risk_score > 0.55:
        gaps.append(
            CoverageGap(
                severity="medium",
                title="Flood excluded on file",
                detail="Flood is excluded in retrieved policy language; evaluate flood endorsement if location is flood-prone.",
            )
        )
    if pol is None and profile.property_sqft > 2000:
        gaps.append(
            CoverageGap(
                severity="low",
                title="No policy on file to compare",
                detail="Upload a policy PDF for limit-level gap detection and RAG citations.",
            )
        )
    return gaps


def premium_band(risk_score: float, profile: BusinessProfile) -> PremiumEstimate:
    base = 2500 + 0.00002 * profile.annual_revenue_usd + 12 * profile.employee_count
    factor = 0.75 + 0.85 * risk_score
    low = int(base * factor * 0.9)
    high = int(base * factor * 1.25)
    low = max(1200, low)
    high = max(low + 500, high)
    return PremiumEstimate(
        low_usd=low,
        high_usd=high,
        basis="Heuristic underwriting band from risk score, revenue, and headcount (not a quote).",
    )


def build_narrative(
    profile: BusinessProfile,
    risk_score: float,
    shap_pct: dict[str, float],
    gaps: list[CoverageGap],
    naics: Optional[NaicsResolution] = None,
) -> Recommendation:
    ind = INDUSTRY_LABELS.get(profile.industry, profile.industry)
    if naics and naics.matched and naics.industry_title:
        ind = f"{ind} — {naics.industry_title}"
    top = sorted(shap_pct.items(), key=lambda x: -x[1])[:3]
    drivers = ", ".join(f"{k.replace('_', ' ')} ({v:.0f}%)" for k, v in top)
    actions = []
    for g in gaps:
        if g.severity == "high":
            actions.append(g.title)
    if not actions:
        actions.append("Review limits and endorsements annually as exposures change.")
    cov = recommended_coverages(profile)
    if profile.full_address and profile.full_address.strip():
        loc = profile.full_address.strip()
        if len(loc) > 80:
            loc = loc[:77] + "…"
    elif profile.zip_code and profile.zip_code.strip():
        loc = f"ZIP {profile.zip_code.strip()}"
    else:
        loc = "location"
    narrative = (
        f"{ind} at {loc}: modeled risk score {risk_score:.2f}. "
        f"SHAP-style drivers: {drivers}. "
        f"Prioritize: {actions[0] if actions else 'align limits with exposure'}."
    )
    return Recommendation(coverages=cov, actions=actions[:5], narrative=narrative)
