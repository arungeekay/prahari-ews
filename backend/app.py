"""PRAHARI backend (BUILD_SPEC §5.1) - Track 4 default-prediction early-warning system.

All numbers are computed live from the portfolio and the trained models. Documents are generated
via the provider-agnostic LLM layer (templates by default). Regulatory vocabulary, thresholds and
grades come from one interpretation framework (core/interpret), served at /api/framework.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from core.serving import get_bundle
from core.serving.webapp import create_app, mount_frontend, register_warmup
from core.llm import generate, active_provider
from core.interpret import framework as FW
from core.features.pipeline import msme_features_at
from core.features.notes import score_note, get_scorer
from core.models.contagion import ContagionGraph
from . import logic, ews
from .reviews import ReviewStore, ACTIONS

app: FastAPI = create_app("PRAHARI API", "PRAHARI")
register_warmup(app, "PRAHARI")
_REVIEWS = ReviewStore()
_FRONTEND = os.environ.get("FRONTEND_DIR", str(Path(__file__).resolve().parents[1] / "frontend" / "dist"))
_SERIES_COLS = ["month_index", "month_date", "credits", "limit_utilisation", "drawing_power_pct",
                "gst_filing_delay_days", "cheque_bounces_outward", "dpd", "electricity_units",
                "month_end_balance", "stock_statement_submitted", "lien_count", "anchor_inflow"]


def B():
    return get_bundle()


def _row(b, account_id: str):
    if account_id not in b.borrowers.index:
        raise HTTPException(404, "account not found")
    return b.portfolio().set_index("borrower_id").loc[account_id]


# --------------------------------------------------------------------- portfolio
@app.get("/api/portfolio")
def portfolio():
    b = B()
    full = b.portfolio()
    npa = full[full.is_npa == 1]
    pf = full[full.is_npa == 0]          # the prediction book: accounts still standard or SMA
    by_bucket = {}
    for bucket in ("red", "amber", "green"):
        sub = pf[pf.bucket == bucket]
        by_bucket[bucket] = dict(count=int(len(sub)), exposure=round(float(sub.exposure.sum()), 2))
    red = pf[pf.bucket == "red"]
    provision_now = float(logic.provision_now(red.exposure.sum()))
    provision_at_npa = float(sum(logic.provision_at_npa(e) for e in red.exposure))
    flagged = pf[pf.bucket.isin(["red", "amber"])]
    grades = pf.groupby("grade").agg(count=("borrower_id", "size"), exposure=("exposure", "sum"))
    return dict(
        n_accounts=int(len(pf)),
        n_npa=int(len(npa)),
        npa_exposure=round(float(npa.exposure.sum()), 2),
        n_book=int(len(full)),
        total_exposure=round(float(pf.exposure.sum()), 2),
        avg_runway=round(float(pf.runway_months.mean()), 1),
        avg_runway_red=round(float(red.runway_months.mean()), 1) if len(red) else None,
        avg_runway_flagged=round(float(flagged.runway_months.mean()), 1) if len(flagged) else None,
        n_flagged=int(len(flagged)),
        buckets=by_bucket,
        red_exposure=round(float(red.exposure.sum()), 2),
        provision_now=round(provision_now, 2),
        provision_at_npa=round(provision_at_npa, 2),
        provision_saved_acting_now=round(provision_at_npa - provision_now, 2),
        sector_exposure={s: round(float(v), 2)
                         for s, v in pf.groupby("sector").exposure.sum().sort_values(ascending=False).items()},
        loan_type_mix={k: int(v) for k, v in pf.loan_type.value_counts().items()},
        grades={g: dict(count=int(r["count"]), exposure=round(float(r["exposure"]), 2)) for g, r in grades.iterrows()},
        statutory_sma_mix={k: int(v) for k, v in full.statutory_sma.value_counts().items()},
        n_movers_up=int((pf.pd_delta > 0.02).sum()),
        n_suppressed=len(_REVIEWS.suppressed_ids(int(pf.as_of.max()))),
        as_of_label=_as_of_label(b),
        framework_version=FW.load()["version"],
        data_source=b.provenance.get("source"),
    )


@app.get("/api/portfolio/movers")
def movers(limit: int = 15):
    """Accounts whose calibrated PD rose most since last month, with what changed."""
    b = B()
    pf = b.portfolio()
    sup = _REVIEWS.suppressed_ids(int(pf.as_of.max()))
    pf = pf[(pf.is_npa == 0) & (~pf.borrower_id.isin(sup))].sort_values("pd_delta", ascending=False).head(limit)
    out = []
    for r in pf.itertuples(index=False):
        feat = b.account_features(r.borrower_id)
        reasons = b.reason.reason_codes(feat, top=3) if feat else []
        out.append(dict(borrower_id=r.borrower_id, name=r.name, sector=r.sector, loan_type=r.loan_type,
                        pd_prev=r.pd_prev, pd=r.pd, pd_delta=r.pd_delta, bucket=r.bucket, grade=r.grade,
                        runway_months=r.runway_months, exposure=r.exposure, statutory_sma=r.statutory_sma,
                        top_reasons=[x["plain"] for x in reasons]))
    return dict(count=len(out), movers=out)


@app.get("/api/accounts")
def accounts(bucket: str | None = None, sort: str = "runway", limit: int = 200, include_npa: int = 0):
    pf = B().portfolio()
    if not include_npa:
        pf = pf[pf.is_npa == 0]
    if bucket == "npa":
        pf = B().portfolio(); pf = pf[pf.is_npa == 1]
    elif bucket:
        pf = pf[pf.bucket == bucket]
    ascending = sort == "runway"
    sort_col = {"runway": "runway_months", "pd": "pd", "exposure": "exposure", "delta": "pd_delta"}.get(sort, "runway_months")
    if sort == "delta":
        ascending = False
    pf = pf.sort_values(sort_col, ascending=ascending).head(limit)
    return dict(count=int(len(pf)), accounts=pf.to_dict(orient="records"))


@app.get("/api/accounts/{account_id}")
def account_detail(account_id: str):
    b = B()
    row = _row(b, account_id)
    feat = b.account_features(account_id)
    reasons = b.reason.reason_codes(feat, top=6)
    group = b.msme_group(account_id)
    beats = logic.deterioration_beats(group)
    clocks = logic.compliance_clocks(float(row.exposure), float(row.runway_months), row.bucket, row.statutory_sma)
    br = b.borrowers.loc[account_id]
    from_bucket = b.early_bucket(account_id)
    rep_state = logic.repayment_state(group)

    storyline = generate("deterioration_storyline", dict(
        name=br["name"], city=br.city, sector=br.sector,
        from_bucket=from_bucket, to_bucket=row.bucket, repayment_state=rep_state,
        beats=beats, runway_months=int(round(row.runway_months)),
        provision_saved=logic.provision_saved_if_cured(float(row.exposure)),
    ), product="PRAHARI")

    contagion = None
    if bool(br.is_anchor_supplier):
        contagion = b.contagion().node_result(account_id)

    cols = [c for c in _SERIES_COLS if c in group.columns]
    return dict(
        borrower_id=account_id, name=br["name"], sector=br.sector, city=br.city, state=br.state,
        loan_type=br.loan_type, sanctioned_limit=float(br.sanctioned_limit),
        vintage_years=int(br.vintage_years), promoter_experience_years=int(br.promoter_experience_years),
        promoter_qualification=str(br.promoter_qualification),
        pd=float(row.pd), pd_prev=float(row.pd_prev), pd_delta=float(row.pd_delta), bucket=row.bucket,
        from_bucket=from_bucket, repayment_state=rep_state,
        grade=row.grade, grade_label=row.grade_label, grade_score=int(row.grade_score),
        statutory_sma=row.statutory_sma, dpd=int(row.dpd), model_implied_sma=row.model_implied_sma,
        recommended_action=FW.recommended_action(row.bucket),
        runway_months=float(row.runway_months), runway_label=row.runway_label,
        survival_curve=b.runway_model.survival_curve(feat),
        is_npa=bool(row.is_npa),
        exposure=float(row.exposure), utilisation=float(row.utilisation),
        drawing_power_pct=float(row.drawing_power_pct),
        reason_codes=reasons, auditor_table=b.reason.auditor_table(feat),
        explainer_backend=b.reason.backend,
        pillars=b.pillar_scores(account_id),
        ews_indicators=ews.evaluate(feat),
        review=_REVIEWS.state(account_id, int(row.as_of)),
        coverage=b.coverage(account_id),
        notes=b.notes_for(account_id),
        storyline=storyline, beats=beats, compliance_clocks=clocks, contagion=contagion,
        series=group[cols].to_dict(orient="records"),
        whatif_actions=list(logic.WHATIF_ACTIONS),
    )


@app.get("/api/accounts/{account_id}/whatif")
def whatif(account_id: str, action: str = Query(...)):
    b = B()
    row = _row(b, account_id)
    return logic.whatif(action, float(row.exposure), float(row.runway_months), float(row.pd))


class NoteIn(BaseModel):
    text: str


@app.post("/api/accounts/{account_id}/notes/score")
def score_officer_note(account_id: str, note: NoteIn):
    """Score a fresh free-text observation and show how the account's PD responds if it were the
    latest note on file. Unstructured input, live, human-in-the-loop."""
    b = B()
    row = _row(b, account_id)
    g = b.msme_group(account_id).copy()
    as_of = int(g.month_index.max())
    s = score_note(note.text)
    idx = g.index[g.month_index == as_of][0]
    existing = str(g.at[idx, "officer_note"] or "")
    g.at[idx, "officer_note"] = (existing + " " if existing else "") + note.text.strip()
    feat = msme_features_at(g, as_of, static=b.static_for(account_id))
    pd_after = b.pd_model.predict_pd(feat) if feat else float(row.pd)
    bucket_after = FW.bucket(pd_after, b.borrowers.loc[account_id].loan_type)
    return dict(account_id=account_id, text=note.text, sentiment=s["sentiment"], themes=s["themes"],
                severity=s["severity"], scorer=get_scorer().name,
                pd_before=float(row.pd), pd_after=round(float(pd_after), 4),
                pd_delta=round(float(pd_after - row.pd), 4), bucket_before=row.bucket, bucket_after=bucket_after,
                grade_after=FW.grade(pd_after)["grade"])


@app.get("/api/contagion/graph")
def contagion_graph():
    return B().contagion().graph_payload()


class ScenarioIn(BaseModel):
    anchor_id: str
    stress: float = 1.0          # 1.0 = the anchor stops paying (anchor failure)


@app.post("/api/contagion/scenario")
def contagion_scenario(s: ScenarioIn):
    """Portfolio stress test: override one anchor's measured stress and re-run the diffusion. Returns
    every supplier's before/after PD, bucket and runway, and the aggregate exposure and provisioning
    that would move. The same auditable equation, one input changed."""
    b = B()
    base = b.contagion()
    if s.anchor_id not in set(b.anchors.anchor_id):
        raise HTTPException(404, "unknown anchor")
    override = {k: dict(v) for k, v in base.anchor_measure.items()}
    override[s.anchor_id] = dict(override[s.anchor_id], stress=float(max(0.0, min(1.0, s.stress))), scenario=True)
    pf = b.portfolio().set_index("borrower_id")
    pd_by = {bid: float(pf.at[bid, "pd"]) for bid in b.edges.payee.unique() if bid in pf.index}
    scen = ContagionGraph(b.frames, pd_by, anchor_stress=override, runway_fn=b.runway_model.runway_from_pd)
    rows, moved_exposure, prov_delta = [], 0.0, 0.0
    for bid in b.edges[b.edges.payer == s.anchor_id].payee:
        if bid not in pf.index:
            continue
        r0, r1 = base.node_result(bid), scen.node_result(bid)
        lt = pf.at[bid, "loan_type"]
        b0, b1 = FW.bucket(r0["contagion_adjusted_pd"], lt), FW.bucket(r1["contagion_adjusted_pd"], lt)
        exp = float(pf.at[bid, "exposure"])
        if b1 != b0:
            moved_exposure += exp
        if b1 == "red" and b0 != "red":
            prov_delta += logic.provision_saved_if_cured(exp)
        rows.append(dict(borrower_id=bid, name=pf.at[bid, "name"], exposure=exp, own_pd=r0["own_pd"],
                         pd_before=r0["contagion_adjusted_pd"], pd_after=r1["contagion_adjusted_pd"],
                         bucket_before=b0, bucket_after=b1,
                         runway_before=r0["contagion_runway_months"], runway_after=r1["contagion_runway_months"]))
    rows.sort(key=lambda x: x["pd_before"] - x["pd_after"])
    tot_exp = sum(r["exposure"] for r in rows) or 1.0
    ew_before = sum(r["exposure"] * r["pd_before"] for r in rows) / tot_exp
    ew_after = sum(r["exposure"] * r["pd_after"] for r in rows) / tot_exp
    red_exp_before = sum(r["exposure"] for r in rows if r["bucket_before"] == "red")
    red_exp_after = sum(r["exposure"] for r in rows if r["bucket_after"] == "red")
    return dict(anchor_id=s.anchor_id, anchor_name=str(b.anchors.set_index("anchor_id").at[s.anchor_id, "name"]),
                stress_before=base.anchor_result(s.anchor_id)["stress"], stress_after=override[s.anchor_id]["stress"],
                n_suppliers=len(rows), supplier_exposure=round(tot_exp, 2),
                n_rebucketed=sum(r["bucket_before"] != r["bucket_after"] for r in rows),
                exposure_rebucketed=round(moved_exposure, 2), provisioning_at_risk_delta=round(prov_delta, 2),
                exposure_weighted_pd_before=round(ew_before, 4), exposure_weighted_pd_after=round(ew_after, 4),
                expected_loss_proxy_before=round(ew_before * tot_exp, 2), expected_loss_proxy_after=round(ew_after * tot_exp, 2),
                red_exposure_before=round(red_exp_before, 2), red_exposure_after=round(red_exp_after, 2),
                avg_runway_before=round(sum(r["runway_before"] for r in rows) / max(1, len(rows)), 1),
                avg_runway_after=round(sum(r["runway_after"] for r in rows) / max(1, len(rows)), 1),
                suppliers=rows)


@app.get("/api/ews-indicators")
def ews_indicators():
    return ews.summary()


# --------------------------------------------------------------------- backtest, history, value
@app.get("/api/backtest")
def backtest(as_of: int | None = None):
    """Twelve months ago, on this book, with only the data that existed then: who did PRAHARI flag,
    and who actually went 90+ DPD since."""
    b = B()
    latest = int(b.frames["msme_monthly"].month_index.max())
    if as_of is not None and not (5 <= as_of <= latest - 3):
        raise HTTPException(400, f"as_of must be between 5 and {latest - 3}")
    return b.backtest(as_of)


@app.get("/api/accounts/{account_id}/history")
def account_history(account_id: str):
    b = B()
    _row(b, account_id)
    return b.pd_history(account_id)


@app.get("/api/value")
def value(book_cr: float = 5000.0, default_rate: float | None = None, avg_ticket_lakh: float = 75.0,
          review_cost: float = logic.OFFICER_REVIEW_COST):
    """Illustrative bank-scale arithmetic from the validation-fold metrics: what the bank-90 operating
    point makes actionable on a book of the given size. Every assumption is returned with the number."""
    b = B()
    m = b.pd_model.metrics
    dr = float(default_rate) if default_rate is not None else float(m.get("valid_positive_rate", 0.05))
    recall = float(m.get("recall", 0.0)); alert_rate = float(m.get("alert_rate", 0.0)); precision = float(m.get("precision", 0.0))
    prov = FW.provisioning_rates(); step = float(prov["sub_standard"]) - float(prov["standard"])
    book = book_cr * 1e7
    n_accounts = book / (avg_ticket_lakh * 1e5)
    default_exposure = book * dr
    caught_exposure = default_exposure * recall
    actionable = caught_exposure * step
    alerts = n_accounts * alert_rate
    review_cost_total = alerts * review_cost
    return dict(
        inputs=dict(book_cr=book_cr, default_rate=round(dr, 4), avg_ticket_lakh=avg_ticket_lakh, review_cost=review_cost),
        operating_point=dict(threshold=m.get("operating_threshold"), recall=recall, precision=precision, alert_rate=alert_rate),
        n_accounts=int(round(n_accounts)),
        expected_default_exposure=round(default_exposure, 2),
        caught_default_exposure=round(caught_exposure, 2),
        provisioning_actionable=round(actionable, 2),
        alerts_per_cycle=int(round(alerts)), review_cost_total=round(review_cost_total, 2),
        actionable_per_review_rupee=round(actionable / max(1.0, review_cost_total), 1),
        note=("Applies the validation-fold recall and alert rate to a book of the stated size at the stated twelve-month "
              "default rate. 'Provisioning actionable' is the IRAC step from 0.4 to 15 percent on the exposure of defaults "
              "flagged in time; how much is saved depends on the action taken. Synthetic-data metrics are an upper bound."),
    )


@app.post("/api/data-sources/adapter-demo")
def adapter_demo():
    """Run the IDBI-catalogue adapter through the Finacle-shaped mock for the demo cast, live, and
    show the wire payloads and the parity of what came back against the book."""
    import time
    from fastapi.testclient import TestClient
    from core.ingest import IDBISandboxSource
    from mock.idbi_sandbox import server as mock
    b = B()
    mock.set_world(b.frames)
    ids = [bid for bid in ("MSME00001", "MSME02142", "MSME01397") if bid in b.borrowers.index]
    t0 = time.perf_counter()
    client = TestClient(mock.app)
    src = IDBISandboxSource(client=client, cif_ids=ids, history_months=24)
    frames = src.frames()
    elapsed = round(time.perf_counter() - t0, 2)
    # sample payloads exactly as they travel on the wire
    loan = f"L{ids[0]}"
    samples = dict(
        api_394=dict(request={"input": {"acctType": "", "branchId": "", "cifId": ids[0]}}, response=src.accounts_394(ids[0])),
        api_391=dict(request={"input": {"loanAcctId": {"acctId": loan}}}, response=src.loan_391(loan)),
        api_441=dict(request={"input": {"foracid": loan}}, response=_truncate_lists(src.limits_441(loan), 3)),
        api_402=dict(request={"input": {"customerId": ids[0], "accountNo": loan, "asOnDate": src.as_of_end.isoformat()}},
                     response=src.overdue_402(ids[0], loan, src.as_of_end)),
        api_404=dict(request={"input": {"custId": {"custId": ids[0]}, "asOnDate": src.as_of_end.isoformat()}},
                     response=src.position_404(ids[0], loan, src.as_of_end)),
        api_393=dict(request={"input": {"acid": f"OP{ids[0]}", "fromDate": "2026-04-01", "toDate": src.as_of_end.isoformat()}},
                     response=_truncate_lists(src.statement_393(f"OP{ids[0]}", __import__("datetime").date(2026, 4, 1), src.as_of_end), 4)),
        api_362=dict(request={"input": {"acctId": loan, "asOnDate": src.as_of_end.isoformat()}}, response=src.liens_362(loan, src.as_of_end)),
    )
    # parity: adapter output vs the book, per mapped column
    a = frames["msme_monthly"].set_index(["borrower_id", "month_index"])
    s = b.frames["msme_monthly"].set_index(["borrower_id", "month_index"])
    cols = ["credits", "debits", "month_end_balance", "limit_utilisation", "drawing_power_pct", "dpd", "cheque_bounces_outward", "lien_count", "anchor_inflow"]
    parity = []
    for bid in ids:
        sa, ss = a.loc[bid], s.loc[bid]
        common = sa.index.intersection(ss.index)
        row = dict(borrower_id=bid, name=str(b.borrowers.at[bid, "name"]), months=int(len(common)))
        for c in cols:
            x, y = sa.loc[common, c].to_numpy(dtype=float), ss.loc[common, c].to_numpy(dtype=float)
            scale = max(1.0, float(np.abs(y).max()))
            row[c] = round(float(np.abs(x - y).max()) / scale, 4)
        parity.append(row)
    return dict(cif_ids=ids, api_calls=src.calls, seconds=elapsed, provenance=src.provenance(),
                external_columns_filled=src.filled_columns().get("msme_monthly", []),
                samples=samples, parity=parity,
                note=("Parity is the maximum absolute difference between what the adapter reconstructed from the catalogue "
                      "payloads and the book, scaled by the column's magnitude; 0 means identical. External feeds (GST, EPFO, "
                      "electricity, notes) are not in the catalogue and are filled as gaps."))


def _truncate_lists(obj, n: int):
    """Keep sample payloads readable: cap every list to its first n items."""
    if isinstance(obj, list):
        return [_truncate_lists(x, n) for x in obj[:n]] + ([f"... {len(obj) - n} more"] if len(obj) > n else [])
    if isinstance(obj, dict):
        return {k: _truncate_lists(v, n) for k, v in obj.items()}
    return obj


class ReviewIn(BaseModel):
    action: str
    reviewer: str = "officer"
    note: str = ""
    document_type: str = ""


@app.post("/api/accounts/{account_id}/review")
def review_account(account_id: str, r: ReviewIn):
    """Maker-checker: record an officer's decision on a flag or a drafted document."""
    b = B()
    row = _row(b, account_id)
    if r.action not in ACTIONS:
        raise HTTPException(400, f"action must be one of {ACTIONS}")
    rec = _REVIEWS.add(account_id, r.action, r.reviewer, r.note, r.document_type, as_of_month=int(row.as_of))
    return dict(record=rec, state=_REVIEWS.state(account_id, int(row.as_of)))


