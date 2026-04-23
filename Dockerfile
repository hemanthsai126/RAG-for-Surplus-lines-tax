# Insurance RAG — FastAPI + static UI.
# Hugging Face Spaces: listens on 0.0.0.0:7860 by default.
#
# Build index locally, then either:
#   A) Upload data/vectorstore/* to a private HF Dataset and set HF_VECTORSTORE_REPO at runtime, or
#   B) docker build with data/vectorstore copied (remove data/vectorstore from .dockerignore first).
#
# LLM: set OPENAI_* for a cloud API, or point OLLAMA_BASE_URL at a reachable Ollama host.

FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app
COPY static ./static
COPY scripts ./scripts

# Default ingest roots: only data/ exists in image unless you COPY more.
RUN mkdir -p data/vectorstore

EXPOSE 7860

CMD ["sh", "-c", "python scripts/bootstrap_vectorstore.py && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
