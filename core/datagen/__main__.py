"""CLI entry point:  python -m core.datagen --seed 42 --out data/

Generates the full synthetic Bharat dataset and writes Parquet + SQLite + checksums.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import config as C
from .generate import generate, summarise
from .writer import write_parquet, write_sqlite, write_manifest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="core.datagen", description="Synthetic Bharat data generator")
    p.add_argument("--seed", type=int, default=C.SEED_DEFAULT, help="RNG seed (default 42)")
    p.add_argument("--out", default="data", help="output directory (default ./data)")
    p.add_argument("--no-sqlite", action="store_true", help="skip the SQLite mirror")
    p.add_argument("--quiet", action="store_true", help="suppress the summary print")
    args = p.parse_args(argv)

    t0 = time.perf_counter()
    frames = generate(seed=args.seed)
    summary = summarise(frames)
    checksums = write_parquet(frames, args.out)
    write_manifest(args.out, args.seed, summary, checksums)
    if not args.no_sqlite:
        write_sqlite(frames, args.out)
    dt = time.perf_counter() - t0

    if not args.quiet:
        print(f"Generated synthetic Bharat dataset (seed={args.seed}) -> {args.out}/  in {dt:.1f}s")
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
