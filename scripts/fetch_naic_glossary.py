#!/usr/bin/env python3
"""Download NAIC 'Glossary of Insurance Terms' as clean Markdown for RAG indexing."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

DEFAULT_URL = "https://content.naic.org/glossary-insurance-terms"
USER_AGENT = "Mozilla/5.0 (compatible; InsuranceRAG-GlossaryFetch/1.0; +https://github.com)"


def parse_entries(html_text: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html_text, "html.parser")
    out: list[tuple[str, str]] = []
    for body in soup.select("div.accordion-body"):
        for p in body.find_all("p", recursive=False):
            strong = p.find("strong")
            if not strong:
                continue
            term = strong.get_text(strip=True)
            if not term:
                continue
            rest = p.get_text(strip=True)
            if rest.startswith(term):
                definition = rest[len(term) :].lstrip(" -–—\u00a0").strip()
            else:
                definition = rest
            if not definition:
                continue
            out.append((term, definition))
    return out


def build_markdown(url: str, entries: list[tuple[str, str]]) -> str:
    lines = [
        "# Glossary of Insurance Terms",
        "",
        f"Source: [{url}]({url}) (National Association of Insurance Commissioners).",
        "",
        "Definitions are reproduced for research and RAG context; refer to the NAIC page for the current version.",
        "",
        "---",
        "",
    ]
    for term, definition in entries:
        lines.append(f"## {term}")
        lines.append("")
        lines.append(definition)
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "pdfs" / "naic-glossary.md",
        help="Write Markdown here (default: data/pdfs/naic-glossary.md)",
    )
    ap.add_argument(
        "--pdf",
        action="store_true",
        help="Also run naic_glossary_md_to_pdf.py (writes .pdf next to .md by default)",
    )
    args = ap.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=120.0,
        follow_redirects=True,
    ) as client:
        r = client.get(args.url)
        r.raise_for_status()

    entries = parse_entries(r.text)
    if not entries:
        print("No glossary entries found (page structure may have changed).", file=sys.stderr)
        return 1

    md = build_markdown(args.url, entries)
    args.output.write_text(md, encoding="utf-8")
    print(f"Wrote {len(entries)} terms to {args.output}")
    if args.pdf:
        pdf_out = args.output.with_suffix(".pdf")
        conv = Path(__file__).resolve().parent / "naic_glossary_md_to_pdf.py"
        subprocess.run([sys.executable, str(conv), "-i", str(args.output), "-o", str(pdf_out)], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
