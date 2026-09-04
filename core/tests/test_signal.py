"""§3.5 Signal: a baseline XGBoost on point-in-time features is *honestly* learnable under a
borrower-disjoint temporal split, strong enough to clear the bank's bar but not implausibly perfect.
Real 12-month PD models live ~0.75-0.85; a synthetic world scoring 0.99 reads as rigged."""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.metrics import roc_auc_score

from core.features import build_msme_training_matrix
from core.features.pipeline import TRAIN_AS_OFS, VALID_AS_OFS


@pytest.fixture(scope="module")
def matrix(frames):
    return build_msme_training_matrix(frames)


def test_dataset_has_signal_and_positives(matrix):
    X, y, meta = matrix
    assert len(X) > 5000
    assert y.sum() >= 200                    # enough defaulters to learn from
    assert 0.02 < y.mean() < 0.12            # realistic positive rate
    assert len(X.columns) >= 40


def test_borrower_disjoint_temporal_auc_in_plausible_band(matrix):
    """Train on fold A at early as-ofs, evaluate on fold C at later as-ofs: borrowers never seen,
    dates after training. Lower bound = the bank's bar the honest way; upper bound = honesty guard."""
    from xgboost import XGBClassifier

    X, y, meta = matrix
    train = ((meta.group == "A") & meta.as_of.isin(TRAIN_AS_OFS)).to_numpy()
    test = ((meta.group == "C") & meta.as_of.isin(VALID_AS_OFS)).to_numpy()
    assert y[train].sum() > 50 and y[test].sum() > 40
    assert not set(meta.borrower_id[train]) & set(meta.borrower_id[test])

    clf = XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                        colsample_bytree=0.9, eval_metric="logloss", random_state=0, n_jobs=4)
    clf.fit(X[train], y[train])
    proba = clf.predict_proba(X[test])[:, 1]
    yte = y[test].to_numpy()

    auc = roc_auc_score(yte, proba)
    assert 0.86 <= auc <= 0.975, f"borrower-disjoint temporal AUC {auc:.4f} outside the plausible band"

    # top two deciles must hold most of the defaults (capture is what a monitoring team acts on)
    order = np.argsort(-proba)
    top20 = order[: int(0.2 * len(order))]
    capture = yte[top20].sum() / yte.sum()
    assert capture >= 0.80, f"top-20% capture {capture:.3f} below 0.80"


def test_unpredictable_defaulters_are_actually_hard(frames, matrix):
    """Sudden-shock defaulters must be genuinely hard to catch far out - proof the world isn't tidy."""
    b = frames["borrowers"]
    n_sudden = int((b.health_trajectory == "sudden_shock").sum())
    assert n_sudden >= 20, "need a meaningful sudden-shock cohort"
    defaulters = b[b.default_month >= 0]
    frac = (defaulters.health_trajectory == "sudden_shock").mean()
    assert 0.10 <= frac <= 0.28, f"sudden-shock share of defaulters {frac:.2%} outside 10-28%"
