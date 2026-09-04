"""Field and unit translations from IDBI's API catalogue (api req response hackathon.xlsx) to the
PRAHARI table contract. Pure functions over parsed JSON, unit-testable against sample payloads.

Catalogue references: 391 getLoanAccountDetails, 394 getCustomerAccountsByCustId, 441
fetchLoanAccountLimits, 404 getLoanOverduePositionEnquiry (asOnDate), 402 getLoanOverdueDetails,
393 getFullAccountStatementWithPagination, 362 accountLienEnquiry, 408 fetch CIBIL Score.
"""

from __future__ import annotations

import re
from datetime import date

import numpy as np
import pandas as pd

SCHEME_TO_LOAN_TYPE = {"CC": "CC", "CCA": "CC", "ODA": "OD", "OD": "OD", "LAA": "term", "TL": "term", "TLA": "term"}
RETURN_MARKERS = ("RETURN", "RTN", "BOUNCE", "DISHONOUR", "INSUFFICIENT")
FUEL_MARKERS = ("HPCL", "BPCL", "IOCL", "INDIAN OIL", "PETROL", "DIESEL", "FUEL", "FREIGHT", "TRANSPORT")


def amount(obj) -> float:
    """Finacle amounts arrive as {"amountValue": "...", "currencyCode": "INR"} or plain numbers."""
    if obj is None:
        return 0.0
    if isinstance(obj, dict):
        obj = obj.get("amountValue", obj.get("value", 0.0))
    try:
        return float(str(obj).replace(",", "") or 0.0)
    except ValueError:
        return 0.0


def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%m-%y", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(s[:19], fmt).date()
        except ValueError:
            continue
    return None


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_index_of(d: date, start: date) -> int:
    return (d.year - start.year) * 12 + (d.month - start.month)


def loan_type_from_391(resp: dict) -> str:
    r = resp.get("result", resp)
    code = str(((r.get("loanAcctId") or {}).get("acctType") or {}).get("schmType", "")).upper()
    return SCHEME_TO_LOAN_TYPE.get(code, "term" if code.startswith("L") else "CC")


def static_from_391(resp: dict, borrower_id: str) -> dict:
    r = resp.get("result", resp)
    gen = r.get("loanGenDetails") or {}
    addr = ((r.get("loanAcctId") or {}).get("bankInfo") or {}).get("postAddr") or {}
    return dict(borrower_id=borrower_id,
                name=(r.get("loanAcctGenInfo") or {}).get("acctName") or ((r.get("custId") or {}).get("personName") or {}).get("name", borrower_id),
                loan_type=loan_type_from_391(resp),
                sanctioned_limit=amount(gen.get("loanAmt")) or amount(r.get("disbAmt")),
                loan_start_date=str(r.get("acctOpenDt", "")),
                city=addr.get("city", ""), state=addr.get("stateProv", ""),
                restructured=bool((gen.get("reschedParams") or {}).get("reschedAmtFlg") in ("Y", "y", True)),
                operating_account=((gen.get("operAcctId") or {}).get("acctId") or ""))


def limits_from_441(resp: dict) -> pd.DataFrame:
    """Dated drawing-power and sanction history -> DataFrame[date, drawing_power, sanction]."""
    r = (resp.get("result", resp).get("accountLimitDetails") or {})
    dp_rows = ((r.get("acctDrwngPowerLimitHistMsgInq") or {}).get("olimitLL") or [])
    sl_rows = ((r.get("acctSanctLimitHistMsg") or {}).get("olimitLL") or [])
    dp = pd.DataFrame([dict(date=parse_date(x.get("applicableDate")), drawing_power=amount(x.get("drwngPower"))) for x in dp_rows])
    sl = pd.DataFrame([dict(date=parse_date(x.get("applicableDate")), sanction=amount(x.get("sanctLimit"))) for x in sl_rows])
    return dp, sl


def value_asof(hist: pd.DataFrame, col: str, when: date, default: float = 0.0) -> float:
    if hist is None or hist.empty:
        return default
    h = hist.dropna(subset=["date"]).sort_values("date")
    h = h[h.date <= when]
    return float(h[col].iloc[-1]) if len(h) else default


def overdue_from_402(resp: dict) -> dict | None:
    """None when the bank holds no position for that account on that date (not yet opened)."""
    rows = (resp.get("result", resp).get("overdueDetails") or [])
    if not rows:
        return None
    x = rows[0]
    return dict(dpd=int(float(x.get("dpd") or 0)), npa_status=str(x.get("npaStatus", "")),
                npa_date=parse_date(x.get("npaDate")), outstanding=amount(x.get("outstandingBal")),
                overdue_amt=amount(x.get("totalOverdueAmt")))


