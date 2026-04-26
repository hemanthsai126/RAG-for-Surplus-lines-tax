import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const ABOUT_MD = `# Insurance RAG + P&C Copilot

One **FastAPI** backend combines:

1. **Document RAG** — hybrid BM25 + FAISS over your PDFs / markdown / statutes; streaming chat via \`POST /api/chat/stream\`.
2. **P&C Copilot** (from the Zprojects reference) — XGBoost + SHAP risk scoring, policy TF-IDF insights, coverage gaps, NAICS lookup, quote-compare forwarding, PDF text extraction.
3. **Risko (UI)** — one chat experience: **retrieval-augmented** answers over your index via \`POST /api/chat/stream\` (re-index, streaming Markdown). The separate \`POST /api/risko/chat\` route still exists for plain LLM-only calls if you need it from scripts.

**Frontend:** **React** + **Vite** + **Tailwind** in \`frontend/\` — nav: **Copilot**, **Compare quotes**, **Risko**, **About**. In dev, Vite proxies \`/api\` to the Python server.

---

## Pages

| Route | Purpose |
|-------|---------|
| \`/\` | **Copilot** — business profile form, run analyze, view SHAP / gaps / premium band |
| \`/compare\` | Quote comparison wizard |
| \`/risko\` | **Risko** — indexed-document chat (same as former “Document RAG”; \`/rag\` redirects here) |
| \`/about\` | This document |

---

## Run locally

**Backend** (repo root):

\`\`\`bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
\`\`\`

**Frontend** (second terminal):

\`\`\`bash
cd frontend && npm install && npm run dev
\`\`\`

Open **http://127.0.0.1:5173** . Set \`VITE_API_PORT\` in \`frontend/.env\` if the API is not on **8001**.

**Production-style:** \`cd frontend && npm run build\` then open **http://127.0.0.1:8001/** — FastAPI serves \`frontend/dist/index.html\` and \`/spa-assets/*\` when the build exists. Legacy static files remain under \`/assets/*\` (original single-page UI assets).

---

## Key API routes

| Method | Path |
|--------|------|
| \`GET\` | \`/api/health\` |
| \`POST\` | \`/api/ingest\`, \`/api/chat/stream\` |
| \`POST\` | \`/api/analyze\`, \`/api/analyze-upload\`, \`/api/upload-policy\` |
| \`GET\` | \`/api/naics/lookup\` |
| \`POST\` | \`/api/quotes/compare\`, \`/api/risko/chat\` |

Copilot data and optional \`risk_xgb.joblib\` live under \`app/copilot/data/\`. See the repo **README.md** for env vars (\`INSURANCE_QUOTES_API_URL\`, \`RISKO_LLM_BACKEND\`, \`OLLAMA_MODEL\`, \`OPENAI_*\`, \`USE_RISKO\`, etc.).

---

## Disclaimer

Educational / demo software — not licensed advice or bindable quotes unless you wire real carrier APIs and comply with applicable law.
`;

export default function About() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <p className="mb-6 font-mono text-xs uppercase tracking-[0.2em] text-teal-700">Project readme</p>
      <article className="readme-content prose prose-slate max-w-none prose-headings:scroll-mt-24 prose-h1:mb-8 prose-h1:text-3xl prose-h1:font-semibold prose-h1:tracking-tight prose-h2:mt-10 prose-h2:border-b prose-h2:border-slate-200 prose-h2:pb-2 prose-table:text-sm prose-a:text-teal-700 prose-a:no-underline hover:prose-a:underline prose-code:rounded-md prose-code:bg-slate-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:font-mono prose-code:text-slate-800 prose-code:before:content-none prose-code:after:content-none prose-pre:bg-slate-900 prose-pre:text-slate-100 prose-th:border prose-th:border-slate-300 prose-td:border prose-td:border-slate-200">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{ABOUT_MD}</ReactMarkdown>
      </article>
    </div>
  );
}
