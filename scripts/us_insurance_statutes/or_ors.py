"""Oregon Revised Statutes — insurance-heavy ORS chapters as one .md per chapter (static HTML)."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from .common import get_text, make_client, ssl_verify, write_md

ORS_BASE = "https://www.oregonlegislature.gov/bills_laws/ors/ors{}.html"
# Chapters commonly cited as insurance / financial institutions (ORS Vol. 17 neighborhood).
CHAPTERS = (740, 741, 742, 743, 744, 745, 746, 747, 748, 749, 750)


def fetch_oregon(
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
    ok, skip, fail = 0, 0, 0
    with make_client(user_agent=user_agent, timeout=timeout, verify=verify) as client:
        for ch in CHAPTERS:
            url = ORS_BASE.format(ch)
            dest = out_dir / f"ORS_chapter_{ch}.md"
            if dest.exists() and dest.stat().st_size > 200 and not force:
                skip += 1
                continue
            try:
                html = get_text(client, url, delay_sec)
                soup = BeautifulSoup(html, "html.parser")
                title_el = soup.find("title")
                title_txt = title_el.get_text(strip=True) if title_el else f"ORS Chapter {ch}"
                body = soup.get_text("\n", strip=True)
                write_md(
                    dest,
                    f"Oregon Revised Statutes — {title_txt}",
                    url,
                    body[:500_000],
                )
                ok += 1
            except Exception:
                fail += 1
    return {"wrote": ok, "skipped": skip, "failed": fail, "sections_total": len(CHAPTERS)}
