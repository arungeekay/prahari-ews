"""§3.5 Named demo characters exist exactly as specified (BUILD_SPEC §9). These storylines
must render precisely in the demos, so we assert their scripted behavioural beats here."""

from __future__ import annotations

import numpy as np

from core.datagen import config as C


# ---------------------------------------------------------------- MSME cast (§9.1 / §9.2)
def _demo(borrowers, tag):
    rows = borrowers[borrowers.demo == tag]
    assert len(rows) == 1, f"demo MSME '{tag}' missing/duplicated"
    return rows.iloc[0]


def _series(msme_monthly, bid):
    return msme_monthly.query("borrower_id == @bid").sort_values("month_index")


def test_sharma_identity(borrowers):
    s = _demo(borrowers, "sharma")
    assert s["name"] == "Sharma Fabricators"
    assert s.sector == "manufacturing" and s.city == "Ludhiana"
    assert s.health_trajectory == "distress_at_month_k"


def test_sharma_storyline_beats(borrowers, msme_monthly):
    """month-3 GST delays → month-5 credits −22% & util >85% → month-7 first cheque return,
    all while repayment is still clean, and default ~7 months out (runway ≈ 7)."""
    s = _demo(borrowers, "sharma")
    g = _series(msme_monthly, s.borrower_id).set_index("month_index")
    start = int(s.traj_start)  # 16 → storyline month 0

    # beat: GST filing delays climbing by storyline month 3 (idx 19)
    assert g.loc[start + 3, "gst_filing_delay_days"] > 0
    assert g.loc[C.DEMO_MONTH, "gst_filing_delay_days"] > g.loc[start + 1, "gst_filing_delay_days"]

    # beat: credits down ~22% and utilisation over 85% by storyline month 5 (idx 21)
    assert g.loc[start + 5, "credits"] / g.loc[start - 1, "credits"] <= 0.85
    assert g.loc[start + 5, "limit_utilisation"] >= 0.85

    # beat: first outward cheque return by storyline month 7 (idx 23) - and none before it
    assert g.loc[C.DEMO_MONTH, "cheque_bounces_outward"] >= 1
    assert g.loc[:C.DEMO_MONTH - 1, "cheque_bounces_outward"].sum() == 0

    # flagged early: repayment still clean at demo, default ≈ 7 months later (runway ≈ 7)
    assert g.loc[C.DEMO_MONTH, "dpd"] == 0
    runway = int(s.default_month) - C.DEMO_MONTH
    assert 6 <= runway <= 8


def test_bharat_auto_anchor(frames, borrowers):
    anchors = frames["anchors"]
    a1 = anchors[anchors.anchor_id == "ANCH1"].iloc[0]
    assert a1["name"] == "Bharat Auto Components Ltd"
    assert a1.n_suppliers == 14
    assert (borrowers.anchor_id == "ANCH1").sum() == 14


def test_verma_gupta_twins(borrowers, msme_monthly):
    v = _demo(borrowers, "verma")
    gp = _demo(borrowers, "gupta")
    assert v["name"] == "Verma Textiles" and gp["name"] == "Gupta Trading Co"
    assert v.health_trajectory == "growing" and gp.health_trajectory == "fraud_pattern"
    # identical declared GST turnover
    vg = _series(msme_monthly, v.borrower_id).gst_turnover.to_numpy()
    gg = _series(msme_monthly, gp.borrower_id).gst_turnover.to_numpy()
    assert np.allclose(vg, gg)


def test_nisha_thin_file(borrowers, msme_monthly):
    n = _demo(borrowers, "nisha")
    assert n["name"] == "Nisha Snacks" and n.sector == "food_processing"
    g = _series(msme_monthly, n.borrower_id)
    assert len(g) == 5                       # only 5 months of history (§9.2)
    assert sorted(g.month_index.tolist()) == [19, 20, 21, 22, 23]


# ---------------------------------------------------------------- Retail cast (§9.3)
def _demo_cust(customers, tag):
    rows = customers[customers.demo == tag]
    assert len(rows) == 1, f"demo customer '{tag}' missing/duplicated"
    return rows.iloc[0]


def test_ravi_gig_worker(customers, retail_monthly, engagement):
    r = _demo_cust(customers, "ravi")
    assert r["name"] == "Ravi Kumar" and r.city == "Pune"
    assert r.occupation_type == "gig_worker" and r.loan_intent == "serious"

    m = retail_monthly[retail_monthly.customer_id == r.customer_id]
    assert m.income_credit_count.mean() >= 30            # 30+ volatile UPI credits/month
    assert 27_000 <= m.income_credits.mean() <= 36_000   # reconstructed income ≈ ₹31k
    disposable = (m.income_credits - m.existing_emi - m.rent - m.essential_spend).mean()
    assert 12_000 <= disposable <= 16_500                # disposable ≈ ₹14k

    e = engagement[engagement.customer_id == r.customer_id]
    assert len(e) >= 5
    assert (e.page == "personal_loan").any()             # clicked personal-loan page
    assert e.is_evening.sum() >= 2                        # evening repeat sessions
    assert e.emi_calc_used.sum() >= 1                     # EMI-calculator interactions


def test_discipline_twins(customers, retail_monthly):
    saver = _demo_cust(customers, "discipline_saver")
    spender = _demo_cust(customers, "discipline_spender")

    # same ₹60k salary, both salaried
    assert saver.occupation_type == "salaried" and spender.occupation_type == "salaried"
    assert abs(saver.base_income - 60_000) < 1 and abs(spender.base_income - 60_000) < 1

    ms = retail_monthly[retail_monthly.customer_id == saver.customer_id]
    mp = retail_monthly[retail_monthly.customer_id == spender.customer_id]
    # saver holds 30%+ balance all month; spender exhausts by day 3
    assert (ms.retained_balance_ratio >= 0.30).all()
    assert (mp.day3_balance_ratio <= 0.15).all()
    # → different capacity tiers
    assert saver.capacity_score > spender.capacity_score + 0.2
