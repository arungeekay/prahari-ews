"""MSME point-in-time features for the PD / survival / origination models.

`msme_features_at(group, as_of)` returns a trailing-window feature dict using only months
<= as_of. `build_msme_training_matrix` assembles the temporal-split-ready (X, y, meta) frame.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

WINDOW = 6
HORIZON = 12
TRAIN_AS_OFS = (6, 9, 12)
VALID_AS_OFS = (15, 18)
ALL_AS_OFS = TRAIN_AS_OFS + VALID_AS_OFS

# --- note sentiment (keyword fallback; the LLM layer can override in Phase 2 core/llm) ---
_NEG_WORDS = ["evasive", "idle", "delayed", "delay", "pressure", "lower than book", "late",
              "disrupted", "halted", "lost", "dispute", "fire", "slowdown", "reduced"]
_POS_WORDS = ["well stocked", "healthy", "satisfactory", "cooperative", "strong", "expansion",
              "upbeat", "hiring", "improving", "normalising", "recovering", "resolved"]


def note_sentiment(note: str) -> float:
    """Cheap deterministic note sentiment in [-1, 1]. Replaced by the LLM layer when available."""
    if not note:
        return 0.0
    t = note.lower()
    score = sum(w in t for w in _POS_WORDS) - sum(w in t for w in _NEG_WORDS)
    return float(np.clip(score, -1, 1))


def _slope(y: np.ndarray) -> float:
    if len(y) < 2:
        return 0.0
    return float(np.polyfit(np.arange(len(y)), y, 1)[0])


MSME_FEATURES = [
    "util_last", "util_mean", "util_max", "util_slope",
    "credit_slope", "credit_last_over_first", "credit_cv", "credit_mean_lakh",
    "gst_delay_mean", "gst_delay_max", "gst_delay_slope",
    "bounce_out_sum", "bounce_in_sum",
    "balance_cv", "balance_last_over_credit",
    "missed_cnt", "delayed_cnt", "dpd_max", "emi_late_max",
    "bureau_dpd_other_max", "bureau_enq_sum", "bureau_newloans_sum",
    "epfo_delay_max", "epfo_emp_slope",
    "sentiment_last", "note_sentiment_mean",
    "electricity_slope", "fuel_slope",
]


def msme_features_at(group: pd.DataFrame, as_of: int, window: int = WINDOW) -> dict | None:
    """Trailing-window features for one borrower as of `as_of` (uses only months <= as_of)."""
    w = group[(group.month_index <= as_of) & (group.month_index > as_of - window)]
    if len(w) < 3:
        return None
    util = w.limit_utilisation.to_numpy()
    cred = w.credits.to_numpy()
    gd = w.gst_filing_delay_days.to_numpy()
    bal = w.month_end_balance.to_numpy()
    emp = w.epfo_employee_count.to_numpy(dtype=float)
    elec = w.electricity_units.to_numpy()
    fuel = w.fuel_spend.to_numpy()
    notes = [note_sentiment(n) for n in w.officer_note.tolist()]
    return {
        "util_last": util[-1], "util_mean": util.mean(), "util_max": util.max(), "util_slope": _slope(util),
        "credit_slope": _slope(cred / (cred[0] + 1.0)),
        "credit_last_over_first": cred[-1] / (cred[0] + 1.0),
        "credit_cv": cred.std() / (cred.mean() + 1.0),
        "credit_mean_lakh": cred.mean() / 1e5,
        "gst_delay_mean": gd.mean(), "gst_delay_max": gd.max(), "gst_delay_slope": _slope(gd),
        "bounce_out_sum": float(w.cheque_bounces_outward.sum()),
        "bounce_in_sum": float(w.cheque_bounces_inward.sum()),
        "balance_cv": bal.std() / (bal.mean() + 1.0),
        "balance_last_over_credit": bal[-1] / (cred[-1] + 1.0),
        "missed_cnt": float((w.repayment_status == "missed").sum()),
        "delayed_cnt": float((w.repayment_status == "delayed").sum()),
        "dpd_max": float(w.dpd.max()),
        "emi_late_max": float(w.emi_days_late.max()),
        "bureau_dpd_other_max": float(w.bureau_dpd_other.max()),
        "bureau_enq_sum": float(w.bureau_enquiries.sum()),
        "bureau_newloans_sum": float(w.bureau_new_loans.sum()),
        "epfo_delay_max": float(w.epfo_contribution_delay_days.max()),
        "epfo_emp_slope": _slope(emp),
        "sentiment_last": w.sector_sentiment.to_numpy()[-1],
        "note_sentiment_mean": float(np.mean(notes)) if notes else 0.0,
        "electricity_slope": _slope(elec / (elec[0] + 1.0)),
        "fuel_slope": _slope(fuel / (fuel[0] + 1.0)),
    }


def build_msme_training_matrix(frames: dict, as_ofs=ALL_AS_OFS, horizon=HORIZON, window=WINDOW):
    """Return (X: DataFrame[MSME_FEATURES], y: Series, meta: DataFrame[borrower_id, as_of]).

    label = 1 iff the borrower defaults within `horizon` months AFTER as_of; accounts already at
    90+ DPD by as_of are dropped (already NPA, not a prediction target)."""
    b = frames["borrowers"].set_index("borrower_id")
    mm = frames["msme_monthly"]
    rows, labels, meta = [], [], []
    for bid, g in mm.groupby("borrower_id", sort=True):
        g = g.sort_values("month_index")
        dm = int(b.at[bid, "default_month"])
        for a in as_ofs:
            if 0 <= dm <= a:
                continue
            feats = msme_features_at(g, a, window)
            if feats is None:
                continue
            rows.append(feats)
            labels.append(1 if (a < dm <= a + horizon) else 0)
            meta.append((bid, a))
    X = pd.DataFrame(rows, columns=MSME_FEATURES)
    y = pd.Series(labels, name="label")
    meta_df = pd.DataFrame(meta, columns=["borrower_id", "as_of"])
    return X, y, meta_df
