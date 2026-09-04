"""The single seam between data and the engine: a `PortfolioSource` yields the table dictionary the
bundle already consumes. Implementations: `SyntheticSource` (parquet or generate) and
`IDBISandboxSource` (IDBI's Finacle and Account Aggregator API catalogue)."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from .schema import validate


class PortfolioSource(ABC):
    name = "abstract"
    mode = "unknown"

    @abstractmethod
    def load_tables(self) -> dict[str, pd.DataFrame]:
        """Return raw tables keyed by name (borrowers, anchors, edges, msme_monthly,
        sector_sentiment, customers, retail_monthly, retail_engagement)."""

    def provenance(self) -> dict:
        return dict(source=self.name, mode=self.mode)

    def frames(self) -> dict[str, pd.DataFrame]:
        tables = self.load_tables()
        filled: dict[str, list[str]] = {}
        for name in ("borrowers", "anchors", "edges", "msme_monthly", "sector_sentiment"):
            if name in tables:
                tables[name], f = validate(tables[name], name)
                if f:
                    filled[name] = f
        self._filled = filled
        return tables

    def filled_columns(self) -> dict[str, list[str]]:
        return getattr(self, "_filled", {})
