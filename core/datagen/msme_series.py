"""MSME monthly behavioural series (24 months) - causally consistent with latent trajectory.

The cascade for a *predictably* distressing account (BUILD_SPEC §3.2/§3.3/§9.1):
    GST filing delays (d≥3) → utilisation creep (d≥1, 62%→94%) → credit-turnover decline
    (d≥3, real sales fall) → cheque bounces (d≥7) → repayment breaks only in the final ~3
    months before 90+ DPD.  (d = month_index − onset)

But a realistic book is NOT that tidy (otherwise a model scores AUC ≈ 0.99 and reads as rigged):
    * sudden_shock          - healthy, then an abrupt default with NO precursor (unpredictable).
    * distress_then_recover - genuine 4–6 month drift that recovers (honest false positives).
    * per-firm `severity`   - defaulters drift at different steepness (some barely detectable).
    * clean-majority noise  - stray one-off bounces / late filings / lumpy months.

Key invariants preserved throughout:
    * No feature leakage: field at month m depends only on the trajectory up to m.
    * Fraud (GST↔electricity): electricity/EPFO track *real* operations; fraud decouples GST up.
    * Contagion: Anchor #1 suppliers lose ~payment_cut×anchor_share of inflows from the event.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import characters as CH
from .util import month_index_to_date

_M = C.N_MONTHS_MSME
_MONTHS = np.arange(_M)
_MONTH_DATES = [month_index_to_date(i).isoformat() for i in range(_M)]

# distress_at_month_k (defaults) and distress_then_recover (keeps paying) share the SAME soft
# cascade - utilisation, credit, GST, bounces, EPFO, bureau DPD - driven by onset + severity.
# They diverge ONLY in the terminal repayment outcome. This is the deliberate aleatoric overlap:
# point-in-time before the terminal DPD ramp, a defaulter and a survivor are indistinguishable, so
# no feature set can perfectly separate them and AUC honestly caps ~0.92.
_SOFT_DISTRESS = ("distress_at_month_k", "distress_then_recover")

# ---- loan-officer note templates, keyed to account state (BUILD_SPEC §3.2) ----
_NOTES = {
    "growing": [
        "Capacity expansion underway; new machinery observed on the floor.",
        "Order inflow strong; promoter upbeat on demand for the quarter.",
        "Unit visit: additional shift running, hiring in progress.",
    ],
    "healthy": [
        "Unit visit: godown well stocked, operations normal.",
        "Stock and receivables verified; no adverse observations.",
        "Routine review: account conduct satisfactory.",
        "Promoter cooperative; order book healthy.",
    ],
    "warning": [
        "Promoter mentions delayed receivables from two buyers.",
        "Utilisation edging up; enquired about a limit enhancement.",
        "Slight slowdown noted; festival season expected to help.",
    ],
    "distress": [
        "Unit visit: reduced activity, some machines idle.",
        "Promoter evasive about receivables and creditor pressure.",
        "Cheque presented late; promoter cites buyer payment delays.",
        "Stock levels lower than book value; monitoring closely.",
    ],
    "shock": [
        "Sudden setback: fire reported at unit, operations halted.",
        "Key buyer exited abruptly; large order book lost overnight.",
        "Promoter dispute disclosed; business operations disrupted.",
    ],
    "recover": [
        "Earlier stress easing; receivables position improving.",
        "Order book recovering; utilisation normalising.",
        "Promoter reports one-off disruption now resolved.",
    ],
    "fraud": [
        "Turnover growth reported but floor activity appears modest.",
        "Routine review: promoter reports rising sales.",
        "Books show strong turnover; physical stock verification pending.",
    ],
}


def build_sector_sentiment(rng: np.random.Generator) -> tuple[pd.DataFrame, dict]:
    """News/sector sentiment in [-1, 1] per sector-month (BUILD_SPEC §3.2)."""
    rows, lookup = [], {}
    for sector in C.SECTORS:
        base = rng.uniform(*C.SENTIMENT["base"])
        series = np.empty(_M)
        val = base
        for m in range(_M):
            val = 0.8 * val + 0.2 * base + rng.normal(0, C.SENTIMENT["month_vol"])
            series[m] = float(np.clip(val, -1.0, 1.0))
        lookup[sector] = series
        for m in range(_M):
            rows.append(dict(sector=sector, month_index=m, month_date=_MONTH_DATES[m],
                             sentiment_score=round(series[m], 4)))
    return pd.DataFrame(rows), lookup


def _twin_gst_series() -> np.ndarray:
    """Declared GST turnover shared *identically* by Verma (clean) and Gupta (fraud)."""
    g = CH.TWIN_GST_GROWTH_PER_MONTH
    seasonal = 1 + 0.04 * np.sin(2 * np.pi * _MONTHS / 12 + 0.6)
    return CH.TWIN_BASE_TURNOVER * (1 + g) ** _MONTHS * seasonal


_TWIN_GST = _twin_gst_series()




def _op_trend(rng, row) -> np.ndarray:
    """Real-operations trend (drives electricity, EPFO, fuel, real receipts)."""
    traj = row.health_trajectory
    sev = float(row.severity)
    trend = np.ones(_M)
    if traj == "growing":
        g = rng.uniform(*C.GROWING["turnover_growth"])
        trend = (1 + g) ** _MONTHS
    elif traj == "stable":
        drift = rng.uniform(-0.001, 0.003)
        trend = 1 + drift * _MONTHS
    elif traj == "slow_decline":
        s = int(row.traj_start)
        for m in range(_M):
            if m >= s:
                trend[m] = max(C.SLOW_DECLINE["credit_floor"],
                               (1 - C.SLOW_DECLINE["credit_decline_per_month"]) ** (m - s))
    elif traj in _SOFT_DISTRESS:
        s = int(row.traj_start)
        cds, rate, floor = (C.DISTRESS["credit_decline_start"],
                            C.DISTRESS["credit_decline_per_month"], C.DISTRESS["credit_floor"])
        for m in range(_M):
            d = m - s
            if d >= 0:
                trend[m] = max(floor, 1 - max(0, d - (cds - 1)) * rate * sev)
    elif traj == "sudden_shock":
        s = int(row.traj_start)
        drift = rng.uniform(-0.001, 0.003)
        trend = 1 + drift * _MONTHS                     # healthy until the shock
        cf = rng.uniform(*C.SHOCK["collapse_factor"])
        for m in range(_M):
            if m >= s:
                trend[m] = trend[m] * cf * max(0.4, 1 - 0.05 * (m - s))
        trend = np.maximum(trend, 0.05)
    elif traj == "fraud_pattern":
        ch = rng.uniform(*C.FRAUD["elec_change_per_month"])
        trend = (1 + ch) ** _MONTHS
    return trend


def _noise_mult(row) -> float:
    """Random firms carry realistic observation noise; the pinned demo cast does not."""
    return 1.0 if row.demo else C.FEATURE_NOISE_MULT


def _utilisation(rng, row) -> np.ndarray:
    traj = row.health_trajectory
    sev = float(row.severity)
    noise = rng.normal(0, 0.02 * _noise_mult(row), _M)
    if traj in _SOFT_DISTRESS:
        s = int(row.traj_start)
        util = np.full(_M, 0.50)
        for m in range(_M):
            d = m - s
            if d >= 0:
                util[m] = C.DISTRESS["util_base"] + d * C.DISTRESS["util_creep_per_month"] * sev
        util = np.clip(util + noise, 0.15, C.DISTRESS["util_max"])
    elif traj == "sudden_shock":
        s = int(row.traj_start)
        util = np.full(_M, 0.50)
        for m in range(_M):
            if m >= s:
                util[m] = C.SHOCK["util_spike"]
        util = np.clip(util + noise, 0.15, 0.99)
    elif traj == "slow_decline":
        s = int(row.traj_start)
        util = np.full(_M, 0.50)
        for m in range(_M):
            if m >= s:
                util[m] = min(C.SLOW_DECLINE["util_cap"],
                              C.SLOW_DECLINE["util_base"] + (m - s) * C.SLOW_DECLINE["util_creep_per_month"])
        util = np.clip(util + noise, 0.15, 0.9)
    elif traj == "growing":
        util = np.clip(C.GROWING["util_base"] - 0.003 * _MONTHS + noise, 0.15, 0.85)
    elif traj == "fraud_pattern":
        util = np.clip(0.60 + 0.008 * _MONTHS + noise, 0.2, 0.95)
    else:  # stable
        util = np.clip(C.STABLE["util_base"] + noise, 0.2, 0.9)
    # persistent per-firm utilisation-level offset (random population only)
    if row.demo == "":
        util = np.clip(util + rng.normal(0, C.FIRM_UTIL_BASE_SPREAD), 0.08, 0.99)
    return util


def _gst_filing_delay(rng, row) -> np.ndarray:
    traj = row.health_trajectory
    sev = float(row.severity)
    delay = np.zeros(_M)
    if traj in _SOFT_DISTRESS:
        s = int(row.traj_start)
        for m in range(_M):
            d = m - s
            if d >= C.DISTRESS["gst_delay_start"]:
                delay[m] = min(C.DISTRESS["gst_delay_max"],
                               (d - (C.DISTRESS["gst_delay_start"] - 1)) * C.DISTRESS["gst_delay_per_month"] * sev)
    elif traj == "sudden_shock":
        s = int(row.traj_start)
        for m in range(_M):
            if m >= s:
                delay[m] = min(60.0, (m - s + 1) * 15.0)   # filing collapses at the shock
    elif traj == "slow_decline":
        s = int(row.traj_start)
        for m in range(_M):
            if m >= s:
                delay[m] = min(C.SLOW_DECLINE["gst_delay_max"], (m - s) * C.SLOW_DECLINE["gst_delay_per_month"])
    # baseline tiny delays for everyone (0–2 days)
    delay = delay + (rng.random(_M) < 0.15) * rng.integers(0, 3, _M)
    # one-off real filing delays for the clean majority (a single quarter's slip) + some firms
    # are chronically-slightly-late filers (a persistent confounder with early distress)
    if traj in ("stable", "growing") and row.demo == "":
        oneoff = rng.random(_M) < C.CLEAN_NOISE["oneoff_gst_delay_prob"]
        delay = delay + oneoff * rng.integers(*C.CLEAN_NOISE["oneoff_gst_delay_range"], _M)
        if rng.random() < C.FIRM_GST_BASE_DELAY_PROB:
            delay = delay + rng.integers(*C.FIRM_GST_BASE_DELAY_RANGE)
    return np.round(delay).astype(np.int64)


def _repayment(row) -> tuple[list, np.ndarray, np.ndarray]:
    """repayment_status list, emi_days_late, dpd - driven by months-to-default.

    Non-defaulting firms are on_time, EXCEPT a near-miss (distress_then_recover) posts a single
    delayed EMI at its trough (a soft signal that then cures)."""
    dm = int(row.default_month)
    traj = row.health_trajectory
    status, emi_late, dpd = [], np.zeros(_M, np.int64), np.zeros(_M, np.int64)

    if dm < 0:
        # Non-defaulters keep servicing our EMI. distress_then_recover pays throughout (DPD 0) -
        # identical to a distress firm BEFORE its terminal ramp, which is the whole point (the
        # observable overlap that makes default genuinely uncertain point-in-time). slow_decline
        # posts a couple of delayed-but-cured EMIs (mild chronic stress).
        delayed_months = set()
        if traj == "slow_decline":
            delayed_months = {int(row.traj_start) + k for k in C.SLOW_DECLINE["delayed_emi_months"]}
        for m in range(_M):
            if m in delayed_months:
                status.append("delayed"); emi_late[m] = 18; dpd[m] = C.SLOW_DECLINE["delayed_dpd"]
            else:
                status.append("on_time")
        return status, emi_late, dpd

    for m in range(_M):
        mtd = dm - m
        if mtd > C.DISTRESS["repay_break_months"]:
            status.append("on_time")
        elif mtd == 3:
            status.append("delayed"); emi_late[m] = 14; dpd[m] = 15
        elif mtd == 2:
            status.append("delayed"); emi_late[m] = 35; dpd[m] = 45
        elif mtd == 1:
            status.append("missed"); emi_late[m] = 70; dpd[m] = 75
        elif mtd == 0:
            status.append("missed"); emi_late[m] = 90; dpd[m] = C.DEFAULT_DPD
        else:  # post-default within window
            status.append("missed"); emi_late[m] = 90 + 30 * (-mtd); dpd[m] = C.DEFAULT_DPD + 30 * (-mtd)
    return status, emi_late, dpd


def _gen_borrower(rng: np.random.Generator, row, sent_lookup: dict) -> dict:
    traj = row.health_trajectory
    sev = float(row.severity)
    nz = _noise_mult(row)                                 # observation-noise multiplier
    seasonal = 1 + 0.05 * np.sin(2 * np.pi * _MONTHS / 12 + rng.uniform(0, 2 * np.pi))

    op = _op_trend(rng, row)                              # real operations trend
    # --- declared GST turnover ---
    if row.demo in ("verma", "gupta"):
        gst = _TWIN_GST.copy()
    elif traj == "fraud_pattern":
        g = rng.uniform(*C.FRAUD["gst_growth_per_month"])
        gst = row.base_turnover * (1 + g) ** _MONTHS * seasonal
    else:
        gst = row.base_turnover * op * seasonal * (1 + rng.normal(0, 0.03 * nz, _M))
    gst = np.maximum(gst, row.base_turnover * 0.05)

    # --- bank credits (real receipts) ---
    if row.demo == "gupta" or traj == "fraud_pattern":
        # invoice inflation: actual receipts grow far slower than declared GST
        base_credit = row.base_turnover * row.bank_credit_share
        credits = base_credit * (1 + C.FRAUD["gst_growth_per_month"][0] * C.FRAUD["bank_credit_lag"]) ** _MONTHS
        credits = credits * seasonal * (1 + rng.normal(0, 0.04 * nz, _M))
    else:
        credits = gst * row.bank_credit_share * (1 + rng.normal(0, 0.05 * nz, _M))

    # contagion: cut Anchor #1 suppliers' inflows from event+lag
    if row.is_anchor_supplier and row.anchor_id == "ANCH1":
        ev = C.CONTAGION["event_month"] + int(row.anchor_lag)
        cut = C.CONTAGION["payment_cut"] * float(row.anchor_share)
        credits[ev:] = credits[ev:] * (1 - cut)

    credits = np.maximum(credits, row.base_turnover * 0.02)
    debits = credits * (1 + rng.normal(0.0, 0.06, _M))
    debits = np.clip(debits, credits * 0.75, credits * 1.15)

    # clean-majority noise: occasional lumpy (spike/dip) credit months
    if traj in ("stable", "growing"):
        lumpy = rng.random(_M) < C.CLEAN_NOISE["lumpy_prob"]
        factors = np.where(lumpy, rng.uniform(*C.CLEAN_NOISE["lumpy_range"], _M), 1.0)
        credits = credits * factors

    util = _utilisation(rng, row)

    # --- month-end balance via a liquidity buffer that thins under stress ---
    if traj in _SOFT_DISTRESS:
        s = int(row.traj_start)
        buf = np.array([0.16 if (m - s) < 0 else max(0.01, 0.16 - (m - s) * 0.02) for m in range(_M)])
    elif traj == "sudden_shock":
        s = int(row.traj_start)
        buf = np.array([0.16 if m < s else 0.02 for m in range(_M)])
    elif traj == "slow_decline":
        s = int(row.traj_start)
        buf = np.array([0.16 if m < s else max(0.06, 0.16 - (m - s) * 0.01) for m in range(_M)])
    elif traj == "growing":
        buf = np.full(_M, 0.22)
    elif traj == "fraud_pattern":
        buf = np.full(_M, 0.06)     # thin liquidity despite high declared turnover
    else:
        buf = np.full(_M, 0.17)
    balance = np.maximum(0.0, credits * buf * (1 + rng.normal(0, 0.1 * nz, _M)))

    # --- electricity / fuel / EPFO track REAL operations (op), not declared GST ---
    e_int, _tol, f_int, emp_pl = C.SECTOR_PROFILE[row.sector]
    turnover_lakh0 = row.base_turnover / 1e5
    if row.demo == "gupta":
        # fraud twin: electricity falls ~5% over the window while GST climbs
        elec_ch = 0.95 ** (1 / (_M - 1)) - 1
        elec_trend = (1 + elec_ch) ** _MONTHS
    else:
        elec_trend = op
    electricity = turnover_lakh0 * e_int * elec_trend * (1 + rng.normal(0, 0.06, _M))
    electricity = np.maximum(electricity, 0.0)
    fuel = turnover_lakh0 * f_int * op * (1 + rng.normal(0, 0.08, _M))
    fuel = np.maximum(fuel, 0.0)

    emp0 = max(2, int(round(turnover_lakh0 * emp_pl)))
    if row.demo == "gupta":
        emp_trend = np.ones(_M)            # headcount flat despite declared growth
    else:
        emp_trend = op
    employees = np.maximum(2, np.round(emp0 * emp_trend * (1 + rng.normal(0, 0.03, _M)))).astype(np.int64)
    # EPFO contribution timeliness worsens under stress - but stressed SURVIVORS (near-miss /
    # slow_decline) and even healthy firms delay too, so this is a noisy risk indicator, NOT a
    # distress-only label proxy (that would be quasi-leakage and inflate AUC).
    emp_delay = np.zeros(_M, np.int64)
    if traj in _SOFT_DISTRESS:
        s = int(row.traj_start)
        for m in range(_M):
            d = m - s
            if d >= 4:
                emp_delay[m] = min(45, int((d - 3) * 5 * sev))
    elif traj == "sudden_shock":
        s = int(row.traj_start)
        for m in range(_M):
            if m >= s:
                emp_delay[m] = min(45, (m - s + 1) * 12)
    elif traj == "slow_decline":
        s = int(row.traj_start)
        for m in range(_M):
            if m >= s:
                emp_delay[m] = min(24, (m - s) * 2)
    elif row.demo == "":   # occasional one-off EPFO slips in healthy/fraud firms (noise)
        oneoff = rng.random(_M) < 0.05
        emp_delay = (oneoff * rng.integers(3, 12, _M)).astype(np.int64)

    gst_delay = _gst_filing_delay(rng, row)

    # --- cheque bounces ---
    bounces_out = np.zeros(_M, np.int64)
    bounces_in = np.zeros(_M, np.int64)
    if traj in _SOFT_DISTRESS:
        s = int(row.traj_start)
        for m in range(_M):
            d = m - s
            if d >= C.DISTRESS["bounce_start"]:
                bounces_out[m] = int(rng.poisson((d - (C.DISTRESS["bounce_start"] - 1)) * C.DISTRESS["bounce_rate"] * sev))
            if d >= 5:
                bounces_in[m] = int(rng.poisson((d - 4) * 0.25))
    elif traj == "sudden_shock":
        s = int(row.traj_start)
        for m in range(_M):
            if m >= s:
                bounces_out[m] = int(rng.poisson((m - s + 1) * 0.5))
    elif traj == "slow_decline":
        s = int(row.traj_start)
        for m in range(_M):
            if m >= s and rng.random() < C.SLOW_DECLINE["occasional_bounce_prob"]:
                bounces_out[m] = 1
    else:
        bounces_in = (rng.random(_M) < 0.02).astype(np.int64)
        if traj in ("stable", "growing"):
            bounces_out = (rng.random(_M) < C.CLEAN_NOISE["oneoff_bounce_prob"]).astype(np.int64)

    # --- bureau events ---
    enquiries = np.zeros(_M, np.int64)
    new_loans = np.zeros(_M, np.int64)
    dpd_other = np.zeros(_M, np.int64)
    for m in range(_M):
        if traj in _SOFT_DISTRESS:
            d = m - int(row.traj_start)
            lam = 0.1 + max(0, d) * 0.06 if d >= 2 else 0.1
            enquiries[m] = int(rng.poisson(lam))
            if d >= 3:
                new_loans[m] = int(rng.poisson(0.1))
            if d >= 5:
                dpd_other[m] = min(120, (d - 4) * 20)
        elif traj == "sudden_shock":
            enquiries[m] = int(rng.poisson(0.4 if m >= int(row.traj_start) else 0.1))
            if m >= int(row.traj_start) + 1:
                dpd_other[m] = min(120, (m - int(row.traj_start)) * 25)
        elif traj == "slow_decline":
            enquiries[m] = int(rng.poisson(0.12))
            if m >= int(row.traj_start) and rng.random() < 0.15:
                dpd_other[m] = 30
        elif traj == "fraud_pattern":
            enquiries[m] = int(rng.poisson(0.25))
            new_loans[m] = int(rng.poisson(0.12))
        elif traj == "growing":
            enquiries[m] = int(rng.poisson(0.15))
        else:  # stable
            enquiries[m] = int(rng.poisson(0.1))
            if row.demo == "" and rng.random() < 0.02:   # rare bureau DPD even in healthy firms
                dpd_other[m] = 30

    status, emi_late, dpd = _repayment(row)

    # --- officer notes (roughly quarterly) ---
    notes = [""] * _M
    note_phase = int(row.base_turnover) % 3
    for m in range(_M):
        if m % 3 != note_phase:
            continue
        if traj == "growing":
            key = "growing"
        elif traj == "fraud_pattern":
            key = "fraud"
        elif traj in _SOFT_DISTRESS:
            d = m - int(row.traj_start)
            key = "distress" if d >= 5 else ("warning" if d >= 0 else "healthy")
        elif traj == "sudden_shock":
            key = "shock" if m >= int(row.traj_start) else "healthy"
        elif traj == "slow_decline":
            key = "warning" if m >= int(row.traj_start) else "healthy"
        else:
            key = "healthy"
        pool = _NOTES[key]
        notes[m] = pool[int(rng.integers(len(pool)))]

    # --- demo overrides to pin scripted beats ---
    if row.demo == "sharma":
        bounces_out[C.DEMO_MONTH] = max(1, int(bounces_out[C.DEMO_MONTH]))  # first cheque return at month 23
        notes[C.DEMO_MONTH] = "Cheque presented late; promoter evasive about receivables."

    return dict(
        credits=credits, debits=debits, month_end_balance=balance,
        cheque_bounces_inward=bounces_in, cheque_bounces_outward=bounces_out,
        limit_utilisation=util, gst_turnover=gst, gst_filing_delay_days=gst_delay,
        electricity_units=electricity, fuel_spend=fuel,
        epfo_employee_count=employees, epfo_contribution_delay_days=emp_delay,
        bureau_enquiries=enquiries, bureau_new_loans=new_loans, bureau_dpd_other=dpd_other,
        repayment_status=status, emi_days_late=emi_late, dpd=dpd,
        sector_sentiment=sent_lookup[row.sector],
        officer_note=notes,
    )


def build_msme_monthly(rng: np.random.Generator, borrowers: pd.DataFrame):
    """Return (msme_monthly_df, sector_sentiment_df)."""
    sent_df, sent_lookup = build_sector_sentiment(rng)

    months_avail = borrowers["months_available"].to_numpy()
    total = int(months_avail.sum())

    # preallocate
    float_cols = ["credits", "debits", "month_end_balance", "limit_utilisation",
                  "gst_turnover", "electricity_units", "fuel_spend", "sector_sentiment"]
    int_cols = ["cheque_bounces_inward", "cheque_bounces_outward", "gst_filing_delay_days",
                "epfo_employee_count", "epfo_contribution_delay_days", "bureau_enquiries",
                "bureau_new_loans", "bureau_dpd_other", "emi_days_late", "dpd"]
    buf = {c: np.empty(total, np.float64) for c in float_cols}
    buf.update({c: np.empty(total, np.int64) for c in int_cols})
    month_index = np.empty(total, np.int64)
    borrower_id = np.empty(total, dtype=object)
    month_date = np.empty(total, dtype=object)
    repayment_status = np.empty(total, dtype=object)
    officer_note = np.empty(total, dtype=object)

    children = rng.spawn(len(borrowers))
    off = 0
    for i, (_, row) in enumerate(borrowers.iterrows()):
        L = int(row.months_available)
        start = _M - L
        s = _gen_borrower(children[i], row, sent_lookup)
        sl = slice(off, off + L)
        for c in float_cols:
            buf[c][sl] = s[c][start:_M]
        for c in int_cols:
            buf[c][sl] = np.asarray(s[c])[start:_M]
        month_index[sl] = _MONTHS[start:_M]
        borrower_id[sl] = row.borrower_id
        month_date[sl] = _MONTH_DATES[start:_M]
        repayment_status[sl] = s["repayment_status"][start:_M]
        officer_note[sl] = s["officer_note"][start:_M]
        off += L

    data = {"borrower_id": borrower_id, "month_index": month_index, "month_date": month_date}
    for c in float_cols:
        data[c] = np.round(buf[c], 2) if c not in ("limit_utilisation", "sector_sentiment") else np.round(buf[c], 4)
    for c in int_cols:
        data[c] = buf[c]
    data["repayment_status"] = repayment_status
    data["officer_note"] = officer_note
    df = pd.DataFrame(data)
    # stable column order
    cols = ["borrower_id", "month_index", "month_date", "credits", "debits", "month_end_balance",
            "cheque_bounces_inward", "cheque_bounces_outward", "limit_utilisation",
            "gst_turnover", "gst_filing_delay_days", "electricity_units", "fuel_spend",
            "epfo_employee_count", "epfo_contribution_delay_days", "bureau_enquiries",
            "bureau_new_loans", "bureau_dpd_other", "repayment_status", "emi_days_late",
            "dpd", "sector_sentiment", "officer_note"]
    return df[cols], sent_df
