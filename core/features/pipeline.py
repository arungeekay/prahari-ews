"""MSME point-in-time features for the PD / survival / origination models.

`msme_features_at(group, as_of, static=...)` returns a trailing-window feature dict using ONLY
months <= as_of. `build_msme_training_matrix` assembles the (X, y, meta) frame for the
borrower-disjoint temporal split used by the PD model.

Feature families (each maps to a pillar of the interpretation framework):
    conduct     utilisation level / trend (CC/OD only), drawing-power gap and drawn-over-DP
                (IDBI API 441), repayment record, cheque returns, balance behaviour, liens
                (IDBI API 362), stock-statement submission
    compliance  GST filing delay level / trend, EPFO contribution delay
    activity    credit turnover trend and volatility, electricity and fuel trends, headcount trend
    external    bureau enquiries / new loans / DPD elsewhere, sector sentiment
    profile     loan type, sector, size, vintage, promoter experience and qualification (static)
    notes       officer-note sentiment and themes (unstructured)
    contagion   anchor-attributable inflow trend and dependence

Strict rule: no feature may use data after as_of_month (leakage-tested against this module).
"""

from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from .notes import note_window_features, note_sentiment, NOTE_FEATURES  # noqa: F401  (re-exported)

WINDOW = 6
HORIZON = 12
TRAIN_AS_OFS = (6, 9, 12)
VALID_AS_OFS = (15, 18)
ALL_AS_OFS = TRAIN_AS_OFS + VALID_AS_OFS

SECTORS = ["manufacturing", "trading", "logistics", "services", "food_processing"]
QUAL_ORDINAL = {"Below SSC": 0, "SSC": 1, "HSC": 2, "Graduate": 3, "Post-graduate": 4, "Professional": 5}

CONDUCT_FEATURES = [
    "util_last", "util_mean", "util_max", "util_slope",
    "dp_gap_last", "dp_gap_slope", "drawn_over_dp_last", "over_dp_months",
    "stmt_missed_cnt", "lien_cnt_sum", "lien_amt_over_limit",
    "bounce_out_sum", "bounce_in_sum",
    "balance_cv", "balance_last_over_credit",
    "missed_cnt", "delayed_cnt", "dpd_max", "emi_late_max",
]
COMPLIANCE_FEATURES = ["gst_delay_mean", "gst_delay_max", "gst_delay_slope", "epfo_delay_max"]
ACTIVITY_FEATURES = ["credit_slope", "credit_last_over_first", "credit_cv", "credit_mean_lakh",
                     "electricity_slope", "fuel_slope", "epfo_emp_slope"]
EXTERNAL_FEATURES = ["bureau_dpd_other_max", "bureau_enq_sum", "bureau_newloans_sum", "sentiment_last"]
PROFILE_FEATURES = ["is_cc", "is_od", "is_term"] + [f"sector_{s}" for s in SECTORS] + \
                   ["log_limit", "vintage_years", "promoter_experience_years", "promoter_qual_ord"]
CONTAGION_FEATURES = ["anchor_inflow_slope", "anchor_dependence"]

MSME_FEATURES = (CONDUCT_FEATURES + COMPLIANCE_FEATURES + ACTIVITY_FEATURES + EXTERNAL_FEATURES
                 + PROFILE_FEATURES + NOTE_FEATURES + CONTAGION_FEATURES)

PILLARS = {
    "Conduct": CONDUCT_FEATURES,
    "Compliance": COMPLIANCE_FEATURES,
    "Activity": ACTIVITY_FEATURES,
    "External": EXTERNAL_FEATURES,
    "Promoter profile": PROFILE_FEATURES,
    "Officer notes": NOTE_FEATURES,
    "Contagion": CONTAGION_FEATURES,
}

# Utilisation is a working-capital concept; for term loans these features are masked to 0 and
# the model reads term-loan stress from cash-flow, compliance and repayment instead.
UTIL_FEATURES = ["util_last", "util_mean", "util_max", "util_slope",
                 "dp_gap_last", "dp_gap_slope", "drawn_over_dp_last", "over_dp_months", "stmt_missed_cnt"]


def _slope(y: np.ndarray) -> float:
    if len(y) < 2:
        return 0.0
    return float(np.polyfit(np.arange(len(y)), y, 1)[0])


