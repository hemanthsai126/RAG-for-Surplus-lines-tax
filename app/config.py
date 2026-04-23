from pathlib import Path
from typing import Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent.parent


def _default_pdfs_dirs() -> list[Path]:
    """Index ``webpage_pdfs/``, ``data/``, and ``ins_ipynb/data/`` when present (recursive .pdf/.md/.txt).

    Statute notebooks often write under ``ins_ipynb/data/<state>/ins_codes/`` when the kernel cwd is
    ``ins_ipynb/``. That tree can be **very large**; ingest time grows with file count and embedding work.
    To index only specific folders, set ``PDFS_DIRS`` (comma-separated roots) instead of relying on defaults.
    """
    roots: list[Path] = []
    wp = _ROOT / "webpage_pdfs"
    data = _ROOT / "data"
    nb_data = _ROOT / "ins_ipynb" / "data"
    if wp.is_dir():
        roots.append(wp)
    if data.is_dir():
        roots.append(data)
    if nb_data.is_dir():
        roots.append(nb_data)
    if not roots:
        roots.append(data)
    return roots


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    data_dir: Path = Field(default=_ROOT / "data")
    # Comma-separated roots (e.g. data/pdfs,data/california). If unset, see pdfs_dirs computed field.
    pdfs_dirs_csv: str = Field(default="", validation_alias="PDFS_DIRS")
    # Single root (backward compatible). Ignored if PDFS_DIRS is set.
    pdfs_dir_env: Optional[Path] = Field(default=None, validation_alias="PDFS_DIR")
    vector_dir: Path = Field(default=_ROOT / "data" / "vectorstore")

    # Dense embeddings (balanced default; override for stronger retrieval)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    chunk_size: int = 512
    chunk_overlap: int = 80

    # Hybrid retrieval
    bm25_top_k: int = 40
    faiss_top_k: int = 40
    rrf_k: int = 60
    fuse_top_n: int = 50
    rerank_top_k: int = 8

    # Boost hybrid RRF when chunk `source` path contains any of these (comma-separated, case-insensitive).
    # Default matches .../ins_codes/... under any state folder, e.g. data/texas/ins_codes/sec_1.md
    retrieval_path_bonus_substrings: str = Field(
        default="ins_codes",
        validation_alias="RETRIEVAL_PATH_BONUS_SUBSTRINGS",
    )
    retrieval_path_rrf_bonus: float = Field(default=0.12, validation_alias="RETRIEVAL_PATH_RRF_BONUS")

    # LLM — must match `ollama list` (e.g. qwen2.5:3b-instruct, qwen3:latest)
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    ollama_timeout_s: float = 300.0

    # Optional: OpenAI-compatible endpoint (vLLM, etc.)
    openai_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None

    # If true, block questions that lack insurance-related keywords (see app/guards/domain.py).
    strict_domain_guard: bool = False

    @computed_field
    @property
    def pdfs_dirs(self) -> list[Path]:
        if self.pdfs_dirs_csv.strip():
            return [Path(p.strip()) for p in self.pdfs_dirs_csv.split(",") if p.strip()]
        if self.pdfs_dir_env is not None:
            return [self.pdfs_dir_env]
        return _default_pdfs_dirs()


settings = Settings()
