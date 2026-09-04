"""Retail features for DISHA - capacity (from the monthly series) and intent (from engagement).

Capacity reconstructs true disposable income from behavioural cash-flow; engagement turns raw
sessions into an intent signal. Both are point-in-time over the retail window.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RETAIL_FEATURES = [
    "income_mean", "income_cv", "income_credit_count_mean",
    "obligations_mean", "essential_mean", "discretionary_mean",
    "disposable_mean", "disposable_ratio",
    "discipline_retained", "day3_ratio", "sip_mean",
    "multi_account_flag", "existing_loans",
]

ENGAGEMENT_FEATURES = [
    "n_sessions", "n_evening", "evening_ratio", "depth_mean",
    "calc_uses", "calc_amount_cv", "deepest_stage", "distinct_pages",
]

_STAGE_ORDER = {"landing": 0, "eligibility": 1, "documents": 2, "otp": 3, "submitted": 4}


def retail_capacity_features(monthly: pd.DataFrame, customer_row) -> dict:
    """Reconstruct income + disposable income + discipline from the monthly cash-flow series.

    `monthly` is one customer's retail_monthly rows; `customer_row` carries bureau flags."""
    inc = monthly.income_credits.to_numpy()
    oblig = (monthly.existing_emi + monthly.rent).to_numpy()
    ess = monthly.essential_spend.to_numpy()
    disc = monthly.discretionary_spend.to_numpy()
    disposable = inc - oblig - ess
    income_mean = float(inc.mean())
    return {
        "income_mean": income_mean,
        "income_cv": float(inc.std() / (income_mean + 1.0)),
        "income_credit_count_mean": float(monthly.income_credit_count.mean()),
        "obligations_mean": float(oblig.mean()),
        "essential_mean": float(ess.mean()),
        "discretionary_mean": float(disc.mean()),
        "disposable_mean": float(disposable.mean()),
        "disposable_ratio": float(disposable.mean() / (income_mean + 1.0)),
        "discipline_retained": float(monthly.retained_balance_ratio.mean()),
        "day3_ratio": float(monthly.day3_balance_ratio.mean()),
        "sip_mean": float(monthly.sip_debits.mean()),
        "multi_account_flag": float(bool(customer_row.bureau_other_bank_flag)),
        "existing_loans": float(customer_row.bureau_existing_loans),
    }


def engagement_features(events: pd.DataFrame) -> dict:
    """Turn a customer's digital sessions into intent features."""
    if events is None or len(events) == 0:
        return {k: 0.0 for k in ENGAGEMENT_FEATURES}
    n = len(events)
    evening = int(events.is_evening.sum())
    calc = events[events.emi_calc_used]
    calc_amounts = calc.calc_amount.to_numpy()
    calc_cv = float(calc_amounts.std() / (calc_amounts.mean() + 1.0)) if len(calc_amounts) >= 2 else 0.0
    deepest = max(_STAGE_ORDER.get(s, 0) for s in events.dropoff_stage.tolist())
    return {
        "n_sessions": float(n),
        "n_evening": float(evening),
        "evening_ratio": float(evening / n),
        "depth_mean": float(events.page_depth.mean()),
        "calc_uses": float(len(calc)),
        "calc_amount_cv": calc_cv,          # low CV = consistent target amount = serious
        "deepest_stage": float(deepest),
        "distinct_pages": float(events.page.nunique()),
    }
