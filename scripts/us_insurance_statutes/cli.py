from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ca_leginfo import fetch_california
from .or_ors import fetch_oregon
from .stub import write_stub
from .va_code import fetch_virginia


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _all_state_keys() -> list[str]:
    portals = Path(__file__).resolve().parent / "portals.json"
    return sorted(json.loads(portals.read_text(encoding="utf-8")).keys())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch insurance-related statute text into data/<state>/ins_codes/ "
        "(California, Virginia, Oregon) or write _OFFICIAL_SOURCE.md stubs for other states."
    )
    parser.add_argument(
        "--states",
        default="all",
        help="Comma-separated folders (e.g. california,virginia) or 'all' (51 jurisdictions).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Project data root (default: <repo>/data).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.35,
        help="Seconds to sleep after each HTTP response (default 0.35).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="HTTP timeout seconds (default 120).",
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Disable TLS certificate verification (macOS SSL issues only).",
    )
    parser.add_argument(
        "--max-branch-pages",
        type=int,
        default=2500,
        help="California only: max leginfo branch TOC pages to crawl.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing section files where supported.",
    )
    parser.add_argument(
        "--skip-stub",
        action="store_true",
        help="Do not write _OFFICIAL_SOURCE.md for states without automated fetchers.",
    )
    parser.add_argument(
        "--implementations-only",
        action="store_true",
        help="Same as --states california,virginia,oregon --skip-stub (no portal stubs).",
    )
    args = parser.parse_args(argv)

    if args.implementations_only:
        args.states = "california,virginia,oregon"
        args.skip_stub = True

    root = _repo_root()
    data = args.data_dir or (root / "data")
    if not data.is_dir():
        print(f"Data directory not found: {data}", file=sys.stderr)
        return 1

    if args.states.strip().lower() == "all":
        wanted = _all_state_keys()
    else:
        wanted = [s.strip().lower() for s in args.states.split(",") if s.strip()]

    user_agent = "RAG-US-Insurance-Statutes/1.0 (public codes; educational indexing)"
    verify_ssl = not args.no_verify_ssl

    implementations = {
        "california": lambda out: fetch_california(
            out,
            user_agent=user_agent,
            delay_sec=args.delay,
            timeout=args.timeout,
            verify_ssl=verify_ssl,
            max_branch_pages=args.max_branch_pages,
            force=args.force,
        ),
        "virginia": lambda out: fetch_virginia(
            out,
            user_agent=user_agent,
            delay_sec=args.delay,
            timeout=args.timeout,
            verify_ssl=verify_ssl,
            force=args.force,
        ),
        "oregon": lambda out: fetch_oregon(
            out,
            user_agent=user_agent,
            delay_sec=args.delay,
            timeout=args.timeout,
            verify_ssl=verify_ssl,
            force=args.force,
        ),
    }

    summary: list[tuple[str, str]] = []
    for key in wanted:
        out = data / key / "ins_codes"
        if key in implementations:
            try:
                r = implementations[key](out)
                summary.append((key, str(r)))
            except Exception as e:
                summary.append((key, f"ERROR {e!r}"))
        elif not args.skip_stub:
            wrote = write_stub(out, key, force=args.force)
            summary.append((key, "stub written" if wrote else "stub skipped (exists)"))
        else:
            summary.append((key, "skipped (no fetcher, --skip-stub)"))

    for k, msg in summary:
        print(f"{k}: {msg}")
    return 0
