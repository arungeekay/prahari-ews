"""Verification Triangle (BUILD_SPEC §4.2/§6.2): three pairwise consistency checks that catch
invoice inflation. Declared GST turnover is cross-checked against three independent corroborants:
electricity (real production), bank/AA inflows (real receipts) and EPFO headcount (real labour).

A firm whose declared turnover races ahead of ALL its real-operations signals is the fraud target.
Each side returns consistency 0–100, a verdict, and a hypothesis string when broken.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

CONSISTENT_CUTOFF = 65
_BAND = 0.12          # tolerated growth gap before a side is flagged (base band)


def _energy_band(sector: str) -> float:
    """Sector-calibrated tolerance for the GST↔electricity side (BUILD_SPEC §4.2).

    Energy-per-₹ varies more month-to-month in low-intensity sectors (trading, services) than in
    manufacturing/food, so the tolerated growth gap widens with the sector's energy-band
    tolerance from SECTOR_PROFILE. Manufacturing ≈ 0.135, trading/services ≈ 0.145."""
    from ..datagen.config import SECTOR_PROFILE
    tol = SECTOR_PROFILE.get(sector, (0, 0.40, 0, 0))[1]
    return 0.10 + 0.10 * tol


def _growth(a: np.ndarray) -> float:
    if len(a) < 4:
        return 0.0
    h = min(6, len(a) // 2)          # early-6 vs latest-6 months (sharper than half-window halves)
    return float(a[-h:].mean() / (a[:h].mean() + 1e-9) - 1)


def _side(name: str, corroborant: str, gst_g: float, other_g: float, hypothesis_kind: str,
          band: float = _BAND) -> dict:
    divergence = gst_g - other_g               # positive = declared turnover outpaces reality
    consistency = float(np.clip(100 - 130 * max(0.0, divergence - band), 0, 100))
    consistent = consistency >= CONSISTENT_CUTOFF
    hyp = None
    if not consistent:
        hyp = (f"Declared GST turnover grew {gst_g:+.0%} while {corroborant} moved {other_g:+.0%} "
               f"- a {abs(divergence):.0%} gap, consistent with {hypothesis_kind}.")
    return dict(pair=name, corroborant=corroborant, consistency=round(consistency, 1),
                verdict="consistent" if consistent else "anomaly",
                gst_growth=round(gst_g, 3), corroborant_growth=round(other_g, 3),
                divergence=round(divergence, 3), hypothesis=hyp)


def verification_triangle(borrower_row, monthly: pd.DataFrame) -> dict:
    m = monthly.sort_values("month_index")
    gst_g = _growth(m.gst_turnover.to_numpy())
    elec_g = _growth(m.electricity_units.to_numpy())
    inflow_g = _growth(m.credits.to_numpy())
    emp_g = _growth(m.epfo_employee_count.to_numpy(dtype=float))

    sides = [
        _side("GST ↔ Electricity", "electricity consumption", gst_g, elec_g, "invoice inflation",
              band=_energy_band(str(borrower_row.sector))),
        _side("GST ↔ Bank/AA inflows", "actual bank receipts", gst_g, inflow_g, "circular / inflated billing"),
        _side("GST ↔ EPFO headcount", "employee headcount", gst_g, emp_g, "shell-like operations"),
    ]
    broken = [s for s in sides if s["verdict"] == "anomaly"]
    overall = "broken" if broken else "closed"
    return dict(
        sides=sides,
        overall=overall,
        n_broken=len(broken),
        summary=("all three sides consistent" if not broken
                 else "; ".join(s["pair"] + " broken" for s in broken)),
    )
