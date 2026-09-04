"""Small deterministic helpers shared across the generator."""

from __future__ import annotations

import datetime as _dt

import numpy as np

from . import config as C


def month_index_to_date(idx: int) -> _dt.date:
    """month_index 0 → START (July 2024); returns the first day of that calendar month."""
    total = (C.START_MONTH - 1) + idx
    year = C.START_YEAR + total // 12
    month = total % 12 + 1
    return _dt.date(year, month, 1)


def month_labels(n: int) -> list[str]:
    """Human labels like 'Jul-2024' for month_index 0..n-1."""
    return [month_index_to_date(i).strftime("%b-%Y") for i in range(n)]


def weighted_choice(rng: np.random.Generator, options: list, weights: list, size=None):
    """Deterministic weighted choice over an explicit ordered list."""
    p = np.asarray(weights, dtype=float)
    p = p / p.sum()
    idx = rng.choice(len(options), size=size, p=p)
    if size is None:
        return options[int(idx)]
    return [options[int(i)] for i in idx]


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def jitter(rng: np.random.Generator, scale: float, size=None):
    """Zero-mean gaussian noise, clipped to ±3σ to avoid rare wild outliers."""
    z = rng.normal(0.0, 1.0, size=size)
    z = np.clip(z, -3.0, 3.0)
    return z * scale
