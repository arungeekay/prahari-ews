"""Interpretation framework + note scorer invariants."""

from __future__ import annotations

from core.interpret import framework as FW
from core.features.notes import score_note, note_window_features, LexiconScorer, THEMES


def test_grade_is_monotone_and_bands_cover_pd():
    prev = None
    for p in [0.0, 0.005, 0.02, 0.04, 0.08, 0.15, 0.3, 0.6, 0.99]:
        g = FW.grade(p)
        assert g["grade"].startswith("PR") and 0 <= g["score"] <= 1000
        if prev is not None:
            assert g["score"] <= prev
        prev = g["score"]
    assert FW.grade(0.001)["grade"] == "PR1" and FW.grade(0.9)["grade"] == "PR7"


def test_bucket_thresholds_from_config():
    rag = FW.load()["rag"]
    assert FW.bucket(rag["amber_pd"] - 1e-6) == "green"
    assert FW.bucket(rag["amber_pd"]) == "amber"
    assert FW.bucket(rag["red_pd"]) == "red"


def test_statutory_sma_is_dpd_defined():
    assert FW.statutory_sma(0) == "Standard"
    assert FW.statutory_sma(15) == "SMA-0"
    assert FW.statutory_sma(45) == "SMA-1"
    assert FW.statutory_sma(75) == "SMA-2"
    assert FW.statutory_sma(120) == "NPA"
    assert "model-implied" in FW.load()["model_implied_sma"]["note"].lower() or "MODEL-IMPLIED" in FW.load()["model_implied_sma"]["note"]


def test_note_scorer_is_deterministic_and_sensible():
    s = LexiconScorer()
    bad = s.score("Promoter evasive about receivables and creditor pressure from the anchor buyer.")
    good = s.score("Unit visit: godown well stocked, operations normal.")
    assert bad["sentiment"] < -0.4 and "receivables" in bad["themes"] and "promoter" in bad["themes"]
    assert good["sentiment"] > 0.3
    assert s.score("") == dict(sentiment=0.0, themes=[], severity=0)
    assert score_note("Legal notice received from a supplier.")["severity"] == 3
    assert set(THEMES) >= set(bad["themes"])


def test_note_window_features_ignore_empty_months_and_weight_recency():
    f = note_window_features(["", "Order inflow strong; promoter upbeat on demand.", "", "", "Unit running a single shift; promoter unable to meet interest this month.", ""])
    assert f["note_n"] == 2 and f["note_adverse_cnt"] == 1
    assert f["note_sent_ewma"] < 0            # the recent adverse note dominates the older positive one
    assert f["note_sent_min"] <= -0.6 and f["note_severity_max"] == 3
    assert note_window_features(["", "", ""])["note_n"] == 0