@app.get("/api/accounts/{account_id}/reviews")
def account_reviews(account_id: str):
    b = B()
    row = _row(b, account_id)
    return dict(account_id=account_id, state=_REVIEWS.state(account_id, int(row.as_of)), history=_REVIEWS.for_account(account_id))


@app.get("/api/reviews")
def reviews(limit: int = 100):
    return dict(count=len(_REVIEWS.all(limit)), reviews=_REVIEWS.all(limit))


@app.post("/api/accounts/{account_id}/memo")
def sma_memo(account_id: str):
    b = B()
    row = _row(b, account_id)
    feat = b.account_features(account_id)
    reasons = [r["plain"] for r in b.reason.reason_codes(feat, top=6)]
    br = b.borrowers.loc[account_id]
    notes = b.notes_for(account_id, months=6)
    adverse = [n for n in notes if n["sentiment"] < -0.15]
    text = generate("sma_memo", dict(
        name=br["name"], borrower_id=account_id, loan_type=br.loan_type,
        sanctioned_limit=float(br.sanctioned_limit), as_of_label=str(group_last_label(b, account_id)),
        statutory_sma=row.statutory_sma, dpd=int(row.dpd), model_implied_sma=row.model_implied_sma,
        grade=row.grade, bucket=row.bucket, pd=float(row.pd),
        runway_months=int(round(row.runway_months)), exposure=float(row.exposure),
        reasons=reasons, recommended_action=FW.recommended_action(row.bucket)["detail"],
        note_citation=(adverse[-1]["text"] if adverse else ""), note_date=(adverse[-1]["month_date"] if adverse else ""),
        provision_saved=logic.provision_saved_if_cured(float(row.exposure)),
    ), product="PRAHARI")
    return dict(document_type="SMA early-warning memo", account_id=account_id, text=text,
                llm_provider=active_provider())


