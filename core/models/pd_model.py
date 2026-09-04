"""PD model (BUILD_SPEC §4.2): XGBoost, default within 12 months of as_of, with an honest
validation design and a full model-risk battery.

Validation design (borrower-disjoint AND temporal):
    Borrowers are hashed into three folds: A (train, 70%), B (calibration, 15%), C (validation,
    15%). The classifier is fit on fold A at the early as-of months (6, 9, 12). Fold B at the later
    as-of months (15, 18) is used ONLY to fit the probability calibrator and to choose the operating
    thresholds. Every reported metric is computed on fold C at the later as-of months, on borrowers
    the model has never seen, at dates after the training window. Nothing is tuned on the fold
    that is reported. The deployed model is exactly the evaluated one (no refit), so the numbers on
    the Model Card describe the model that scores the book.

Calibration: isotonic regression on fold B (global), with per-loan-type Platt scaling where the
fold holds enough defaults, so a 10 percent PD means the same thing on a CC account and a term
loan. Calibrated PD feeds the interpretation framework's fixed bands.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from ..features.pipeline import (MSME_FEATURES, PILLARS, TRAIN_AS_OFS, VALID_AS_OFS,
                                 build_msme_training_matrix, msme_features_at)
from ..interpret import framework as FW
from . import metrics as MX
from .baselines import evaluate_baselines

_XGB_PARAMS = dict(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                   colsample_bytree=0.9, eval_metric="logloss", random_state=0, n_jobs=4)
_MIN_POS_FOR_SEGMENT_CAL = 25


class _Calibrator:
    """Global isotonic + optional per-loan-type Platt scaling, fitted on the calibration fold."""

    def __init__(self):
        self.iso = None
        self.platt: dict[str, tuple[float, float]] = {}
        self.method = "identity"

    @staticmethod
    def _logit(p):
        p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
        return np.log(p / (1 - p))

    def fit(self, p_raw: np.ndarray, y: np.ndarray, loan_type: np.ndarray) -> "_Calibrator":
        from sklearn.isotonic import IsotonicRegression
        from sklearn.linear_model import LogisticRegression
        self.iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(p_raw, y)
        self.method = "isotonic"
        for lt in sorted(pd.unique(loan_type)):
            m = loan_type == lt
            if int(y[m].sum()) >= _MIN_POS_FOR_SEGMENT_CAL and int((1 - y[m]).sum()) >= _MIN_POS_FOR_SEGMENT_CAL:
                lr = LogisticRegression(C=1.0, max_iter=1000).fit(self._logit(p_raw[m]).reshape(-1, 1), y[m])
                self.platt[str(lt)] = (float(lr.coef_[0][0]), float(lr.intercept_[0]))
        if self.platt:
            self.method = "isotonic + per-loan-type Platt"
        return self

    def transform(self, p_raw: np.ndarray, loan_type: np.ndarray | None = None) -> np.ndarray:
        p_raw = np.asarray(p_raw, dtype=float)
        if self.iso is None:
            return p_raw
        out = self.iso.predict(p_raw)
        if loan_type is not None and self.platt:
            lt = np.asarray(loan_type).astype(str)
            for k, (a, b) in self.platt.items():
                m = lt == k
                if m.any():
                    z = a * self._logit(p_raw[m]) + b
                    platt = 1 / (1 + np.exp(-z))
                    out[m] = 0.5 * out[m] + 0.5 * platt      # blend: segment shape, global level
        # a probability of exactly 0 or 1 is never an honest statement about the next 12 months
        return np.clip(out, 0.0005, 0.99)


def _loan_type_from_feat(feat: dict) -> str:
    if feat.get("is_term", 0.0) >= 0.5:
        return "term"
    if feat.get("is_od", 0.0) >= 0.5:
        return "OD"
    return "CC"


@dataclass
class PDModel:
    model: object = None
    calibrator: _Calibrator = field(default_factory=_Calibrator)
    thresholds: dict = field(default_factory=dict)
    threshold: float = 0.05
    features: list = field(default_factory=lambda: list(MSME_FEATURES))
    metrics: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ training
    @classmethod
    def train(cls, frames: dict) -> "PDModel":
        from xgboost import XGBClassifier
        X, y, meta = build_msme_training_matrix(frames)
        yv = y.to_numpy()
        trA = (meta.group == "A") & meta.as_of.isin(TRAIN_AS_OFS)
        calB = (meta.group == "B") & meta.as_of.isin(VALID_AS_OFS)
        valC = (meta.group == "C") & meta.as_of.isin(VALID_AS_OFS)
        trA, calB, valC = trA.to_numpy(), calB.to_numpy(), valC.to_numpy()

        model = XGBClassifier(**_XGB_PARAMS)
        model.fit(X[trA], yv[trA])

        # calibration fold: fit calibrator + choose thresholds (never on the reported fold)
        p_cal_raw = model.predict_proba(X[calB])[:, 1]
        cal = _Calibrator().fit(p_cal_raw, yv[calB], meta.loan_type.to_numpy()[calB])
        p_cal = cal.transform(p_cal_raw, meta.loan_type.to_numpy()[calB])
        thresholds = MX.named_thresholds(yv[calB], p_cal)

        # validation fold: everything reported
        yc = yv[valC]
        p_raw_c = model.predict_proba(X[valC])[:, 1]
        pc = cal.transform(p_raw_c, meta.loan_type.to_numpy()[valC])
        mc = meta[valC].reset_index(drop=True)
        thr90 = thresholds["bank_90_accuracy"]
        thr_cap = thresholds["max_capture"]
        head90 = MX.confusion_at(yc, pc, thr90)
        headcap = MX.confusion_at(yc, pc, thr_cap)

        seg = []
        seg += MX.segment_metrics(yc, pc, mc.loan_type.to_numpy(), thr90, "loan_type")
        seg += MX.segment_metrics(yc, pc, mc.sector.to_numpy(), thr90, "sector")
        vint = pd.cut(mc.vintage_years, [-1, 3, 7, 15, 200], labels=["0-3y", "4-7y", "8-15y", "15y+"]).astype(str).to_numpy()
        seg += MX.segment_metrics(yc, pc, vint, thr90, "vintage")
        seg += MX.segment_metrics(yc, pc, mc.as_of.astype(str).to_numpy(), thr90, "as_of_month")

        as_of_vals = sorted(mc.as_of.unique())
        psi_val = MX.psi(pc[mc.as_of == as_of_vals[0]], pc[mc.as_of == as_of_vals[-1]]) if len(as_of_vals) > 1 else 0.0

        # ---- ablation: bank-internal data only (what if the external feeds never arrive?)
        external = [f for f in X.columns if f.startswith(("gst_", "epfo_", "electricity_", "sentiment_"))]
        internal_cols = [f for f in X.columns if f not in external]
        m_int = XGBClassifier(**_XGB_PARAMS).fit(X.loc[trA, internal_cols], yv[trA])
        p_int = m_int.predict_proba(X.loc[valC, internal_cols])[:, 1]
        budget = int((pc >= thr90).sum())
        ablation = dict(
            external_features_removed=external,
            n_internal_features=len(internal_cols),
            full_model_auc=round(float(roc_auc_score(yc, pc)), 4),
            internal_only_auc=round(float(roc_auc_score(yc, p_int)), 4),
            full_model_recall_at_budget=MX.matched_alert_recall(yc, pc, budget)["recall"],
            internal_only_recall_at_budget=MX.matched_alert_recall(yc, p_int, budget)["recall"],
            alert_budget=budget,
            note=("The internal-only model is trained and evaluated on the same folds using only the columns that IDBI's "
                  "core-banking catalogue provides (conduct, drawing power, liens, statements, bureau, notes, contagion, profile). "
                  "The gap to the full model is what the external GST, EPFO, electricity and sector feeds are worth."),
        )

        # ---- challengers: one dedicated model per loan type versus the global calibrated model
        segment_models = []
        for lt in sorted(pd.unique(meta.loan_type)):
            trm = trA & (meta.loan_type == lt).to_numpy()
            tem = valC & (meta.loan_type == lt).to_numpy()
            if yv[trm].sum() < 20 or yv[tem].sum() < 5:
                segment_models.append(dict(loan_type=str(lt), n_train=int(trm.sum()), n_valid=int(tem.sum()),
                                           verdict="too few defaults to fit a dedicated model"))
                continue
            m_lt = XGBClassifier(**_XGB_PARAMS).fit(X[trm], yv[trm])
            p_lt = m_lt.predict_proba(X[tem])[:, 1]
            g_auc = float(roc_auc_score(yv[tem], cal.transform(model.predict_proba(X[tem])[:, 1], meta.loan_type.to_numpy()[tem])))
            d_auc = float(roc_auc_score(yv[tem], p_lt))
            segment_models.append(dict(loan_type=str(lt), n_train=int(trm.sum()), n_valid=int(tem.sum()), defaults_valid=int(yv[tem].sum()),
                                       global_model_auc=round(g_auc, 4), dedicated_model_auc=round(d_auc, 4),
                                       verdict=("dedicated model is not better" if d_auc <= g_auc + 0.005 else "dedicated model is better")))

        metrics = dict(
            auc=round(float(roc_auc_score(yc, pc)), 4),
            auc_raw=round(float(roc_auc_score(yc, p_raw_c)), 4),
            auc_ci95=MX.bootstrap_auc(yc, pc),
            ks=MX.ks_statistic(yc, pc),
            # headline at the bank-90-percent-accuracy operating point
            operating_threshold=thr90,
            accuracy=head90["accuracy"], balanced_accuracy=head90["balanced_accuracy"],
            precision=head90["precision"], recall=head90["recall"], f1=head90["f1"],
            confusion_matrix=head90["confusion_matrix"], alerts=head90["alerts"], alert_rate=head90["alert_rate"],
            max_capture=headcap,
            thresholds=thresholds,
            operating_points=MX.operating_points(yc, pc, thresholds),
            # full trade-off curve so the bank can pick its own alert budget on screen
            threshold_curve=[MX.confusion_at(yc, pc, float(t)) for t in np.round(np.linspace(0.01, 0.60, 60), 3)],
            deciles=MX.decile_table(yc, pc, mc.exposure_proxy.to_numpy()),
            lead_time=MX.lead_time_curve(yc, pc, mc.months_ahead.to_numpy(), thr_cap),
            lead_time_threshold=thr_cap,
            calibration=MX.calibration_table(yc, pc),
            calibration_method=cal.method,
            segments=seg,
            baselines=evaluate_baselines(X[trA], yv[trA], X[valC], yc, pc),
            ablation=ablation,
            segment_models=segment_models,
            psi_between_as_ofs=psi_val,
            n_train=int(trA.sum()), n_calibration=int(calB.sum()), n_valid=int(valC.sum()),
            n_borrowers_train=int(meta.borrower_id[trA].nunique()),
            n_borrowers_valid=int(meta.borrower_id[valC].nunique()),
            train_positive_rate=round(float(yv[trA].mean()), 4),
            valid_positive_rate=round(float(yc.mean()), 4),
            validation=("borrower-disjoint + temporal: train fold A at as_of %s; calibrate and choose "
                        "thresholds on fold B at as_of %s; report fold C at as_of %s (borrowers never seen, "
                        "dates after training). Deployed model = evaluated model, no refit."
                        % (list(TRAIN_AS_OFS), list(VALID_AS_OFS), list(VALID_AS_OFS))),
            horizon_months=12,
            n_features=len(X.columns),
        )
        return cls(model=model, calibrator=cal, thresholds=thresholds, threshold=thr90,
                   features=list(X.columns), metrics=metrics)

    # ------------------------------------------------------------------ scoring
    def _row(self, feat: dict) -> pd.DataFrame:
        return pd.DataFrame([[feat.get(f, 0.0) for f in self.features]], columns=self.features)

    def predict_raw(self, feat: dict) -> float:
        return float(self.model.predict_proba(self._row(feat))[:, 1][0])

    def predict_pd(self, feat: dict) -> float:
        raw = self.predict_raw(feat)
        return float(self.calibrator.transform(np.array([raw]), np.array([_loan_type_from_feat(feat)]))[0])

    def predict_pd_batch(self, X: pd.DataFrame, loan_types: np.ndarray) -> np.ndarray:
        raw = self.model.predict_proba(X[self.features])[:, 1]
        return self.calibrator.transform(raw, np.asarray(loan_types))

    def predict_from_series(self, group: pd.DataFrame, as_of: int, static: dict | None = None) -> float | None:
        feat = msme_features_at(group, as_of, static=static)
        return None if feat is None else self.predict_pd(feat)

    def rag_bucket(self, pd_value: float, loan_type: str | None = None) -> str:
        """RAG bucket from the interpretation framework (single source of truth)."""
        return FW.bucket(pd_value, loan_type)

    # ------------------------------------------------------------------ persistence
    def save(self, model_dir: str | Path) -> None:
        d = Path(model_dir)
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "pd_model.pkl", "wb") as f:
            pickle.dump({"model": self.model, "calibrator": self.calibrator, "thresholds": self.thresholds,
                         "threshold": self.threshold, "features": self.features, "metrics": self.metrics}, f)
        with open(d / "pd_model_card.json", "w", encoding="utf-8") as f:
            json.dump(self.model_card(), f, indent=2, default=float)
        with open(d / "pd_model_card.md", "w", encoding="utf-8") as f:
            f.write(self.model_card_markdown())

    @classmethod
    def load(cls, model_dir: str | Path) -> "PDModel":
        with open(Path(model_dir) / "pd_model.pkl", "rb") as f:
            d = pickle.load(f)
        return cls(model=d["model"], calibrator=d.get("calibrator", _Calibrator()),
                   thresholds=d.get("thresholds", {}), threshold=d["threshold"],
                   features=d["features"], metrics=d["metrics"])

    # ------------------------------------------------------------------ model card
    def model_card(self) -> dict:
        return dict(
            name="PRAHARI PD model",
            task="Probability of default within 12 months (RBI SMA early warning)",
            algorithm="XGBoost (gradient-boosted trees) with isotonic probability calibration",
            features=self.features,
            pillars={k: v for k, v in PILLARS.items()},
            metrics=self.metrics,
            honesty_note=(
                "Every number is computed on borrowers the model never saw, at as-of months after the "
                "training window (borrower-disjoint temporal validation), and the operating thresholds were "
                "chosen on a separate calibration fold. The deployed model is the evaluated model. The "
                "headline is reported at the operating point that meets the bank's stated 90 percent "
                "accuracy requirement; the maximum-capture point and the full threshold table are shown "
                "alongside so the bank can pick its own trade-off. Data is synthetic and cleaner than a "
                "real book, so these numbers are an upper bound on what the method would achieve on IDBI "
                "data; the method, not the number, is what transfers."
            ),
        )

    def model_card_markdown(self) -> str:
        m = self.metrics
        cm = m.get("confusion_matrix", [[0, 0], [0, 0]])
        ci = m.get("auc_ci95", {})
        lines = [
            "# PRAHARI PD Model Card", "",
            "**Task:** probability of default within 12 months (RBI SMA early warning).", "",
            "**Algorithm:** XGBoost with isotonic calibration. **Validation:** %s" % m.get("validation", ""), "",
            "## Headline metrics (validation fold C, borrowers never seen, later as-of months)",
            "| Metric | Value |", "|---|---|",
            "| AUC | %.3f (95%% CI %s to %s) |" % (m.get("auc", 0), ci.get("low"), ci.get("high")),
            "| KS | %.3f |" % m.get("ks", 0),
            "| Operating threshold (bank 90%% accuracy point) | %.3f |" % m.get("operating_threshold", 0),
            "| Accuracy | %.3f |" % m.get("accuracy", 0),
            "| Balanced accuracy | %.3f |" % m.get("balanced_accuracy", 0),
            "| Recall | %.3f |" % m.get("recall", 0),
            "| Precision | %.3f |" % m.get("precision", 0),
            "| Brier | %.4f |" % m.get("calibration", {}).get("brier", 0), "",
            "Confusion matrix (rows = actual, cols = predicted) at the operating threshold:", "",
            "|  | pred 0 | pred 1 |", "|---|---|---|",
            "| actual 0 | %d | %d |" % (cm[0][0], cm[0][1]),
            "| actual 1 | %d | %d |" % (cm[1][0], cm[1][1]), "",
            "## Operating points", "| Point | Threshold | Accuracy | Bal. acc | Recall | Precision | Alerts | Missed |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in m.get("operating_points", []):
            lines.append("| %s | %.3f | %.3f | %.3f | %.3f | %.3f | %d | %d |" % (
                r["label"], r["threshold"], r["accuracy"], r["balanced_accuracy"], r["recall"], r["precision"],
                r["alerts"], r["missed"]))
        lines += ["", "## Lead time (share of eventual defaulters already flagged)",
                  "| Months before 90+ DPD | n | Flagged |", "|---|---|---|"]
        for r in m.get("lead_time", []):
            lines.append("| %s | %d | %s |" % (r["months_ahead"], r["n"], r["flagged"]))
        lines += ["", "## Baselines on the same fold", "| Method | Recall | Precision | Alerts | PRAHARI recall at same alerts |",
                  "|---|---|---|---|---|"]
        for r in m.get("baselines", []):
            lines.append("| %s | %.3f | %.3f | %d | %.3f |" % (r["name"], r["recall"], r["precision"], r["alerts"],
                                                           r["prahari_recall_at_same_alerts"]))
        lines += ["", "## Honesty note", self.model_card()["honesty_note"], ""]
        return "\n".join(lines)