def static_from_row(b) -> dict:
    """Static borrower attributes the feature builder needs (from a borrowers row or dict)."""
    g = (lambda k, d=None: b.get(k, d)) if isinstance(b, dict) else (lambda k, d=None: getattr(b, k, d))
    return dict(loan_type=str(g("loan_type", "CC")), sector=str(g("sector", "manufacturing")),
                sanctioned_limit=float(g("sanctioned_limit", 0.0) or 0.0),
                vintage_years=float(g("vintage_years", 0) or 0),
                promoter_experience_years=float(g("promoter_experience_years", 0) or 0),
                promoter_qualification=str(g("promoter_qualification", "")))


def _static_features(static: dict | None) -> dict:
    s = static or {}
    lt = s.get("loan_type", "")
    sec = s.get("sector", "")
    out = {"is_cc": float(lt == "CC"), "is_od": float(lt == "OD"), "is_term": float(lt == "term")}
    for x in SECTORS:
        out[f"sector_{x}"] = float(sec == x)
    lim = float(s.get("sanctioned_limit", 0.0) or 0.0)
    out["log_limit"] = float(np.log10(lim)) if lim > 0 else 0.0
    out["vintage_years"] = float(s.get("vintage_years", 0.0) or 0.0)
    out["promoter_experience_years"] = float(s.get("promoter_experience_years", 0.0) or 0.0)
    out["promoter_qual_ord"] = float(QUAL_ORDINAL.get(str(s.get("promoter_qualification", "")), 3))
    return out


def _col(w: pd.DataFrame, name: str, default=0.0) -> np.ndarray:
    """Column as float array, tolerating legacy frames that predate a column."""
    if name in w.columns:
        return w[name].to_numpy(dtype=float)
    return np.full(len(w), float(default))


def msme_features_at(group: pd.DataFrame, as_of: int, window: int = WINDOW, static: dict | None = None) -> dict | None:
    """Trailing-window features for one borrower as of `as_of` (uses only months <= as_of).

    `static` carries loan_type / sector / sanctioned_limit / vintage / promoter fields from the
    borrowers table (see `static_from_row`). When omitted the profile features are zero and
    utilisation is treated as a CC/OD account."""
    w = group[(group.month_index <= as_of) & (group.month_index > as_of - window)]
    if len(w) < 3:
        return None
    util = w.limit_utilisation.to_numpy(dtype=float)
    cred = w.credits.to_numpy(dtype=float)
    gd = w.gst_filing_delay_days.to_numpy(dtype=float)
    bal = w.month_end_balance.to_numpy(dtype=float)
    emp = w.epfo_employee_count.to_numpy(dtype=float)
    elec = w.electricity_units.to_numpy(dtype=float)
    fuel = w.fuel_spend.to_numpy(dtype=float)
    dp = _col(w, "drawing_power_pct", 0.0)
    stmt = _col(w, "stock_statement_submitted", 1.0)
    lien_cnt = _col(w, "lien_count", 0.0)
    lien_amt = _col(w, "lien_amount", 0.0)
    anchor_in = _col(w, "anchor_inflow", 0.0)
    notes = w.officer_note.tolist() if "officer_note" in w.columns else []

    s = static or {}
    limit = float(s.get("sanctioned_limit", 0.0) or 0.0)
    is_term = str(s.get("loan_type", "")) == "term"

    has_dp = bool((dp > 0).any())
    dp_gap = np.where(dp > 0, 1.0 - dp, 0.0)
    drawn_over_dp = np.where(dp > 0, util / np.maximum(dp, 1e-6), 0.0)

    feats = {
        # conduct
        "util_last": util[-1], "util_mean": util.mean(), "util_max": util.max(), "util_slope": _slope(util),
        "dp_gap_last": float(dp_gap[-1]) if has_dp else 0.0,
        "dp_gap_slope": _slope(dp_gap) if has_dp else 0.0,
        "drawn_over_dp_last": float(drawn_over_dp[-1]) if has_dp else 0.0,
        "over_dp_months": float((drawn_over_dp > 1.0).sum()) if has_dp else 0.0,
        "stmt_missed_cnt": float((stmt < 0.5).sum()),
        "lien_cnt_sum": float(lien_cnt.sum()),
        "lien_amt_over_limit": float(lien_amt.sum() / limit) if limit > 0 else 0.0,
        "bounce_out_sum": float(w.cheque_bounces_outward.sum()),
        "bounce_in_sum": float(w.cheque_bounces_inward.sum()),
        "balance_cv": bal.std() / (bal.mean() + 1.0),
        "balance_last_over_credit": bal[-1] / (cred[-1] + 1.0),
        "missed_cnt": float((w.repayment_status == "missed").sum()),
        "delayed_cnt": float((w.repayment_status == "delayed").sum()),
        "dpd_max": float(w.dpd.max()),
        "emi_late_max": float(w.emi_days_late.max()),
        # compliance
        "gst_delay_mean": gd.mean(), "gst_delay_max": gd.max(), "gst_delay_slope": _slope(gd),
        "epfo_delay_max": float(w.epfo_contribution_delay_days.max()),
        # activity
        "credit_slope": _slope(cred / (cred[0] + 1.0)),
        "credit_last_over_first": cred[-1] / (cred[0] + 1.0),
        "credit_cv": cred.std() / (cred.mean() + 1.0),
        "credit_mean_lakh": cred.mean() / 1e5,
        "electricity_slope": _slope(elec / (elec[0] + 1.0)),
        "fuel_slope": _slope(fuel / (fuel[0] + 1.0)),
        "epfo_emp_slope": _slope(emp),
        # external
        "bureau_dpd_other_max": float(w.bureau_dpd_other.max()),
        "bureau_enq_sum": float(w.bureau_enquiries.sum()),
        "bureau_newloans_sum": float(w.bureau_new_loans.sum()),
        "sentiment_last": float(w.sector_sentiment.to_numpy()[-1]),
        # contagion
        "anchor_inflow_slope": _slope(anchor_in / (anchor_in[0] + 1.0)) if anchor_in[0] > 0 else 0.0,
        "anchor_dependence": float(anchor_in.mean() / (cred.mean() + 1.0)),
    }
    feats.update(_static_features(static))
    feats.update(note_window_features(notes))
    if is_term:
        for f in UTIL_FEATURES:
            feats[f] = 0.0
    return {k: float(v) for k, v in feats.items()}


