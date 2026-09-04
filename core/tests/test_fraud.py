"""§3.5 Fraud: fraud_pattern firms violate GST↔electricity consistency (declared turnover
grows while electricity stays flat/falls); clean firms don't. The Verification Triangle's target."""

from __future__ import annotations

import numpy as np

from core.datagen import config as C

# Divergence threshold: turnover growth outpacing electricity growth by >25 pts is a violation.
VIOLATION = 0.25


def _gst_elec_divergence(g):
    """(GST growth) − (electricity growth), last-6 vs first-6 month means. None if thin file."""
    g = g.sort_values("month_index")
    if len(g) < C.N_MONTHS_MSME:            # only assess full-history firms (thin files → low confidence, not fraud)
        return None
    gt = g.gst_turnover.to_numpy()
    el = g.electricity_units.to_numpy()
    gst_growth = gt[-6:].mean() / gt[:6].mean() - 1
    elec_growth = el[-6:].mean() / el[:6].mean() - 1
    return float(gst_growth - elec_growth)


def _divergences(borrowers, msme_monthly, trajectory):
    ids = borrowers[borrowers.health_trajectory == trajectory].borrower_id
    out = []
    for bid, g in msme_monthly[msme_monthly.borrower_id.isin(ids)].groupby("borrower_id"):
        d = _gst_elec_divergence(g)
        if d is not None:
            out.append(d)
    return np.array(out)


def test_fraud_firms_violate_consistency(borrowers, msme_monthly):
    fraud = _divergences(borrowers, msme_monthly, "fraud_pattern")
    assert len(fraud) > 30
    frac_violating = (fraud > VIOLATION).mean()
    assert frac_violating >= 0.90, f"only {frac_violating:.2%} of fraud firms violate the triangle"


def test_clean_firms_do_not_violate(borrowers, msme_monthly):
    for traj in ("stable", "growing"):
        clean = _divergences(borrowers, msme_monthly, traj)
        assert len(clean) > 30
        frac_violating = (clean > VIOLATION).mean()
        assert frac_violating <= 0.05, f"{frac_violating:.2%} of {traj} firms falsely flagged"


def test_distress_firms_are_not_flagged_as_fraud(borrowers, msme_monthly):
    """Genuine distress = GST and electricity both fall together → NOT a triangle violation."""
    distress = _divergences(borrowers, msme_monthly, "distress_at_month_k")
    assert len(distress) > 20
    assert (distress > VIOLATION).mean() <= 0.10


def test_twins_gst_identical_but_triangle_breaks_only_for_gupta(borrowers, msme_monthly):
    verma = borrowers[borrowers.demo == "verma"].iloc[0].borrower_id
    gupta = borrowers[borrowers.demo == "gupta"].iloc[0].borrower_id
    vg = msme_monthly.query("borrower_id == @verma").sort_values("month_index")
    gg = msme_monthly.query("borrower_id == @gupta").sort_values("month_index")

    # identical declared GST turnover (BUILD_SPEC §9.2)
    assert np.allclose(vg.gst_turnover.to_numpy(), gg.gst_turnover.to_numpy())

    assert _gst_elec_divergence(gg) > VIOLATION      # fraud twin breaks the triangle
    assert _gst_elec_divergence(vg) < VIOLATION      # clean twin closes it
