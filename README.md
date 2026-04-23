# Insurance RAG (Surplus lines & statutes)

[![Repository](https://img.shields.io/badge/GitHub-hemanthsai126%2FRAG--for--Surplus--lines--tax-blue?logo=github)](https://github.com/hemanthsai126/RAG-for-Surplus-lines-tax)

Retrieval-augmented Q&A over **insurance PDFs**, **regulator materials**, and **state statute excerpts** (Markdown). The stack is **FastAPI** + a static chat UI, **hybrid retrieval** (BM25 + FAISS with RRF fusion), **cross-encoder reranking**, and answers streamed from **Ollama** or any **OpenAI-compatible** API.

---

## Features

- **Hybrid search** — lexical BM25 and dense embeddings (`sentence-transformers`), fused with reciprocal rank fusion (RRF).
- **Reranking** — `cross-encoder/ms-marco-MiniLM-L-6-v2` on fused candidates before generation.
- **Grounded answers** — retrieved passages carry statute **Source / Verify** metadata where present; the system prompt steers citation behavior.
- **Ingest** — recursive indexing of `.pdf`, `.md`, `.txt` under configurable roots; writes `chunks.json`, `faiss.index`, `bm25.pkl`, `embedder.txt` (default: `data/vectorstore/`).
- **UI** — dark-themed single page: health check, re-index, streaming chat with Markdown (Marked + DOMPurify).

---

## Quick start (local)

```bash
git clone https://github.com/hemanthsai126/RAG-for-Surplus-lines-tax.git
cd RAG-for-Surplus-lines-tax
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Put content under `data/`, `webpage_pdfs/`, and/or **`ins_ipynb/data/`** (see [Data on disk](#data-on-disk)), or set **`PDFS_DIRS`** to a comma-separated list of roots.

```bash
python -m app.ingest          # build the index
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Open **http://127.0.0.1:8001/** . Use **Re-index** or `POST /api/ingest` after changing documents.

**LLM:** run [Ollama](https://ollama.com/) locally and align **`OLLAMA_MODEL`** with `ollama list`, **or** set **`OPENAI_BASE_URL`** and **`OPENAI_MODEL`** (and **`OPENAI_API_KEY`** if required) for a cloud / vLLM endpoint.

---

## Docker & Hugging Face Spaces

The repo includes a **`Dockerfile`**: installs dependencies, runs **`scripts/bootstrap_vectorstore.py`** (optional Hub download of the index), then **`uvicorn`** on **`0.0.0.0:${PORT}`** (default **7860**).

| Variable | Purpose |
|----------|---------|
| **`HF_VECTORSTORE_REPO`** | Dataset or model id on the Hub that holds `chunks.json`, `faiss.index`, `bm25.pkl`, `embedder.txt`. |
| **`HF_VECTORSTORE_REPO_TYPE`** | `dataset` (default) or `model`. |
| **`HF_VECTORSTORE_PATH_PREFIX`** | Subfolder inside the Hub repo, if files are not at the root. |
| **`HF_TOKEN`** / **`HUGGING_FACE_HUB_TOKEN`** | Read private Hub assets. |
| **`OPENAI_BASE_URL`**, **`OPENAI_MODEL`**, **`OPENAI_API_KEY`** | Typical cloud setup on Spaces (Ollama on your laptop is not reachable from HF). |
| **`VECTOR_DIR`** | Where artifacts are stored (default `data/vectorstore`). |

To **bake** the index into the image instead, copy `data/vectorstore/` into the build context and remove the `data/vectorstore` line from **`.dockerignore`**.

---

## Data on disk

The large multi-state statute tree **`ins_ipynb/data/`** is **not committed** to Git (size and push reliability). After clone, restore that folder yourself (copy from backup, zip, or Hugging Face dataset) or point **`PDFS_DIRS`** at another corpus path. See **`ins_ipynb/DATA.txt`**.

Generated index files live under **`data/vectorstore/`** and are **gitignored**; produce them with ingest or download them via **`HF_VECTORSTORE_REPO`** in Docker/Spaces.

---

## Configuration (high level)

| Variable | Role |
|----------|------|
| **`PDFS_DIRS`** | Comma-separated ingest roots (overrides defaults). |
| **`PDFS_DIR`** | Single root; ignored if `PDFS_DIRS` is set. |
| **`VECTOR_DIR`** | Vector artifact directory (`vector_dir` in code). |
| **`OLLAMA_BASE_URL`**, **`OLLAMA_MODEL`**, **`OLLAMA_TIMEOUT_S`** | Ollama defaults. |
| **`OPENAI_BASE_URL`**, **`OPENAI_MODEL`**, **`OPENAI_API_KEY`** | OpenAI-compatible chat when base URL and model are both set. |
| **`STRICT_DOMAIN_GUARD`** | If `true`, optional insurance-domain gate before retrieval. |
| **`RETRIEVAL_PATH_BONUS_SUBSTRINGS`**, **`RETRIEVAL_PATH_RRF_BONUS`** | Nudge retrieval toward paths containing substrings (e.g. `ins_codes`). |

Full semantics and defaults: **`app/config.py`**.

---

## HTTP API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Web UI |
| GET | `/api/health` | Index status, chunk count, paths |
| POST | `/api/ingest` | Rebuild index from configured directories |
| POST | `/api/chat/stream` | SSE chat: `{ "message", "history" }` |
| GET | `/api/context_preview?q=…` | Retrieval debug (no LLM) |

---

## Development

```bash
pytest
SKIP_LLM=1 python -m app.eval.run_eval --benchmark benchmarks/qa_sample.json
```

---

## License

Use and modify for your own deployment; add a `LICENSE` file if you redistribute.
