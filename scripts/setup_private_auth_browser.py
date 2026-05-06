#!/usr/bin/env python3
"""Run the browser-assisted Sleeper private auth setup from a checkout."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "src"))
    from sleeper_mcp.private_auth_browser import main

    raise SystemExit(main())
