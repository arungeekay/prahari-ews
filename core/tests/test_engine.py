"""Engine + demo-cast regression guard (protects the scripted storylines in BUILD_SPEC §9).

Trains the models once and asserts the signature demo outcomes hold: Sharma's runway, the
Verma/Gupta triangle split, Nisha's thin-file REFER, Ravi's capacity+match, and the contagion
reveal. If a future change breaks a demo storyline, this fails loudly.
"""

from __future__ import annotations

import pytest

from core.datagen import config as C
from core.models import (PDModel, RunwayModel, IntentModel, score_arogya,
                         verification_triangle, capacity_profile, match_products, ContagionGraph)
from core.features.pipeline import msme_features_at, static_from_row
from core.interpret import framework as FW


@pytest.fixture(scope="module")
def engine(frames):
    pdm = PDModel.train(frames)
    rw = RunwayModel.train(frames, pdm)
    im = IntentModel.train(frames)
    return dict(pdm=pdm, rw=rw, im=im, frames=frames)


def _bid(frames, demo):
    return frames["borrowers"].loc[frames["borrowers"].demo == demo, "borrower_id"].iloc[0]


def _cid(frames, demo):
    return frames["customers"].loc[frames["customers"].demo == demo, "customer_id"].iloc[0]


def test_pd_metrics_plausible_and_honest(engine):
    m = engine["pdm"].metrics
    assert 0.86 <= m["auc"] <= 0.975
    assert m["accuracy"] >= 0.88                       # bank-90 operating point (0.88 tolerance for a small fold)
    assert m["max_capture"]["recall"] >= 0.75
    assert m["n_borrowers_valid"] > 300
    assert "borrower-disjoint" in m["validation"]
    assert m["calibration"]["brier"] < 0.06
    assert len(m["operating_points"]) == 3 and len(m["deciles"]) == 10 and len(m["baselines"]) >= 2
    assert m["lead_time"][-1]["months_ahead"] == "10-12"


def test_sharma_red_runway_seven(engine):
    frames = engine["frames"]
    bid = _bid(frames, "sharma")
    b = frames["borrowers"].set_index("borrower_id").loc[bid]
    g = frames["msme_monthly"].query("borrower_id == @bid").sort_values("month_index")
    feat = msme_features_at(g, C.DEMO_MONTH, static=static_from_row(b))
    pd_v = engine["pdm"].predict_pd(feat)
    runway = engine["rw"].runway(feat, pd_v)
    assert FW.bucket(pd_v, "CC") == "red"
    assert 4.0 <= runway <= 10.0           # scripted runway ≈ 7 months (default at month 30, as of 23)
    rm = engine["rw"].metrics
    assert rm["concordance_defaulters_fold_C"] is None or rm["concordance_defaulters_fold_C"] >= 0.6
    assert rm["hazard_model_12m_auc"] is None or rm["hazard_model_12m_auc"] >= 0.85


def test_verma_clean_gupta_fraud(engine):
    frames = engine["frames"]
    b = frames["borrowers"].set_index("borrower_id")
    for demo, expect_closed in (("verma", True), ("gupta", False)):
        bid = _bid(frames, demo)
        g = frames["msme_monthly"].query("borrower_id == @bid")
        tri = verification_triangle(b.loc[bid], g)
        assert (tri["overall"] == "closed") == expect_closed
    vbid = _bid(frames, "verma")
    sc = score_arogya(b.loc[vbid], frames["msme_monthly"].query("borrower_id == @vbid"))
    assert sc["bucket"] == "REFER" and 660 <= sc["unified_score"] <= 759


def test_nisha_thin_file_refer(engine):
    frames = engine["frames"]
    b = frames["borrowers"].set_index("borrower_id")
    bid = _bid(frames, "nisha")
    sc = score_arogya(b.loc[bid], frames["msme_monthly"].query("borrower_id == @bid"))
    assert sc["thin_file"] and sc["bucket"] == "REFER"
    assert 0.5 <= sc["confidence"] <= 0.7


def test_ravi_capacity_and_match(engine):
    frames = engine["frames"]
    cust = frames["customers"].set_index("customer_id")
    cid = _cid(frames, "ravi")
    monthly = frames["retail_monthly"].query("customer_id == @cid")
    cap = capacity_profile(monthly, cust.loc[cid])
    assert cap["income_type"] == "gig_worker"
    assert 27_000 <= cap["reconstructed_income"] <= 36_000
    assert 12_000 <= cap["disposable_income"] <= 16_500
    match = match_products(cap, cust.loc[cid])
    assert match["best_match"]["product"] == "consumer_durable_loan"


def test_contagion_shortens_supplier_runways(engine):
    frames = engine["frames"]
    b = frames["borrowers"].set_index("borrower_id")
    a1 = b[b.anchor_id == "ANCH1"].index.tolist()
    mm = frames["msme_monthly"]
    pd_by = {}
    for bid in a1:
        g = mm.query("borrower_id == @bid").sort_values("month_index")
        feat = msme_features_at(g, C.DEMO_MONTH, static=static_from_row(b.loc[bid]))
        pd_by[bid] = engine["pdm"].predict_pd(feat) if feat is not None else 0.05
    cg = ContagionGraph(frames, pd_by, runway_fn=engine["rw"].runway_from_pd)
    res = [cg.node_result(bid) for bid in a1]
    lifted = sum(r["contagion_adjusted_pd"] > r["own_pd"] + 0.05 for r in res)
    assert lifted >= 12                                   # the measured anchor stress reaches nearly every supplier
    assert all(r["runway_delta"] <= 0 for r in res)       # contagion never lengthens a runway
    assert sum(r["runway_delta"] < 0 for r in res) >= 8   # and materially shortens most of them
    a = cg.anchor_result("ANCH1")
    assert a["stress"] >= 0.5 and a["n_suppliers_measured"] == 14
