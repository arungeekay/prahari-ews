"""§3.5 / §4.1 Leakage guard on the PRODUCTION feature pipeline.

Operational proof: corrupting every column strictly after as_of (and deleting those months) leaves
the features computed at as_of unchanged, for every as-of month the model trains or validates on
and for borrowers of different trajectories. Plus a label-window correctness test."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.features.pipeline import (msme_features_at, build_msme_training_matrix, static_from_row,
                                    ALL_AS_OFS, HORIZON, MSME_FEATURES)

_NUMERIC_EXCLUDE = {"borrower_id", "month_index", "month_date", "repayment_status", "officer_note"}


def _pick(frames, trajectory):
    """A full-history (24-month) borrower of the trajectory; thin files have no window at early as-ofs."""
    b = frames["borrowers"]
    cand = b[(b.health_trajectory == trajectory) & (b.months_available == 24)]
    row = cand[cand.loan_type == "CC"].iloc[0] if (cand.loan_type == "CC").any() else cand.iloc[0]
    g = frames["msme_monthly"].query("borrower_id == @row.borrower_id").sort_values("month_index")
    return g, static_from_row(row)


@pytest.mark.parametrize("trajectory", ["distress_at_month_k", "sudden_shock", "stable", "slow_decline"])
@pytest.mark.parametrize("as_of", ALL_AS_OFS)
def test_future_corruption_does_not_change_any_feature(frames, trajectory, as_of):
    g, static = _pick(frames, trajectory)
    baseline = msme_features_at(g, as_of, static=static)
    assert baseline is not None and set(baseline) == set(MSME_FEATURES)

    corrupted = g.copy()
    future = corrupted.month_index > as_of
    for col in corrupted.columns:
        if col in _NUMERIC_EXCLUDE:
            continue
        corrupted.loc[future, col] = 10 ** 9
    corrupted.loc[future, "repayment_status"] = "missed"
    corrupted.loc[future, "officer_note"] = "Unit shut; legal notice received; promoter not reachable; fire at unit."

    after = msme_features_at(corrupted, as_of, static=static)
    assert after == baseline, "features changed when future months were corrupted: leakage"


@pytest.mark.parametrize("as_of", ALL_AS_OFS)
def test_dropping_future_does_not_change_features(frames, as_of):
    g, static = _pick(frames, "distress_at_month_k")
    baseline = msme_features_at(g, as_of, static=static)
    truncated = g[g.month_index <= as_of]
    assert msme_features_at(truncated, as_of, static=static) == baseline


def test_static_features_do_not_read_the_series(frames):
    """Profile features must come from the static row only (no back-door through the series)."""
    g, static = _pick(frames, "stable")
    f1 = msme_features_at(g, 12, static=dict(static, loan_type="CC"))
    f2 = msme_features_at(g, 12, static=dict(static, loan_type="term"))
    assert f1["is_term"] == 0.0 and f2["is_term"] == 1.0
    for k in ("util_last", "dp_gap_last"):
        assert f2[k] == 0.0, "term loans must have utilisation features masked"


def test_label_window_is_correct(frames):
    """label = 1 iff as_of < default_month <= as_of + HORIZON; already-defaulted rows are excluded."""
    X, y, meta = build_msme_training_matrix(frames)
    dm = meta.default_month.to_numpy(); a = meta.as_of.to_numpy(); lab = y.to_numpy()
    expected = ((a < dm) & (dm <= a + HORIZON)).astype(int)
    assert np.array_equal(lab, expected)
    assert not ((dm >= 0) & (dm <= a)).any(), "accounts already at 90+ DPD by as_of must be dropped"
    assert set(meta.group.unique()) <= {"A", "B", "C"}
    # borrower folds are disjoint by construction
    per_b = meta.groupby("borrower_id").group.nunique()
    assert (per_b == 1).all()
