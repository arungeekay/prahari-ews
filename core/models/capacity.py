"""DISHA capacity model (BUILD_SPEC §4.2): reconstruct true repayment capacity from behaviour.

Classifies income type from credit patterns, reconstructs monthly income (incl. volatile gig
income), detects obligations, computes true disposable income = income − obligations − essential
spend, a discipline score from the retained-balance rhythm, and a serviceable EMI (≤ 50% of
disposable). Rule-based and transparent - every number is auditable for RM review.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..features.retail import retail_capacity_features


def _income_type(count_mean: float, cv: float) -> str:
    if count_mean >= 15:
        return "gig_worker"           # many small volatile UPI credits
    if cv >= 0.22:
        return "self_employed"        # few, lumpy business credits
    return "salaried"                 # regular, low-volatility credit


def capacity_profile(monthly: pd.DataFrame, customer_row) -> dict:
    f = retail_capacity_features(monthly.sort_values("month_index"), customer_row)
    income = f["income_mean"]
    disposable = max(0.0, f["disposable_mean"])
    income_type = _income_type(f["income_credit_count_mean"], f["income_cv"])

    # serviceable EMI: ≤ 50% of disposable, trimmed for volatile (gig) income
    haircut = 0.85 if income_type == "gig_worker" else 1.0
    serviceable_emi = 0.50 * disposable * haircut

    disposable_ratio = f["disposable_ratio"]
    band = "HIGH" if disposable_ratio >= 0.30 else ("MEDIUM" if disposable_ratio >= 0.15 else "LOW")
    discipline_score = int(round(100 * f["discipline_retained"]))

    return dict(
        income_type=income_type,
        reconstructed_income=int(round(income)),
        income_volatility=round(f["income_cv"], 3),
        income_credit_count=round(f["income_credit_count_mean"], 1),
        obligations=int(round(f["obligations_mean"])),
        essential_spend=int(round(f["essential_mean"])),
        disposable_income=int(round(disposable)),
        disposable_ratio=round(disposable_ratio, 3),
        capacity_band=band,
        discipline_score=discipline_score,
        serviceable_emi=int(round(serviceable_emi)),
        multi_account_flag=bool(f["multi_account_flag"]),
        existing_loans=int(f["existing_loans"]),
    )
