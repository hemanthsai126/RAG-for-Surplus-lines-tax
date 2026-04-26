import { type FormEvent, useEffect, useMemo, useState } from "react";
import { analyzeBusiness, extractPdfText, lookupNaics } from "../api";
import type { AnalyzeResponse, BuildingType, BusinessProfile, Industry, NaicsResolution } from "../types";

const INDUSTRIES: { value: Industry; label: string }[] = [
  { value: "restaurant", label: "Restaurant / food" },
  { value: "retail", label: "Retail" },
  { value: "warehouse", label: "Warehouse / logistics" },
  { value: "office", label: "Office / professional" },
  { value: "manufacturing", label: "Manufacturing" },
  { value: "other", label: "Other" },
];

const BUILDINGS: { value: BuildingType; label: string }[] = [
  { value: "masonry", label: "Masonry / non-combustible" },
  { value: "frame", label: "Frame / wood" },
  { value: "mixed", label: "Mixed" },
  { value: "unknown", label: "Unknown" },
];

function riskLabel(score: number): string {
  if (score >= 0.65) return "Medium–High";
  if (score >= 0.4) return "Medium";
  if (score >= 0.25) return "Low–Medium";
  return "Low";
}

function ScoreRing({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100);
  const dash = 2 * Math.PI * 42;
  const offset = dash * (1 - value);
  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative h-36 w-36">
        <svg className="-rotate-90 transform" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="42" fill="none" stroke="#e2e8f0" strokeWidth="8" />
          <circle
            cx="50"
            cy="50"
            r="42"
            fill="none"
            stroke="url(#grad)"
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={dash}
            strokeDashoffset={offset}
            className="transition-[stroke-dashoffset] duration-700 ease-out"
          />
          <defs>
            <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#0d9488" />
              <stop offset="100%" stopColor="#14b8a6" />
            </linearGradient>
          </defs>
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono text-3xl font-semibold text-slate-800">{pct}</span>
          <span className="text-xs text-slate-500">risk index</span>
        </div>
      </div>
      <p className="text-center text-sm text-slate-600">{label}</p>
    </div>
  );
}

