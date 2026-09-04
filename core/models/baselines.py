"""Baseline comparators for the PD model - the rules a bank runs today, on the same fold.

    dpd_rule        flag if the account touched 30+ DPD or missed an EMI in the window
                    (what an arrears-based early-warning system sees)
    util_dpd_rule   the dpd_rule OR utilisation at 90% or more
    logistic        L2 logistic regression on the same features (a transparent statistical model)

Each returns recall / precision / alert count on the validation fold, plus PRAHARI's recall at the
SAME alert budget, so the comparison is like for like.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import confusion_at, matched_alert_recall


def dpd_rule(X: pd.DataFrame) -> np.ndarray:
    return ((X["dpd_max"] >= 30) | (X["missed_cnt"] >= 1)).to_numpy().astype(float)


def util_dpd_rule(X: pd.DataFrame) -> np.ndarray:
    return (((X["dpd_max"] >= 30) | (X["missed_cnt"] >= 1)) | (X["util_last"] >= 0.90)).to_numpy().astype(float)


def _rule_row(name: str, desc: str, flag: np.ndarray, y: np.ndarray, p_model: np.ndarray) -> dict:
    c = confusion_at(y, flag, 0.5)
    matched = matched_alert_recall(y, p_model, c["alerts"])
    return dict(name=name, description=desc, recall=c["recall"], precision=c["precision"],
                alerts=c["alerts"], alert_rate=c["alert_rate"],
                prahari_recall_at_same_alerts=matched["recall"],
                prahari_precision_at_same_alerts=matched["precision"],
                uplift_x=round(matched["recall"] / c["recall"], 2) if c["recall"] > 0 else None)


def evaluate_baselines(X_tr: pd.DataFrame, y_tr: np.ndarray, X_te: pd.DataFrame, y_te: np.ndarray,
                       p_model: np.ndarray) -> list[dict]:
    rows = [
        _rule_row("Arrears rule", "30+ DPD or a missed EMI in the trailing 6 months", dpd_rule(X_te), y_te, p_model),
        _rule_row("Arrears or utilisation rule", "Arrears rule, or limit utilisation at 90% or more",
                  util_dpd_rule(X_te), y_te, p_model),
    ]
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import roc_auc_score
        lr = make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=2000, class_weight="balanced"))
        lr.fit(X_tr.fillna(0.0), y_tr)
        p_lr = lr.predict_proba(X_te.fillna(0.0))[:, 1]
        # match the model's alert budget at the max-capture point for a fair comparison
        budget = int((p_model >= np.quantile(p_model, 0.85)).sum())
        order = np.argsort(-p_lr)[:budget]
        tp = int(y_te[order].sum())
        matched = matched_alert_recall(y_te, p_model, budget)
        rows.append(dict(name="Logistic regression", description="L2 logistic regression on the same features",
                         auc=round(float(roc_auc_score(y_te, p_lr)), 4),
                         recall=round(tp / max(1, int(y_te.sum())), 4), precision=round(tp / max(1, budget), 4),
                         alerts=budget, alert_rate=round(budget / max(1, len(y_te)), 4),
                         prahari_recall_at_same_alerts=matched["recall"],
                         prahari_precision_at_same_alerts=matched["precision"],
                         uplift_x=round(matched["recall"] / (tp / max(1, int(y_te.sum()))), 2) if tp else None))
    except Exception:
        pass
    return rows
