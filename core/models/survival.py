"""Runway model (BUILD_SPEC §4.2): months until 90+ DPD, learned as a DISCRETE-TIME HAZARD.

Earlier versions mapped PD to runway with a closed-form exponential hazard: a monotone re-labelling
of PD with no timing information that shifted whenever PD was recalibrated. This model learns
timing from the data:

    For every (borrower, as_of) row and every month-ahead k = 1..12 the account survived to, the
    target is "defaults exactly in month as_of + k". An XGBoost classifier on (features, k) gives
    the monthly hazard h_k; the survival curve is S(t) = prod_{k<=t} (1 - h_k), extended past 12
    months with the last hazard. Runway is the median of S (the first month S falls to one half),
    "24+" when S(24) is still above one half. This is a proper time-to-event estimate: two accounts
    with the same 12-month PD but different trajectories get different runways.

Validation, all on borrower fold C at the later as-of months (never used to fit): concordance
between predicted runway and observed time among defaulters, median absolute error in months for
defaulters within the horizon, agreement of 1 - S(12) with the calibrated PD, and a band table of
predicted vs observed median time by calibrated-PD band.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from ..features.pipeline import MSME_FEATURES, TRAIN_AS_OFS, VALID_AS_OFS, build_msme_training_matrix

MAX_RUNWAY = 24
HORIZON = 12
PD_EDGES = [0.0, 0.01, 0.025, 0.05, 0.10, 0.20, 0.40, 0.60, 0.80, 1.0001]
_XGB = dict(n_estimators=250, max_depth=4, learning_rate=0.06, subsample=0.9, colsample_bytree=0.9,
            eval_metric="logloss", random_state=0, n_jobs=4)


def _expand(X: pd.DataFrame, meta: pd.DataFrame, mask: np.ndarray):
    """Person-period expansion: one row per (account-month, k) the account was still standard at."""
    dm = meta.default_month.to_numpy()[mask]
    a = meta.as_of.to_numpy()[mask]
    Xm = X[mask].reset_index(drop=True)
    parts, ks, ys = [], [], []
    for k in range(1, HORIZON + 1):
        alive = (dm < 0) | (dm - a >= k)           # survived to the start of month k
        if not alive.any():
            continue
        parts.append(Xm[alive])
        ks.append(np.full(int(alive.sum()), k))
        ys.append(((dm - a) == k)[alive].astype(int))
    Xe = pd.concat(parts, ignore_index=True)
    Xe["k"] = np.concatenate(ks)
    return Xe, np.concatenate(ys)


class RunwayModel:
    """Predicts runway (months until 90+ DPD) from the same point-in-time features as the PD model."""

    def __init__(self, model=None, features=None, calibration=None, metrics=None):
        self.model = model
        self.features = list(features or MSME_FEATURES)
        self.calibration = calibration or []
        self.metrics = metrics or {}

    # ------------------------------------------------------------------ training
    @classmethod
    def train(cls, frames: dict, pd_model=None) -> "RunwayModel":
        from xgboost import XGBClassifier
        X, y, meta = build_msme_training_matrix(frames)
        trA = ((meta.group == "A") & meta.as_of.isin(TRAIN_AS_OFS)).to_numpy()
        valC = ((meta.group == "C") & meta.as_of.isin(VALID_AS_OFS)).to_numpy()
        Xe, ye = _expand(X, meta, trA)
        model = XGBClassifier(**_XGB).fit(Xe, ye)
        rm = cls(model=model, features=list(X.columns))

        # ---- validation on fold C
        Xc = X[valC].reset_index(drop=True)
        dm = meta.default_month.to_numpy()[valC]; a = meta.as_of.to_numpy()[valC]
        obs_t = np.where(dm > a, dm - a, MAX_RUNWAY + 1).astype(float)
        event = (dm > a) & (dm - a <= MAX_RUNWAY)
        pred = rm.runway_batch(Xc, None)
        s12 = 1.0 - rm.survival_batch(Xc)[:, HORIZON - 1]
        within = event & (obs_t <= HORIZON)
        conc = _concordance(-pred[event], obs_t[event]) if event.sum() >= 5 else None
        mae = float(np.median(np.abs(pred[within] - obs_t[within]))) if within.sum() else None
        y12 = (within).astype(int)
        try:
            from sklearn.metrics import roc_auc_score, brier_score_loss
            auc12 = round(float(roc_auc_score(y12, s12)), 4) if 0 < y12.sum() < len(y12) else None
            brier12 = round(float(brier_score_loss(y12, s12)), 4)
        except Exception:
            auc12, brier12 = None, None
        pd_c = pd_model.predict_pd_batch(Xc, meta.loan_type.to_numpy()[valC]) if pd_model is not None else s12
        band = np.clip(np.searchsorted(PD_EDGES, pd_c, side="right") - 1, 0, len(PD_EDGES) - 2)
        calibration = []
        for b in range(len(PD_EDGES) - 1):
            m = band == b
            if m.sum() == 0:
                continue
            md_obs, _, ne = _km_median(np.minimum(obs_t[m], MAX_RUNWAY), event[m].astype(int))
            calibration.append(dict(band=f"{PD_EDGES[b]:.3f}-{min(PD_EDGES[b+1], 1.0):.3f}", n=int(m.sum()),
                                    events=int(ne), predicted_median_months=round(float(np.median(pred[m])), 1),
                                    observed_km_median_months=round(md_obs, 1)))
        rm.calibration = calibration
        rm.metrics = dict(concordance_defaulters_fold_C=conc, median_abs_error_months_defaulters=mae,
                          n_valid=int(valC.sum()), n_defaulters_valid=int(event.sum()),
                          hazard_model_12m_auc=auc12, hazard_model_12m_brier=brier12,
                          agreement_with_pd_model_corr=round(float(np.corrcoef(s12, pd_c)[0, 1]), 3) if len(s12) > 2 else None,
                          n_person_periods_train=int(len(Xe)), horizon_months=HORIZON, max_runway=MAX_RUNWAY)
        return rm

    # ------------------------------------------------------------------ prediction
    def _frame(self, feat: dict) -> pd.DataFrame:
        return pd.DataFrame([[feat.get(f, 0.0) for f in self.features]], columns=self.features)

    def survival_batch(self, X: pd.DataFrame) -> np.ndarray:
        """S(t) for t = 1..MAX_RUNWAY, shape (n, MAX_RUNWAY)."""
        n = len(X)
        Xf = X[self.features].reset_index(drop=True)
        rep = pd.concat([Xf] * HORIZON, ignore_index=True)
        rep["k"] = np.repeat(np.arange(1, HORIZON + 1), n)
        h = self.model.predict_proba(rep)[:, 1].reshape(HORIZON, n).T          # (n, 12)
        h = np.clip(h, 1e-5, 0.95)
        tail = np.repeat(h[:, -1:], MAX_RUNWAY - HORIZON, axis=1)              # last hazard carried forward
        hz = np.concatenate([h, tail], axis=1)
        return np.cumprod(1.0 - hz, axis=1)

    def runway_batch(self, X: pd.DataFrame, pd_values=None) -> np.ndarray:
        S = self.survival_batch(X)
        below = S <= 0.5
        first = np.where(below.any(axis=1), below.argmax(axis=1) + 1, MAX_RUNWAY).astype(float)
        # sub-month interpolation so the dial does not jump in whole months
        out = np.empty(len(S))
        for i in range(len(S)):
            t = int(first[i])
            if t >= MAX_RUNWAY or t <= 1:
                out[i] = float(min(t, MAX_RUNWAY))
                continue
            s_prev, s_now = S[i, t - 2], S[i, t - 1]
            frac = (s_prev - 0.5) / max(1e-9, s_prev - s_now)
            out[i] = (t - 1) + float(np.clip(frac, 0.0, 1.0))
        return np.clip(out, 0.0, MAX_RUNWAY)

    def runway(self, feat: dict, pd_value: float | None = None) -> float:
        return float(self.runway_batch(self._frame(feat), None)[0])

    def runway_from_pd(self, pd_value: float) -> float:
        """PD-only fallback used where features are not at hand (contagion deltas): the median of an
        exponential survival curve whose 12-month default probability equals pd_value."""
        p = float(np.clip(pd_value, 1e-5, 0.999))
        h = 1 - (1 - p) ** (1 / 12)
        return float(np.clip(np.log(0.5) / np.log(1 - h), 0.0, MAX_RUNWAY))

    def survival_curve(self, feat: dict) -> list[float]:
        return [round(float(v), 4) for v in self.survival_batch(self._frame(feat))[0]]

    @staticmethod
    def runway_label(runway: float) -> str:
        return "24+" if runway >= MAX_RUNWAY else str(int(round(runway)))

    # ------------------------------------------------------------------ card
    def card(self) -> dict:
        return dict(method=("Discrete-time hazard: XGBoost on (point-in-time features, months ahead k) gives the "
                            "monthly hazard; runway is the month the survival curve falls to one half, 24+ if never. "
                            "Evaluated on borrower fold C at later as-of months."),
                    metrics=self.metrics, calibration=self.calibration)

    # ------------------------------------------------------------------ persistence
    def save(self, model_dir) -> None:
        d = Path(model_dir); d.mkdir(parents=True, exist_ok=True)
        with open(d / "runway_model.pkl", "wb") as f:
            pickle.dump(dict(model=self.model, features=self.features, calibration=self.calibration,
                             metrics=self.metrics, kind="hazard"), f)

    @classmethod
    def load(cls, model_dir) -> "RunwayModel":
        with open(Path(model_dir) / "runway_model.pkl", "rb") as f:
            d = pickle.load(f)
        if d.get("kind") != "hazard":
            raise ValueError("legacy runway model; retrain")
        return cls(model=d["model"], features=d["features"], calibration=d["calibration"], metrics=d["metrics"])


def _km_median(times: np.ndarray, events: np.ndarray, horizon: int = MAX_RUNWAY) -> tuple[float, float, int]:
    """Kaplan-Meier: (median or horizon if S never falls to 0.5, restricted mean, n_events)."""
    if len(times) == 0:
        return float(horizon), float(horizon), 0
    order = np.argsort(times)
    t, e = times[order], events[order]
    s, prev_t, area, median = 1.0, 0.0, 0.0, None
    for ut in np.unique(t):
        area += s * (ut - prev_t)
        at_risk = int((t >= ut).sum()); d = int(e[t == ut].sum())
        if at_risk > 0 and d > 0:
            s *= (1.0 - d / at_risk)
        if median is None and s <= 0.5:
            median = float(ut)
        prev_t = ut
    area += s * max(0.0, horizon - prev_t)
    return (float(horizon) if median is None else median), float(min(horizon, area)), int(e.sum())


def _concordance(score: np.ndarray, time: np.ndarray) -> float | None:
    """Harrell-style concordance among events: a higher score should mean a shorter time."""
    n = len(score)
    if n < 2:
        return None
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            if time[i] == time[j]:
                continue
            earlier, later = (i, j) if time[i] < time[j] else (j, i)
            if score[earlier] > score[later]:
                conc += 1
            elif score[earlier] < score[later]:
                disc += 1
    return round(conc / (conc + disc), 3) if (conc + disc) else None