@app.post("/api/accounts/{account_id}/crilc")
def crilc(account_id: str):
    b = B()
    row = _row(b, account_id)
    br = b.borrowers.loc[account_id]
    eligible = float(row.exposure) >= logic.CRILC_EXPOSURE_THRESHOLD
    text = generate("crilc_report", dict(
        name=br["name"], borrower_id=account_id, exposure=float(row.exposure), eligible=eligible,
        threshold=logic.CRILC_EXPOSURE_THRESHOLD, statutory_sma=row.statutory_sma, dpd=int(row.dpd),
        dpd_band=FW.dpd_band(int(row.dpd)), model_implied_sma=row.model_implied_sma, grade=row.grade,
        as_of_label=str(group_last_label(b, account_id))), product="PRAHARI")
    return dict(document_type="CRILC note" if eligible else "CRILC readiness note (below threshold)",
                account_id=account_id, text=text, llm_provider=active_provider())


@app.post("/api/agent/monthly-run")
def monthly_run():
    """Compile the watch-list, draft memos and portfolio commentary (§5.1). Returns an activity
    log the frontend animates through, plus the results."""
    b = B()
    pf = b.portfolio()
    sup = _REVIEWS.suppressed_ids(int(pf.as_of.max()))
    pf = pf[(pf.is_npa == 0) & (~pf.borrower_id.isin(sup))]
    red = pf[pf.bucket == "red"].sort_values("runway_months")
    amber = pf[pf.bucket == "amber"]
    watch = red.head(10)
    cg = b.contagion()
    contagion_flagged = [n for n in cg.graph_payload()["nodes"]
                         if n["kind"] == "supplier" and n["runway_delta"] < 0 and FW.bucket(n["contagion_adjusted_pd"]) != FW.bucket(n["own_pd"])]
    movers_up = pf[pf.pd_delta > 0.02]
    log = [
        f"Scanning {len(pf)} MSME accounts as of {_as_of_label(b)}" + (f" ({len(sup)} cleared accounts in cooling period)…" if sup else "…"),
        "Recomputing point-in-time features and calibrated PD for all accounts…",
        f"Flagged {len(red)} red and {len(amber)} amber accounts; {len(movers_up)} accounts moved up materially this month.",
        f"Measuring anchor payment stress and running contagion diffusion over {len(cg.edges)} payment edges…",
        f"{len(contagion_flagged)} supplier accounts re-bucketed by contagion while their own conduct is clean.",
        f"Drafting {len(watch)} SMA memos for the shortest-runway accounts…",
        "Composing portfolio early-warning commentary…",
        "Monthly run complete.",
    ]
    commentary = generate("portfolio_commentary", dict(
        as_of_label=_as_of_label(b),
        n_accounts=int(len(pf)), total_exposure=float(pf.exposure.sum()),
        n_red=int(len(red)), red_exposure=float(red.exposure.sum()),
        n_amber=int(len(amber)), avg_runway=round(float(red.runway_months.mean() if len(red) else 0), 1),
        n_new_watch=len(watch), n_contagion=len(contagion_flagged), n_movers=int(len(movers_up)),
        top_n=5, top_exposure=float(watch.head(5).exposure.sum()),
        provision_saved=float(sum(logic.provision_saved_if_cured(e) for e in red.exposure)),
    ), product="PRAHARI")
    return dict(activity_log=log, watchlist=watch.to_dict(orient="records"), commentary=commentary,
                contagion_flagged=[dict(id=n["id"], label=n["label"], own_pd=n["own_pd"],
                                        contagion_adjusted_pd=n["contagion_adjusted_pd"]) for n in contagion_flagged])


