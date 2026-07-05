"""Retail behavioural series (12 months) + digital-engagement events — for DISHA.

Income shapes by occupation (BUILD_SPEC §3.4): salaried = fixed monthly credit; gig = 20–40
volatile UPI credits/month; self-employed = lumpy business credits. Spending discipline shows
as a day-of-month balance curve (savers retain, day-3 exhausters don't). Digital engagement is
generated *causally from latent intent* so an intent model is honestly learnable: serious →
repeat evening sessions + EMI-calculator use + deeper funnel; browsing → shallow one-offs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .util import month_index_to_date

_R0 = C.RETAIL_START_INDEX               # 12 → first retail month
_RMONTHS = np.arange(_R0, C.N_MONTHS_MSME)   # absolute month indices 12..23
_NR = len(_RMONTHS)                        # 12
_RDATES = [month_index_to_date(i).isoformat() for i in _RMONTHS]


def _balance_curve(disc: float, rng) -> tuple[float, float, float, float]:
    """4-point day-of-month balance-to-income ratio (day 3/10/20/30) from a discipline score."""
    d03 = np.clip(0.12 + 0.75 * disc + rng.normal(0, 0.03), 0.02, 0.98)
    d10 = np.clip(0.08 + 0.62 * disc + rng.normal(0, 0.03), 0.02, 0.95)
    d20 = np.clip(0.05 + 0.52 * disc + rng.normal(0, 0.03), 0.01, 0.9)
    d30 = np.clip(0.04 + 0.40 * disc + rng.normal(0, 0.03), 0.01, 0.85)
    return float(d03), float(d10), float(d20), float(d30)


def _income_month(rng, occ, base):
    if occ == "salaried":
        return base * (1 + rng.normal(0, 0.01)), int(rng.integers(1, 3))
    if occ == "gig_worker":
        return base * (1 + rng.normal(0, 0.16)), int(rng.integers(20, 43))
    # self_employed: lumpy
    return base * (1 + rng.normal(0, 0.28)), int(rng.integers(2, 7))


def _gen_customer_monthly(rng, cust) -> dict:
    occ, base = cust.occupation_type, cust.base_income
    disc = cust.discipline_score_latent

    # obligations (recurring, detectable)
    has_emi = cust.bureau_existing_loans > 0
    emi = base * rng.uniform(0.08, 0.20) if has_emi else 0.0
    is_renter = rng.random() < 0.55
    rent = base * rng.uniform(0.15, 0.28) if is_renter else 0.0
    sip = base * rng.uniform(0.05, 0.15) if (disc > 0.55 and rng.random() < 0.7) else 0.0

    # demo overrides for exact scripted numbers
    if cust.demo == "ravi":
        emi, rent, sip = 3_000.0, 6_000.0, 0.0
    elif cust.demo in ("discipline_saver", "discipline_spender"):
        emi = base * 0.12
        rent = base * 0.20
        sip = base * 0.12 if cust.demo == "discipline_saver" else 0.0

    income = np.empty(_NR)
    icount = np.empty(_NR, np.int64)
    for i in range(_NR):
        inc, cnt = _income_month(rng, occ, base)
        income[i] = max(base * 0.2, inc)
        icount[i] = cnt
    if cust.demo == "ravi":
        icount = np.clip(icount, 30, 45)

    obligations = emi + rent
    d03, d10, d20, d30 = _balance_curve(disc, rng)
    if cust.demo == "discipline_saver":
        d03, d10, d20, d30 = 0.82, 0.68, 0.52, 0.38     # holds 30%+ all month
    elif cust.demo == "discipline_spender":
        d03, d10, d20, d30 = 0.08, 0.05, 0.04, 0.04     # exhausts by day 3

    retained = d30 * income
    savings = np.full(_NR, sip)
    spendable = np.maximum(0.0, income - obligations - savings - retained)
    # essential vs discretionary
    ess_frac = np.clip(0.60 - 0.15 * disc, 0.35, 0.70)
    if cust.demo == "ravi":
        # tune so income − obligations − essential ≈ ₹14k disposable
        essential = np.full(_NR, 8_000.0)
    else:
        essential = spendable * ess_frac
    bills = spendable * rng.uniform(0.08, 0.14)
    discretionary = np.maximum(0.0, spendable - essential - bills)
    spend_total = essential + bills + discretionary
    month_end_balance = retained
    merchant_div = np.maximum(1, np.round(
        (discretionary / (base + 1)) * 40 + (icount * 0.3) + rng.normal(0, 2, _NR))).astype(np.int64)

    return dict(
        income_credits=income, income_credit_count=icount,
        spend_total=spend_total, essential_spend=essential, discretionary_spend=discretionary,
        bills_spend=bills, upi_merchant_diversity=merchant_div,
        existing_emi=np.full(_NR, emi), rent=np.full(_NR, rent), sip_debits=savings,
        month_end_balance=month_end_balance,
        bal_d03=np.full(_NR, d03), bal_d10=np.full(_NR, d10),
        bal_d20=np.full(_NR, d20), bal_d30=np.full(_NR, d30),
    )


def _gen_engagement(rng, cust, event_counter: list) -> list:
    """Digital sessions causal from latent intent (BUILD_SPEC §3.4)."""
    intent = cust.loan_intent
    E = C.ENGAGEMENT
    if intent == "serious":
        n = int(rng.integers(*E["serious_sessions"])); evening_p = E["serious_evening_prob"]
        depth_rng = E["serious_depth"]; calc_p = E["calc_use_prob_serious"]
    elif intent == "browsing":
        n = int(rng.integers(*E["browsing_sessions"])); evening_p = E["browsing_evening_prob"]
        depth_rng = E["browsing_depth"]; calc_p = E["calc_use_prob_browsing"]
    else:
        n = int(rng.integers(*E["none_sessions"])); evening_p = 0.2
        depth_rng = (1, 2); calc_p = 0.05

    if cust.demo == "ravi":
        n = max(n, 6)

    # serious users have a consistent target product + amount; browsers roam
    target_page = cust.clicked_page or E["loan_pages"][int(rng.integers(len(E["loan_pages"])))]
    if cust.demo == "ravi":
        target_page = "personal_loan"
    target_amount = float(round(cust.base_income * rng.uniform(6, 14) / 1000) * 1000)

    rows = []
    for s in range(n):
        # serious sessions cluster in the recent months (repeat visits)
        if intent == "serious":
            month = int(rng.choice(_RMONTHS[-3:]))
        else:
            month = int(rng.choice(_RMONTHS))
        is_evening = bool(rng.random() < evening_p)
        hour = int(rng.integers(18, 23)) if is_evening else int(rng.integers(9, 18))
        page = target_page if (intent == "serious" or rng.random() < 0.4) \
            else E["loan_pages"][int(rng.integers(len(E["loan_pages"])))]
        depth = int(rng.integers(depth_rng[0], depth_rng[1] + 1))
        calc = bool(rng.random() < calc_p)
        calc_amount = float(target_amount * (1 + rng.normal(0, 0.02))) if calc else 0.0
        # serious users progress deeper into the funnel
        if intent == "serious":
            stage = E["dropoff_stages"][min(len(E["dropoff_stages"]) - 1, 1 + int(rng.integers(0, 3)))]
        elif intent == "browsing":
            stage = E["dropoff_stages"][int(rng.integers(0, 2))]
        else:
            stage = E["dropoff_stages"][0]
        event_counter[0] += 1
        rows.append(dict(
            customer_id=cust.customer_id, event_id=f"EVT{event_counter[0]:07d}",
            session_id=f"{cust.customer_id}-S{s+1}", month_index=month,
            month_date=month_index_to_date(month).isoformat(),
            day_of_month=int(rng.integers(1, 29)), hour=hour, is_evening=is_evening,
            page=page, page_depth=depth, emi_calc_used=calc,
            calc_amount=round(calc_amount, 2), dropoff_stage=stage,
        ))
    return rows


def build_retail(rng: np.random.Generator, customers: pd.DataFrame):
    """Return (retail_monthly_df, engagement_df)."""
    children = rng.spawn(len(customers))

    # preallocate monthly
    float_cols = ["income_credits", "spend_total", "essential_spend", "discretionary_spend",
                  "bills_spend", "existing_emi", "rent", "sip_debits", "month_end_balance",
                  "bal_d03", "bal_d10", "bal_d20", "bal_d30"]
    int_cols = ["income_credit_count", "upi_merchant_diversity"]
    total = len(customers) * _NR
    buf = {c: np.empty(total, np.float64) for c in float_cols}
    buf.update({c: np.empty(total, np.int64) for c in int_cols})
    customer_id = np.empty(total, dtype=object)
    month_index = np.empty(total, np.int64)
    month_date = np.empty(total, dtype=object)

    engagement_rows = []
    event_counter = [0]
    off = 0
    for i, (_, cust) in enumerate(customers.iterrows()):
        child = children[i]
        s = _gen_customer_monthly(child, cust)
        sl = slice(off, off + _NR)
        for c in float_cols:
            buf[c][sl] = s[c]
        for c in int_cols:
            buf[c][sl] = s[c]
        customer_id[sl] = cust.customer_id
        month_index[sl] = _RMONTHS
        month_date[sl] = _RDATES
        off += _NR
        engagement_rows.extend(_gen_engagement(child, cust, event_counter))

    data = {"customer_id": customer_id, "month_index": month_index, "month_date": month_date}
    for c in float_cols:
        data[c] = np.round(buf[c], 2) if not c.startswith("bal_") else np.round(buf[c], 4)
    data["retained_balance_ratio"] = data["bal_d30"]
    data["day3_balance_ratio"] = data["bal_d03"]
    for c in int_cols:
        data[c] = buf[c]
    monthly = pd.DataFrame(data)
    mcols = ["customer_id", "month_index", "month_date", "income_credits", "income_credit_count",
             "spend_total", "essential_spend", "discretionary_spend", "bills_spend",
             "upi_merchant_diversity", "existing_emi", "rent", "sip_debits", "month_end_balance",
             "bal_d03", "bal_d10", "bal_d20", "bal_d30", "retained_balance_ratio", "day3_balance_ratio"]
    monthly = monthly[mcols]

    engagement = pd.DataFrame(engagement_rows) if engagement_rows else pd.DataFrame(
        columns=["customer_id", "event_id", "session_id", "month_index", "month_date",
                 "day_of_month", "hour", "is_evening", "page", "page_depth",
                 "emi_calc_used", "calc_amount", "dropoff_stage"])
    return monthly, engagement