def assign_group(borrower_id: str, seed: int = 42) -> str:
    """Deterministic, order-independent borrower fold: 'A' train (60%), 'B' calibration (20%),
    'C' validation (20%). Hash based so it is stable across platforms and data regenerations."""
    h = zlib.crc32(f"{seed}:{borrower_id}".encode("utf-8")) % 100
    return "A" if h < 60 else ("B" if h < 80 else "C")


def build_msme_training_matrix(frames: dict, as_ofs=ALL_AS_OFS, horizon=HORIZON, window=WINDOW):
    """Return (X: DataFrame[MSME_FEATURES], y: Series, meta: DataFrame).

    meta columns: borrower_id, as_of, group (A/B/C borrower fold), loan_type, sector,
    vintage_years, default_month, months_ahead (months from as_of to default, -1 if none),
    exposure_proxy (sanctioned_limit x last utilisation).

    label = 1 iff the borrower defaults within `horizon` months AFTER as_of; accounts already at
    90+ DPD by as_of are dropped (already NPA, not a prediction target)."""
    b = frames["borrowers"].set_index("borrower_id")
    mm = frames["msme_monthly"]
    rows, labels, meta = [], [], []
    for bid, g in mm.groupby("borrower_id", sort=True):
        g = g.sort_values("month_index")
        brow = b.loc[bid]
        dm = int(brow["default_month"])
        static = static_from_row(brow)
        for a in as_ofs:
            if 0 <= dm <= a:
                continue
            feats = msme_features_at(g, a, window, static=static)
            if feats is None:
                continue
            rows.append(feats)
            labels.append(1 if (a < dm <= a + horizon) else 0)
            meta.append(dict(borrower_id=bid, as_of=a, group=assign_group(bid),
                             loan_type=static["loan_type"], sector=static["sector"],
                             vintage_years=static["vintage_years"], default_month=dm,
                             months_ahead=(dm - a) if dm > a else -1,
                             exposure_proxy=static["sanctioned_limit"] * feats["util_last"]
                             if static["loan_type"] != "term" else static["sanctioned_limit"] * float(g[g.month_index <= a].limit_utilisation.iloc[-1])))
    X = pd.DataFrame(rows, columns=MSME_FEATURES)
    y = pd.Series(labels, name="label")
    meta_df = pd.DataFrame(meta)
    return X, y, meta_df
