"""The diffusion model itself (not the generated data): exact arithmetic on a hand-built graph,
no double counting, zero-stress anchors change nothing, and anchor stress is MEASURED from data."""

from __future__ import annotations

import pandas as pd
import pytest

from core.models.contagion import ContagionGraph, measure_anchor_stress


def _frames(anchor_stress_measure):
    anchors = pd.DataFrame([dict(anchor_id="A1", name="Anchor One", sector="manufacturing", n_suppliers=2)])
    borrowers = pd.DataFrame([
        dict(borrower_id="S1", name="Supplier One", sector="trading", anchor_id="A1", anchor_share=0.5, is_anchor_supplier=True),
        dict(borrower_id="S2", name="Supplier Two", sector="trading", anchor_id="A1", anchor_share=0.25, is_anchor_supplier=True),
    ])
    edges = pd.DataFrame([
        dict(payer="A1", payer_name="Anchor One", payee="S1", payee_name="Supplier One", avg_monthly_amount=100.0, regularity=0.9, inflow_share=0.5),
        dict(payer="A1", payer_name="Anchor One", payee="S2", payee_name="Supplier Two", avg_monthly_amount=50.0, regularity=0.8, inflow_share=0.25),
    ])
    mm = pd.DataFrame(columns=["borrower_id", "month_index", "anchor_inflow"])
    return dict(anchors=anchors, borrowers=borrowers, edges=edges, msme_monthly=mm), anchor_stress_measure


def test_exact_single_hop_arithmetic_no_double_count():
    frames, meas = _frames({"A1": dict(stress=0.8, inflow_decline=0.4, n_suppliers_measured=2)})
    cg = ContagionGraph(frames, {"S1": 0.02, "S2": 0.10}, anchor_stress=meas)
    # s_S1 = 0.02 + 0.9 * 0.8 * 0.5 = 0.38 ; s_S2 = 0.10 + 0.8 * 0.8 * 0.25 = 0.26
    assert cg.adjusted_pd("S1") == pytest.approx(0.38, abs=1e-6)
    assert cg.adjusted_pd("S2") == pytest.approx(0.26, abs=1e-6)
    r = cg.node_result("S1")
    assert r["contributions"][0]["added_stress"] == pytest.approx(0.36, abs=1e-4)   # the applied delta, not an approximation
    assert r["why"] and "40%" in r["why"]


def test_zero_stress_anchor_changes_nothing():
    frames, meas = _frames({"A1": dict(stress=0.0, inflow_decline=0.0, n_suppliers_measured=2)})
    cg = ContagionGraph(frames, {"S1": 0.02, "S2": 0.10}, anchor_stress=meas)
    assert cg.adjusted_pd("S1") == pytest.approx(0.02)
    assert cg.node_result("S2")["runway_delta"] == 0.0


def test_stress_is_capped_and_iterations_idempotent():
    frames, meas = _frames({"A1": dict(stress=1.0, inflow_decline=0.9, n_suppliers_measured=2)})
    cg = ContagionGraph(frames, {"S1": 0.9, "S2": 0.5}, anchor_stress=meas)
    assert cg.adjusted_pd("S1") <= 0.99
    # a second construction (more iterations would be the same fixed point) yields identical numbers
    cg2 = ContagionGraph(frames, {"S1": 0.9, "S2": 0.5}, anchor_stress=meas)
    assert cg2.adjusted_pd("S2") == cg.adjusted_pd("S2")


def test_anchor_stress_is_measured_from_inflows(frames):
    meas = measure_anchor_stress(frames)
    assert meas["ANCH1"]["n_suppliers_measured"] == 14
    assert 0.30 <= meas["ANCH1"]["inflow_decline"] <= 0.50      # the generator's 40% payment cut, observed
    assert meas["ANCH1"]["stress"] >= 0.6
    for aid in ("ANCH2", "ANCH3", "ANCH4"):
        assert meas[aid]["stress"] <= 0.10
