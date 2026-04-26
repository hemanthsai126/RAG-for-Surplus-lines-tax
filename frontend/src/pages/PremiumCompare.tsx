import { useState } from "react";
import { submitQuoteCompare } from "../api";
import type { Industry } from "../types";
import type { QuoteApplicantPayload, QuoteCompareResponse } from "../types";

const INDUSTRIES: { value: Industry; label: string }[] = [
  { value: "restaurant", label: "Restaurant / food" },
  { value: "retail", label: "Retail" },
  { value: "warehouse", label: "Warehouse / logistics" },
  { value: "office", label: "Office / professional" },
  { value: "manufacturing", label: "Manufacturing" },
  { value: "other", label: "Other" },
];

const COVERAGE_OPTS = [
  { id: "General Liability", label: "General liability" },
  { id: "Commercial Property", label: "Commercial property" },
  { id: "Business Interruption", label: "Business interruption" },
  { id: "Cyber Liability", label: "Cyber liability" },
  { id: "Workers Compensation", label: "Workers’ compensation" },
  { id: "Commercial Auto", label: "Commercial auto" },
];

const emptyApplicant = (): QuoteApplicantPayload => ({
  zip_code: "",
  full_address: "",
  contact_email: "",
  industry: "retail",
  annual_revenue_usd: 500_000,
  employee_count: 10,
  property_sqft: 3000,
  years_in_business: undefined,
  entity_type: "",
  coverages_requested: [],
  general_liability_limit_usd: 1_000_000,
  property_limit_usd: undefined,
  deductible_preference_usd: 2500,
  claims_in_last_5_years: undefined,
  workers_comp_needed: undefined,
  cyber_needed: undefined,
});

