"""Finacle-shaped mock of IDBI's API catalogue (api req response hackathon.xlsx), populated from the
synthetic world, so PRAHARI's `IDBISandboxSource` adapter can be exercised end to end without
credentials. Every response reproduces the catalogue's field names, nesting and the
{"amountValue", "currencyCode"} wrappers. Point-in-time is honoured: a request with `asOnDate`
never returns anything recorded after that date.

Run:  uvicorn mock.idbi_sandbox.server:app --port 8790
Then: DATA_SOURCE=idbi_sandbox IDBI_BASE_URL=http://localhost:8790 uvicorn prahari.backend.app:app
"""

from __future__ import annotations

import calendar
import os
from datetime import date
from functools import lru_cache

import pandas as pd
from fastapi import FastAPI, HTTPException

from core.datagen import config as C
from core.datagen.util import month_index_to_date
from core.ingest.synthetic import SyntheticSource

app = FastAPI(title="IDBI sandbox mock (Finacle-shaped)")
SCHEME = {"CC": "CCA", "OD": "ODA", "term": "LAA"}
EMI_SHARE_OF_LIMIT = 0.02          # notional monthly demand as a share of sanction


_OVERRIDE: dict | None = None


def set_world(frames: dict) -> None:
    """Inject frames (tests) instead of loading from DATA_DIR."""
    global _OVERRIDE
    _OVERRIDE = _index(dict(frames))
    world.cache_clear()


def _index(fr: dict) -> dict:
    fr["_groups"] = {bid: g.sort_values("month_index") for bid, g in fr["msme_monthly"].groupby("borrower_id")}
    fr["_borrowers"] = fr["borrowers"].set_index("borrower_id")
    fr["_anchor_names"] = dict(zip(fr["anchors"].anchor_id, fr["anchors"].name))
    return fr


@lru_cache(maxsize=1)
def world() -> dict:
    if _OVERRIDE is not None:
        return _OVERRIDE
    src = SyntheticSource(os.environ.get("DATA_DIR", "data"))
    return _index(src.frames())


def _amt(v) -> dict:
    return {"amountValue": f"{float(v):.2f}", "currencyCode": "INR"}


def _parse(d: str | None) -> date | None:
    if not d:
        return None
    try:
        return date.fromisoformat(str(d)[:10])
    except ValueError:
        return None


def _month_idx(d: date) -> int:
    start = month_index_to_date(0)
    return (d.year - start.year) * 12 + (d.month - start.month)


def _month_end(idx: int) -> date:
    d = month_index_to_date(idx)
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _loan_acct(bid: str) -> str:
    return f"L{bid}"


def _oper_acct(bid: str) -> str:
    return f"OP{bid}"


def _bid_from_acct(acct: str) -> str:
    return acct[2:] if acct.startswith("OP") else acct[1:]


def _errors():
    return [{"code": "", "type": "", "message": ""}]


# --------------------------------------------------------------------------- helper (not in catalogue)
@app.post("/api/portfolio/cifs")
def cifs(body: dict):
    """Enumerates CIFs for the demo. Not an IDBI API; a real run would take the CIF list from the
    bank's portfolio extract. IDBI_CIF_LIMIT bounds the demo run."""
    w = world()
    ids = list(w["_borrowers"].index)
    limit = int(os.environ.get("IDBI_CIF_LIMIT", body.get("limit", 150)))
    demo = [b for b in ids if w["_borrowers"].at[b, "demo"]]
    a1 = [b for b in ids if w["_borrowers"].at[b, "anchor_id"] == "ANCH1"]
    rest = [b for b in ids if b not in demo and b not in a1]
    return {"cifIds": (demo + a1 + rest)[:limit], "total": len(ids)}


