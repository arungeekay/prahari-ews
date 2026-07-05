"""DISHA intent model (BUILD_SPEC §4.2): digital-engagement features → intent tier
{HOT, WARM, BROWSING} with a calibrated probability. Trained to recover the latent `serious`
intent from behavioural signals (repeat evening sessions, EMI-calculator use, funnel depth)."""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..features.retail import engagement_features, ENGAGEMENT_FEATURES

HOT_CUTOFF, WARM_CUTOFF = 0.60, 0.30


@dataclass
class IntentModel:
    model: object = None
    features: list = field(default_factory=lambda: list(ENGAGEMENT_FEATURES))

    @classmethod
    def train(cls, frames: dict) -> "IntentModel":
        from sklearn.linear_model import LogisticRegression
        customers = frames["customers"]
        eng = frames["retail_engagement"]
        by_cust = {cid: g for cid, g in eng.groupby("customer_id")}
        rows, labels = [], []
        for c in customers.itertuples(index=False):
            feats = engagement_features(by_cust.get(c.customer_id))
            rows.append([feats[f] for f in ENGAGEMENT_FEATURES])
            labels.append(1 if c.loan_intent == "serious" else 0)
        X = np.array(rows, dtype=float)
        y = np.array(labels)
        clf = LogisticRegression(max_iter=1000, class_weight="balanced")
        clf.fit(X, y)
        return cls(model=clf, features=list(ENGAGEMENT_FEATURES))

    def predict(self, events: pd.DataFrame | None) -> dict:
        feats = engagement_features(events)
        x = np.array([[feats[f] for f in self.features]], dtype=float)
        p = float(self.model.predict_proba(x)[:, 1][0])
        tier = "HOT" if p >= HOT_CUTOFF else ("WARM" if p >= WARM_CUTOFF else "BROWSING")
        return dict(intent_tier=tier, intent_probability=round(p, 4), engagement=feats)

    def save(self, model_dir: str | Path) -> None:
        d = Path(model_dir); d.mkdir(parents=True, exist_ok=True)
        with open(d / "intent_model.pkl", "wb") as f:
            pickle.dump({"model": self.model, "features": self.features}, f)

    @classmethod
    def load(cls, model_dir: str | Path) -> "IntentModel":
        with open(Path(model_dir) / "intent_model.pkl", "rb") as f:
            d = pickle.load(f)
        return cls(model=d["model"], features=d["features"])
