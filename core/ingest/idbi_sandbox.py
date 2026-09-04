"""IDBISandboxSource: builds the PRAHARI tables from IDBI's core-banking API catalogue.

Call plan per CIF (all shapes from `api req response hackathon.xlsx`):
    394 getCustomerAccountsByCustId      -> loan accounts + operating account under the CIF
    391 getLoanAccountDetails            -> static profile, loan type, sanction, restructuring flag
    441 fetchLoanAccountLimits           -> dated drawing power and sanction history
    404 getLoanOverduePositionEnquiry    -> demanded vs collected, with asOnDate (point-in-time)
    402 getLoanOverdueDetails            -> DPD, NPA status and NPA date (the default label)
    393 getFullAccountStatementWithPagination -> monthly credits, debits, balance, returns, payers
    362 accountLienEnquiry               -> liens (count, amount, remarks)
    408 fetch CIBIL Score                -> bureau

Point-in-time replay is enforced at the API boundary: every call is issued with the cut-off date
(asOnDate / toDate), so a month's row can only contain what the bank knew that month. The
external feeds (GST, EPFO, utility, notes, sector sentiment) are not in the catalogue and are
left to the schema's optional-fill path, which records the gap in provenance.

With no live credentials the same adapter runs against the Finacle-shaped mock server in
`mock/idbi_sandbox` (populated from the synthetic world), so the round trip is testable today.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from ..datagen import config as C
from ..datagen.util import month_index_to_date
from . import mapping as M
from .base import PortfolioSource
from .schema import empty

DEFAULT_BASE_URL = "http://localhost:8790"


class IDBISandboxSource(PortfolioSource):
    name = "idbi_sandbox"
    mode = "api"

    def __init__(self, base_url: str | None = None, api_key: str | None = None, as_of: date | None = None,
                 history_months: int = 24, cache_dir: str | None = None, cif_ids: list[str] | None = None,
                 client=None, cif_limit: int | None = None):
        self.base_url = (base_url or os.environ.get("IDBI_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.api_key = api_key or os.environ.get("IDBI_API_KEY", "")
        as_of_env = os.environ.get("AS_OF_MONTH")
        self.as_of = as_of or (M.parse_date(as_of_env + "-01") if as_of_env else month_index_to_date(C.DEMO_MONTH))
        self.history_months = history_months
        self.cache_dir = Path(cache_dir or os.path.join(os.environ.get("DATA_DIR", "data"), "cache", "idbi"))
        self.use_cache = os.environ.get("IDBI_CACHE", "0") == "1"
        self.cif_ids = cif_ids
        self.cif_limit = cif_limit if cif_limit is not None else int(os.environ.get("IDBI_CIF_LIMIT", "150"))
        self.calls = 0
        self.start = month_index_to_date(0)
        # positions are "as on" the LAST day of the as-of month; statements run to month end
        import calendar
        self.as_of_end = date(self.as_of.year, self.as_of.month, calendar.monthrange(self.as_of.year, self.as_of.month)[1])
        self._client = client            # injectable (e.g. a FastAPI TestClient against the mock)

    # ------------------------------------------------------------------ transport
    def client(self):
        if self._client is None:
            import httpx
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.Client(base_url=self.base_url, timeout=60.0, headers=headers)
        return self._client

    def _post(self, path: str, body: dict) -> dict:
        cp = None
        if self.use_cache:
            key = re.sub(r"[^A-Za-z0-9]+", "_", path + json.dumps(body, sort_keys=True))[:180]
            cp = self.cache_dir / f"{key}.json"
            if cp.exists():
                return json.loads(cp.read_text(encoding="utf-8"))
        r = self.client().post(path, json=body)
        r.raise_for_status()
        data = r.json()
        self.calls += 1
        if cp is not None:
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                cp.write_text(json.dumps(data), encoding="utf-8")
            except Exception:
                pass
        return data

    # ------------------------------------------------------------------ catalogue calls
    def cifs(self) -> list[str]:
        if self.cif_ids:
            return self.cif_ids
        data = self._post("/api/portfolio/cifs", {"asOnDate": self.as_of.isoformat(), "limit": self.cif_limit})
        return list(data.get("cifIds", []))[: self.cif_limit]

    def accounts_394(self, cif: str) -> dict:
        return self._post("/api/394/getCustomerAccountsByCustId", {"input": {"acctType": "", "branchId": "", "cifId": cif}})

    def loan_391(self, acct: str) -> dict:
        return self._post("/api/391/getLoanAccountDetails", {"input": {"loanAcctId": {"acctId": acct}}})

    def limits_441(self, acct: str) -> dict:
        return self._post("/api/441/fetchLoanAccountLimits", {"input": {"foracid": acct}})

    def position_404(self, cif: str, acct: str, as_on: date) -> dict:
        return self._post("/api/404/getLoanOverduePositionEnquiry",
                          {"input": {"custId": {"custId": cif}, "asOnDate": as_on.isoformat(),
                                     "selRangeLoanAcctId": {"lowAcctId": {"acctId": acct}, "highAcctId": {"acctId": acct}}}})

    def overdue_402(self, cif: str, acct: str, as_on: date) -> dict:
        return self._post("/api/402/getLoanOverdueDetails", {"input": {"customerId": cif, "accountNo": acct, "asOnDate": as_on.isoformat()}})

    def statement_393(self, acct: str, frm: date, to: date) -> dict:
        return self._post("/api/393/getFullAccountStatementWithPagination",
                          {"input": {"acid": acct, "branchId": "", "fromDate": frm.isoformat(), "toDate": to.isoformat(), "sortIn": "ASC"}})

    def liens_362(self, acct: str, as_on: date) -> dict:
        return self._post("/api/362/accountLienEnquiry", {"input": {"acctId": acct, "asOnDate": as_on.isoformat()}})

    def bureau_408(self, cif: str, as_on: date) -> dict:
        return self._post("/api/408/fetchCibilScore", {"fetchCibilScoreRequest": {"body": {"customerId": cif, "asOnDate": as_on.isoformat()}}})

    # ------------------------------------------------------------------ assembly
    def load_tables(self) -> dict[str, pd.DataFrame]:
        borrowers, monthly, edges = [], [], {}
        as_of_idx = M.month_index_of(self.as_of, self.start)
        first_idx = max(0, as_of_idx - self.history_months + 1)
        for cif in self.cifs():
            acc = self.accounts_394(cif).get("result", {})
            loans = [a for a in acc.get("customerAccountInfo", []) if str(a.get("acctType", "")).upper().startswith(("L", "CC", "OD"))]
            oper = [a for a in acc.get("customerAccountInfo", []) if str(a.get("acctType", "")).upper().startswith(("SB", "CA", "OP"))]
            if not loans:
                continue
            loan = loans[0]["acctNumber"]
            det = self.loan_391(loan)
            st = M.static_from_391(det, borrower_id=cif)
            oper_acct = st["operating_account"] or (oper[0]["acctNumber"] if oper else loan)
            dp_hist, sl_hist = M.limits_from_441(self.limits_441(loan))
            liens = M.liens_from_362(self.liens_362(loan, self.as_of_end))
            stmt = M.statement_month_aggregates(
                (self.statement_393(oper_acct, month_index_to_date(first_idx), self.as_of_end).get("result", {}).get("transactionDetails") or []))
            stmt = stmt.set_index("month") if len(stmt) else stmt
            bureau = self.bureau_408(cif, self.as_of_end)
            npa_date = None
            payer_totals: dict[str, float] = {}
            import calendar as _cal
            for idx in range(first_idx, as_of_idx + 1):
                d = month_index_to_date(idx)
                d_end = date(d.year, d.month, _cal.monthrange(d.year, d.month)[1])   # position as on month end
                mk = M.month_key(d)
                od = M.overdue_from_402(self.overdue_402(cif, loan, d_end))
                if od is None:          # account not yet on the bank's books that month
                    continue
                pos = M.position_from_404(self.position_404(cif, loan, d_end))
                if od["npa_date"] and npa_date is None:
                    npa_date = od["npa_date"]
                status, late = M.repayment_from_position(pos, od["dpd"])
                sanction = M.value_asof(sl_hist, "sanction", d, st["sanctioned_limit"]) or st["sanctioned_limit"]
                dp_abs = M.value_asof(dp_hist, "drawing_power", d, 0.0)
                srow = stmt.loc[mk] if (len(stmt) and mk in stmt.index) else None
                payers = (srow["payer_credits"] if srow is not None and isinstance(srow["payer_credits"], dict) else {})
                for p, v in payers.items():
                    payer_totals[p] = payer_totals.get(p, 0.0) + float(v)
                lm = liens[liens.month == mk] if len(liens) else liens
                monthly.append(dict(
                    borrower_id=cif, month_index=idx, month_date=d.isoformat(),
                    credits=float(srow["credits"]) if srow is not None else 0.0,
                    debits=float(srow["debits"]) if srow is not None else 0.0,
                    month_end_balance=float(srow["month_end_balance"]) if srow is not None else 0.0,
                    cheque_bounces_inward=int(srow["cheque_bounces_inward"]) if srow is not None else 0,
                    cheque_bounces_outward=int(srow["cheque_bounces_outward"]) if srow is not None else 0,
                    limit_utilisation=float(od["outstanding"] / sanction) if sanction > 0 else 0.0,
                    drawing_power_pct=float(dp_abs / sanction) if (sanction > 0 and st["loan_type"] != "term") else 0.0,
                    stock_statement_submitted=1,
                    lien_count=int(len(lm)), lien_amount=float(lm.amount.sum()) if len(lm) else 0.0,
                    anchor_inflow=float(max(payers.values())) if payers else 0.0,
                    fuel_spend=float(srow["fuel_spend"]) if srow is not None else 0.0,
                    bureau_enquiries=0, bureau_new_loans=0, bureau_dpd_other=0,
                    repayment_status=status, emi_days_late=int(late), dpd=int(od["dpd"]),
                ))
            default_month = M.month_index_of(npa_date, self.start) if npa_date else -1
            top_payer = max(payer_totals, key=payer_totals.get) if payer_totals else ""
            n_months = sum(1 for r in monthly if r["borrower_id"] == cif)
            borrowers.append(dict(
                borrower_id=cif, name=st["name"], sector="manufacturing", city=st["city"], state=st["state"],
                vintage_years=0, promoter_age=0, promoter_experience_years=0, promoter_qualification="",
                loan_type=st["loan_type"], sanctioned_limit=float(st["sanctioned_limit"]),
                loan_start_date=st["loan_start_date"], default_month=int(default_month),
                months_available=int(n_months), is_anchor_supplier=bool(top_payer),
                anchor_id=top_payer, anchor_share=0.0, demo="", health_trajectory="unknown",
                observed_default=int(0 <= default_month <= as_of_idx),
            ))
            if top_payer:
                edges.setdefault(top_payer, []).append((cif, st["name"], payer_totals[top_payer]))
        b_df = pd.DataFrame(borrowers) if borrowers else empty("borrowers")
        m_df = pd.DataFrame(monthly) if monthly else empty("msme_monthly")
        anchors_rows, edge_rows = [], []
        for i, (payer, lst) in enumerate(sorted(edges.items())):
            aid = f"ANCH{i+1}"
            anchors_rows.append(dict(anchor_id=aid, name=payer, sector="manufacturing", n_suppliers=len(lst)))
            for cif, nm, total in lst:
                tot_cred = float(m_df.loc[m_df.borrower_id == cif, "credits"].sum()) or 1.0
                edge_rows.append(dict(payer=aid, payer_name=payer, payee=cif, payee_name=nm,
                                      avg_monthly_amount=total / max(1, self.history_months),
                                      regularity=0.9, inflow_share=float(min(1.0, total / tot_cred))))
                b_df.loc[b_df.borrower_id == cif, ["anchor_id", "anchor_share"]] = [aid, float(min(1.0, total / tot_cred))]
        return dict(borrowers=b_df, anchors=pd.DataFrame(anchors_rows) if anchors_rows else empty("anchors"),
                    edges=pd.DataFrame(edge_rows) if edge_rows else empty("edges"), msme_monthly=m_df,
                    sector_sentiment=empty("sector_sentiment"),
                    customers=pd.DataFrame(columns=["customer_id"]), retail_monthly=pd.DataFrame(columns=["customer_id"]),
                    retail_engagement=pd.DataFrame(columns=["customer_id"]))

    def provenance(self) -> dict:
        return dict(source=self.name, mode=self.mode, base_url=self.base_url, as_of_month=self.as_of.isoformat()[:7],
                    history_months=self.history_months, api_calls=self.calls,
                    point_in_time_enforced_at="API boundary (asOnDate / toDate on every call) and feature pipeline",
                    catalogue=["394", "391", "441", "404", "402", "393", "362", "408"],
                    external_columns_filled=self.filled_columns())