# --------------------------------------------------------------------------- 394
@app.post("/api/394/getCustomerAccountsByCustId")
def api_394(body: dict):
    w = world()
    cif = body["input"]["cifId"].strip()
    if cif not in w["_borrowers"].index:
        raise HTTPException(404, "unknown CIF")
    b = w["_borrowers"].loc[cif]
    g = w["_groups"][cif]
    last = g.iloc[-1]
    return {"result": {"acctTypeRequested": body["input"].get("acctType", ""), "cifId": cif,
                       "customerAccountInfo": [
                           {"acctBalance": _amt(-float(b.sanctioned_limit) * float(last.limit_utilisation)), "acctCurrCode": "INR",
                            "acctNumber": _loan_acct(cif), "acctType": SCHEME.get(b.loan_type, "LAA")},
                           {"acctBalance": _amt(last.month_end_balance), "acctCurrCode": "INR",
                            "acctNumber": _oper_acct(cif), "acctType": "CA"}],
                       "numOfAccounts": 2, "customData": {"thb": ""}, "errors": _errors()}}


# --------------------------------------------------------------------------- 391
@app.post("/api/391/getLoanAccountDetails")
def api_391(body: dict):
    w = world()
    cif = _bid_from_acct(body["input"]["loanAcctId"]["acctId"])
    b = w["_borrowers"].loc[cif]
    return {"result": {
        "loanAcctId": {"acctId": _loan_acct(cif), "acctType": {"schmCode": SCHEME.get(b.loan_type, "LAA"), "schmType": SCHEME.get(b.loan_type, "LAA")},
                       "acctCurr": "INR", "bankInfo": {"bankId": "IDBI", "name": "IDBI Bank", "branchId": "0001", "branchName": b.city,
                                                       "postAddr": {"addr1": "", "addr2": "", "addr3": "", "city": b.city, "stateProv": b.state,
                                                                    "postalCode": "", "country": "IN", "addrType": "Business"}}},
        "netIntRate": {"value": "10.25"}, "acctOpenDt": str(b.loan_start_date), "modeOfOper": "SOW",
        "custId": {"custId": cif, "personName": {"lastName": "", "firstName": "", "middleName": "", "name": b["name"], "titlePrefix": "M/s"}},
        "loanAcctGenInfo": {"acctName": b["name"], "acctShortName": b["name"][:10]},
        "amtAlreadyDisb": _amt(b.sanctioned_limit), "amtAvailForDisb": _amt(0), "disbAmt": _amt(b.sanctioned_limit),
        "loanGenDetails": {"loanAmt": _amt(b.sanctioned_limit), "loanPeriodDays": "", "loanPeriodMonths": "60" if b.loan_type == "term" else "12",
                           "rePmtMethod": "EMI" if b.loan_type == "term" else "INTEREST",
                           "operAcctId": {"acctId": _oper_acct(cif), "acctType": {"schmCode": "CA", "schmType": "CA"}, "acctCurr": "INR"},
                           "reschedParams": {"reschedAmtFlg": "N"}},
        "relPartyRec": [], "postDtChkRec": [], "errors": _errors()}}


# --------------------------------------------------------------------------- 441
@app.post("/api/441/fetchLoanAccountLimits")
def api_441(body: dict):
    w = world()
    cif = _bid_from_acct(body["input"]["foracid"])
    b = w["_borrowers"].loc[cif]
    g = w["_groups"][cif]
    as_on = _parse(body["input"].get("asOnDate"))
    dp_rows = []
    if b.loan_type != "term":
        for r in g.itertuples(index=False):
            d = month_index_to_date(int(r.month_index))
            if as_on and d > as_on:
                break
            dp_rows.append({"applicableDate": d.isoformat(), "drwngPower": _amt(float(r.drawing_power_pct) * float(b.sanctioned_limit)),
                            "drwngPowerPcnt": {"value": f"{float(r.drawing_power_pct) * 100:.2f}"}})
    return {"result": {"accountLimitDetails": {
        "acctDrwngPowerLimitHistMsgInq": {"olimitLL": dp_rows},
        "acctSanctLimitHistMsg": {"olimitLL": [{"applicableDate": str(b.loan_start_date), "expiryDate": "", "sanctLimit": _amt(b.sanctioned_limit)}]},
        "errors": _errors()}}}


