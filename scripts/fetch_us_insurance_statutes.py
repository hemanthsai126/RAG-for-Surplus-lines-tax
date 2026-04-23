#!/usr/bin/env python3
"""CLI: fetch CA / VA / OR insurance statute markdown; write portal stubs for other states."""

from __future__ import annotations

import sys
from pathlib import Path

# Make `scripts/us_insurance_statutes` importable as package `us_insurance_statutes`.
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from us_insurance_statutes.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
