"""Contract parity: the IDBI-sandbox adapter, run against the Finacle-shaped mock server populated
from the synthetic world, must reproduce the mapped PRAHARI columns for the same borrowers.

This is the claim the deck makes ("response contracts matched") made checkable: every field name,
nesting and amount wrapper on the wire is the catalogue's; the adapter does the translation; the
engine never knows which source it is reading.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from core.ingest import IDBISandboxSource, validate
from core.ingest.schema import MSME_MONTHLY_SCHEMA
from core.features.pipeline import msme_features_at, static_from_row, MSME_FEATURES
from mock.idbi_sandbox import server as mock


@pytest.fixture(scope="module")
def adapter_frames(frames):
    mock.set_world(frames)
    b = frames["borrowers"]
    ids = [b.loc[b.demo == "sharma", "borrower_id"].iloc[0], b.loc[b.demo == "nisha", "borrower_id"].iloc[0]]
    ids += b.loc[b.anchor_id == "ANCH1", "borrower_id"].head(3).tolist()
    ids += b.loc[(b.default_month >= 0) & (b.default_month <= 20), "borrower_id"].head(2).tolist()
    src = IDBISandboxSource(client=TestClient(mock.app), cif_ids=ids, history_months=24)
    out = src.frames()
    return out, src, ids


def test_adapter_reproduces_mapped_columns(frames, adapter_frames):
    out, src, ids = adapter_frames
    a = out["msme_monthly"].set_index(["borrower_id", "month_index"]).sort_index()
    s = frames["msme_monthly"].set_index(["borrower_id", "month_index"]).sort_index()
    for bid in ids:
        sa, ss = a.loc[bid], s.loc[bid]
        common = sa.index.intersection(ss.index)
        assert len(common) >= 5, f"{bid}: adapter produced {len(common)} months"
        sa, ss = sa.loc[common], ss.loc[common]
        for col in ["credits", "debits", "month_end_balance", "lien_amount"]:
            assert np.allclose(sa[col], ss[col], rtol=0.02, atol=1.0), f"{bid}.{col} mismatch"
        for col in ["cheque_bounces_inward", "cheque_bounces_outward", "dpd", "lien_count"]:
            assert (sa[col].to_numpy() == ss[col].to_numpy()).all(), f"{bid}.{col} mismatch"
        assert np.allclose(sa["limit_utilisation"], ss["limit_utilisation"], atol=1e-3), f"{bid}.limit_utilisation"
        assert np.allclose(sa["drawing_power_pct"], ss["drawing_power_pct"], atol=1e-3), f"{bid}.drawing_power_pct"
        assert np.allclose(sa["fuel_spend"], ss["fuel_spend"], rtol=0.02, atol=1.0), f"{bid}.fuel_spend"
        if frames["borrowers"].set_index("borrower_id").at[bid, "is_anchor_supplier"]:
            assert np.allclose(sa["anchor_inflow"], ss["anchor_inflow"], rtol=0.02, atol=1.0), f"{bid}.anchor_inflow"
        # repayment status derived from the overdue APIs matches the generator's ladder
        assert (sa["repayment_status"].to_numpy() == ss["repayment_status"].to_numpy()).all(), f"{bid}.repayment_status"


def test_adapter_static_and_label(frames, adapter_frames):
    out, src, ids = adapter_frames
    ab = out["borrowers"].set_index("borrower_id")
    sb = frames["borrowers"].set_index("borrower_id")
    for bid in ids:
        assert ab.at[bid, "loan_type"] == sb.at[bid, "loan_type"]
        assert abs(float(ab.at[bid, "sanctioned_limit"]) - float(sb.at[bid, "sanctioned_limit"])) < 1.0
        exp_dm = int(sb.at[bid, "default_month"])
        got_dm = int(ab.at[bid, "default_month"])
        # the label is only knowable when the NPA date is on or before the as-of month
        assert got_dm == (exp_dm if 0 <= exp_dm <= 23 else -1), f"{bid}: default_month {got_dm} vs {exp_dm}"
    assert src.provenance()["point_in_time_enforced_at"].startswith("API boundary")
    assert src.calls > 100


def test_adapter_output_validates_and_features_build(adapter_frames):
    out, src, ids = adapter_frames
    filled = src.filled_columns().get("msme_monthly", [])
    assert set(filled) >= {"gst_turnover", "electricity_units", "officer_note"}   # the external feeds, recorded as gaps
    df, _ = validate(out["msme_monthly"], "msme_monthly")
    assert [c for c, _ in MSME_MONTHLY_SCHEMA if c not in df.columns] == []
    b = out["borrowers"].set_index("borrower_id")
    g = df[df.borrower_id == ids[0]].sort_values("month_index")
    f = msme_features_at(g, int(g.month_index.max()), static=static_from_row(b.loc[ids[0]]))
    assert f is not None and set(f) == set(MSME_FEATURES)


def test_anchor_graph_is_derived_from_statement_payers(frames, adapter_frames):
    out, src, ids = adapter_frames
    e = out["edges"]
    assert len(e) >= 3 and (e.payer_name.str.contains("Bharat Auto", case=False)).any()
    assert ((e.inflow_share > 0) & (e.inflow_share <= 1)).all()
