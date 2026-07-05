#!/usr/bin/env python
"""Train all trainable models and write artifacts to <data>/models/ (BUILD_SPEC §11 step 4).

Stateless models (AROGYA score, Verification Triangle, capacity, matcher) need no training.
Idempotent and deterministic given --seed. Backends call this on boot if artifacts are missing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.datagen import generate, write_parquet, write_manifest, summarise   # noqa: E402
from core.datagen.writer import write_sqlite                                   # noqa: E402
from core.models import PDModel, RunwayModel, IntentModel                      # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="train_all")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--data", default="data")
    p.add_argument("--models", default=None, help="model dir (default <data>/models)")
    p.add_argument("--skip-data", action="store_true", help="assume data/ already written")
    p.add_argument("--sqlite", action="store_true")
    args = p.parse_args(argv)
    model_dir = args.models or str(Path(args.data) / "models")

    t0 = time.perf_counter()
    frames = generate(seed=args.seed)
    if not args.skip_data:
        checks = write_parquet(frames, args.data)
        write_manifest(args.data, args.seed, summarise(frames), checks)
        if args.sqlite:
            write_sqlite(frames, args.data)

    pd_model = PDModel.train(frames)
    pd_model.save(model_dir)
    RunwayModel.train(frames).save(model_dir)
    IntentModel.train(frames).save(model_dir)

    dt = time.perf_counter() - t0
    print(f"Trained + saved models -> {model_dir}/  in {dt:.1f}s")
    print("PD metrics:", json.dumps(pd_model.metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
