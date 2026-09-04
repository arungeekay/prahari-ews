"""SyntheticSource: the deterministic synthetic Bharat world, read from parquet when present or
generated from the seed. Keyless, offline, byte-reproducible."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from .. import datagen
from ..datagen import config as C
from .base import PortfolioSource


class SyntheticSource(PortfolioSource):
    name = "synthetic"

    def __init__(self, data_dir: str = "data", seed: int | None = None, require_parquet: bool = False):
        self.data_dir = Path(data_dir)
        self.seed = int(seed if seed is not None else os.environ.get("DATA_SEED", C.SEED_DEFAULT))
        self.require_parquet = require_parquet
        self.mode = "parquet" if (self.data_dir / "borrowers.parquet").exists() else "generated"
        self._manifest = None

    def load_tables(self) -> dict[str, pd.DataFrame]:
        pq = self.data_dir / "borrowers.parquet"
        if pq.exists():
            frames = {name: pd.read_parquet(self.data_dir / f"{name}.parquet") for name in datagen.TABLES}
            # a parquet set written by an older generator lacks the newer conduct columns: regenerate
            if "drawing_power_pct" not in frames["msme_monthly"].columns:
                frames = self._generate_and_write()
            self.mode = "parquet"
            mf = self.data_dir / "manifest.json"
            if mf.exists():
                try:
                    self._manifest = json.loads(mf.read_text(encoding="utf-8"))
                except Exception:
                    self._manifest = None
            return frames
        if self.require_parquet:
            raise FileNotFoundError(f"no parquet under {self.data_dir}")
        return self._generate_and_write()

    def _generate_and_write(self) -> dict[str, pd.DataFrame]:
        frames = datagen.generate(seed=self.seed)
        self.mode = "generated"
        try:
            checks = datagen.write_parquet(frames, self.data_dir)
            datagen.write_manifest(self.data_dir, self.seed, datagen.summarise(frames), checks)
        except Exception:
            pass
        return frames

    def provenance(self) -> dict:
        from ..datagen.util import month_index_to_date
        p = dict(source=self.name, mode=self.mode, seed=self.seed, data_dir=str(self.data_dir),
                 as_of_month=month_index_to_date(C.DEMO_MONTH).isoformat()[:7], as_of_month_index=C.DEMO_MONTH,
                 point_in_time_enforced_at="feature pipeline",
                 external_columns_filled=self.filled_columns())
        if self._manifest:
            p["checksums"] = self._manifest.get("checksums", {})
            p["summary"] = self._manifest.get("summary", {})
        return p
