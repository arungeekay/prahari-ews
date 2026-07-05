"""Synthetic Bharat data generator (BUILD_SPEC §3).

Public API:
    generate(seed=42) -> dict[str, DataFrame]   full deterministic dataset
    summarise(frames) -> dict                    headline stats
    write_parquet / write_sqlite / write_manifest  persistence helpers

CLI:  python -m core.datagen --seed 42 --out data/
"""

from __future__ import annotations

from .generate import generate, summarise, TABLES
from .writer import write_parquet, write_sqlite, write_manifest, content_hash

__all__ = [
    "generate", "summarise", "TABLES",
    "write_parquet", "write_sqlite", "write_manifest", "content_hash",
]
