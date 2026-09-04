"""§3.5 Contagion: Anchor #1's 14 suppliers show measurable inflow decline after the
month-16 payment slowdown, and ≥5 of them enter distress trajectories afterwards."""

from __future__ import annotations

from core.datagen import config as C


def _anchor1_suppliers(borrowers):
    return borrowers[borrowers.anchor_id == "ANCH1"]


def test_anchor1_has_14_suppliers(borrowers):
    assert len(_anchor1_suppliers(borrowers)) == C.CONTAGION["anchor1_n_suppliers"] == 14


def test_supplier_inflows_decline_after_event(borrowers, msme_monthly):
    ids = _anchor1_suppliers(borrowers).borrower_id.tolist()
    ev = C.CONTAGION["event_month"]
    sub = msme_monthly[msme_monthly.borrower_id.isin(ids)]
    pre = sub[(sub.month_index >= ev - 6) & (sub.month_index < ev)].groupby("borrower_id").credits.mean()
    post = sub[(sub.month_index >= ev + 2) & (sub.month_index <= C.DEMO_MONTH)].groupby("borrower_id").credits.mean()
    ratio = (post / pre).dropna()

    # essentially all suppliers lose inflows; the fleet average drops clearly
    declined = int((ratio < 0.95).sum())
    assert declined >= 12, f"only {declined}/14 suppliers show inflow decline"
    assert ratio.mean() < 0.90, f"mean post/pre inflow ratio {ratio.mean():.3f} not a clear decline"


def test_five_suppliers_enter_distress(borrowers):
    a1 = _anchor1_suppliers(borrowers)
    induced = a1[a1.contagion_induced]
    assert len(induced) >= C.CONTAGION["n_induced_distress"] >= 5
    assert (induced.health_trajectory == "distress_at_month_k").all()
    # onset is *after* the event (2–4 month lag)
    assert (induced.traj_start > C.CONTAGION["event_month"]).all()


def test_induced_suppliers_repayment_still_clean_at_demo(borrowers, msme_monthly):
    """Their runway is shortened by contagion while their own repayment record is still clean
    (BUILD_SPEC §9.1) - i.e. no 90+ DPD at the demo month."""
    induced = borrowers[(borrowers.anchor_id == "ANCH1") & (borrowers.contagion_induced)]
    demo_rows = msme_monthly[(msme_monthly.borrower_id.isin(induced.borrower_id)) &
                             (msme_monthly.month_index == C.DEMO_MONTH)]
    assert (demo_rows.dpd == 0).all()
    # default lies beyond the observation window (still-performing at demo)
    assert (induced.default_month > C.DEMO_MONTH).all()
