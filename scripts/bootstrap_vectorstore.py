#!/usr/bin/env python3
"""Optional: download FAISS/BM25/chunks from Hugging Face Hub before the API starts.

Set ``HF_VECTORSTORE_REPO`` to a dataset or model repo id (e.g. ``username/my-rag-index``).
Files expected at repo root (or under ``HF_VECTORSTORE_PATH_PREFIX``):

  - chunks.json
  - faiss.index
  - bm25.pkl
  - embedder.txt

Destination: ``VECTOR_DIR`` (default ``data/vectorstore``), same as ``app.config.settings.vector_dir``.

Auth: ``HF_TOKEN`` or ``HUGGING_FACE_HUB_TOKEN`` for private repos.

Exit 0 if nothing to do or download succeeds; exit 1 if repo is set but download fails.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

REQUIRED = ("chunks.json", "faiss.index", "bm25.pkl", "embedder.txt")


def _vector_dir() -> Path:
    return Path(os.environ.get("VECTOR_DIR", "data/vectorstore")).resolve()


def _all_present(out: Path) -> bool:
    return all((out / name).is_file() for name in REQUIRED)


def main() -> int:
    repo = (os.environ.get("HF_VECTORSTORE_REPO") or "").strip()
    if not repo:
        if not _all_present(_vector_dir()):
            print(
                "bootstrap_vectorstore: HF_VECTORSTORE_REPO unset and vector dir incomplete — "
                "run ingest locally or set HF_VECTORSTORE_REPO to a Hub dataset/model.",
                file=sys.stderr,
            )
        return 0

    out = _vector_dir()
    out.mkdir(parents=True, exist_ok=True)
    if _all_present(out):
        print(f"bootstrap_vectorstore: all files already in {out}", file=sys.stderr)
        return 0

    prefix = (os.environ.get("HF_VECTORSTORE_PATH_PREFIX") or "").strip().strip("/")
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    repo_type = (os.environ.get("HF_VECTORSTORE_REPO_TYPE") or "dataset").strip().lower()
    if repo_type not in ("dataset", "model"):
        print("bootstrap_vectorstore: HF_VECTORSTORE_REPO_TYPE must be dataset or model", file=sys.stderr)
        return 1

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("bootstrap_vectorstore: install huggingface_hub", file=sys.stderr)
        return 1

    revision = (os.environ.get("HF_VECTORSTORE_REVISION") or "main").strip()

    for name in REQUIRED:
        remote = f"{prefix}/{name}" if prefix else name
        print(f"bootstrap_vectorstore: downloading {remote!r} from {repo!r} …", file=sys.stderr)
        hf_hub_download(
            repo_id=repo,
            filename=remote,
            repo_type=repo_type,
            revision=revision,
            local_dir=str(out),
            local_dir_use_symlinks=False,
            token=token,
        )

    if prefix:
        for name in REQUIRED:
            flat = out / name
            nested = out / prefix / name
            if flat.is_file():
                continue
            if nested.is_file():
                shutil.move(str(nested), str(flat))

    if not _all_present(out):
        print(f"bootstrap_vectorstore: missing files under {out} after download", file=sys.stderr)
        return 1

    print(f"bootstrap_vectorstore: ready at {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
