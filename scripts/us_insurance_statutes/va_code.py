"""Virginia Code Title 38.2 (Insurance) — one HTTP GET on the full-title HTML, split into per-section .md files."""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup

from .common import get_text, make_client, ssl_verify, write_md

FULL_TITLE_URL = "https://law.lis.virginia.gov/vacodefull/title38.2/"
HEADER_SPLIT = re.compile(r"(<b>§\s*38\.2-[^<]+</b>)")


def _slug_from_section_id(sec_id: str) -> str:
    return re.sub(r"[^\w.-]+", "_", sec_id).replace(".", "_")


def fetch_virginia(
    out_dir: Path,
    *,
    user_agent: str,
    delay_sec: float,
    timeout: float,
    verify_ssl: bool,
    force: bool,
) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    verify = ssl_verify() if verify_ssl else False
    with make_client(user_agent=user_agent, timeout=timeout, verify=verify) as client:
        html = get_text(client, FULL_TITLE_URL, delay_sec)

    soup = BeautifulSoup(html, "html.parser")
    node = soup.find(id="va_code")
    if not node:
        raise RuntimeError("Virginia: could not find #va_code in title 38.2 page")
    inner = str(node)
    parts = HEADER_SPLIT.split(inner)
    ok, skip = 0, 0
    for i in range(1, len(parts), 2):
        header_html = parts[i]
        body_html = parts[i + 1] if i + 1 < len(parts) else ""
        header_text = BeautifulSoup(header_html, "html.parser").get_text(" ", strip=True)
        m = re.search(r"§\s*(38\.2-[0-9.]+)", header_text)
        if not m:
            continue
        sec_id = m.group(1)
        dest = out_dir / f"VAC_sec_{_slug_from_section_id(sec_id)}.md"
        if dest.exists() and dest.stat().st_size > 80 and not force:
            skip += 1
            continue
        body = BeautifulSoup(body_html, "html.parser").get_text("\n", strip=True)
        per_url = f"https://law.lis.virginia.gov/vacode/title38.2/section{sec_id}/"
        title = f"Virginia Code — Title 38.2 Insurance — § {sec_id}"
        write_md(dest, title, per_url, body)
        ok += 1
    return {"wrote": ok, "skipped": skip, "failed": 0, "sections_total": ok + skip}
