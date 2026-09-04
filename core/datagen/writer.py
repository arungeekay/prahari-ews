"""Persist generated tables to Parquet (source of truth) + a SQLite mirror, with checksums.

Parquet is written deterministically so ``checksums.json`` is stable across runs on the same
install (BUILD_SPEC §3.5). SQLite is a convenience mirror and is intentionally *not* part of
the determinism contract (its file layout is not byte-reproducible).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pandas as pd

from .generate import TABLES


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def content_hash(df: pd.DataFrame) -> str:
    """Order-sensitive hash of a frame's logical content (robust determinism check)."""
    h = hashlib.md5()
    h.update("|".join(map(str, df.columns)).encode())
    row_hashes = pd.util.hash_pandas_object(df, index=False).to_numpy()
    h.update(row_hashes.tobytes())
    return h.hexdigest()


def write_parquet(frames: dict, out_dir: str | Path) -> dict:
    """Write every table as parquet. Returns {table: {md5, content_hash, rows}}."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    checksums = {}
    for name in TABLES:
        df = frames[name]
        path = out / f"{name}.parquet"
        # deterministic settings: fixed compression, no pandas index
        df.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
        checksums[name] = dict(md5=_md5(path), content_hash=content_hash(df), rows=int(len(df)))
    with open(out / "checksums.json", "w", encoding="utf-8") as f:
        json.dump(checksums, f, indent=2, sort_keys=True)
    return checksums


def write_sqlite(frames: dict, out_dir: str | Path, filename: str = "bharat.db") -> Path:
    """Mirror all tables into a single SQLite DB (not checksummed)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    db_path = out / filename
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        for name in TABLES:
            frames[name].to_sql(name, conn, if_exists="replace", index=False)
        conn.commit()
    finally:
        conn.close()
    return db_path


def write_manifest(out_dir: str | Path, seed: int, summary: dict, checksums: dict) -> Path:
    """Machine-readable manifest (seed + counts + checksums). No wall-clock time (determinism)."""
    out = Path(out_dir)
    manifest = dict(seed=seed, tables=TABLES, summary=summary,
                    checksums={k: v["md5"] for k, v in checksums.items()})
    path = out / "manifest.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return path