function ShapBars({ shap }: { shap: Record<string, number> }) {
  const rows = useMemo(
    () => Object.entries(shap).sort((a, b) => b[1] - a[1]),
    [shap],
  );
  return (
    <div className="space-y-3">
      {rows.map(([k, v]) => (
        <div key={k}>
          <div className="mb-1 flex justify-between text-xs text-slate-600">
            <span className="capitalize">{k.replaceAll("_", " ")}</span>
            <span className="font-mono text-accent">{v.toFixed(1)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-gradient-to-r from-accent-dim to-accent transition-all duration-500"
              style={{ width: `${Math.min(100, v)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Home() {
  const [profile, setProfile] = useState<BusinessProfile>({
    industry: "restaurant",
    naics_code: "",
    annual_revenue_usd: 850_000,
    employee_count: 22,
    full_address: "123 Market St, San Francisco, CA 94102",
    zip_code: "",
    property_sqft: 4200,
    building_type: "frame",
    building_owned: false,
    stores_customer_pii: true,
    has_kitchen_or_food_prep: null,
  });
  const [policyFile, setPolicyFile] = useState<File | null>(null);
  const [pastedPolicy, setPastedPolicy] = useState("");
  const [useSamplePolicy, setUseSamplePolicy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [naicsPreview, setNaicsPreview] = useState<NaicsResolution | null>(null);

  useEffect(() => {
    const code = (profile.naics_code ?? "").trim();
    if (code.length < 2) {
      setNaicsPreview(null);
      return;
    }
    const id = window.setTimeout(() => {
      lookupNaics(code)
        .then(setNaicsPreview)
        .catch(() => setNaicsPreview(null));
    }, 420);
    return () => clearTimeout(id);
  }, [profile.naics_code]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      let text = pastedPolicy.trim() || null;
      if (policyFile) {
        text = await extractPdfText(policyFile);
      }
      const res = await analyzeBusiness(profile, text, useSamplePolicy && !text);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <header className="border-b border-slate-200 bg-white/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-10 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="mb-2 font-mono text-xs uppercase tracking-[0.2em] text-teal-700">
              Commercial P&C · SMB focus
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900 md:text-4xl">
              P&amp;C Copilot
            </h1>
            <p className="mt-3 max-w-xl text-slate-600">
              Underwriting-style risk scoring with SHAP, policy TF-IDF insights, coverage gaps, and premium bands
              (illustrative). Part of the <strong>Insurance RAG</strong> repo — not a bindable quote.
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4 text-sm text-slate-600">
            <p className="font-mono text-xs text-slate-500">Model output → SHAP → structured UI</p>
            <p className="mt-1 text-slate-700">Replace broker + underwriter workflow (simulated).</p>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-10 px-6 pt-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <section className="space-y-6">
          <form
            onSubmit={onSubmit}
            className="rounded-2xl border border-slate-200 bg-white p-6 shadow-lg shadow-slate-300/40"
          >
            <h2 className="text-lg font-semibold text-slate-900">Business profile</h2>
            <p className="mt-1 text-sm text-slate-500">Structured inputs → feature engineering → XGBoost</p>

            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <label className="block sm:col-span-2">
                <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Industry</span>
                <select
                  className="mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-900 shadow-sm outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  value={profile.industry}
                  onChange={(e) =>
                    setProfile({ ...profile, industry: e.target.value as Industry })
                  }
                >
                  {INDUSTRIES.map((i) => (
                    <option key={i.value} value={i.value}>
                      {i.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="sm:col-span-2">
                <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Full street address (US)
                </span>
                <textarea
                  className="mt-1.5 min-h-[80px] w-full resize-y rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 shadow-sm outline-none placeholder:text-slate-400 focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  value={profile.full_address ?? ""}
                  onChange={(e) =>
                    setProfile({ ...profile, full_address: e.target.value || null })
                  }
                  placeholder="123 Main St, City, ST 12345"
                  autoComplete="street-address"
                />
                <p className="mt-1 text-xs text-slate-500">
                  Used to geocode the risk location (Nominatim) and query FEMA NFHL at that point.
                </p>
              </label>

              <label>
                <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  ZIP / postal (optional)
                </span>
                <input
                  className="mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 font-mono text-slate-900 shadow-sm outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  value={profile.zip_code ?? ""}
                  onChange={(e) => setProfile({ ...profile, zip_code: e.target.value || null })}
                  placeholder="94102 — fallback if address fails"
                />
              </label>

              <div className="sm:col-span-2 rounded-xl border border-teal-100 bg-teal-50/40 p-4">
                <label className="block">
                  <span className="text-xs font-medium uppercase tracking-wide text-teal-800">
                    NAICS code (recommended)
                  </span>
                  <input
                    className="mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 font-mono text-slate-900 shadow-sm outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                    value={profile.naics_code ?? ""}
                    onChange={(e) => setProfile({ ...profile, naics_code: e.target.value || null })}
                    placeholder="e.g. 722511 (restaurant) or 54 (professional services)"
                    inputMode="numeric"
                    autoComplete="off"
                  />
                </label>
                <p className="mt-2 text-xs text-slate-600">
                  2012 NAICS (2–6 digits). We match your code to the Census industry table and use the sector in
                  risk scoring.
                </p>
                {naicsPreview && (profile.naics_code ?? "").trim().length >= 2 && (
                  <div
                    className={`mt-3 rounded-lg border px-3 py-2 text-sm ${
                      naicsPreview.matched
                        ? "border-teal-200 bg-white text-slate-800"
                        : "border-amber-200 bg-amber-50/80 text-amber-900"
                    }`}
                  >
                    {naicsPreview.matched && naicsPreview.industry_title ? (
                      <>
                        <span className="font-medium text-teal-900">Sector: </span>
                        <span>{naicsPreview.industry_title}</span>
                        {naicsPreview.sector_code != null && (
                          <span className="ml-2 font-mono text-xs text-slate-500">
                            (2012 NAICS sector {naicsPreview.sector_code})
                          </span>
                        )}
                      </>
                    ) : (
                      <span>{naicsPreview.note ?? "Could not resolve this code."}</span>
                    )}
                  </div>
                )}
              </div>

              <label>
                <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Annual revenue (USD)
                </span>
                <input
                  type="number"
                  className="mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 font-mono text-slate-900 shadow-sm outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  value={profile.annual_revenue_usd}
                  onChange={(e) =>
                    setProfile({ ...profile, annual_revenue_usd: Number(e.target.value) })
                  }
                />
              </label>

              <label>
                <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Employees</span>
                <input
                  type="number"
                  className="mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 font-mono text-slate-900 shadow-sm outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  value={profile.employee_count}
                  onChange={(e) =>
                    setProfile({ ...profile, employee_count: Number(e.target.value) })
                  }
                />
              </label>

              <label>
                <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Property sq ft
                </span>
                <input
                  type="number"
                  className="mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 font-mono text-slate-900 shadow-sm outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  value={profile.property_sqft}
                  onChange={(e) =>
                    setProfile({ ...profile, property_sqft: Number(e.target.value) })
                  }
                />
              </label>

              <label>
                <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Building</span>
                <select
                  className="mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-900 shadow-sm outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                  value={profile.building_type}
                  onChange={(e) =>
                    setProfile({ ...profile, building_type: e.target.value as BuildingType })
                  }
                >
                  {BUILDINGS.map((b) => (
                    <option key={b.value} value={b.value}>
                      {b.label}
                    </option>
                  ))}
                </select>
              </label>

              <div className="flex flex-col gap-3 sm:col-span-2">
                <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <input
                    type="checkbox"
                    checked={profile.building_owned}
                    onChange={(e) => setProfile({ ...profile, building_owned: e.target.checked })}
                    className="size-4 rounded border-slate-300 accent-teal-600"
                  />
                  <span className="text-sm text-slate-700">Building owned (vs leased)</span>
                </label>
                <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <input
                    type="checkbox"
                    checked={profile.stores_customer_pii}
                    onChange={(e) =>
                      setProfile({ ...profile, stores_customer_pii: e.target.checked })
                    }
                    className="size-4 rounded border-slate-300 accent-teal-600"
                  />
                  <span className="text-sm text-slate-700">Stores customer PII / payment data</span>
                </label>
                <label className="flex flex-col gap-1.5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <span className="text-xs uppercase text-slate-500">Kitchen / food prep (optional)</span>
                  <select
                    className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none"
                    value={
                      profile.has_kitchen_or_food_prep === null
                        ? ""
                        : profile.has_kitchen_or_food_prep
                          ? "yes"
                          : "no"
                    }
                    onChange={(e) => {
                      const v = e.target.value;
                      setProfile({
                        ...profile,
                        has_kitchen_or_food_prep:
                          v === "" ? null : v === "yes",
                      });
                    }}
                  >
                    <option value="">Auto (from industry)</option>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                </label>
              </div>
            </div>

            <div className="mt-8 border-t border-slate-200 pt-6">
              <h3 className="text-sm font-semibold text-slate-900">Policy document (optional)</h3>
              <p className="mt-1 text-xs text-slate-500">
                PDF → text extraction → TF‑IDF RAG + coverage parsing
              </p>
              <label className="mt-4 flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-8 transition hover:border-teal-400">
                <input
                  type="file"
                  accept="application/pdf"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0] ?? null;
                    setPolicyFile(f);
                    if (f) setUseSamplePolicy(false);
                  }}
                />
                <span className="text-sm text-slate-600">
                  {policyFile ? policyFile.name : "Drop policy PDF or click to browse"}
                </span>
              </label>
              <textarea
                className="mt-4 min-h-[100px] w-full resize-y rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-800 shadow-sm outline-none placeholder:text-slate-400 focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
                placeholder="Or paste policy text here (optional)"
                value={pastedPolicy}
                onChange={(e) => {
                  setPastedPolicy(e.target.value);
                  if (e.target.value.trim()) setPolicyFile(null);
                }}
              />

              <label className="mt-4 flex cursor-pointer items-center gap-3">
                <input
                  type="checkbox"
                  checked={useSamplePolicy}
                  onChange={(e) => {
                    setUseSamplePolicy(e.target.checked);
                    if (e.target.checked) setPolicyFile(null);
                  }}
                  className="size-4 accent-teal-600"
                />
                <span className="text-sm text-slate-600">Use embedded sample policy for RAG demo</span>
              </label>
            </div>

            {error && (
              <p className="mt-4 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="mt-6 w-full rounded-xl bg-gradient-to-r from-teal-600 to-teal-500 py-4 text-sm font-semibold text-white shadow-md shadow-teal-900/20 transition hover:brightness-105 disabled:opacity-50"
            >
              {loading ? "Running models…" : "Run underwriting analysis"}
            </button>
          </form>
        </section>

        <section className="space-y-6">
          {!result && (
            <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-10 text-center text-slate-600">
              <p className="text-lg text-slate-700">Results appear here</p>
              <p className="mt-2 text-sm text-slate-600">
                Risk score, SHAP, gaps, premium band, and policy citations.
              </p>
            </div>
          )}

          {result && (
            <>
              <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <p className="font-mono text-xs uppercase tracking-widest text-slate-500">Profile</p>
                <p className="mt-2 text-slate-700">{result.profile_summary}</p>
              </div>

              {result.naics && (result.naics.input_raw || "").length > 0 && (
                <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <p className="font-mono text-xs uppercase tracking-widest text-slate-500">NAICS (2012)</p>
                  {result.naics.matched && result.naics.industry_title ? (
                    <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                      <div className="sm:col-span-2">
                        <dt className="text-slate-500">Industry title</dt>
                        <dd className="text-slate-900">{result.naics.industry_title}</dd>
                      </div>
                      <div>
                        <dt className="text-slate-500">Sector code</dt>
                        <dd className="font-mono text-slate-900">{result.naics.sector_code ?? "—"}</dd>
                      </div>
                      <div>
                        <dt className="text-slate-500">Sector risk prior (blended into model)</dt>
                        <dd className="font-mono text-slate-900">
                          {result.naics.industry_risk != null ? result.naics.industry_risk.toFixed(3) : "—"}
                        </dd>
                      </div>
                    </dl>
                  ) : (
                    <p className="mt-2 text-sm text-amber-800">
                      {result.naics.note ?? "NAICS code could not be mapped to a sector in the dataset."}
                    </p>
                  )}
                </div>
              )}

              {result.location_evidence && (
                <div className="rounded-2xl border border-teal-200 bg-teal-50/60 p-6 shadow-sm">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-teal-800">
                    Location, flood, crime & weather
                  </h3>
                  <p className="mt-1 text-xs text-slate-600">
                    <a
                      className="text-teal-700 underline hover:text-teal-900"
                      href="https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
                      target="_blank"
                      rel="noreferrer"
                    >
                      FEMA NFHL MapServer
                    </a>{" "}
                    layer {String(result.location_evidence.nfhl_layer_id ?? 28)} ·{" "}
                    {result.location_evidence.geocode_mode != null
                      ? `Mode: ${String(result.location_evidence.geocode_mode)} · `
                      : ""}
                    {String(result.location_evidence.geocoder ?? "—")}
                  </p>
                  <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
                    <div>
                      <dt className="text-slate-500">Flood proxy source</dt>
                      <dd className="font-mono text-slate-900">
                        {String(result.location_evidence.flood_proxy_source ?? "—")}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-slate-500">FLD_ZONE</dt>
                      <dd className="font-mono text-slate-900">
                        {result.location_evidence.nfhl_fld_zone != null
                          ? String(result.location_evidence.nfhl_fld_zone)
                          : "—"}
                      </dd>
                    </div>
                    <div className="sm:col-span-2">
                      <dt className="text-slate-500">Zone subtype</dt>
                      <dd className="text-slate-700">
                        {result.location_evidence.nfhl_zone_subty != null
                          ? String(result.location_evidence.nfhl_zone_subty)
                          : "—"}
                      </dd>
                    </div>
                    {result.location_evidence.latitude != null &&
                      result.location_evidence.longitude != null && (
                        <div className="sm:col-span-2 font-mono text-xs text-slate-500">
                          Point: {String(result.location_evidence.latitude)},{" "}
                          {String(result.location_evidence.longitude)}
                        </div>
                      )}
                    <div className="sm:col-span-2 mt-3 border-t border-teal-200/80 pt-3">
                      <p className="text-xs font-medium uppercase text-slate-500">
                        Weather hazard (historical exposure)
                      </p>
                      <p className="mt-1 text-xs text-slate-600">
                        Uses multi-year daily archive at this point — not a &quot;today&quot; forecast.
                      </p>
                      <dl className="mt-2 grid gap-2 sm:grid-cols-2">
                        <div>
                          <dt className="text-slate-500">Source</dt>
                          <dd className="font-mono text-slate-900">
                            {String(result.location_evidence.weather_proxy_source ?? "—")}
                          </dd>
                        </div>
                        {result.location_evidence.weather_archive_start != null &&
                          result.location_evidence.weather_archive_end != null && (
                            <div>
                              <dt className="text-slate-500">Archive window</dt>
                              <dd className="font-mono text-slate-900">
                                {String(result.location_evidence.weather_archive_start)} →{" "}
                                {String(result.location_evidence.weather_archive_end)}
                              </dd>
                            </div>
                          )}
                        {result.location_evidence.weather_heavy_rain_days_ge_25mm_per_year_avg != null && (
                          <div>
                            <dt className="text-slate-500">Heavy rain days / yr (≥25 mm)</dt>
                            <dd className="font-mono text-slate-900">
                              {Number(
                                result.location_evidence.weather_heavy_rain_days_ge_25mm_per_year_avg,
                              ).toFixed(2)}
                            </dd>
                          </div>
                        )}
                        {result.location_evidence.weather_wind_daily_max_p95_kmh != null && (
                          <div>
                            <dt className="text-slate-500">Wind daily max (p95, km/h)</dt>
                            <dd className="font-mono text-slate-900">
                              {Number(
                                result.location_evidence.weather_wind_daily_max_p95_kmh,
                              ).toFixed(1)}
                            </dd>
                          </div>
                        )}
                        {result.location_evidence.weather_error != null && (
                          <div className="sm:col-span-2 text-xs text-warn">
                            {String(result.location_evidence.weather_error)}
                          </div>
                        )}
                      </dl>
                    </div>
                    <div className="sm:col-span-2 mt-3 border-t border-teal-200/80 pt-3">
                      <p className="text-xs font-medium uppercase text-slate-500">Crime index (ZIP lookup)</p>
                      <dl className="mt-2 grid gap-2 sm:grid-cols-2">
                        <div>
                          <dt className="text-slate-500">Source</dt>
                          <dd className="font-mono text-slate-900">
                            {String(result.location_evidence.crime_proxy_source ?? "—")}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-slate-500">ZIP used</dt>
                          <dd className="font-mono text-slate-900">
                            {result.location_evidence.zip_used_for_crime_lookup != null
                              ? String(result.location_evidence.zip_used_for_crime_lookup)
                              : "—"}
                          </dd>
                        </div>
                        {result.location_evidence.crime_murder_rate_per_100k_annual != null && (
                          <div className="sm:col-span-2">
                            <dt className="text-slate-500">Homicide rate (annual / 100k, windowed)</dt>
                            <dd className="font-mono text-slate-800">
                              {Number(
                                result.location_evidence.crime_murder_rate_per_100k_annual,
                              ).toFixed(2)}
                              {result.location_evidence.crime_matched_city != null && (
                                <span className="ml-2 text-slate-500">
                                  ({String(result.location_evidence.crime_matched_city)})
                                </span>
                              )}
                            </dd>
                          </div>
                        )}
                      </dl>
                    </div>
                    {result.location_evidence.error != null && (
                      <div className="sm:col-span-2 text-sm text-warn">
                        {String(result.location_evidence.error)}
                      </div>
                    )}
                  </dl>
                </div>
              )}

              <div className="grid gap-6 md:grid-cols-2">
                <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Risk profile</h3>
                  <div className="mt-4 flex flex-col items-center">
                    <ScoreRing value={result.risk.risk_score} label={riskLabel(result.risk.risk_score)} />
                    <p className="mt-4 text-center text-sm text-slate-600">
                      Claim probability (proxy):{" "}
                      <span className="font-mono text-warn">
                        {(result.risk.claim_probability * 100).toFixed(1)}%
                      </span>
                    </p>
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                    SHAP explainability
                  </h3>
                  <p className="mt-1 text-xs text-slate-500">Feature attribution (magnitude %)</p>
                  <div className="mt-6">
                    <ShapBars shap={result.risk.shap_percentages} />
                  </div>
                  <ul className="mt-6 space-y-2 border-t border-slate-200 pt-4 text-xs text-slate-600">
                    {result.risk.top_drivers.map((t) => (
                      <li key={t}>· {t}</li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Key risks</h3>
                <ul className="mt-4 space-y-2">
                  {result.key_risks.map((r) => (
                    <li
                      key={r}
                      className="flex gap-2 rounded-lg border border-amber-100 bg-amber-50/80 px-4 py-3 text-sm text-slate-700"
                    >
                      <span className="text-warn">⚠</span>
                      {r}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-2xl border border-amber-200 bg-amber-50/50 p-6 shadow-sm">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-amber-800">Coverage gaps</h3>
                <ul className="mt-4 space-y-3">
                  {result.coverage_gaps.map((g) => (
                    <li
                      key={g.title}
                      className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm"
                    >
                      <span
                        className={`text-xs font-semibold uppercase ${
                          g.severity === "high"
                            ? "text-danger"
                            : g.severity === "medium"
                              ? "text-warn"
                              : "text-slate-500"
                        }`}
                      >
                        {g.severity}
                      </span>
                      <p className="mt-1 font-medium text-slate-900">{g.title}</p>
                      <p className="mt-1 text-sm text-slate-600">{g.detail}</p>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-2xl border border-teal-200 bg-teal-50/70 p-6 shadow-sm">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-teal-800">Premium estimate</h3>
                <p className="mt-3 font-mono text-3xl text-slate-900">
                  ${result.premium.low_usd.toLocaleString()} – ${result.premium.high_usd.toLocaleString()}
                  <span className="text-lg text-slate-500">/yr</span>
                </p>
                <p className="mt-2 text-sm text-slate-500">{result.premium.basis}</p>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Recommendations</h3>
                <div className="mt-4 flex flex-wrap gap-2">
                  {result.recommended_coverages.map((c) => (
                    <span
                      key={c}
                      className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-800"
                    >
                      {c}
                    </span>
                  ))}
                </div>
                <p className="mt-4 text-sm leading-relaxed text-slate-700">{result.recommendation.narrative}</p>
                <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-slate-600">
                  {result.recommendation.actions.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </div>

              {(result.policy_insights || result.rag_citations.length > 0) && (
                <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                    Policy intelligence (RAG)
                  </h3>
                  {result.policy_insights && (
                    <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                      <div>
                        <dt className="text-slate-500">GL limit</dt>
                        <dd className="font-mono text-slate-900">
                          {result.policy_insights.general_liability_limit_usd != null
                            ? `$${result.policy_insights.general_liability_limit_usd.toLocaleString()}`
                            : "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-slate-500">Property limit</dt>
                        <dd className="font-mono text-slate-900">
                          {result.policy_insights.property_limit_usd != null
                            ? `$${result.policy_insights.property_limit_usd.toLocaleString()}`
                            : "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-slate-500">Business interruption</dt>
                        <dd className="text-slate-800">
                          {result.policy_insights.business_interruption ? "Detected" : "Not detected"}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-slate-500">Cyber</dt>
                        <dd className="text-slate-800">
                          {result.policy_insights.cyber_coverage ? "Detected" : "Not detected"}
                        </dd>
                      </div>
                    </dl>
                  )}
                  {result.rag_citations.length > 0 && (
                    <div className="mt-6">
                      <p className="text-xs uppercase text-slate-500">Retrieved chunks</p>
                      <ul className="mt-2 max-h-48 space-y-2 overflow-y-auto text-xs text-slate-600">
                        {result.rag_citations.map((c, i) => (
                          <li key={i} className="rounded-lg border border-slate-100 bg-slate-50 p-3 font-mono leading-relaxed">
                            {c.slice(0, 320)}
                            {c.length > 320 ? "…" : ""}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </section>
      </main>

    </>
  );
}
