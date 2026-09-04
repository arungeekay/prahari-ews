"""Data ingestion: the one seam between data sources and the PRAHARI engine.

    DATA_SOURCE=synthetic (default)  parquet under DATA_DIR, generated from the seed if absent
    DATA_SOURCE=parquet              parquet only; fail if missing
    DATA_SOURCE=idbi_sandbox         IDBI's core-banking API catalogue via IDBI_BASE_URL / IDBI_API_KEY
"""

from __future__ import annotations

import os

from .base import PortfolioSource
from .schema import validate, SchemaError, SCHEMAS
from .synthetic import SyntheticSource
from .idbi_sandbox import IDBISandboxSource


def get_source(data_dir: str = "data") -> PortfolioSource:
    mode = os.environ.get("DATA_SOURCE", "synthetic").lower()
    if mode == "idbi_sandbox":
        return IDBISandboxSource()
    if mode == "parquet":
        return SyntheticSource(data_dir, require_parquet=True)
    return SyntheticSource(data_dir)


__all__ = ["PortfolioSource", "SyntheticSource", "IDBISandboxSource", "get_source", "validate", "SchemaError", "SCHEMAS"]
