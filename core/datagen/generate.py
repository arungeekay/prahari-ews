"""Top-level orchestration: seed → full synthetic Bharat dataset (a dict of DataFrames).

Deterministic by construction: a single seeded root generator is split into ordered,
independent sub-streams (numpy SeedSequence spawning), so the same seed always yields the
same tables regardless of platform (BUILD_SPEC §3.5).
"""

from __future__ import annotations

import numpy as np

from . import config as C
from .entities import build_borrowers, build_anchors_and_edges, build_customers
from .msme_series import build_msme_monthly
from .retail_series import build_retail

# Stable output order — also the order tables are written and checksummed.
TABLES = [
    "borrowers", "anchors", "edges", "msme_monthly", "sector_sentiment",
    "customers", "retail_monthly", "retail_engagement",
]


def generate(seed: int = C.SEED_DEFAULT) -> dict:
    """Generate all tables. Returns {table_name: DataFrame} in stable TABLES order."""
    root = np.random.default_rng(seed)
    # ordered sub-streams — DO NOT reorder (determinism depends on it)
    s_borrowers, s_anchors, s_msme, s_customers, s_retail = root.spawn(5)

    borrowers = build_borrowers(s_borrowers)
    anchors, edges = build_anchors_and_edges(s_anchors, borrowers)   # mutates borrowers in place
    msme_monthly, sector_sentiment = build_msme_monthly(s_msme, borrowers)
    customers = build_customers(s_customers)
    retail_monthly, retail_engagement = build_retail(s_retail, customers)

    frames = dict(
        borrowers=borrowers, anchors=anchors, edges=edges,
        msme_monthly=msme_monthly, sector_sentiment=sector_sentiment,
        customers=customers, retail_monthly=retail_monthly,
        retail_engagement=retail_engagement,
    )
    return {name: frames[name] for name in TABLES}


def summarise(frames: dict) -> dict:
    """A few headline stats for logging / sanity (BUILD_SPEC §3.3 / §9)."""
    b = frames["borrowers"]
    n = len(b)
    observed_default_rate = float(b["observed_default"].mean())
    traj_counts = b["health_trajectory"].value_counts().to_dict()
    a1_suppliers = int((b["anchor_id"] == "ANCH1").sum())
    contagion = int(b["contagion_induced"].sum())
    defaulters = b[b["default_month"] >= 0]
    n_def = len(defaulters)
    sudden_share = float((defaulters["health_trajectory"] == "sudden_shock").mean()) if n_def else 0.0
    return dict(
        n_borrowers=n,
        n_customers=len(frames["customers"]),
        observed_default_rate=round(observed_default_rate, 4),
        n_observed_defaults=int(b["observed_default"].sum()),
        n_ever_defaulters=n_def,
        sudden_shock_share_of_defaulters=round(sudden_share, 3),
        trajectory_counts=traj_counts,
        anchor1_suppliers=a1_suppliers,
        contagion_induced=contagion,
        msme_monthly_rows=len(frames["msme_monthly"]),
        retail_monthly_rows=len(frames["retail_monthly"]),
        engagement_events=len(frames["retail_engagement"]),
    )