# --------------------------------------------------------------------------- 404
@app.post("/api/404/getLoanOverduePositionEnquiry")
def api_404(body: dict):
    w = world()
    cif = body["input"]["custId"]["custId"]
    as_on = _parse(body["input"].get("asOnDate")) or _month_end(C.DEMO_MONTH)
    b = w["_borrowers"].loc[cif]
    g = w["_groups"][cif]
    idx = min(_month_idx(as_on), int(g.month_index.max()))
    hist = g[g.month_index <= idx]
    if hist.empty:      # account not yet opened on that date: no position, as Finacle would report
        return {"result": {"loanOvduRec": [], "recCtrlOut": {"isLastSet": "Y", "setNum": 1}}, "errors": _errors()}
    emi = float(b.sanctioned_limit) * EMI_SHARE_OF_LIMIT
    n = len(hist)
    last = hist.iloc[-1]
    overdue_months = max(0.0, float(last.dpd) / 30.0)
    p_ovdu = emi * overdue_months * 0.7
    i_ovdu = emi * overdue_months * 0.3
    return {"result": {"loanOvduRec": [{
        "totalIntColl": _amt(emi * 0.3 * n - i_ovdu), "totalIntDmd": _amt(emi * 0.3 * n), "totalIntOvdu": _amt(i_ovdu),
        "pTotalColl": _amt(emi * 0.7 * n - p_ovdu), "pTotalDmd": _amt(emi * 0.7 * n), "pTotalOvdu": _amt(p_ovdu),
        "acctId": {"acctId": _loan_acct(cif), "acctType": {"schmCode": SCHEME.get(b.loan_type, "LAA"), "schmType": SCHEME.get(b.loan_type, "LAA")}, "acctCurr": "INR"}}],
        "recCtrlOut": {"isLastSet": "Y", "setNum": 1}}, "errors": _errors()}


