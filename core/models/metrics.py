"""Validation battery for the PD model - what a bank's model-risk team expects to see.

Everything here is computed on the held-out validation fold only. Functions are pure (arrays in,
dicts out) so they are unit-testable and the model card can serialise them directly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, brier_score_loss


def confusion_at(y: np.ndarray, p: np.ndarray, thr: float) -> dict:
    pred = (p >= thr).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    tn = int(((pred == 0) & (y == 0)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
    n = max(1, len(y))
    rec = tp / max(1, tp + fn); spec = tn / max(1, tn + fp); prec = tp / max(1, tp + fp)
    return dict(threshold=round(float(thr), 4), accuracy=round((tp + tn) / n, 4),
                balanced_accuracy=round(0.5 * (rec + spec), 4), recall=round(rec, 4),
                precision=round(prec, 4), f1=round(2 * prec * rec / max(1e-9, prec + rec), 4),
                alerts=tp + fp, alert_rate=round((tp + fp) / n, 4), missed=fn,
                confusion_matrix=[[tn, fp], [fn, tp]])


def named_thresholds(y: np.ndarray, p: np.ndarray) -> dict:
    """Choose the three named operating points on the CALIBRATION fold (never the reported fold).

    max_capture       maximum balanced accuracy (Youden-style), recall-heavy
    bank_90_accuracy  the lowest threshold whose raw accuracy is >= 90% (the bank's stated bar),
                      i.e. the most defaults that can be caught while meeting it
    precision_weighted the threshold that maximises F1
    """
    ths = np.unique(np.round(p, 3))
    ths = ths[(ths > 0.0) & (ths < 1.0)]
    if len(ths) == 0:
        ths = np.array([0.5])
    rows = [confusion_at(y, p, t) for t in ths]
    max_cap = max(rows, key=lambda r: (r["balanced_accuracy"], r["recall"]))
    ok = [r for r in rows if r["accuracy"] >= 0.90]
    bank90 = max(ok, key=lambda r: (r["recall"], -r["threshold"])) if ok else max(rows, key=lambda r: r["accuracy"])
    prec_w = max(rows, key=lambda r: (r["f1"], r["precision"]))
    return {"max_capture": max_cap["threshold"], "bank_90_accuracy": bank90["threshold"],
            "precision_weighted": prec_w["threshold"]}


def operating_points(y: np.ndarray, p: np.ndarray, thresholds: dict) -> list[dict]:
    labels = {"max_capture": "Maximum capture", "bank_90_accuracy": "Bank 90% accuracy",
              "precision_weighted": "Precision weighted"}
    out = []
    for key, thr in thresholds.items():
        r = confusion_at(y, p, thr)
        r.update(key=key, label=labels.get(key, key))
        out.append(r)
    return out


def decile_table(y: np.ndarray, p: np.ndarray, exposure: np.ndarray | None = None) -> list[dict]:
    df = pd.DataFrame({"p": p, "y": y, "e": exposure if exposure is not None else np.zeros(len(y))})
    df = df.sort_values("p", ascending=False).reset_index(drop=True)
    df["decile"] = (df.index * 10 // len(df)) + 1
    base = df.y.mean() if len(df) else 0.0
    total_pos = max(1, int(df.y.sum()))
    rows, cum = [], 0
    for d, g in df.groupby("decile"):
        cum += int(g.y.sum())
        rows.append(dict(decile=int(d), n=int(len(g)), defaults=int(g.y.sum()),
                         default_rate=round(float(g.y.mean()), 4),
                         lift=round(float(g.y.mean() / base), 2) if base > 0 else 0.0,
                         cum_capture=round(cum / total_pos, 4),
                         min_pd=round(float(g.p.min()), 4), max_pd=round(float(g.p.max()), 4),
                         exposure=round(float(g.e.sum()), 2)))
    return rows


def lead_time_curve(y: np.ndarray, p: np.ndarray, months_ahead: np.ndarray, thr: float) -> list[dict]:
    """Share of eventual defaulters already flagged, by how many months before 90+ DPD."""
    pos = (y == 1) & (months_ahead > 0)
    bins = [(1, 3), (4, 6), (7, 9), (10, 12)]
    out = []
    for lo, hi in bins:
        m = pos & (months_ahead >= lo) & (months_ahead <= hi)
        n = int(m.sum())
        out.append(dict(months_ahead=f"{lo}-{hi}", n=n,
                        flagged=round(float((p[m] >= thr).mean()), 4) if n else None))
    return out


def calibration_table(y: np.ndarray, p: np.ndarray) -> dict:
    edges = [0, 0.02, 0.05, 0.10, 0.20, 0.40, 0.60, 1.0001]
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum() == 0:
            continue
        rows.append(dict(bin=f"{lo:.2f}-{min(hi, 1.0):.2f}", n=int(m.sum()),
                         mean_predicted=round(float(p[m].mean()), 4), observed=round(float(y[m].mean()), 4)))
    ece = float(sum(r["n"] * abs(r["mean_predicted"] - r["observed"]) for r in rows) / max(1, len(y)))
    return dict(bins=rows, brier=round(float(brier_score_loss(y, p)), 4), expected_calibration_error=round(ece, 4))


def ks_statistic(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(-p)
    ys = y[order]
    pos = np.cumsum(ys) / max(1, ys.sum())
    neg = np.cumsum(1 - ys) / max(1, (1 - ys).sum())
    return round(float(np.max(np.abs(pos - neg))), 4)


def bootstrap_auc(y: np.ndarray, p: np.ndarray, n_boot: int = 300, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    aucs = []
    n = len(y)
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if y[idx].sum() == 0 or y[idx].sum() == n:
            continue
        aucs.append(roc_auc_score(y[idx], p[idx]))
    if not aucs:
        return dict(low=None, high=None, n_boot=0)
    return dict(low=round(float(np.percentile(aucs, 2.5)), 4), high=round(float(np.percentile(aucs, 97.5)), 4),
                n_boot=len(aucs))


def segment_metrics(y: np.ndarray, p: np.ndarray, seg: np.ndarray, thr: float, name: str) -> list[dict]:
    out = []
    for k in sorted(pd.unique(seg), key=lambda v: str(v)):
        m = seg == k
        yk, pk = y[m], p[m]
        auc = round(float(roc_auc_score(yk, pk)), 4) if (yk.sum() > 0 and yk.sum() < len(yk)) else None
        c = confusion_at(yk, pk, thr) if len(yk) else None
        out.append(dict(segment=name, value=str(k), n=int(m.sum()), defaults=int(yk.sum()),
                        default_rate=round(float(yk.mean()), 4) if len(yk) else None, auc=auc,
                        recall=c["recall"] if c else None, precision=c["precision"] if c else None,
                        alert_rate=c["alert_rate"] if c else None))
    return out


def psi(p_ref: np.ndarray, p_new: np.ndarray, bins: int = 10) -> float:
    """Population stability index of the score distribution between two as-of months."""
    edges = np.quantile(p_ref, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    a = np.histogram(p_ref, edges)[0] / max(1, len(p_ref))
    b = np.histogram(p_new, edges)[0] / max(1, len(p_new))
    a = np.clip(a, 1e-6, None); b = np.clip(b, 1e-6, None)
    return round(float(np.sum((b - a) * np.log(b / a))), 4)


def matched_alert_recall(y: np.ndarray, p: np.ndarray, n_alerts: int) -> dict:
    """PRAHARI's capture when allowed exactly the same number of alerts as a baseline rule."""
    if n_alerts <= 0:
        return dict(alerts=0, recall=0.0, precision=0.0)
    order = np.argsort(-p)[:n_alerts]
    tp = int(y[order].sum())
    return dict(alerts=int(n_alerts), recall=round(tp / max(1, int(y.sum())), 4), precision=round(tp / n_alerts, 4))
