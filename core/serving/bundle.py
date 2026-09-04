"""Bundle: one process-wide object holding the data + trained models + precomputed serving tables
(PRAHARI portfolio, DISHA leads). Built once on backend boot.

Data enters through exactly one seam, `core.ingest.get_source().frames()`, so a synthetic parquet
world and an IDBI-sandbox adapter are interchangeable without touching models or routes.
"""

from __future__ import annotations

import os
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from ..datagen import config as C
from ..features.pipeline import msme_features_at, MSME_FEATURES, PILLARS, static_from_row, assign_group
from ..models import (PDModel, RunwayModel, IntentModel, ContagionGraph,
                      score_arogya, verification_triangle, capacity_profile, match_products)
from ..explain import ReasonExplainer
from ..interpret import framework as FW
from ..interpret.framework import PillarScorer

SEED = int(os.environ.get("DATA_SEED", C.SEED_DEFAULT))


def _synthetic_gstin(borrower_id: str) -> str:
    """Stable fake GSTIN for a borrower (AROGYA looks accounts up by GSTIN)."""
    n = int(borrower_id.replace("MSME", ""))
    return f"27AAACS{n:04d}Q1Z5"


class Bundle:
    def __init__(self, frames: dict, pd_model, runway_model, intent_model, provenance: dict | None = None):
        self.frames = frames
        self.provenance = provenance or {"source": "unknown"}
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
        self._features: dict[str, dict] = {}
        self._contagion = None
        self._leads = None
        self._pillars: PillarScorer | None = None
        self._lock = threading.RLock()      # one computation of each heavy table, never a race

    # ------------------------------------------------------------------ warmup
    def warm(self, product: str) -> None:
        """Precompute the heavy serving tables so the first user click is instant (demo polish)."""
        if product == "PRAHARI":
            self.portfolio()
            self.contagion()
            self.pillar_scorer()
            self.backtest()                     # the "twelve months ago" replay
        elif product == "DISHA":
            self.leads()

    # ------------------------------------------------------------------ scoring at any as-of
    def score_all_at(self, as_of: int) -> pd.DataFrame:
        """Score every account using ONLY months <= as_of (point-in-time replay). Cached per as_of."""
        cache = self.__dict__.setdefault("_score_cache", {})
        if as_of in cache:
            return cache[as_of]
        rows, feats, lts = [], [], []
        for bid, g in self._msme_groups.items():
            static = self.static_for(bid)
            f = msme_features_at(g, as_of, static=static)
            if f is None:
                continue
            hist = g[g.month_index <= as_of]
            last = hist.iloc[-1]
            rows.append(dict(borrower_id=bid, name=self.borrowers.at[bid, "name"], loan_type=static["loan_type"],
                             sector=static["sector"], exposure=float(self.borrowers.at[bid, "sanctioned_limit"]) * float(last.limit_utilisation),
                             dpd_at_as_of=int(last.dpd), months_on_file=int(len(hist)),
                             group=assign_group(bid)))
            feats.append([f.get(k, 0.0) for k in MSME_FEATURES]); lts.append(static["loan_type"])
        X = pd.DataFrame(feats, columns=MSME_FEATURES)
        df = pd.DataFrame(rows)
        df["pd"] = self.pd_model.predict_pd_batch(X, np.asarray(lts))
        df["bucket"] = [FW.bucket(p, lt) for p, lt in zip(df.pd, df.loan_type)]
        df["as_of"] = as_of
        cache[as_of] = df
        return df

    def backtest(self, as_of: int | None = None) -> dict:
        """Replay: score the book as of `as_of` (default twelve months before the latest month) with
        only the data that existed then, and compare with what actually happened by the latest month.
        Realised outcomes come from the observed 90+ DPD month (in production: API 402 npaDate)."""
        latest = int(self.frames["msme_monthly"].month_index.max())
        as_of = latest - 12 if as_of is None else int(as_of)
        cache = self.__dict__.setdefault("_backtest_cache", {})
        if as_of in cache:
            return cache[as_of]
        sc = self.score_all_at(as_of)
        b = self.borrowers
        dm = sc.borrower_id.map(b.default_month).astype(int)
        sc = sc[(dm < 0) | (dm > as_of)].copy()                 # drop accounts already in default at as_of
        dm = sc.borrower_id.map(b.default_month).astype(int)
        sc["realised_default"] = ((dm > as_of) & (dm <= latest)).astype(int)
        sc["months_ahead"] = np.where(sc.realised_default == 1, dm - as_of, -1)
        sc["flagged"] = sc.bucket.isin(["amber", "red"]).astype(int)
        sc["flagged_red"] = (sc.bucket == "red").astype(int)
        prov = FW.provisioning_rates()
        delta = float(prov["sub_standard"]) - float(prov["standard"])

        def summarise(d: pd.DataFrame, label: str) -> dict:
            realised = d[d.realised_default == 1]
            caught = realised[realised.flagged == 1]
            caught_red = realised[realised.flagged_red == 1]
            flagged = d[d.flagged == 1]
            return dict(
                scope=label, n_scored=int(len(d)), n_flagged=int(len(flagged)), flag_rate=round(len(flagged) / max(1, len(d)), 4),
                n_realised_defaults=int(len(realised)), n_caught=int(len(caught)), n_caught_red=int(len(caught_red)),
                capture=round(len(caught) / max(1, len(realised)), 4), capture_red=round(len(caught_red) / max(1, len(realised)), 4),
                precision=round(len(caught) / max(1, len(flagged)), 4),
                median_lead_months=float(caught.months_ahead.median()) if len(caught) else None,
                mean_lead_months=round(float(caught.months_ahead.mean()), 1) if len(caught) else None,
                lead_distribution={f"{lo}-{hi}": int(((caught.months_ahead >= lo) & (caught.months_ahead <= hi)).sum())
                                   for lo, hi in ((1, 3), (4, 6), (7, 9), (10, 12))},
                caught_exposure=round(float(caught.exposure.sum()), 2),
                provisioning_actionable=round(float(caught.exposure.sum()) * delta, 2),
                missed_exposure=round(float(realised[realised.flagged == 0].exposure.sum()), 2),
                arrears_visible_at_as_of=int((realised.dpd_at_as_of > 0).sum()),
            )

        out = dict(
            as_of=as_of, as_of_label=str(self.frames["msme_monthly"].loc[self.frames["msme_monthly"].month_index == as_of, "month_date"].iloc[0])[:7],
            outcome_month=latest, outcome_label=str(self.frames["msme_monthly"].month_date.max())[:7],
            horizon_months=latest - as_of,
            all=summarise(sc, "all scorable accounts"),
            unseen=summarise(sc[sc.group.isin(["B", "C"])], "borrowers never used to train the model (folds B and C)"),
            caught=sc[(sc.realised_default == 1) & (sc.flagged == 1)].sort_values("months_ahead", ascending=False)
                     [["borrower_id", "name", "loan_type", "sector", "pd", "bucket", "exposure", "months_ahead", "dpd_at_as_of", "group"]].head(40).to_dict(orient="records"),
            missed=sc[(sc.realised_default == 1) & (sc.flagged == 0)].sort_values("exposure", ascending=False)
                     [["borrower_id", "name", "loan_type", "sector", "pd", "bucket", "exposure", "months_ahead", "dpd_at_as_of", "group"]].head(40).to_dict(orient="records"),
            note=("Scores use only data up to the as-of month; outcomes are the observed 90+ DPD months in the following "
                  "twelve months. Accounts already in default at the as-of month are excluded. 'Provisioning actionable' is the "
                  "0.4 to 15 percent IRAC step on the exposure of the defaults that were flagged in time; whether it is saved "
                  "depends on the action taken."),
        )
        cache[as_of] = out
        return out

    def pd_history(self, borrower_id: str) -> dict:
        """Calibrated PD, bucket and statutory status at every month the account could be scored:
        when PRAHARI first flagged it versus when arrears first appeared."""
        from ..features.pipeline import WINDOW
        g = self._msme_groups[borrower_id]
        static = self.static_for(borrower_id)
        lt = static["loan_type"]
        first = int(g.month_index.min()) + 2
        pts = []
        for as_of in range(first, int(g.month_index.max()) + 1):
            f = msme_features_at(g, as_of, static=static)
            if f is None:
                continue
            row = g[g.month_index == as_of].iloc[0]
            p = self.pd_model.predict_pd(f)
            pts.append(dict(month_index=as_of, month_date=str(row.month_date)[:7], pd=round(float(p), 4),
                            bucket=FW.bucket(p, lt), dpd=int(row.dpd), statutory_sma=FW.statutory_sma(int(row.dpd)),
                            full_window=bool(as_of - first + 3 >= WINDOW)))
        # flags are only trusted once a full feature window exists (the first 2-3 months are thin)
        full = [x for x in pts if x["full_window"]]
        first_flag = next((x for x in full if x["bucket"] != "green"), None)
        first_red = next((x for x in full if x["bucket"] == "red"), None)
        first_arrears = next((x for x in pts if x["dpd"] > 0), None)
        dm = int(self.borrowers.at[borrower_id, "default_month"])
        return dict(borrower_id=borrower_id, points=pts,
                    first_flag_month=first_flag["month_index"] if first_flag else None,
                    first_flag_label=first_flag["month_date"] if first_flag else None,
                    first_red_month=first_red["month_index"] if first_red else None,
                    first_arrears_month=first_arrears["month_index"] if first_arrears else None,
                    first_arrears_label=first_arrears["month_date"] if first_arrears else None,
                    projected_default_month=dm if dm >= 0 else None,
                    lead_over_arrears_months=(first_arrears["month_index"] - first_flag["month_index"]) if (first_flag and first_arrears) else None,
                    lead_over_default_months=(dm - first_flag["month_index"]) if (first_flag and dm >= 0) else None)

    def coverage(self, borrower_id: str) -> dict:
        g = self._msme_groups[borrower_id]
        n = int(len(g))
        label = "high" if n >= 18 else ("medium" if n >= 12 else "low")
        return dict(months_on_file=n, coverage=round(n / 24, 2), confidence=label,
                    note=("Thin file: fewer than 12 months of conduct; the score rests on a short window and should be read "
                          "with the officer's own knowledge of the account." if label == "low" else ""))

    # ------------------------------------------------------------------ MSME group access
    def msme_group(self, borrower_id: str) -> pd.DataFrame | None:
        return self._msme_groups.get(borrower_id)

    def as_of_for(self, borrower_id: str) -> int:
        g = self._msme_groups[borrower_id]
        return int(g.month_index.max())

    def static_for(self, borrower_id: str) -> dict:
        return static_from_row(self.borrowers.loc[borrower_id])

    # ------------------------------------------------------------------ PRAHARI portfolio
    def portfolio(self) -> pd.DataFrame:
        if self._portfolio is not None:
            return self._portfolio
        with self._lock:
            if self._portfolio is not None:
                return self._portfolio
            self._portfolio = self._build_portfolio()
            return self._portfolio

    def _build_portfolio(self) -> pd.DataFrame:
        rows, feats_now, feats_prev, loan_types = [], [], [], []
        for bid, g in self._msme_groups.items():
            as_of = int(g.month_index.max())
            static = self.static_for(bid)
            f = msme_features_at(g, as_of, static=static)
            if f is None:
                continue
            fp = msme_features_at(g, as_of - 1, static=static)
            self._features[bid] = f
            rows.append((bid, as_of, f, g))
            feats_now.append([f.get(k, 0.0) for k in MSME_FEATURES])
            feats_prev.append([(fp or f).get(k, 0.0) for k in MSME_FEATURES])
            loan_types.append(static["loan_type"])
        X = pd.DataFrame(feats_now, columns=MSME_FEATURES)
        Xp = pd.DataFrame(feats_prev, columns=MSME_FEATURES)
        lt = np.asarray(loan_types)
        pds = self.pd_model.predict_pd_batch(X, lt)
        pds_prev = self.pd_model.predict_pd_batch(Xp, lt)
        runways = self.runway_model.runway_batch(X, pds)

        recs = []
        for (bid, as_of, f, g), pd_v, pd_p, rw in zip(rows, pds, pds_prev, runways):
            b = self.borrowers.loc[bid]
            last = g.iloc[-1]
            util = float(last.limit_utilisation)
            # exposure: drawn balance for CC/OD; outstanding principal for term loans (both are
            # sanctioned x the account's outstanding ratio, which is what limit_utilisation holds)
            exposure = float(b.sanctioned_limit) * util
            bucket = FW.bucket(float(pd_v), b.loan_type)
            gr = FW.grade(float(pd_v))
            is_npa = int(last.dpd) >= 90        # already 90+ DPD: a classification fact, not a prediction target
            months_on_file = int(len(g))
            recs.append(dict(
                borrower_id=bid, name=b["name"], sector=b.sector, city=b.city, state=b.state,
                loan_type=b.loan_type, sanctioned_limit=float(b.sanctioned_limit),
                is_npa=is_npa, months_on_file=months_on_file,
                confidence="high" if months_on_file >= 18 else ("medium" if months_on_file >= 12 else "low"),
                pd=round(float(pd_v), 4), pd_prev=round(float(pd_p), 4), pd_delta=round(float(pd_v - pd_p), 4),
                runway_months=round(float(rw), 1), runway_label=RunwayModel.runway_label(rw),
                bucket=bucket, grade=gr["grade"], grade_label=gr["label"], grade_score=gr["score"],
                statutory_sma=FW.statutory_sma(int(last.dpd)), dpd=int(last.dpd),
                model_implied_sma=FW.model_implied_sma(bucket),
                exposure=round(exposure, 2), utilisation=round(util, 4),
                drawing_power_pct=round(float(getattr(last, "drawing_power_pct", 0.0)), 4),
                is_anchor_supplier=bool(b.is_anchor_supplier), anchor_id=b.anchor_id,
                demo=b.demo, as_of=as_of,
            ))
        return pd.DataFrame(recs)

    def account_features(self, borrower_id: str) -> dict | None:
        if borrower_id in self._features:
            return self._features[borrower_id]
        g = self._msme_groups.get(borrower_id)
        if g is None:
            return None
        f = msme_features_at(g, int(g.month_index.max()), static=self.static_for(borrower_id))
        if f is not None:
            self._features[borrower_id] = f
        return f

    def early_bucket(self, borrower_id: str) -> str:
        """RAG bucket at the first month with a full feature window (for 'moved from X to Y')."""
        from ..features.pipeline import WINDOW
        g = self._msme_groups[borrower_id]
        first = int(g.month_index.min()) + WINDOW - 1
        f = msme_features_at(g, first, static=self.static_for(borrower_id))
        if f is None:
            return "green"
        return FW.bucket(self.pd_model.predict_pd(f), self.borrowers.loc[borrower_id].loan_type)

    # ------------------------------------------------------------------ pillars
    def pillar_scorer(self) -> PillarScorer:
        if self._pillars is None:
            with self._lock:
                if self._pillars is None:
                    self.portfolio()
                    ref = [self.reason.shap_by_feature(f) for f in self._features.values()]
                    self._pillars = PillarScorer(PILLARS).fit_reference(ref)
        return self._pillars

    def pillar_scores(self, borrower_id: str) -> list[dict]:
        feat = self.account_features(borrower_id)
        if not feat:
            return []
        scores = self.pillar_scorer().scores(self.reason.shap_by_feature(feat))
        for s in scores:
            s["applicable"] = True
            if s["pillar"] == "Contagion" and feat.get("anchor_dependence", 0.0) == 0.0:
                s.update(score=100, applicable=False, description=s["description"] + " (no anchor concentration on this account)")
            if s["pillar"] == "Officer notes" and feat.get("note_n", 0.0) == 0.0:
                s.update(applicable=False, description=s["description"] + " (no notes on file in the window)")
        return scores

    # ------------------------------------------------------------------ notes
    def notes_for(self, borrower_id: str, months: int = 12) -> list[dict]:
        from ..features.notes import score_note
        g = self._msme_groups[borrower_id]
        if "officer_note" not in g.columns:
            return []
        out = []
        for r in g.tail(months).itertuples(index=False):
            if r.officer_note and str(r.officer_note).strip():
                s = score_note(r.officer_note)
                out.append(dict(month_index=int(r.month_index), month_date=r.month_date, text=r.officer_note,
                                sentiment=s["sentiment"], themes=s["themes"], severity=s["severity"]))
        return out

    # ------------------------------------------------------------------ contagion
    def contagion(self) -> ContagionGraph:
        if self._contagion is None:
            with self._lock:
                if self._contagion is None:
                    pf = self.portfolio().set_index("borrower_id")
                    pd_by = {bid: float(pf.at[bid, "pd"]) for bid in self.edges.payee.unique() if bid in pf.index}
                    self._contagion = ContagionGraph(self.frames, pd_by, runway_fn=self.runway_model.runway_from_pd)
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
            conv = ip * cap_factor * 0.185
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


def _load_or_train(frames: dict, model_dir: str):
    d = Path(model_dir)
    try:
        pdm = PDModel.load(d); rw = RunwayModel.load(d); im = IntentModel.load(d)
        if list(pdm.features) != list(MSME_FEATURES):
            raise ValueError("feature list changed; retrain")
    except Exception:
        pdm = PDModel.train(frames); rw = RunwayModel.train(frames, pdm); im = IntentModel.train(frames)
        try:
            pdm.save(d); rw.save(d); im.save(d)
        except Exception:
            pass
    return pdm, rw, im


@lru_cache(maxsize=1)
def get_bundle(data_dir: str | None = None, model_dir: str | None = None) -> Bundle:
    from ..ingest import get_source
    data_dir = data_dir or os.environ.get("DATA_DIR", "data")
    model_dir = model_dir or os.environ.get("MODEL_DIR", str(Path(data_dir) / "models"))
    source = get_source(data_dir)
    frames = source.frames()
    pdm, rw, im = _load_or_train(frames, model_dir)
    return Bundle(frames, pdm, rw, im, provenance=source.provenance())
