"""California Insurance Code (INS) from leginfo.legislature.ca.gov (same logic as ca_insurance_code_official.ipynb)."""

from __future__ import annotations

import html as html_module
import re
from pathlib import Path
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from .common import get_text, make_client, ssl_verify, write_md

ORIGIN = "https://leginfo.legislature.ca.gov"
EXPAND_PATH = "/faces/codedisplayexpand.xhtml?tocCode=INS"
EXPAND_URL = ORIGIN + EXPAND_PATH

BRANCH_HREF = re.compile(
    r'href="(/faces/codes_displayexpandedbranch\.xhtml[^"]+)"',
    re.I,
)
SUBMIT_CODES = re.compile(r"submitCodesValues\s*\(\s*'([^']+)'\s*,", re.I)


def is_law_section_key(s: str) -> bool:
    s = s.strip()
    if not s or not s[0].isdigit():
        return False
    core = s.rstrip(".")
    parts = core.split(".")
    if not parts or not all(p.isdigit() for p in parts):
        return False
    if len(parts) == 3 and all(len(p) == 1 for p in parts):
        return False
    return True


def extract_branch_paths(page_html: str) -> set[str]:
    out: set[str] = set()
    for m in BRANCH_HREF.finditer(page_html):
        out.add(html_module.unescape(m.group(1)))
    return out


def extract_section_keys(page_html: str) -> set[str]:
    keys: set[str] = set()
    for m in SUBMIT_CODES.finditer(page_html):
        k = m.group(1).strip()
        if is_law_section_key(k):
            keys.add(k)
    return keys


def section_sort_key(s: str) -> tuple[int, ...]:
    parts: list[int] = []
    for p in s.strip().rstrip(".").split("."):
        if p.isdigit():
            parts.append(int(p))
    return tuple(parts) if parts else (0,)


def section_display_url(section_key: str) -> str:
    sn = section_key.strip()
    return f"{ORIGIN}/faces/codes_displaySection.xhtml?lawCode=INS&sectionNum={quote(sn, safe='.')}"


def section_key_to_filename(key: str) -> str:
    safe = re.sub(r"[^0-9.]+", "_", key.strip().rstrip(".")).strip("_") or "unknown"
    return f"INS_sec_{safe}.md"


def extract_section_body(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.find(id="single_law_section")
    if not node:
        return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)[:50_000]
    return node.get_text("\n", strip=True)


def fetch_california(
    out_dir: Path,
    *,
    user_agent: str,
    delay_sec: float,
    timeout: float,
    verify_ssl: bool,
    max_branch_pages: int,
    force: bool,
) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    verify = ssl_verify() if verify_ssl else False

    def discover() -> tuple[list[str], set[str]]:
        seen_branches: set[str] = set()
        queue: list[str] = []
        all_sections: set[str] = set()
        with make_client(user_agent=user_agent, timeout=timeout, verify=verify) as client:
            seed_html = get_text(client, EXPAND_URL, delay_sec)
            for p in extract_branch_paths(seed_html):
                if p not in seen_branches:
                    seen_branches.add(p)
                    queue.append(p)
            all_sections |= extract_section_keys(seed_html)
            opened = 0
            while queue and opened < max_branch_pages:
                path = queue.pop(0)
                url = urljoin(ORIGIN + "/", path.lstrip("/"))
                opened += 1
                html = get_text(client, url, delay_sec)
                all_sections |= extract_section_keys(html)
                for p in extract_branch_paths(html):
                    if p not in seen_branches:
                        seen_branches.add(p)
                        queue.append(p)
        return sorted(seen_branches), all_sections

    branch_list, section_keys = discover()
    (out_dir / "_branches.txt").write_text("\n".join(branch_list), encoding="utf-8")

    extras_path = out_dir / "_extras_sections.txt"
    if not extras_path.exists():
        extras_path.write_text(
            "# Optional: one INS section number per line.\n# 790.03\n",
            encoding="utf-8",
        )
    for raw in extras_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if not line.endswith("."):
            line = line + "."
        if is_law_section_key(line):
            section_keys.add(line)

    (out_dir / "_section_keys.txt").write_text(
        "\n".join(sorted(section_keys, key=section_sort_key)),
        encoding="utf-8",
    )

    keys = sorted(section_keys, key=section_sort_key)
    ok, skip, fail = 0, 0, 0
    with make_client(user_agent=user_agent, timeout=timeout, verify=verify) as client:
        for i, key in enumerate(keys, 1):
            dest = out_dir / section_key_to_filename(key)
            if dest.exists() and dest.stat().st_size > 50 and not force:
                skip += 1
                continue
            url = section_display_url(key)
            try:
                html = get_text(client, url, delay_sec)
                body = extract_section_body(html)
                title = f"California Insurance Code (INS) — Section {key.rstrip('.')}"
                write_md(dest, title, url, body)
                ok += 1
            except Exception:
                fail += 1
    return {"wrote": ok, "skipped": skip, "failed": fail, "sections_total": len(keys)}
