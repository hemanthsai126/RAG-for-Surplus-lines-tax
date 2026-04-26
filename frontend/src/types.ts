export type Industry =
  | "restaurant"
  | "retail"
  | "warehouse"
  | "office"
  | "manufacturing"
  | "other";

export type BuildingType = "masonry" | "frame" | "mixed" | "unknown";

export interface BusinessProfile {
  industry: Industry;
  naics_code?: string | null;
  annual_revenue_usd: number;
  employee_count: number;
  /** Street, city, state — used for geocoding (preferred). */
  full_address?: string | null;
  /** Optional; used if address geocoding fails or for ZIP-only runs. */
  zip_code?: string | null;
  property_sqft: number;
  building_type: BuildingType;
  building_owned: boolean;
  stores_customer_pii: boolean;
  has_kitchen_or_food_prep?: boolean | null;
}

export interface PolicyExtraction {
  general_liability_limit_usd?: number | null;
  property_limit_usd?: number | null;
  business_interruption: boolean;
  cyber_coverage: boolean;
  deductible_usd?: number | null;
  flood_excluded?: boolean | null;
  raw_snippets: string[];
}

export interface RiskBreakdown {
  risk_score: number;
  claim_probability: number;
  shap_percentages: Record<string, number>;
  top_drivers: string[];
}

export interface CoverageGap {
  severity: "high" | "medium" | "low";
  title: string;
  detail: string;
}

export interface PremiumEstimate {
  low_usd: number;
  high_usd: number;
  basis: string;
}

export interface Recommendation {
  coverages: string[];
  actions: string[];
  narrative: string;
}

/** 2012 NAICS resolution from backend Census industry CSV */
export type RiskoMessage = { role: "user" | "assistant"; content: string };

export interface RiskoChatResponse {
  message: string;
  model?: string;
}

export interface NaicsResolution {
  matched: boolean;
  input_raw?: string | null;
  normalized_input?: string | null;
  sector_code?: string | null;
  industry_title?: string | null;
  industry_risk?: number | null;
  note?: string | null;
}

/** Compare-quotes wizard → POST /api/quotes/compare */
export interface QuoteApplicantPayload {
  zip_code: string;
  full_address?: string | null;
  contact_email?: string | null;
  industry: string;
  annual_revenue_usd: number;
  employee_count: number;
  property_sqft: number;
  years_in_business?: number;
  entity_type?: string | null;
  coverages_requested: string[];
  general_liability_limit_usd?: number | null;
  property_limit_usd?: number | null;
  deductible_preference_usd?: number | null;
  claims_in_last_5_years?: boolean | null;
  workers_comp_needed?: boolean | null;
  cyber_needed?: boolean | null;
}

export interface QuoteCompareRequestPayload {
  applicant: QuoteApplicantPayload;
}

export interface QuoteOfferRow {
  company_name: string;
  premium_annual_usd: number;
  plan_name?: string | null;
  notes?: string | null;
}

export interface QuoteCompareResponse {
  offers: QuoteOfferRow[];
  configured: boolean;
  /** True when offers are demo-generated (no partner URL). */
  mock_mode?: boolean;
  message?: string | null;
  submission_payload_echo: Record<string, unknown>;
}

export interface AnalyzeResponse {
  profile_summary: string;
  risk: RiskBreakdown;
  key_risks: string[];
  recommended_coverages: string[];
  policy_insights: PolicyExtraction | null;
  coverage_gaps: CoverageGap[];
  premium: PremiumEstimate;
  recommendation: Recommendation;
  rag_citations: string[];
  location_evidence?: Record<string, unknown> | null;
  naics?: NaicsResolution | null;
}
