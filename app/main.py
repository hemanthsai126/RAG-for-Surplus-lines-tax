"""FastAPI entry: ingest, streaming chat, static UI."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import settings
from app.copilot.router import router as copilot_router
from app.ingest import ingest_pdfs
from app.rag.pipeline import stream_answer
from app.store import VectorStore

_store: VectorStore | None = None


def get_store() -> VectorStore | None:
    global _store
    if _store is None:
        _store = VectorStore.load()
    return _store


def reload_store() -> VectorStore | None:
    global _store
    _store = VectorStore.load()
    return _store


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_store()
    yield


app = FastAPI(title="Insurance RAG", lifespan=lifespan)
app.include_router(copilot_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatBody(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[dict[str, str]] = Field(default_factory=list)


@app.get("/api/health")
def health() -> dict[str, Any]:
    s = get_store()
    return {
        "ok": True,
        "indexed": s is not None,
        "chunks": len(s.chunks) if s else 0,
        "pdfs_dirs": [str(p.resolve()) for p in settings.pdfs_dirs],
        "vector_dir": str(settings.vector_dir.resolve()),
        "ollama_model": settings.ollama_model,
        "persona": "risko" if settings.use_risko_persona else "insurance_rag",
        "use_risko": settings.use_risko_persona,
        "copilot": {
            "risko_chat": "/api/risko/chat",
            "analyze": "/api/analyze",
            "analyze_upload": "/api/analyze-upload",
            "naics_lookup": "/api/naics/lookup",
            "quotes_compare": "/api/quotes/compare",
            "upload_policy": "/api/upload-policy",
        },
    }


@app.post("/api/ingest")
def run_ingest() -> dict[str, Any]:
    try:
        out = ingest_pdfs()
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    reload_store()
    return out


@app.post("/api/chat/stream")
async def chat_stream(body: ChatBody) -> StreamingResponse:
    store = get_store()
    if store is None:
        roots = ", ".join(str(p.resolve()) for p in settings.pdfs_dirs)
        vd = settings.vector_dir.resolve()
        raise HTTPException(
            status_code=400,
            detail=(
                f"No vector index yet. Add PDFs under {roots} (or set PDFS_DIRS / PDFS_DIR), then click "
                f"“Re-index PDFs” in the UI or POST /api/ingest. The index is written to {vd}."
            ),
        )

    async def events():
        try:
            async for piece in stream_answer(body.message, store, body.history):
                yield f"data: {json.dumps({'token': piece})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/context_preview")
def context_preview(q: str) -> dict[str, Any]:
    from app.rag.pipeline import retrieve_and_pack_context

    store = get_store()
    if store is None:
        raise HTTPException(status_code=400, detail="No index")
    meta, blocks = retrieve_and_pack_context(store, q)
    return {"chunks": meta, "block_count": len(blocks)}


_root = settings.data_dir.parent
static_dir = _root / "static"
_spa_dist = _root / "frontend" / "dist"
_spa_assets = _spa_dist / "spa-assets"

if static_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(static_dir)), name="assets")
if _spa_assets.is_dir():
    app.mount("/spa-assets", StaticFiles(directory=str(_spa_assets)), name="spa_assets")


@app.get("/")
def root():
    spa_index = _spa_dist / "index.html"
    if spa_index.is_file():
        return FileResponse(spa_index)
    index = static_dir / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse(
        {
            "message": "Build the React app (`cd frontend && npm install && npm run build`) or place "
            "static/index.html. See /api/health."
        }
    )


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """Serve React SPA for client-side routes (/rag, /risko, …) when ``frontend/dist`` exists."""
    if (
        full_path.startswith("api/")
        or full_path.startswith("assets/")
        or full_path.startswith("spa-assets/")
    ):
        raise HTTPException(status_code=404)
    if full_path in ("docs", "redoc"):
        raise HTTPException(status_code=404)
    spa_index = _spa_dist / "index.html"
    if spa_index.is_file():
        return FileResponse(spa_index)
    raise HTTPException(status_code=404)
