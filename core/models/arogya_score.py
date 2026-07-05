"""AROGYA health score (BUILD_SPEC §4.2/§6): five pillars → unified 0–1000 → GO/REFER/NO-GO.

Plus a data-coverage CONFIDENCE (0–1). A thin file gets low confidence and is REFERred - never an
automatic NO-GO purely for missing data (§6.3, enforced here).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

AROGYA_PILLARS = ["Turnover Pulse", "Cash-flow Discipline", "Compliance Hygiene",
                  "Operational Intensity", "Promoter Profile"]
PILLAR_WEIGHTS = {"Turnover Pulse": 0.24, "Cash-flow Discipline": 0.24, "Compliance Hygiene": 0.20,
                  "Operational Intensity": 0.16, "Promoter Profile": 0.16}
GO_CUTOFF, REFER_CUTOFF = 760, 480
CONFIDENCE_REFER_FLOOR = 0.65     # below this a thin file is REFERred (never auto GO or NO-GO)

_QUAL_BONUS = {"Below SSC": 0, "SSC": 6, "HSC": 10, "Graduate": 16, "Post-graduate": 20, "Professional": 24}


def _clip100(x):
    return float(np.clip(x, 0, 100))


def _growth(a: np.ndarray) -> float:
    if len(a) < 4:
        return 0.0
    h = max(3, len(a) // 2)
    first, last = a[:h].mean(), a[-h:].mean()
    return float(last / (first + 1e-9) - 1)


def score_arogya(borrower_row, monthly: pd.DataFrame, config: dict | None = None) -> dict:
    """Return pillars, unified score, bucket and confidence for one applicant (origination snapshot)."""
    cfg = config or {}
    m = monthly.sort_values("month_index")
    n = len(m)
    turnover = m.gst_turnover.to_numpy()
    credits = m.credits.to_numpy()
    bal = m.month_end_balance.to_numpy()
    elec = m.electricity_units.to_numpy()

    # 1. Turnover Pulse - growth + stability
    t_growth = np.clip(_growth(turnover), -0.4, 0.4)
    t_cv = turnover.std() / (turnover.mean() + 1)
    turnover_pulse = _clip100(52 + 70 * t_growth - 22 * t_cv)

    # 2. Cash-flow Discipline - retained balance, low bounces, stable credits
    retained = np.mean(bal / (credits + 1))
    bounces = float(m.cheque_bounces_outward.sum() + m.cheque_bounces_inward.sum())
    c_cv = credits.std() / (credits.mean() + 1)
    cashflow = _clip100(30 + 150 * retained - 7 * bounces - 16 * c_cv)

    # 3. Compliance Hygiene - GST filing timeliness + repayment conduct
    gst_delay = m.gst_filing_delay_days.mean()
    delayed = float((m.repayment_status == "delayed").sum())
    missed = float((m.repayment_status == "missed").sum())
    compliance = _clip100(82 - 2.4 * gst_delay - 9 * delayed - 22 * missed)

    # 4. Operational Intensity - do real operations (electricity) move with declared turnover?
    e_growth = _growth(elec)
    divergence = abs(t_growth - e_growth)
    operational = _clip100(80 - 70 * divergence)

    # 5. Promoter Profile - vintage, experience, qualification
    promoter = _clip100(20 + 1.8 * float(borrower_row.vintage_years)
                        + 1.1 * float(borrower_row.promoter_experience_years)
                        + _QUAL_BONUS.get(str(borrower_row.promoter_qualification), 8))

    pillars = {"Turnover Pulse": round(turnover_pulse, 1), "Cash-flow Discipline": round(cashflow, 1),
               "Compliance Hygiene": round(compliance, 1), "Operational Intensity": round(operational, 1),
               "Promoter Profile": round(promoter, 1)}
    unified = 10 * sum(PILLAR_WEIGHTS[k] * v for k, v in pillars.items())
    unified = int(round(unified))

    # confidence from data coverage (months available + sources present)
    coverage = min(1.0, n / 24)
    months_available = int(getattr(borrower_row, "months_available", n))
    coverage = min(coverage, months_available / 24)
    confidence = float(np.clip(0.50 + 0.50 * coverage, 0.30, 0.97))

    bucket = "GO" if unified >= GO_CUTOFF else ("REFER" if unified >= REFER_CUTOFF else "NO-GO")
    # §6.3: a thin file is REFERred for corroboration - never an automatic GO or NO-GO on coverage
    thin_file = confidence < CONFIDENCE_REFER_FLOOR
    if thin_file and bucket in ("GO", "NO-GO"):
        bucket = "REFER"

    return dict(
        pillars=pillars, unified_score=unified, bucket=bucket,
        confidence=round(confidence, 3), coverage_months=n,
        thin_file=thin_file,
        divergence=round(divergence, 3),
    )
