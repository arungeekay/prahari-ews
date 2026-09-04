#!/usr/bin/env python
"""Convenience wrapper: generate the synthetic Bharat dataset into ./data (or --out).

Equivalent to `python -m core.datagen`. Kept as a stable script path for Makefiles / Docker
(BUILD_SPEC §2.1). Adds the repo root to sys.path so it runs without an editable install.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.datagen.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
