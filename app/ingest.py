"""Extract text from insurance PDFs, chunk, and build vector + BM25 indices."""

from __future__ import annotations

import hashlib
import logging
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# Before urllib3 is imported (via sentence-transformers, requests, etc.): macOS Xcode Python uses LibreSSL.
warnings.filterwarnings("ignore", message=r"urllib3 v2 only supports OpenSSL")

import pdfplumber
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.store import build_store_from_chunks


@contextmanager
def _silence_pdfminer_warnings():
    """pdfminer logs hundreds of WARNINGs on graphics/fonts in many real-world PDFs."""
    root = logging.getLogger()
    prev_disable = getattr(root.manager, "disable", logging.NOTSET)
    logging.disable(logging.WARNING)
    try:
        yield
    finally:
        logging.disable(prev_disable)


def _fallback_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text() or ""
        parts.append(t)
    return "\n\n".join(parts)


def extract_pdf_text(path: Path) -> str:
    """Prefer pdfplumber; fall back to pypdf."""
    with _silence_pdfminer_warnings():
        try:
            with pdfplumber.open(str(path)) as pdf:
                parts = []
                for page in pdf.pages:
                    t = page.extract_text() or ""
                    parts.append(t)
            text = "\n\n".join(parts)
            if text.strip():
                return text
        except Exception:
            pass
        return _fallback_pdf_text(path)


def _is_statute_md_path(rel_posix: str) -> bool:
    r = rel_posix.replace("\\", "/").lower()
    return "/ins_codes/" in r or r.endswith("/ins_codes") or "/ins_codes" in r


def _statute_front_matter(raw: str, max_scan: int = 12288) -> str:
    """Return header through first `---` line (Source / Verify URLs) for statute markdown."""
    s = raw[:max_scan]
    for marker in ("\n---\n", "\r\n---\r\n", "\n---\r\n", "\r\n---\n"):
        if marker in s:
            return s[: s.index(marker) + len(marker)].strip()
    if s.startswith("#") and "\n---" in s:
        i = s.index("\n---")
        j = i + 4
        while j < len(s) and s[j] in "\r\n":
            j += 1
        return s[:j].strip()
    return ""


def _chunk_has_statute_links(text: str) -> bool:
    """True if chunk text already includes typical statute URL lines from our markdown."""
    h = text[:5000].lower()
    return "justia.com" in h or ("revisor." in h and "statute" in h) or "legislature." in h


def chunk_text(text: str, source: str, chunk_size: int, overlap: int) -> list[dict[str, Any]]:
    text = text.replace("\x00", " ").strip()
    if not text:
        return []

    chunks: list[dict[str, Any]] = []
    start = 0
    n = len(text)
    idx = 0
    while start < n:
        end = min(start + chunk_size, n)
        piece = text[start:end].strip()
        if piece:
            cid = hashlib.sha256(f"{source}:{idx}:{piece[:64]}".encode()).hexdigest()[:16]
            chunks.append(
                {
                    "id": cid,
                    "text": piece,
                    "source": source,
                    "start_char": start,
                }
            )
            idx += 1
        if end >= n:
            break
        start = max(0, end - overlap)
    return chunks


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _ingest_progress(pct: int, msg: str) -> None:
    pct = max(0, min(100, pct))
    print(f"Ingest: {pct}% — {msg}", flush=True)


def ingest_pdfs(pdf_dirs: list[Path] | None = None, vector_dir: Path | None = None) -> dict[str, Any]:
    roots = list(pdf_dirs) if pdf_dirs is not None else list(settings.pdfs_dirs)
    roots = [Path(p) for p in roots]
    missing = [p for p in roots if not p.is_dir()]
    if missing:
        raise FileNotFoundError(f"PDF directory not found: {missing[0]}")

    proj_root = settings.data_dir.parent.resolve()
    _ingest_progress(0, f"scanning {len(roots)} root(s): {[str(r) for r in roots]}")
    all_chunks: list[dict[str, Any]] = []
    seen: set[Path] = set()
    files: list[tuple[Path, Path]] = []
    for root in roots:
        for pattern in ("*.pdf", "*.md", "*.txt"):
            for fp in sorted(root.rglob(pattern)):
                rp = fp.resolve()
                if rp in seen:
                    continue
                seen.add(rp)
                files.append((fp, root))
    files.sort(key=lambda t: t[0].as_posix())
    _ingest_progress(1, f"found {len(files)} file(s) to read")

    if not files:
        return {
            "ok": False,
            "message": (
                f"No indexable files under {roots} (searched recursively for .pdf, .md, .txt). "
                "Place files here or set PDFS_DIRS / PDFS_DIR."
            ),
            "chunks": 0,
            "sources": 0,
            "pdfs": 0,
        }

    last_file_pct = -1
    n_files = len(files)
    for i, (fp, root) in enumerate(files):
        suf = fp.suffix.lower()
        if suf == ".pdf":
            raw = extract_pdf_text(fp)
        else:
            raw = _read_text_file(fp)
        try:
            rel = fp.resolve().relative_to(proj_root).as_posix()
        except ValueError:
            try:
                rel = f"{root.name}/{fp.relative_to(root).as_posix()}"
            except ValueError:
                rel = fp.name
        parts = chunk_text(raw, source=rel, chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)
        if suf == ".md" and _is_statute_md_path(rel):
            fm = _statute_front_matter(raw)
            if fm:
                for j, c in enumerate(parts):
                    if not _chunk_has_statute_links(c["text"]):
                        new_text = fm + "\n\n" + c["text"]
                        c["text"] = new_text
                        c["id"] = hashlib.sha256(f"{rel}:{j}:{new_text[:64]}".encode()).hexdigest()[:16]
        all_chunks.extend(parts)
        pct = int((i + 1) / n_files * 35)
        if pct > last_file_pct or i == n_files - 1:
            last_file_pct = pct
            _ingest_progress(pct, f"read & chunked files {i + 1}/{n_files} — {fp.name}")

    if not all_chunks:
        return {
            "ok": False,
            "message": "No text extracted from sources (PDFs may be scanned images or empty).",
            "chunks": 0,
            "sources": len(files),
            "pdfs": sum(1 for f, _ in files if f.suffix.lower() == ".pdf"),
        }

    _ingest_progress(
        36,
        f"{len(all_chunks)} chunks — loading embedder {settings.embedding_model!r} "
        "(first run may download the model)",
    )
    embedder = SentenceTransformer(settings.embedding_model)
    _ingest_progress(38, "embedding chunks (CPU-heavy; may take several minutes)")

    last_emb_pct = -1

    def _on_encode(done: int, total: int) -> None:
        nonlocal last_emb_pct
        pct = 40 + int(48 * done / max(total, 1))
        pct = min(pct, 88)
        if pct > last_emb_pct or done == total:
            last_emb_pct = pct
            _ingest_progress(pct, f"embedded {done}/{total} chunks")

    store = build_store_from_chunks(all_chunks, embedder, on_encode_progress=_on_encode)
    _ingest_progress(92, "writing FAISS index, BM25, and chunks.json")
    store.save(vector_dir)
    _ingest_progress(100, "re-index complete")

    n_pdf = sum(1 for f, _ in files if f.suffix.lower() == ".pdf")
    return {
        "ok": True,
        "pdf_roots": [str(r.resolve()) for r in roots],
        "sources": len(files),
        "pdfs": n_pdf,
        "chunks": len(all_chunks),
        "vector_dir": str(vector_dir or settings.vector_dir),
    }


if __name__ == "__main__":
    import json

    out = ingest_pdfs()
    print(json.dumps(out, indent=2))
