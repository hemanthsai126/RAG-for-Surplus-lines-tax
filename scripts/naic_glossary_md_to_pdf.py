#!/usr/bin/env python3
"""Convert data/pdfs/naic-glossary.md (## term / definition blocks) to a PDF."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from fpdf import FPDF


def parse_glossary_md(content: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (preamble before ---), list of (term, definition)."""
    if "---" in content:
        preamble, rest = content.split("---", 1)
    else:
        preamble, rest = "", content

    terms: list[tuple[str, str]] = []
    current_term: str | None = None
    lines: list[str] = []
    for line in rest.splitlines():
        if line.startswith("## "):
            if current_term is not None:
                terms.append((current_term, "\n".join(lines).strip()))
            current_term = line[3:].strip()
            lines = []
        else:
            lines.append(line)
    if current_term is not None:
        terms.append((current_term, "\n".join(lines).strip()))
    return preamble.strip(), terms


def _for_pdf(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("\x00", " ").replace("\xa0", " ").replace("–", "-").replace("\u2014", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return text


def build_pdf(preamble: str, entries: list[tuple[str, str]], out_path: Path) -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.set_margins(18, 18, 18)
    pdf.add_page()

    pdf.set_font("helvetica", style="B", size=16)
    pdf.multi_cell(w=0, h=8, text=_for_pdf("Glossary of Insurance Terms"))
    pdf.ln(3)

    pdf.set_font("helvetica", size=9)
    pre = _for_pdf(preamble)
    if pre:
        for para in pre.split("\n\n"):
            p = para.strip()
            if p:
                pdf.multi_cell(w=0, h=5, text=p)
                pdf.ln(1)
        pdf.ln(2)

    pdf.set_font("helvetica", size=8)
    pdf.multi_cell(w=0, h=4, text=_for_pdf(f"{len(entries)} terms"))
    pdf.ln(3)

    for term, definition in entries:
        t = _for_pdf(term)
        d = _for_pdf(definition)
        if not t:
            continue
        pdf.set_font("helvetica", style="B", size=11)
        pdf.multi_cell(w=0, h=6, text=t)
        pdf.ln(1)
        pdf.set_font("helvetica", size=10)
        if d:
            pdf.multi_cell(w=0, h=5, text=d)
        pdf.ln(3)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "-i",
        "--input",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "pdfs" / "naic-glossary.md",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "pdfs" / "naic-glossary.pdf",
    )
    args = ap.parse_args()

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    preamble, entries = parse_glossary_md(args.input.read_text(encoding="utf-8"))
    if not entries:
        print("No ## terms found in markdown.", file=sys.stderr)
        return 1

    build_pdf(preamble, entries, args.output)
    print(f"Wrote {args.output} ({len(entries)} terms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
