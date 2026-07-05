"""PRAHARI backend (BUILD_SPEC §5.1) - Track 4 default-prediction early-warning system.

All numbers are computed live from the synthetic portfolio + trained models; nothing is
hardcoded. Documents are generated via the provider-agnostic LLM layer (templates by default).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from core.serving import get_bundle
from core.serving.webapp import create_app, mount_frontend, register_warmup
from core.llm import generate
from . import logic

app: FastAPI = create_app("PRAHARI API", "PRAHARI")
register_warmup(app, "PRAHARI")
_FRONTEND = os.environ.get("FRONTEND_DIR", str(Path(__file__).resolve().parents[1] / "frontend" / "dist"))


def B():
    return get_bundle()


# --------------------------------------------------------------------- portfolio
@app.get("/api/portfolio")
def portfolio():
    pf = B().portfolio()
    active = pf[pf.pd < 0.99]
    by_bucket = {}
    for bucket in ("red", "amber", "green"):
        sub = pf[pf.bucket == bucket]
        by_bucket[bucket] = dict(count=int(len(sub)), exposure=round(float(sub.exposure.sum()), 2))
    red = pf[pf.bucket == "red"]
    provision_now = float(logic.provision_now(red.exposure.sum()))
    provision_at_npa = float(sum(logic.provision_at_npa(e) for e in red.exposure))
    flagged = pf[pf.bucket.isin(["red", "amber"])]
    return dict(
        n_accounts=int(len(pf)),
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
    )


@app.get("/api/accounts")
def accounts(bucket: str | None = None, sort: str = "runway", limit: int = 200):
    pf = B().portfolio()
    if bucket:
        pf = pf[pf.bucket == bucket]
    ascending = sort == "runway"
    sort_col = {"runway": "runway_months", "pd": "pd", "exposure": "exposure"}.get(sort, "runway_months")
    pf = pf.sort_values(sort_col, ascending=ascending).head(limit)
    return dict(count=int(len(pf)), accounts=pf.to_dict(orient="records"))


@app.get("/api/accounts/{account_id}")
def account_detail(account_id: str):
    b = B()
    if account_id not in b.borrowers.index:
        raise HTTPException(404, "account not found")
    row = b.portfolio().set_index("borrower_id").loc[account_id]
    feat = b.account_features(account_id)
    reasons = b.reason.reason_codes(feat, top=6)
    group = b.msme_group(account_id)
    beats = logic.deterioration_beats(group)
    clocks = logic.compliance_clocks(float(row.exposure), float(row.runway_months), row.bucket)
    br = b.borrowers.loc[account_id]

    storyline = generate("deterioration_storyline", dict(
        name=br["name"], city=br.city, sector=br.sector,
        from_bucket="green", to_bucket=row.bucket, repayment_state="current",
        beats=beats, runway_months=int(round(row.runway_months)),
        provision_saved=logic.provision_saved_if_cured(float(row.exposure)),
    ), product="PRAHARI")

    contagion = None
    if bool(br.is_anchor_supplier):
        contagion = b.contagion().node_result(account_id)

    return dict(
        borrower_id=account_id, name=br["name"], sector=br.sector, city=br.city, state=br.state,
        loan_type=br.loan_type, sanctioned_limit=float(br.sanctioned_limit),
        pd=float(row.pd), bucket=row.bucket,
        runway_months=float(row.runway_months), runway_label=row.runway_label,
        exposure=float(row.exposure), utilisation=float(row.utilisation),
        reason_codes=reasons, auditor_table=b.reason.auditor_table(feat),
        storyline=storyline, beats=beats, compliance_clocks=clocks, contagion=contagion,
        series=group[["month_index", "month_date", "credits", "limit_utilisation",
                      "gst_filing_delay_days", "cheque_bounces_outward", "dpd",
                      "electricity_units", "month_end_balance"]].to_dict(orient="records"),
        whatif_actions=list(logic.WHATIF_ACTIONS),
    )


@app.get("/api/accounts/{account_id}/whatif")
def whatif(account_id: str, action: str = Query(...)):
    b = B()
    if account_id not in b.borrowers.index:
        raise HTTPException(404, "account not found")
    row = b.portfolio().set_index("borrower_id").loc[account_id]
    return logic.whatif(action, float(row.exposure), float(row.runway_months), float(row.pd))


@app.get("/api/contagion/graph")
def contagion_graph():
    return B().contagion().graph_payload()


@app.post("/api/accounts/{account_id}/memo")
def sma_memo(account_id: str):
    b = B()
    if account_id not in b.borrowers.index:
        raise HTTPException(404, "account not found")
    row = b.portfolio().set_index("borrower_id").loc[account_id]
    feat = b.account_features(account_id)
    reasons = [r["plain"] for r in b.reason.reason_codes(feat, top=6)]
    br = b.borrowers.loc[account_id]
    sma_stage = "SMA-2" if row.bucket == "red" else ("SMA-1" if row.bucket == "amber" else "SMA-0")
    text = generate("sma_memo", dict(
        name=br["name"], borrower_id=account_id, loan_type=br.loan_type,
        sanctioned_limit=float(br.sanctioned_limit), as_of_label=str(group_last_label(b, account_id)),
        sma_stage=sma_stage, bucket=row.bucket, pd=float(row.pd),
        runway_months=int(round(row.runway_months)), exposure=float(row.exposure),
        reasons=reasons, provision_saved=logic.provision_saved_if_cured(float(row.exposure)),
    ), product="PRAHARI")
    return dict(document_type="SMA early-warning memo", account_id=account_id, text=text)


@app.post("/api/accounts/{account_id}/crilc")
def crilc(account_id: str):
    b = B()
    if account_id not in b.borrowers.index:
        raise HTTPException(404, "account not found")
    row = b.portfolio().set_index("borrower_id").loc[account_id]
    br = b.borrowers.loc[account_id]
    text = generate("crilc_report", dict(
        name=br["name"], borrower_id=account_id, exposure=float(row.exposure),
        sma_stage="SMA-2", as_of_label=str(group_last_label(b, account_id)), dpd_band="61-90 days"),
        product="PRAHARI")
    return dict(document_type="CRILC reporting note", account_id=account_id, text=text)


@app.post("/api/agent/monthly-run")
def monthly_run():
    """Compile the watch-list, draft memos and portfolio commentary (§5.1). Returns an activity
    log the frontend animates through, plus the results."""
    b = B()
    pf = b.portfolio()
    red = pf[pf.bucket == "red"].sort_values("runway_months")
    amber = pf[pf.bucket == "amber"]
    watch = red.head(10)
    log = [
        f"Scanning {len(pf)} MSME accounts as of demo month…",
        f"Recomputing point-in-time features and PD for all accounts…",
        f"Flagged {len(red)} red and {len(amber)} amber accounts.",
        f"Running contagion diffusion over the anchor payment graph…",
        f"Drafting {len(watch)} SMA memos for the shortest-runway accounts…",
        "Composing portfolio early-warning commentary…",
        "Monthly run complete.",
    ]
    commentary = generate("portfolio_commentary", dict(
        as_of_label="demo month",
        n_accounts=int(len(pf)), total_exposure=float(pf.exposure.sum()),
        n_red=int(len(red)), red_exposure=float(red.exposure.sum()),
        n_amber=int(len(amber)), avg_runway=round(float(red.runway_months.mean() if len(red) else 0), 1),
        n_new_watch=len(watch), n_contagion=int(pf.contagion_induced.sum()),
        top_n=5, top_exposure=float(watch.head(5).exposure.sum()),
        provision_saved=float(sum(logic.provision_saved_if_cured(e) for e in red.exposure)),
    ), product="PRAHARI")
    return dict(activity_log=log, watchlist=watch.to_dict(orient="records"), commentary=commentary)


@app.get("/api/model-card")
def model_card():
    b = B()
    card = b.pd_model.model_card()
    pf = b.portfolio()
    red = pf[pf.bucket == "red"]
    avg_exp = float(red.exposure.mean()) if len(red) else float(pf.exposure.mean())
    card["cost_of_error"] = logic.cost_of_error(card["metrics"]["confusion_matrix"], avg_exp)
    return card


def group_last_label(b, account_id):
    g = b.msme_group(account_id)
    return g.month_date.iloc[-1]


mount_frontend(app, _FRONTEND)