export default function PremiumCompare() {
  const [step, setStep] = useState(0);
  const [a, setA] = useState<QuoteApplicantPayload>(emptyApplicant);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QuoteCompareResponse | null>(null);

  function toggleCov(id: string) {
    setA((prev) => {
      const has = prev.coverages_requested.includes(id);
      return {
        ...prev,
        coverages_requested: has
          ? prev.coverages_requested.filter((x) => x !== id)
          : [...prev.coverages_requested, id],
      };
    });
  }

  async function submit() {
    setLoading(true);
    setError(null);
    setResult(null);
    const z = a.zip_code.replace(/\D/g, "");
    if (z.length < 5) {
      setError("Enter a valid ZIP/postal code (at least 5 digits for US).");
      setLoading(false);
      return;
    }
    try {
      const res = await submitQuoteCompare({
        applicant: {
          ...a,
          zip_code: z.slice(0, 5),
          full_address: a.full_address?.trim() || undefined,
          contact_email: a.contact_email?.trim() || undefined,
          entity_type: a.entity_type?.trim() || undefined,
          years_in_business: a.years_in_business,
          general_liability_limit_usd: a.general_liability_limit_usd,
          property_limit_usd: a.property_limit_usd,
          deductible_preference_usd: a.deductible_preference_usd,
        },
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  const hasTiles = result && result.offers.length > 0;

  return (
    <div className={`mx-auto px-6 py-10 ${hasTiles ? "max-w-5xl" : "max-w-2xl"}`}>
      <header className="mb-8">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-teal-700">Quote comparison</p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-900">Compare quotes</h1>
        <p className="mt-3 text-sm leading-relaxed text-slate-600">
          We submit your answers to your backend (<code className="rounded bg-slate-100 px-1 font-mono text-xs">INSURANCE_QUOTES_API_URL</code>).
          If that URL is unset, you get <strong>demonstration</strong> tiles — fictional carrier names and sample premiums
          derived from your inputs. Real rates require a contracted quote API; we do not scrape insurer websites.
        </p>
      </header>

      <div className="mb-6 flex gap-2">
        {["Location", "Business", "Coverage", "Review"].map((label, i) => (
          <button
            key={label}
            type="button"
            onClick={() => setStep(i)}
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              step === i ? "bg-teal-600 text-white" : "bg-slate-100 text-slate-600"
            }`}
          >
            {i + 1}. {label}
          </button>
        ))}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        {step === 0 && (
          <div className="space-y-4">
            <label className="block">
              <span className="text-xs font-medium uppercase text-slate-500">ZIP / postal *</span>
              <input
                className="mt-1 w-full rounded-xl border border-slate-300 px-4 py-3 font-mono"
                value={a.zip_code}
                onChange={(e) => setA({ ...a, zip_code: e.target.value })}
                placeholder="94102"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium uppercase text-slate-500">Street address</span>
              <textarea
                className="mt-1 min-h-[72px] w-full rounded-xl border border-slate-300 px-4 py-3 text-sm"
                value={a.full_address ?? ""}
                onChange={(e) => setA({ ...a, full_address: e.target.value || undefined })}
                placeholder="123 Main St, City, ST"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium uppercase text-slate-500">Email (optional)</span>
              <input
                type="email"
                className="mt-1 w-full rounded-xl border border-slate-300 px-4 py-3"
                value={a.contact_email ?? ""}
                onChange={(e) => setA({ ...a, contact_email: e.target.value || undefined })}
              />
            </label>
            <button
              type="button"
              className="rounded-xl bg-teal-600 px-4 py-3 text-sm font-semibold text-white"
              onClick={() => setStep(1)}
            >
              Next
            </button>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <label className="block">
              <span className="text-xs font-medium uppercase text-slate-500">Industry</span>
              <select
                className="mt-1 w-full rounded-xl border border-slate-300 px-4 py-3"
                value={a.industry}
                onChange={(e) => setA({ ...a, industry: e.target.value })}
              >
                {INDUSTRIES.map((x) => (
                  <option key={x.value} value={x.value}>
                    {x.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label>
                <span className="text-xs font-medium uppercase text-slate-500">Annual revenue (USD)</span>
                <input
                  type="number"
                  className="mt-1 w-full rounded-xl border border-slate-300 px-4 py-3 font-mono"
                  value={a.annual_revenue_usd}
                  onChange={(e) => setA({ ...a, annual_revenue_usd: Number(e.target.value) })}
                />
              </label>
              <label>
                <span className="text-xs font-medium uppercase text-slate-500">Employees</span>
                <input
                  type="number"
                  className="mt-1 w-full rounded-xl border border-slate-300 px-4 py-3 font-mono"
                  value={a.employee_count}
                  onChange={(e) => setA({ ...a, employee_count: Number(e.target.value) })}
                />
              </label>
              <label>
                <span className="text-xs font-medium uppercase text-slate-500">Property sq ft</span>
                <input
                  type="number"
                  className="mt-1 w-full rounded-xl border border-slate-300 px-4 py-3 font-mono"
                  value={a.property_sqft}
                  onChange={(e) => setA({ ...a, property_sqft: Number(e.target.value) })}
                />
              </label>
              <label>
                <span className="text-xs font-medium uppercase text-slate-500">Years in business</span>
                <input
                  type="number"
                  className="mt-1 w-full rounded-xl border border-slate-300 px-4 py-3 font-mono"
                  value={a.years_in_business ?? ""}
                  onChange={(e) =>
                    setA({
                      ...a,
                      years_in_business: e.target.value ? Number(e.target.value) : undefined,
                    })
                  }
                />
              </label>
            </div>
            <label className="block">
              <span className="text-xs font-medium uppercase text-slate-500">Entity type (optional)</span>
              <input
                className="mt-1 w-full rounded-xl border border-slate-300 px-4 py-3"
                value={a.entity_type ?? ""}
                onChange={(e) => setA({ ...a, entity_type: e.target.value || undefined })}
                placeholder="LLC, Corp, Sole prop…"
              />
            </label>
            <div className="flex gap-2">
              <button type="button" className="rounded-xl border border-slate-300 px-4 py-3 text-sm" onClick={() => setStep(0)}>
                Back
              </button>
              <button
                type="button"
                className="rounded-xl bg-teal-600 px-4 py-3 text-sm font-semibold text-white"
                onClick={() => setStep(2)}
              >
                Next
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <p className="text-sm text-slate-600">Select coverages to request:</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {COVERAGE_OPTS.map((c) => (
                <label key={c.id} className="flex cursor-pointer items-center gap-2 rounded-xl border border-slate-200 px-3 py-2">
                  <input
                    type="checkbox"
                    checked={a.coverages_requested.includes(c.id)}
                    onChange={() => toggleCov(c.id)}
                    className="size-4 accent-teal-600"
                  />
                  <span className="text-sm">{c.label}</span>
                </label>
              ))}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <label>
                <span className="text-xs font-medium uppercase text-slate-500">Target GL limit (USD)</span>
                <input
                  type="number"
                  className="mt-1 w-full rounded-xl border border-slate-300 px-4 py-3 font-mono"
                  value={a.general_liability_limit_usd ?? ""}
                  onChange={(e) =>
                    setA({
                      ...a,
                      general_liability_limit_usd: e.target.value ? Number(e.target.value) : undefined,
                    })
                  }
                />
              </label>
              <label>
                <span className="text-xs font-medium uppercase text-slate-500">Target property limit (USD)</span>
                <input
                  type="number"
                  className="mt-1 w-full rounded-xl border border-slate-300 px-4 py-3 font-mono"
                  value={a.property_limit_usd ?? ""}
                  onChange={(e) =>
                    setA({
                      ...a,
                      property_limit_usd: e.target.value ? Number(e.target.value) : undefined,
                    })
                  }
                />
              </label>
              <label>
                <span className="text-xs font-medium uppercase text-slate-500">Deductible preference (USD)</span>
                <input
                  type="number"
                  className="mt-1 w-full rounded-xl border border-slate-300 px-4 py-3 font-mono"
                  value={a.deductible_preference_usd ?? ""}
                  onChange={(e) =>
                    setA({
                      ...a,
                      deductible_preference_usd: e.target.value ? Number(e.target.value) : undefined,
                    })
                  }
                />
              </label>
            </div>
            <div className="flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={a.claims_in_last_5_years === true}
                  onChange={() =>
                    setA((p) => ({
                      ...p,
                      claims_in_last_5_years:
                        p.claims_in_last_5_years === true ? undefined : true,
                    }))
                  }
                  className="accent-teal-600"
                />
                Claims in last 5 years
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={a.workers_comp_needed === true}
                  onChange={() =>
                    setA((p) => ({
                      ...p,
                      workers_comp_needed: p.workers_comp_needed === true ? undefined : true,
                    }))
                  }
                  className="accent-teal-600"
                />
                Need workers’ comp
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={a.cyber_needed === true}
                  onChange={() =>
                    setA((p) => ({
                      ...p,
                      cyber_needed: p.cyber_needed === true ? undefined : true,
                    }))
                  }
                  className="accent-teal-600"
                />
                Need cyber
              </label>
            </div>
            <div className="flex gap-2">
              <button type="button" className="rounded-xl border border-slate-300 px-4 py-3 text-sm" onClick={() => setStep(1)}>
                Back
              </button>
              <button
                type="button"
                className="rounded-xl bg-teal-600 px-4 py-3 text-sm font-semibold text-white"
                onClick={() => setStep(3)}
              >
                Review
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <pre className="max-h-48 overflow-auto rounded-xl bg-slate-50 p-4 text-xs text-slate-700">
              {JSON.stringify({ applicant: a }, null, 2)}
            </pre>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="rounded-xl border border-slate-300 px-4 py-3 text-sm" onClick={() => setStep(2)}>
                Back
              </button>
              <button
                type="button"
                disabled={loading}
                className="rounded-xl bg-gradient-to-r from-teal-600 to-teal-500 px-6 py-3 text-sm font-semibold text-white disabled:opacity-50"
                onClick={() => void submit()}
              >
                {loading ? "Sending…" : "Send to quote API"}
              </button>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">{error}</div>
      )}

      {result && (
        <div className="mt-8 space-y-4">
          {result.mock_mode && (
            <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-950">
              <p className="font-medium">Demonstration quotes</p>
              {result.message && <p className="mt-2 leading-relaxed">{result.message}</p>}
            </div>
          )}
          {!result.configured && !result.mock_mode && (
            <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
              <p className="font-medium">Quote API not configured</p>
              {result.message && <p className="mt-2">{result.message}</p>}
              <p className="mt-2 text-xs text-amber-900/90">
                Payload we would send is echoed below — point your backend env at a real partner endpoint to get live
                offers.
              </p>
            </div>
          )}
          {result.configured && result.message && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">{result.message}</div>
          )}
          {result.offers.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-teal-900">
                {result.mock_mode ? "Sample carriers" : "Returned offers"}
              </h2>
              <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {result.offers.map((o, i) => (
                  <div
                    key={`${o.company_name}-${i}`}
                    className="flex flex-col rounded-2xl border border-teal-200/80 bg-gradient-to-b from-white to-teal-50/40 p-5 shadow-sm ring-1 ring-teal-100/60"
                  >
                    <p className="text-base font-semibold leading-snug text-slate-900">{o.company_name}</p>
                    {o.plan_name && <p className="mt-1 text-xs text-slate-500">{o.plan_name}</p>}
                    <div className="mt-4 flex flex-1 flex-col justify-end">
                      <p className="font-mono text-2xl font-semibold tabular-nums text-teal-800">
                        ${o.premium_annual_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </p>
                      <p className="text-xs text-slate-500">per year (est.)</p>
                    </div>
                    {o.notes && <p className="mt-3 border-t border-teal-100 pt-3 text-xs leading-relaxed text-slate-600">{o.notes}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}
          {Object.keys(result.submission_payload_echo).length > 0 && (
            <details className="rounded-xl border border-slate-200 bg-white p-4 text-xs">
              <summary className="cursor-pointer font-medium text-slate-700">Submission payload (debug)</summary>
              <pre className="mt-2 overflow-auto text-slate-600">{JSON.stringify(result.submission_payload_echo, null, 2)}</pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
