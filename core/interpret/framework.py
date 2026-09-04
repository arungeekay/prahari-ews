"""Common interpretation framework (Track 04 clause: "consistent, comparable and actionable
outputs across all MSME loans").

One JSON configuration (data/interpretation_framework.json, overridable via
PRAHARI_FRAMEWORK) is the single source of truth for: calibrated PD -> unified Risk Grade
(PR1..PR7 and a 0-1000 score) -> RAG bucket -> model-implied SMA-equivalent -> IRAC provisioning
-> recommended action. The backend serves it at /api/framework and the frontend renders from it,
so no threshold is ever hardcoded in two places again.

Pillar sub-scores decompose the same model: the SHAP contribution of each pillar's features is
ranked against the whole book, so "Conduct 18/100" reads as "worse than 82 percent of accounts on
conduct". Same model, same scale, one decomposition.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import numpy as np

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "interpretation_framework.json"


@lru_cache(maxsize=1)
def load() -> dict:
    path = Path(os.environ.get("PRAHARI_FRAMEWORK", str(_DEFAULT_PATH)))
    if not path.exists():
        path = _DEFAULT_PATH
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def reload() -> dict:
    load.cache_clear()
    return load()


# ------------------------------------------------------------------ PD -> grade / bucket
def grade(pd_value: float) -> dict:
    fw = load()
    p = float(np.clip(pd_value, 0.0, 1.0))
    bands = fw["grade_bands"]
    prev_max = 0.0
    for i, b in enumerate(bands):
        if p < b["pd_max"] or i == len(bands) - 1:
            lo_score = bands[i + 1]["score_max"] if i + 1 < len(bands) else 0
            hi_score = b["score_max"]
            span = max(1e-9, min(b["pd_max"], 1.0) - prev_max)
            frac = float(np.clip((p - prev_max) / span, 0.0, 1.0))
            score = int(round(hi_score - frac * (hi_score - lo_score)))
            return dict(grade=b["grade"], label=b["label"], score=score, pd=round(p, 4))
        prev_max = b["pd_max"]
    b = bands[-1]
    return dict(grade=b["grade"], label=b["label"], score=0, pd=round(p, 4))


def bucket(pd_value: float, loan_type: str | None = None) -> str:
    fw = load()["rag"]
    over = fw.get("per_loan_type", {}).get(loan_type or "", {})
    amber = float(over.get("amber_pd", fw["amber_pd"]))
    red = float(over.get("red_pd", fw["red_pd"]))
    if pd_value >= red:
        return "red"
    if pd_value >= amber:
        return "amber"
    return "green"


def model_implied_sma(bucket_name: str) -> str:
    return load()["model_implied_sma"].get(bucket_name, "Standard (no model flag)")


def statutory_sma(dpd: float | int) -> str:
    d = int(max(0, dpd))
    for row in load()["statutory_sma"]:
        if row["dpd_min"] <= d <= row["dpd_max"]:
            return row["label"]
    return "NPA"


def dpd_band(dpd: float | int) -> str:
    d = int(max(0, dpd))
    if d == 0:
        return "0 days"
    for row in load()["statutory_sma"]:
        if row["dpd_min"] <= d <= row["dpd_max"] and row["label"] != "NPA":
            return f"{row['dpd_min']}-{row['dpd_max']} days"
    return "over 90 days"


def provisioning_rates() -> dict:
    return load()["irac_provisioning"]


def crilc_threshold() -> float:
    return float(load()["crilc"]["aggregate_exposure_threshold"])


def recommended_action(bucket_name: str) -> dict:
    for a in load()["actions"]:
        if a["bucket"] == bucket_name:
            return dict(action=a["action"], detail=a["detail"])
    return dict(action="Routine monitoring", detail="")


def runway_bucket(months: float) -> str:
    rc = load()["runway_colours"]
    if months >= rc["green_min_months"]:
        return "green"
    if months >= rc["amber_min_months"]:
        return "amber"
    return "red"


# ------------------------------------------------------------------ pillar sub-scores
class PillarScorer:
    """Turns per-feature SHAP contributions into 0-100 pillar scores by ranking each account's
    pillar risk contribution against a reference distribution (the whole book)."""

    def __init__(self, pillars: dict[str, list[str]], reference: dict[str, np.ndarray] | None = None):
        self.pillars = pillars
        self.reference = reference or {}

    @staticmethod
    def pillar_contributions(shap_by_feature: dict[str, float], pillars: dict[str, list[str]]) -> dict[str, float]:
        return {name: float(sum(shap_by_feature.get(f, 0.0) for f in feats)) for name, feats in pillars.items()}

    def fit_reference(self, rows: list[dict[str, float]]) -> "PillarScorer":
        """rows: per-account {feature: shap} dicts for the whole book."""
        acc = {name: [] for name in self.pillars}
        for r in rows:
            c = self.pillar_contributions(r, self.pillars)
            for name, v in c.items():
                acc[name].append(v)
        self.reference = {name: np.sort(np.asarray(v, dtype=float)) for name, v in acc.items()}
        return self

    def scores(self, shap_by_feature: dict[str, float]) -> list[dict]:
        out = []
        contrib = self.pillar_contributions(shap_by_feature, self.pillars)
        descriptions = load().get("pillars", {})
        for name, v in contrib.items():
            ref = self.reference.get(name)
            if ref is None or len(ref) == 0:
                pct = 0.5
            else:
                pct = float(np.searchsorted(ref, v, side="right") / len(ref))   # share of book with LOWER risk
            score = int(round(100 * (1.0 - pct)))
            out.append(dict(pillar=name, score=score, risk_contribution=round(v, 4),
                            percentile_risk=round(pct, 3),
                            description=descriptions.get(name, {}).get("description", "")))
        return out


def summary() -> dict:
    """The framework as the API serves it (thresholds, bands, vocabulary)."""
    fw = load()
    return dict(version=fw["version"], description=fw["description"], grade_bands=fw["grade_bands"],
                rag=fw["rag"], model_implied_sma=fw["model_implied_sma"], statutory_sma=fw["statutory_sma"],
                irac_provisioning=fw["irac_provisioning"], crilc=fw["crilc"], runway_colours=fw["runway_colours"],
                actions=fw["actions"], pillars=fw["pillars"])
