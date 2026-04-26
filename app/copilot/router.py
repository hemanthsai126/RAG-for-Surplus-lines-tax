"""P&C Copilot API routes ported from Zprojects (NAICS, analyze, quotes, Risko chat, policy upload)."""

from __future__ import annotations

import io
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pypdf import PdfReader

from app.copilot.coverage_engine import (
    build_narrative,
    detect_gaps,
    key_risks,
    premium_band,
    recommended_coverages,
)
from app.copilot.industry_risk import INDUSTRY_LABELS
from app.copilot.naics_2012 import resolve_naics_input
from app.copilot.quote_compare import fetch_quote_offers
from app.copilot.rag_policy import PolicyRAG, load_sample_policy_text
from app.copilot.risk_model import predict_with_shap
from app.copilot.risko_llm import risko_chat_completion
from app.copilot.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    BusinessProfile,
    NaicsResolution,
    QuoteCompareRequest,
    QuoteCompareResponse,
    RiskBreakdown,
    RiskoChatRequest,
    RiskoChatResponse,
)

router = APIRouter(tags=["copilot"])


def _pdf_to_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            parts.append(t)
    return "\n".join(parts)


@router.get("/api/naics/lookup", response_model=NaicsResolution)
def naics_lookup(code: str = "") -> NaicsResolution:
    """Resolve a NAICS code to 2012 sector title (from Census industry CSV)."""
    return NaicsResolution(**resolve_naics_input(code))


@router.post("/api/quotes/compare", response_model=QuoteCompareResponse)
async def quotes_compare(req: QuoteCompareRequest) -> QuoteCompareResponse:
    """Forward applicant answers to INSURANCE_QUOTES_API_URL when configured."""
    try:
        return await fetch_quote_offers(req)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.post("/api/risko/chat", response_model=RiskoChatResponse)
async def risko_chat(req: RiskoChatRequest) -> RiskoChatResponse:
    """
    **Risko** — insurance-only chat without document retrieval.
    Default: Ollama. Optional: ``RISKO_LLM_BACKEND=openai`` + ``OPENAI_API_KEY``.
    """
    try:
        text, model = await risko_chat_completion(req.messages)
        return RiskoChatResponse(message=text, model=model)
    except RuntimeError as e:
        detail = str(e)
        if any(
            s in detail
            for s in (
                "OPENAI_API_KEY",
                "Cannot reach Ollama",
                "RISKO_LLM_BACKEND=openai",
                "ollama pull",
                "Ollama returned",
            )
        ):
            raise HTTPException(status_code=503, detail=detail) from e
        raise HTTPException(status_code=502, detail=detail) from e


@router.post("/api/upload-policy")
async def upload_policy(file: UploadFile = File(...)) -> dict[str, str]:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF policy.")
    raw = await file.read()
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 15MB).")
    try:
        text = _pdf_to_text(raw)
    except Exception as e:
        raise HTTPException(400, f"Could not read PDF: {e}") from e
    if not text.strip():
        raise HTTPException(400, "No extractable text in PDF (try a text-based PDF).")
    return {"text": text}


def _run_analysis(
    profile: BusinessProfile,
    policy_text: Optional[str],
    use_sample_policy: bool,
) -> AnalyzeResponse:
    text = (policy_text or "").strip()
    if not text and use_sample_policy:
        text = load_sample_policy_text()

    policy_insights = None
    rag_citations: list[str] = []
    if text:
        rag = PolicyRAG()
        policy_insights, rag_citations = rag.analyze_policy(text)

    risk, claim_p, shap_pct, top_drivers, location_evidence, naics_info = predict_with_shap(
        profile.industry,
        profile.annual_revenue_usd,
        profile.employee_count,
        profile.zip_code,
        profile.full_address,
        profile.property_sqft,
        profile.building_owned,
        profile.stores_customer_pii,
        profile.has_kitchen_or_food_prep,
        profile.naics_code,
    )

    naics_resolved: Optional[NaicsResolution] = None
    if (profile.naics_code or "").strip():
        naics_resolved = NaicsResolution(**naics_info)

    rec_cov = recommended_coverages(profile, naics_resolved)
    gaps = detect_gaps(profile, risk, policy_insights, rec_cov)
    prem = premium_band(risk, profile)
    narrative = build_narrative(profile, risk, shap_pct, gaps, naics_resolved)

    ind_label = INDUSTRY_LABELS.get(profile.industry, profile.industry)
    loc_bits: list[str] = []
    if profile.full_address and profile.full_address.strip():
        a = profile.full_address.strip()
        loc_bits.append(a if len(a) <= 72 else a[:69] + "…")
    if profile.zip_code and profile.zip_code.strip():
        loc_bits.append(f"ZIP {profile.zip_code.strip()}")
    loc_str = " · ".join(loc_bits) if loc_bits else "location"
    naics_bit = ""
    if naics_resolved and naics_resolved.matched and naics_resolved.industry_title:
        naics_bit = f"{naics_resolved.industry_title} [{naics_resolved.sector_code}] · "
    summary = (
        f"{naics_bit}{ind_label} | ~${profile.annual_revenue_usd:,.0f} revenue | "
        f"{profile.employee_count} employees | {profile.property_sqft:,.0f} sq ft | {loc_str}"
    )

    return AnalyzeResponse(
        profile_summary=summary,
        risk=RiskBreakdown(
            risk_score=round(risk, 4),
            claim_probability=round(claim_p, 4),
            shap_percentages=shap_pct,
            top_drivers=top_drivers,
        ),
        key_risks=key_risks(profile, naics_resolved),
        recommended_coverages=rec_cov,
        policy_insights=policy_insights,
        coverage_gaps=gaps,
        premium=prem,
        recommendation=narrative,
        rag_citations=rag_citations,
        location_evidence=location_evidence,
        naics=naics_resolved,
    )


@router.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    return _run_analysis(req.profile, req.policy_text, req.use_sample_policy)


@router.post("/api/analyze-upload", response_model=AnalyzeResponse)
async def analyze_upload(
    industry: str = Form(...),
    annual_revenue_usd: float = Form(...),
    employee_count: int = Form(...),
    property_sqft: float = Form(...),
    zip_code: Optional[str] = Form(None),
    full_address: Optional[str] = Form(None),
    building_owned: bool = Form(False),
    stores_customer_pii: bool = Form(False),
    building_type: str = Form("unknown"),
    naics_code: Optional[str] = Form(None),
    has_kitchen_or_food_prep: Optional[str] = Form(None),
    use_sample_policy: bool = Form(False),
    policy_file: Optional[UploadFile] = File(None),
) -> AnalyzeResponse:
    kitchen: Optional[bool]
    if has_kitchen_or_food_prep is None or has_kitchen_or_food_prep == "":
        kitchen = None
    else:
        kitchen = has_kitchen_or_food_prep.lower() in ("true", "1", "yes")

    profile = BusinessProfile(
        industry=industry,  # type: ignore[arg-type]
        naics_code=naics_code,
        annual_revenue_usd=annual_revenue_usd,
        employee_count=int(employee_count),
        full_address=full_address,
        zip_code=zip_code,
        property_sqft=property_sqft,
        building_type=building_type,  # type: ignore[arg-type]
        building_owned=building_owned,
        stores_customer_pii=stores_customer_pii,
        has_kitchen_or_food_prep=kitchen,
    )

    policy_text: Optional[str] = None
    if policy_file and policy_file.filename:
        raw = await policy_file.read()
        policy_text = _pdf_to_text(raw)

    return _run_analysis(profile, policy_text, use_sample_policy)