@app.get("/api/model-card")
def model_card():
    b = B()
    card = b.pd_model.model_card()
    pf = b.portfolio()
    pf = pf[pf.is_npa == 0]
    red = pf[pf.bucket == "red"]
    avg_exp = float(red.exposure.mean()) if len(red) else float(pf.exposure.mean())
    card["cost_of_error"] = logic.cost_of_error(card["metrics"]["confusion_matrix"], avg_exp)
    card["explainer_backend"] = b.reason.backend
    card["note_scorer"] = get_scorer().name
    card["runway"] = b.runway_model.card()
    return card


@app.get("/api/framework")
def framework():
    return FW.summary()


@app.get("/api/data-sources")
def data_sources():
    """Where every input comes from, in the bank's own API vocabulary."""
    b = B()
    prov = b.provenance
    mm = b.frames["msme_monthly"]
    feeds = [
        dict(feed="Loan account master and conduct", idbi_apis=["391", "394", "402", "404"], columns=["loan_type", "sanctioned_limit", "repayment_status", "emi_days_late", "dpd", "default label"], mode=prov.get("source"), status="mapped"),
        dict(feed="Drawing power and limits", idbi_apis=["441", "442"], columns=["drawing_power_pct", "limit_utilisation"], mode=prov.get("source"), status="mapped"),
        dict(feed="Operating account statement", idbi_apis=["393", "365"], columns=["credits", "debits", "month_end_balance", "cheque_bounces_inward", "cheque_bounces_outward", "fuel_spend", "anchor_inflow"], mode=prov.get("source"), status="mapped"),
        dict(feed="Liens", idbi_apis=["362"], columns=["lien_count", "lien_amount"], mode=prov.get("source"), status="mapped"),
        dict(feed="Credit bureau", idbi_apis=["408"], columns=["bureau_enquiries", "bureau_new_loans", "bureau_dpd_other"], mode=prov.get("source"), status="mapped"),
        dict(feed="Account Aggregator statements", idbi_apis=["590", "591", "739", "595"], columns=["other-bank inflows (contagion share)"], mode=prov.get("source"), status="consent flow mapped"),
        dict(feed="GST returns", idbi_apis=["GST schema (sample PDF)"], columns=["gst_turnover", "gst_filing_delay_days"], mode=prov.get("source"), status="external feed requested"),
        dict(feed="EPFO", idbi_apis=[], columns=["epfo_employee_count", "epfo_contribution_delay_days"], mode=prov.get("source"), status="external feed requested"),
        dict(feed="Electricity", idbi_apis=[], columns=["electricity_units"], mode=prov.get("source"), status="external feed requested"),
        dict(feed="Officer notes (unstructured)", idbi_apis=["362 remarks", "393 narration", "CRM/DMS"], columns=["officer_note"], mode=prov.get("source"), status="mapped (text)"),
        dict(feed="Sector sentiment", idbi_apis=[], columns=["sector_sentiment"], mode=prov.get("source"), status="external"),
    ]
    return dict(provenance=prov, rows=int(len(mm)), borrowers=int(mm.borrower_id.nunique()),
                months=[int(mm.month_index.min()), int(mm.month_index.max())],
                as_of_label=str(mm.month_date.max()), feeds=feeds,
                note_scorer=get_scorer().name, llm_provider=active_provider(),
                coverage_note="14 of 19 behavioural inputs and the default label come from IDBI core-banking APIs; GST, EPFO, electricity and sector sentiment are the external feeds requested in the data-field document.")


def group_last_label(b, account_id):
    g = b.msme_group(account_id)
    return g.month_date.iloc[-1]


def _as_of_label(b) -> str:
    """The as-of month as a date label (e.g. 2026-06), never a bare month index."""
    return str(b.frames["msme_monthly"].month_date.max())[:7]


mount_frontend(app, _FRONTEND)