# --------------------------------------------------------------------------- 402
@app.post("/api/402/getLoanOverdueDetails")
def api_402(body: dict):
    w = world()
    cif = body["input"]["customerId"]
    as_on = _parse(body["input"].get("asOnDate")) or _month_end(C.DEMO_MONTH)
    b = w["_borrowers"].loc[cif]
    g = w["_groups"][cif]
    idx = min(_month_idx(as_on), int(g.month_index.max()))
    hist = g[g.month_index <= idx]
    if hist.empty:      # account not yet opened on that date
        return {"result": {"overdueDetails": [], "errors": _errors()}}
    last = hist.iloc[-1]
    dm = int(b.default_month)
    npa = dm >= 0 and dm <= idx
    return {"result": {"overdueDetails": [{
        "customerId": cif, "accountId": _loan_acct(cif),
        "outstandingBal": f"{float(b.sanctioned_limit) * float(last.limit_utilisation):.2f}",
        "overdueDate": (_month_end(idx - int(last.dpd) // 30).isoformat() if int(last.dpd) > 0 else ""),
        "dpd": str(int(last.dpd)), "npaStatus": "NPA" if npa else "STD",
        "totalOverdueAmt": f"{float(b.sanctioned_limit) * EMI_SHARE_OF_LIMIT * max(0.0, float(last.dpd) / 30.0):.2f}",
        "npaDate": month_index_to_date(dm).isoformat() if npa else ""}], "errors": _errors()}}


# --------------------------------------------------------------------------- 393
@app.post("/api/393/getFullAccountStatementWithPagination")
def api_393(body: dict):
    w = world()
    inp = body["input"]
    cif = _bid_from_acct(inp["acid"])
    frm, to = _parse(inp.get("fromDate")), _parse(inp.get("toDate"))
    b = w["_borrowers"].loc[cif]
    g = w["_groups"][cif]
    anchor_name = w["_anchor_names"].get(b.anchor_id, "")
    txns = []
    for r in g.itertuples(index=False):
        d = _month_end(int(r.month_index))
        if (frm and d < frm) or (to and d > to):
            continue
        ds = d.isoformat()
        bal = float(r.month_end_balance)
        seq = 0

        def add(amount, ttype, desc, cat=""):
            nonlocal seq
            seq += 1
            txns.append({"pstdDate": ds, "transactionSummary": {"instrumentId": "", "txnAmt": _amt(amount), "txnDate": ds, "txnDesc": desc, "txnType": ttype},
                         "txnBalance": _amt(bal), "txnCat": cat, "txnId": f"T{r.month_index:02d}{seq:03d}", "txnSrlNo": str(seq), "valueDate": ds})

        anchor_in = float(getattr(r, "anchor_inflow", 0.0))
        if anchor_in > 0 and anchor_name:
            add(anchor_in, "C", f"NEFT/{anchor_name.upper()}/INV SETTLEMENT", "TRANSFER")
        add(max(0.0, float(r.credits) - anchor_in), "C", "SALES RECEIPTS/VARIOUS BUYERS", "TRANSFER")
        fuel = float(r.fuel_spend)
        add(max(0.0, float(r.debits) - fuel), "D", "SUPPLIER PAYMENTS/VARIOUS", "TRANSFER")
        if fuel > 0:
            add(fuel, "D", "HPCL FUEL/FLEET CARD", "CARD")
        for _ in range(int(r.cheque_bounces_outward)):
            add(0.0, "D", "CHQ RETURN/INSUFFICIENT FUNDS", "RETURN")
        for _ in range(int(r.cheque_bounces_inward)):
            add(0.0, "C", "INWARD CHQ RETURN/DRAWER INSUFFICIENT FUNDS", "RETURN")
    return {"result": {"accountBalances": {"acid": inp["acid"], "availableBalance": _amt(g.iloc[-1].month_end_balance), "branchId": "0001",
                                           "currencyCode": "INR", "ledgerBalance": _amt(g.iloc[-1].month_end_balance)},
                       "hasMoreData": "N", "transactionDetails": txns}, "customData": {"THB": ""}}


# --------------------------------------------------------------------------- 362
@app.post("/api/362/accountLienEnquiry")
def api_362(body: dict):
    w = world()
    cif = _bid_from_acct(body["input"]["acctId"])
    as_on = _parse(body["input"].get("asOnDate")) or _month_end(C.DEMO_MONTH)
    g = w["_groups"][cif]
    idx = _month_idx(as_on)
    liens = []
    for r in g[g.month_index <= idx].itertuples(index=False):
        if int(getattr(r, "lien_count", 0)) > 0:
            d = _month_end(int(r.month_index))
            liens.append({"newLienAmt": _amt(float(r.lien_amount)), "oldLienAmt": _amt(0), "lienDate": {"startDate": d.isoformat(), "endDate": ""},
                          "reasonCode": "STATUTORY", "remarks": "Hold marked on account under statutory demand; release pending compliance.",
                          "isDeleted": "N", "lienId": f"LN{r.month_index:02d}"})
    return {"result": {"acctId": body["input"]["acctId"], "moduleType": "CA", "acctCurr": "INR", "lienDetails": liens, "errors": _errors()}}


# --------------------------------------------------------------------------- 408
@app.post("/api/408/fetchCibilScore")
def api_408(body: dict):
    return {"fetchCibilScoreResponse": {"header": {"success": "true", "statusCode": 200, "statusMessage": "OK"},
                                        "body": {"dcResponse": {"status": "SUCCESS", "decision": "REFER",
                                                                "bureauResponse": {"status": "SUCCESS", "isSuccess": "true"}}}}}


@app.get("/api/health")
def health():
    w = world()
    return {"status": "ok", "mock": "IDBI Finacle-shaped sandbox", "borrowers": int(len(w["_borrowers"])),
            "apis": ["394", "391", "441", "404", "402", "393", "362", "408"]}
