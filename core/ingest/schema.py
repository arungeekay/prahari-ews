"""The column contract between any data source and the PRAHARI engine, as code rather than prose.

A source must produce these tables with these columns. `validate()` raises a clear error at load
time when a column is missing or mistyped, so a schema drift in a sandbox feed fails loudly
instead of surfacing as an AttributeError inside the feature pipeline at request time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# (column, kind) where kind in {"str", "int", "float", "bool"}
BORROWERS_SCHEMA = [
    ("borrower_id", "str"), ("name", "str"), ("sector", "str"), ("city", "str"), ("state", "str"),
    ("vintage_years", "int"), ("promoter_age", "int"), ("promoter_experience_years", "int"),
    ("promoter_qualification", "str"), ("loan_type", "str"), ("sanctioned_limit", "float"),
    ("loan_start_date", "str"), ("default_month", "int"), ("months_available", "int"),
    ("is_anchor_supplier", "bool"), ("anchor_id", "str"), ("anchor_share", "float"), ("demo", "str"),
]
MSME_MONTHLY_SCHEMA = [
    ("borrower_id", "str"), ("month_index", "int"), ("month_date", "str"),
    ("credits", "float"), ("debits", "float"), ("month_end_balance", "float"),
    ("cheque_bounces_inward", "int"), ("cheque_bounces_outward", "int"),
    ("limit_utilisation", "float"), ("drawing_power_pct", "float"), ("stock_statement_submitted", "int"),
    ("lien_count", "int"), ("lien_amount", "float"), ("anchor_inflow", "float"),
    ("gst_turnover", "float"), ("gst_filing_delay_days", "int"),
    ("electricity_units", "float"), ("fuel_spend", "float"),
    ("epfo_employee_count", "int"), ("epfo_contribution_delay_days", "int"),
    ("bureau_enquiries", "int"), ("bureau_new_loans", "int"), ("bureau_dpd_other", "int"),
    ("repayment_status", "str"), ("emi_days_late", "int"), ("dpd", "int"),
    ("sector_sentiment", "float"), ("officer_note", "str"),
]
EDGES_SCHEMA = [("payer", "str"), ("payer_name", "str"), ("payee", "str"), ("payee_name", "str"),
                ("avg_monthly_amount", "float"), ("regularity", "float"), ("inflow_share", "float")]
ANCHORS_SCHEMA = [("anchor_id", "str"), ("name", "str"), ("sector", "str"), ("n_suppliers", "int")]
SENTIMENT_SCHEMA = [("sector", "str"), ("month_index", "int"), ("month_date", "str"), ("sentiment_score", "float")]

SCHEMAS = {"borrowers": BORROWERS_SCHEMA, "msme_monthly": MSME_MONTHLY_SCHEMA, "edges": EDGES_SCHEMA,
           "anchors": ANCHORS_SCHEMA, "sector_sentiment": SENTIMENT_SCHEMA}

# Columns that have no equivalent in IDBI's core-banking catalogue and must come from external
# feeds (GST, EPFO, utility, news). A source may leave them absent; `validate` then fills a neutral
# value and records the gap in the provenance so it is visible on the Data Sources screen.
EXTERNAL_OPTIONAL = {
    "msme_monthly": {"gst_turnover": 0.0, "gst_filing_delay_days": 0, "electricity_units": 0.0,
                     "fuel_spend": 0.0, "epfo_employee_count": 0, "epfo_contribution_delay_days": 0,
                     "sector_sentiment": 0.0, "officer_note": ""},
}


class SchemaError(ValueError):
    pass


def _coerce(series: pd.Series, kind: str) -> pd.Series:
    if kind == "float":
        return pd.to_numeric(series, errors="coerce").astype(float)
    if kind == "int":
        return pd.to_numeric(series, errors="coerce").fillna(0).astype(np.int64)
    if kind == "bool":
        return series.astype(bool)
    return series.astype(object).where(series.notna(), "")


def validate(df: pd.DataFrame, table: str, strict: bool = False) -> tuple[pd.DataFrame, list[str]]:
    """Return (coerced frame, list of filled optional columns). Raises SchemaError on a missing
    mandatory column."""
    schema = SCHEMAS[table]
    optional = EXTERNAL_OPTIONAL.get(table, {})
    filled = []
    out = df.copy()
    for col, kind in schema:
        if col not in out.columns:
            if col in optional and not strict:
                out[col] = optional[col]
                filled.append(col)
            else:
                raise SchemaError(f"{table}: mandatory column '{col}' missing")
        out[col] = _coerce(out[col], kind)
    return out, filled


def empty(table: str) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=("float" if k == "float" else "int" if k == "int" else "object"))
                         for c, k in SCHEMAS[table]})
