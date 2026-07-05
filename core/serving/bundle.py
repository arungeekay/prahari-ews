"""Bundle: one process-wide object holding the synthetic data + trained models + precomputed
serving tables (PRAHARI portfolio, DISHA leads). Built once on backend boot.

Boot flow (BUILD_SPEC §8.3): if parquet artifacts are missing they are generated; if model
artifacts are missing they are trained - all deterministic from the seed, so cold start is
reproducible and self-contained.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .. import datagen
from ..datagen import config as C
from ..features.pipeline import msme_features_at, MSME_FEATURES
from ..models import (PDModel, RunwayModel, IntentModel, ContagionGraph,
                      score_arogya, verification_triangle, capacity_profile, match_products)
from ..explain import ReasonExplainer

SEED = int(os.environ.get("DATA_SEED", C.SEED_DEFAULT))


def _synthetic_gstin(borrower_id: str) -> str:
    """Stable fake GSTIN for a borrower (AROGYA looks accounts up by GSTIN)."""
    n = int(borrower_id.replace("MSME", ""))
    return f"27AAACS{n:04d}Q1Z5"


class Bundle:
    def __init__(self, frames: dict, pd_model, runway_model, intent_model):
        self.frames = frames
        self.pd_model = pd_model
        self.runway_model = runway_model
        self.intent_model = intent_model
        self.reason = ReasonExplainer(pd_model)

        self.borrowers = frames["borrowers"].set_index("borrower_id", drop=False)
        self.customers = frames["customers"].set_index("customer_id", drop=False)
        self.anchors = frames["anchors"]
        self.edges = frames["edges"]
        self._msme_groups = {bid: g.sort_values("month_index")
                             for bid, g in frames["msme_monthly"].groupby("borrower_id")}
        self._retail_groups = {cid: g.sort_values("month_index")
                               for cid, g in frames["retail_monthly"].groupby("customer_id")}
        self._eng_groups = {cid: g for cid, g in frames["retail_engagement"].groupby("customer_id")}
        self.gstin_to_borrower = {_synthetic_gstin(b): b for b in self.borrowers.index}

        self._portfolio = None
        self._contagion = None
        self._leads = None

    # ------------------------------------------------------------------ warmup
    def warm(self, product: str) -> None:
        """Precompute the heavy serving tables so the first user click is instant (demo polish)."""
        if product == "PRAHARI":
            self.portfolio()
            self.contagion()
        elif product == "DISHA":
            self.leads()
        # AROGYA scores on-demand per applicant - nothing to warm.

    # ------------------------------------------------------------------ MSME group access
    def msme_group(self, borrower_id: str) -> pd.DataFrame | None:
        return self._msme_groups.get(borrower_id)

    def as_of_for(self, borrower_id: str) -> int:
        g = self._msme_groups[borrower_id]
        return int(g.month_index.max())

    # ------------------------------------------------------------------ PRAHARI portfolio
    def portfolio(self) -> pd.DataFrame:
        if self._portfolio is not None:
            return self._portfolio
        rows, feats = [], []
        for bid, g in self._msme_groups.items():
            as_of = int(g.month_index.max())
            f = msme_features_at(g, as_of)
            if f is None:
                continue
            rows.append((bid, as_of, f))
            feats.append([f.get(k, 0.0) for k in MSME_FEATURES])
        X = pd.DataFrame(feats, columns=MSME_FEATURES)
        pds = self.pd_model.model.predict_proba(X)[:, 1]
        runways = self.runway_model.runway_batch(X, pds)

        recs = []
        for (bid, as_of, f), pd_v, rw in zip(rows, pds, runways):
            b = self.borrowers.loc[bid]
            util = float(f.get("util_last", 0.5))
            exposure = float(b.sanctioned_limit) * util
            recs.append(dict(
                borrower_id=bid, name=b["name"], sector=b.sector, city=b.city, state=b.state,
                loan_type=b.loan_type, sanctioned_limit=float(b.sanctioned_limit),
                pd=round(float(pd_v), 4), runway_months=round(float(rw), 1),
                runway_label=RunwayModel.runway_label(rw),
                bucket=self.pd_model.rag_bucket(pd_v),
                exposure=round(exposure, 2), utilisation=round(util, 4),
                is_anchor_supplier=bool(b.is_anchor_supplier), anchor_id=b.anchor_id,
                contagion_induced=bool(b.contagion_induced), demo=b.demo, as_of=as_of,
            ))
        self._portfolio = pd.DataFrame(recs)
        return self._portfolio

    def account_features(self, borrower_id: str) -> dict | None:
        g = self._msme_groups.get(borrower_id)
        if g is None:
            return None
        return msme_features_at(g, int(g.month_index.max()))

    # ------------------------------------------------------------------ contagion
    def contagion(self) -> ContagionGraph:
        if self._contagion is None:
            pf = self.portfolio().set_index("borrower_id")
            pd_by = {bid: float(pf.at[bid, "pd"]) for bid in self.edges.payee.unique() if bid in pf.index}
            self._contagion = ContagionGraph(self.frames, pd_by)
        return self._contagion

    # ------------------------------------------------------------------ AROGYA
    def arogya(self, borrower_id: str) -> dict:
        b = self.borrowers.loc[borrower_id]
        g = self._msme_groups[borrower_id]
        score = score_arogya(b, g)
        tri = verification_triangle(b, g)
        return dict(borrower_id=borrower_id, name=b["name"], sector=b.sector, city=b.city,
                    gstin=_synthetic_gstin(borrower_id), score=score, triangle=tri)

    # ------------------------------------------------------------------ DISHA leads
    def leads(self) -> pd.DataFrame:
        if self._leads is not None:
            return self._leads
        recs = []
        for cid, c in self.customers.iterrows():
            monthly = self._retail_groups.get(cid)
            if monthly is None:
                continue
            events = self._eng_groups.get(cid)
            cap = capacity_profile(monthly, c)
            intent = self.intent_model.predict(events)
            match = match_products(cap, c)
            best = match["best_match"]
            ip = intent["intent_probability"]
            cap_band = cap["capacity_band"]
            n_sessions = intent["engagement"].get("n_sessions", 0)
            cap_factor = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.25}[cap_band]
            # conversion probability = intent × capacity fit (scaled so the top tier ≈ 18%)
            conv = ip * cap_factor * 0.185
            # lead tier on DISHA's two axes (intent × capacity):
            #   HOT     = high-conviction intent AND repayment-capable
            #   WARM    = engaged but either lower conviction or capacity-limited (nurture)
            #   BROWSING= no real digital engagement (cold)
            if ip >= 0.55 and cap_band in ("HIGH", "MEDIUM") and best is not None:
                tier = "HOT"
            elif n_sessions >= 1 or ip >= 0.30:
                tier = "WARM"
            else:
                tier = "BROWSING"
            recs.append(dict(
                customer_id=cid, name=c["name"], city=c.city, age=int(c.age),
                occupation_type=c.occupation_type, income_band=c.income_band,
                intent_tier=tier, intent_probability=ip,
                capacity_band=cap_band, income_type=cap["income_type"],
                reconstructed_income=cap["reconstructed_income"], disposable_income=cap["disposable_income"],
                discipline_score=cap["discipline_score"],
                matched_product=best["label"] if best else "-",
                ticket_size=best["ticket_size"] if best else 0,
                conversion_probability=round(float(conv), 4),
                demo=c.demo,
            ))
        self._leads = pd.DataFrame(recs).sort_values("conversion_probability", ascending=False).reset_index(drop=True)
        return self._leads

    def lead_detail(self, customer_id: str) -> dict:
        c = self.customers.loc[customer_id]
        monthly = self._retail_groups[customer_id]
        events = self._eng_groups.get(customer_id)
        cap = capacity_profile(monthly, c)
        intent = self.intent_model.predict(events)
        match = match_products(cap, c)
        return dict(customer_id=customer_id, name=c["name"], city=c.city, age=int(c.age),
                    occupation_type=c.occupation_type, income_band=c.income_band, clicked_page=c.clicked_page,
                    capacity=cap, intent=intent, match=match,
                    monthly=monthly.to_dict(orient="records"),
                    engagement=(events.sort_values("month_index").to_dict(orient="records") if events is not None else []))


def _load_or_generate(data_dir: str) -> dict:
    d = Path(data_dir)
    pq = d / "borrowers.parquet"
    if pq.exists():
        return {name: pd.read_parquet(d / f"{name}.parquet") for name in datagen.TABLES}
    frames = datagen.generate(seed=SEED)
    try:
        checks = datagen.write_parquet(frames, d)
        datagen.write_manifest(d, SEED, datagen.summarise(frames), checks)
    except Exception:
        pass
    return frames


def _load_or_train(frames: dict, model_dir: str):
    d = Path(model_dir)
    try:
        pdm = PDModel.load(d); rw = RunwayModel.load(d); im = IntentModel.load(d)
    except Exception:
        pdm = PDModel.train(frames); rw = RunwayModel.train(frames); im = IntentModel.train(frames)
        try:
            pdm.save(d); rw.save(d); im.save(d)
        except Exception:
            pass
    return pdm, rw, im


@lru_cache(maxsize=1)
def get_bundle(data_dir: str | None = None, model_dir: str | None = None) -> Bundle:
    data_dir = data_dir or os.environ.get("DATA_DIR", "data")
    model_dir = model_dir or os.environ.get("MODEL_DIR", str(Path(data_dir) / "models"))
    frames = _load_or_generate(data_dir)
    pdm, rw, im = _load_or_train(frames, model_dir)
    return Bundle(frames, pdm, rw, im)
