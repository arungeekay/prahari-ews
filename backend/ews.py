"""RBI Early Warning Signal (EWS) indicator mapping.

RBI's Master Directions on Fraud Risk Management in Commercial Banks (July 2024) require an EWS
framework built on quantitative and qualitative indicators. The families below paraphrase the
kind of indicators that framework expects a bank to monitor and map each to the PRAHARI features
that evidence it, with a trigger rule. This turns a model flag into the vocabulary a compliance
officer already reports in, and lets the memo say which EWS indicators an account has tripped.

The wording is a paraphrase for traceability, not the regulation's text; a bank would substitute
its own approved indicator list here.
"""

from __future__ import annotations

# (id, indicator family (paraphrased), features, predicate(feat) -> bool, evidence(feat) -> str)
INDICATORS = [
    ("EWS-01", "Delay or non-submission of stock and book-debt statements",
     ["stmt_missed_cnt"], lambda f: f.get("stmt_missed_cnt", 0) >= 1,
     lambda f: f"stock statement missing in {f.get('stmt_missed_cnt', 0):.0f} of the last 6 months"),
    ("EWS-02", "Drawings in excess of drawing power; drawing power eroding",
     ["over_dp_months", "drawn_over_dp_last", "dp_gap_slope"],
     lambda f: f.get("over_dp_months", 0) >= 1 or f.get("dp_gap_slope", 0) > 0.01,
     lambda f: f"over DP in {f.get('over_dp_months', 0):.0f} month(s); drawings at {f.get('drawn_over_dp_last', 0):.0%} of DP"),
    ("EWS-03", "Return of cheques or failed mandates",
     ["bounce_out_sum", "bounce_in_sum"], lambda f: f.get("bounce_out_sum", 0) >= 1 or f.get("bounce_in_sum", 0) >= 2,
     lambda f: f"{f.get('bounce_out_sum', 0):.0f} outward and {f.get('bounce_in_sum', 0):.0f} inward returns in window"),
    ("EWS-04", "Delay in payment of statutory dues (GST, provident fund)",
     ["gst_delay_max", "epfo_delay_max"], lambda f: f.get("gst_delay_max", 0) >= 10 or f.get("epfo_delay_max", 0) >= 10,
     lambda f: f"GST filed up to {f.get('gst_delay_max', 0):.0f} days late; EPFO remittance up to {f.get('epfo_delay_max', 0):.0f} days late"),
    ("EWS-05", "Liens, attachment orders or statutory holds on the account",
     ["lien_cnt_sum", "lien_amt_over_limit"], lambda f: f.get("lien_cnt_sum", 0) >= 1,
     lambda f: f"{f.get('lien_cnt_sum', 0):.0f} lien(s), {f.get('lien_amt_over_limit', 0):.0%} of sanction"),
    ("EWS-06", "Unexplained decline in turnover routed through the account",
     ["credit_last_over_first", "credit_slope"], lambda f: f.get("credit_last_over_first", 1.0) < 0.8,
     lambda f: f"credit turnover at {f.get('credit_last_over_first', 1.0):.0%} of six months ago"),
    ("EWS-07", "Concentration of receivables on a few buyers; buyer payment delays",
     ["anchor_dependence", "anchor_inflow_slope", "note_theme_receivables"],
     lambda f: (f.get("anchor_dependence", 0) >= 0.3 and f.get("anchor_inflow_slope", 0) < 0) or f.get("note_theme_receivables", 0) >= 1,
     lambda f: f"{f.get('anchor_dependence', 0):.0%} of inflows from one buyer; receivable delays noted" if f.get("note_theme_receivables", 0) else f"{f.get('anchor_dependence', 0):.0%} of inflows from one buyer, payments falling"),
    ("EWS-08", "Promoter unavailable, evasive or in dispute",
     ["note_theme_promoter", "note_sent_min"], lambda f: f.get("note_theme_promoter", 0) >= 1 and f.get("note_sent_min", 0) < -0.4,
     lambda f: "adverse officer observation on promoter conduct"),
    ("EWS-09", "Idle capacity, closure of unit, fall in utility consumption",
     ["electricity_slope", "note_theme_capacity"], lambda f: f.get("electricity_slope", 0) < -0.02 or f.get("note_theme_capacity", 0) >= 1,
     lambda f: "electricity consumption falling" + ("; idle capacity noted on visit" if f.get("note_theme_capacity", 0) else "")),
    ("EWS-10", "Delay in servicing interest or instalments (SMA ladder)",
     ["dpd_max", "delayed_cnt", "missed_cnt"], lambda f: f.get("dpd_max", 0) >= 1,
     lambda f: f"reached {f.get('dpd_max', 0):.0f} days past due; {f.get('delayed_cnt', 0):.0f} delayed, {f.get('missed_cnt', 0):.0f} missed"),
    ("EWS-11", "Adverse conduct with other lenders; fresh borrowing elsewhere",
     ["bureau_dpd_other_max", "bureau_newloans_sum", "bureau_enq_sum"],
     lambda f: f.get("bureau_dpd_other_max", 0) >= 30 or f.get("bureau_newloans_sum", 0) >= 1 or f.get("bureau_enq_sum", 0) >= 3,
     lambda f: f"other-lender DPD {f.get('bureau_dpd_other_max', 0):.0f}; {f.get('bureau_newloans_sum', 0):.0f} new loan(s); {f.get('bureau_enq_sum', 0):.0f} enquiries"),
    ("EWS-12", "Reduction in workforce, wage arrears or labour stress",
     ["epfo_emp_slope", "note_theme_labour"], lambda f: f.get("epfo_emp_slope", 0) < -0.5 or f.get("note_theme_labour", 0) >= 1,
     lambda f: "headcount shrinking" + ("; wage delays noted" if f.get("note_theme_labour", 0) else "")),
    ("EWS-13", "Legal notices, litigation or regulatory action",
     ["note_theme_legal"], lambda f: f.get("note_theme_legal", 0) >= 1,
     lambda f: "legal or statutory issue noted by officer"),
    ("EWS-14", "Utilisation persistently near sanctioned limit (utilisation creep)",
     ["util_last", "util_slope"], lambda f: f.get("util_last", 0) >= 0.85 and f.get("util_slope", 0) > 0.01,
     lambda f: f"utilisation {f.get('util_last', 0):.0%}, rising {f.get('util_slope', 0) * 100:.1f} points a month"),
]

SOURCE = ("Indicator families paraphrased from the RBI Master Directions on Fraud Risk Management in "
          "Commercial Banks (2024) EWS framework; a bank substitutes its approved indicator list here.")


def evaluate(feat: dict) -> list[dict]:
    """Which EWS indicator families this account trips, with the evidencing values."""
    out = []
    for iid, name, feats, pred, ev in INDICATORS:
        try:
            hit = bool(pred(feat))
        except Exception:
            hit = False
        out.append(dict(id=iid, indicator=name, features=feats, triggered=hit, evidence=ev(feat) if hit else ""))
    return out


def summary() -> dict:
    return dict(source=SOURCE, indicators=[dict(id=i, indicator=n, features=f) for i, n, f, _, _ in INDICATORS])
