from __future__ import annotations

import json
from pathlib import Path


def _display_name(folder: str) -> str:
    return folder.replace("_", " ").title()


def write_stub(out_dir: Path, folder: str, *, force: bool) -> bool:
    """Write _OFFICIAL_SOURCE.md with legislature / code entry URL. Returns True if wrote."""
    portals_path = Path(__file__).resolve().parent / "portals.json"
    data = json.loads(portals_path.read_text(encoding="utf-8"))
    if folder not in data:
        meta = {
            "url": "https://www.ncsl.org/research/civil-and-criminal-justice/state-statutes-websites.aspx",
            "hint": "Use NCSL state legislature / statutes list, then locate this state's Insurance Code or equivalent title.",
        }
    else:
        meta = data[folder]
    dest = out_dir / "_OFFICIAL_SOURCE.md"
    if dest.exists() and not force:
        return False
    out_dir.mkdir(parents=True, exist_ok=True)
    name = _display_name(folder)
    body = (
        f"# {name} — official statutes (entry link)\n\n"
        "This jurisdiction **does not** have a bulk automated fetcher in this repository yet. "
        "Use the link below in a browser, locate the **Insurance** title or chapter, and export or paste text into `.md` files here.\n\n"
        f"**Entry URL:** {meta['url']}\n\n"
        f"**Hint:** {meta['hint']}\n\n"
        "After adding `.md` / `.txt`, run **`python -m app.ingest`** from the project root.\n"
    )
    dest.write_text(body, encoding="utf-8")
    return True