def position_from_404(resp: dict) -> dict:
    recs = (resp.get("result", resp).get("loanOvduRec") or [])
    if not recs:
        return dict(int_dmd=0.0, int_coll=0.0, int_ovdu=0.0, p_dmd=0.0, p_coll=0.0, p_ovdu=0.0)
    x = recs[0]
    return dict(int_dmd=amount(x.get("totalIntDmd")), int_coll=amount(x.get("totalIntColl")),
                int_ovdu=amount(x.get("totalIntOvdu")), p_dmd=amount(x.get("pTotalDmd")),
                p_coll=amount(x.get("pTotalColl")), p_ovdu=amount(x.get("pTotalOvdu")))


def repayment_from_position(pos: dict, dpd: int) -> tuple[str, int]:
    """repayment_status and emi_days_late from demanded-vs-collected and DPD.
    missed: 60+ DPD (two instalments unpaid); delayed: any overdue; else on time."""
    overdue = (pos["p_ovdu"] + pos["int_ovdu"]) > 0
    if dpd >= 60:
        return "missed", dpd
    if dpd > 0 or overdue:
        return "delayed", max(dpd, 1)
    return "on_time", 0


_GENERIC_PAYERS = {"SALES RECEIPTS", "VARIOUS BUYERS", "VARIOUS", "CASH DEPOSIT", "INTEREST", "REVERSAL", "REFUND",
                   "INWARD CHQ RETURN", "DRAWER INSUFFICIENT FUNDS", "INV SETTLEMENT", "SETTLEMENT"}


def statement_month_aggregates(txns: list[dict]) -> pd.DataFrame:
    """API 393 transactions -> per-month credits, debits, closing balance, cheque returns, fuel spend,
    and per-payer credit totals (for the contagion graph)."""
    rows = []
    for t in txns:
        d = parse_date(t.get("valueDate") or t.get("pstdDate") or (t.get("transactionSummary") or {}).get("txnDate"))
        if d is None:
            continue
        ts = t.get("transactionSummary") or {}
        amt = amount(ts.get("txnAmt") or t.get("amount"))
        ttype = str(ts.get("txnType") or t.get("type") or "").upper()
        desc = str(ts.get("txnDesc") or t.get("narration") or "").upper()
        cat = str(t.get("txnCat") or "").upper()
        bal = amount(t.get("txnBalance") or t.get("balance") or t.get("currentBalance"))
        is_credit = ttype.startswith("C")
        rows.append(dict(month=month_key(d), date=d, credit=amt if is_credit else 0.0, debit=0.0 if is_credit else amt,
                         balance=bal, ret_in=int(is_credit and any(m in desc or m in cat for m in RETURN_MARKERS)),
                         ret_out=int((not is_credit) and any(m in desc or m in cat for m in RETURN_MARKERS)),
                         fuel=amt if ((not is_credit) and any(m in desc for m in FUEL_MARKERS)) else 0.0,
                         payer=_payer_from_narration(desc) if is_credit else ""))
    if not rows:
        return pd.DataFrame(columns=["month", "credits", "debits", "month_end_balance", "cheque_bounces_inward",
                                     "cheque_bounces_outward", "fuel_spend", "payer_credits"])
    df = pd.DataFrame(rows).sort_values("date")
    agg = df.groupby("month").agg(credits=("credit", "sum"), debits=("debit", "sum"),
                                  month_end_balance=("balance", "last"), cheque_bounces_inward=("ret_in", "sum"),
                                  cheque_bounces_outward=("ret_out", "sum"), fuel_spend=("fuel", "sum")).reset_index()
    payer = df[df.payer != ""].groupby(["month", "payer"]).credit.sum().reset_index()
    agg["payer_credits"] = agg.month.map(lambda m: payer[payer.month == m].set_index("payer").credit.to_dict())
    return agg


def _payer_from_narration(desc: str) -> str:
    """Best-effort counterparty from a credit narration like 'NEFT/BHARAT AUTO COMPONENTS/INV 2231'."""
    parts = [p.strip() for p in re.split(r"[/|:-]", desc) if p.strip()]
    for p in parts:
        if p in ("NEFT", "RTGS", "IMPS", "UPI", "TRF", "CLG", "CHQ", "BY TRANSFER", "TO TRANSFER"):
            continue
        if p in _GENERIC_PAYERS or any(p.startswith(g) for g in _GENERIC_PAYERS):
            return ""
        if re.search(r"[A-Z]{3,}", p) and not re.fullmatch(r"[A-Z]*\d+[A-Z\d]*", p):
            return p.title()
    return ""


def liens_from_362(resp: dict) -> pd.DataFrame:
    r = resp.get("result", resp)
    det = r.get("lienDetails")
    rows = det if isinstance(det, list) else ([det] if det else [])
    out = []
    for x in rows:
        if str(x.get("isDeleted", "N")).upper() in ("Y", "TRUE"):
            continue
        start = parse_date((x.get("lienDate") or {}).get("startDate"))
        out.append(dict(date=start, month=month_key(start) if start else None, amount=amount(x.get("newLienAmt")),
                        reason=str(x.get("reasonCode", "")), remarks=str(x.get("remarks", ""))))
    return pd.DataFrame(out)
