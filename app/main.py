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


static_dir = settings.data_dir.parent / "static"
if static_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(static_dir)), name="assets")


@app.get("/")
def root():
    index = static_dir / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse(
        {
            "message": "Place static/index.html or use /api/health. "
            "Ingest PDFs via POST /api/ingest after adding files to data/pdfs."
        }
    )
