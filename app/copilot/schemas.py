from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


Industry = Literal[
    "restaurant",
    "retail",
    "warehouse",
    "office",
    "manufacturing",
    "other",
]

BuildingType = Literal["masonry", "frame", "mixed", "unknown"]


class BusinessProfile(BaseModel):
    industry: Industry = Field(description="NAICS-style industry bucket")
    naics_code: Optional[str] = Field(None, description="Optional 6-digit NAICS")
    annual_revenue_usd: float = Field(ge=0, le=1e12)
    employee_count: int = Field(ge=0, le=50000)
    full_address: Optional[str] = Field(
        None,
        max_length=500,
        description="Street, city, state (US). Used for geocoding + NFHL when set.",
    )
    zip_code: Optional[str] = Field(
        None,
        max_length=15,
        description="ZIP/postal code; optional if full_address is provided.",
    )
    property_sqft: float = Field(ge=0, le=10_000_000)
    building_type: BuildingType = "unknown"
    building_owned: bool = False
    stores_customer_pii: bool = False
    has_kitchen_or_food_prep: Optional[bool] = None

    @model_validator(mode="after")
    def require_address_or_zip(self) -> "BusinessProfile":
        fa = (self.full_address or "").strip()
        zd = "".join(c for c in (self.zip_code or "") if c.isdigit())
        if len(fa) >= 5:
            return self
        if len(zd) >= 5:
            return self
        raise ValueError(
            "Provide full_address (e.g. street, city, state) or at least a 5-digit ZIP/postal code."
        )


class AnalyzeRequest(BaseModel):
    profile: BusinessProfile
    policy_text: Optional[str] = None
    use_sample_policy: bool = False


class PolicyExtraction(BaseModel):
    general_liability_limit_usd: Optional[float] = None
    property_limit_usd: Optional[float] = None
    business_interruption: bool = False
    cyber_coverage: bool = False
    deductible_usd: Optional[float] = None
    flood_excluded: Optional[bool] = None
    raw_snippets: list[str] = Field(default_factory=list)


class RiskBreakdown(BaseModel):
    risk_score: float = Field(ge=0, le=1)
    claim_probability: float = Field(ge=0, le=1)
    shap_percentages: dict[str, float]
    top_drivers: list[str]


class CoverageGap(BaseModel):
    severity: Literal["high", "medium", "low"]
    title: str
    detail: str


class PremiumEstimate(BaseModel):
    low_usd: int
    high_usd: int
    basis: str


class Recommendation(BaseModel):
    coverages: list[str]
    actions: list[str]
    narrative: str


class NaicsResolution(BaseModel):
    """Result of resolving a NAICS code against the 2012 industry CSV (US sectors)."""

    matched: bool
    input_raw: Optional[str] = None
    normalized_input: Optional[str] = None
    sector_code: Optional[str] = None
    industry_title: Optional[str] = None
    industry_risk: Optional[float] = Field(None, ge=0, le=1, description="Sector prior blended into model")
    note: Optional[str] = None


class AnalyzeResponse(BaseModel):
    profile_summary: str
    risk: RiskBreakdown
    key_risks: list[str]
    recommended_coverages: list[str]
    policy_insights: Optional[PolicyExtraction] = None
    coverage_gaps: list[CoverageGap]
    premium: PremiumEstimate
    recommendation: Recommendation
    rag_citations: list[str] = Field(default_factory=list)
    location_evidence: Optional[dict[str, Any]] = Field(
        None,
        description="FEMA NFHL + geocoder metadata; crime/weather still placeholders until datasets are added.",
    )
    naics: Optional[NaicsResolution] = Field(
        None,
        description="2012 NAICS resolution from Census industry CSV when a code was provided.",
    )


class RiskoMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=16_000)


class RiskoChatRequest(BaseModel):
    """Conversation turns for the Risko insurance assistant (OpenAI-compatible backend)."""

    messages: list[RiskoMessage] = Field(..., min_length=1, max_length=64)

    @model_validator(mode="after")
    def at_least_one_user_turn(self) -> "RiskoChatRequest":
        if not any(m.role == "user" for m in self.messages):
            raise ValueError("At least one user message is required.")
        return self


class RiskoChatResponse(BaseModel):
    message: str
    model: str = ""


class QuoteApplicant(BaseModel):
    """Structured answers for forwarding to a configured insurer / aggregator quote API."""

    zip_code: str = Field(..., min_length=3, max_length=15)
    full_address: Optional[str] = Field(None, max_length=500)
    contact_email: Optional[str] = None
    industry: str = Field(..., max_length=120)
    annual_revenue_usd: float = Field(ge=0, le=1e12)
    employee_count: int = Field(ge=0, le=50000)
    property_sqft: float = Field(ge=0, le=10_000_000)
    years_in_business: Optional[int] = Field(None, ge=0, le=150)
    entity_type: Optional[str] = Field(None, max_length=80)
    coverages_requested: list[str] = Field(default_factory=list)
    general_liability_limit_usd: Optional[float] = Field(None, ge=0)
    property_limit_usd: Optional[float] = Field(None, ge=0)
    deductible_preference_usd: Optional[float] = Field(None, ge=0)
    claims_in_last_5_years: Optional[bool] = None
    workers_comp_needed: Optional[bool] = None
    cyber_needed: Optional[bool] = None


class QuoteCompareRequest(BaseModel):
    applicant: QuoteApplicant


class QuoteOffer(BaseModel):
    company_name: str
    premium_annual_usd: float = Field(ge=0)
    plan_name: Optional[str] = None
    notes: Optional[str] = None


class QuoteCompareResponse(BaseModel):
    offers: list[QuoteOffer]
    # configured: True when INSURANCE_QUOTES_API_URL is set (live partner).
    configured: bool = True
    # mock_mode: True when offers are generated locally for demo (no partner URL).
    mock_mode: bool = False
    message: Optional[str] = None
    submission_payload_echo: dict[str, Any] = Field(default_factory=dict)
