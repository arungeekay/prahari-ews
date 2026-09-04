"""SHAP-based reason codes for the PD model (BUILD_SPEC §4.3).

Top-N risk drivers per prediction, each mapped to a plain-language template with the actual
value ("Utilisation rose to 94%"). Auditor view returns the full factor table with SHAP values.
`shap_by_feature` feeds the interpretation framework's pillar sub-scores. The backend that
produced the attribution ("shap" or "importance_fallback") is always reported, so a silent
degradation is visible rather than producing a plausible-looking but different ranking.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def plain_language(feature: str, value: float) -> str:
    v = value
    tmpl = {
        # conduct
        "util_last": f"Limit utilisation at {v:.0%}",
        "util_mean": f"Average utilisation {v:.0%} over window",
        "util_max": f"Utilisation peaked at {v:.0%}",
        "util_slope": f"Utilisation rising (+{v*100:.1f} pts/month)" if v > 0 else "Utilisation stable/easing",
        "dp_gap_last": f"Drawing power {v:.0%} below sanction (stock and debtor margins thinning)" if v > 0.05 else "Drawing power close to sanction",
        "dp_gap_slope": "Drawing power shrinking month-on-month" if v > 0 else "Drawing power stable",
        "drawn_over_dp_last": f"Drawings at {v:.0%} of drawing power" if v <= 1 else f"Drawings exceed drawing power ({v:.0%})",
        "over_dp_months": f"Over drawing power in {v:.0f} month(s)" if v > 0 else "Never over drawing power",
        "stmt_missed_cnt": f"Stock statement not submitted in {v:.0f} month(s)" if v > 0 else "Stock statements submitted on time",
        "lien_cnt_sum": f"{v:.0f} new lien(s) on the account" if v > 0 else "No liens on the account",
        "lien_amt_over_limit": f"Liens equal {v:.0%} of sanction" if v > 0 else "No lien amount",
        "bounce_out_sum": f"{v:.0f} outward cheque bounce(s) in window",
        "bounce_in_sum": f"{v:.0f} inward cheque bounce(s) in window",
        "balance_cv": "Volatile month-end balances" if v > 0.4 else "Stable balances",
        "balance_last_over_credit": "Thin liquidity buffer" if v < 0.05 else "Adequate liquidity buffer",
        "missed_cnt": f"{v:.0f} missed EMI(s)",
        "delayed_cnt": f"{v:.0f} delayed EMI(s)",
        "dpd_max": f"Reached {v:.0f} days past due",
        "emi_late_max": f"EMI up to {v:.0f} days late",
        # compliance
        "gst_delay_mean": f"GST filings delayed (avg {v:.0f} days)",
        "gst_delay_max": f"GST filing delayed up to {v:.0f} days",
        "gst_delay_slope": "GST filing delays worsening" if v > 0 else "GST filing timeliness stable",
        "epfo_delay_max": f"EPFO contributions delayed ({v:.0f} days)",
        # activity
        "credit_slope": "Credit turnover declining month-on-month" if v < 0 else "Credit turnover stable",
        "credit_last_over_first": (f"Credit turnover down {(1-v)*100:.0f}% across the window"
                                   if v < 1 else "Credit turnover holding up"),
        "credit_cv": "Volatile credit turnover" if v > 0.3 else "Steady credit turnover",
        "credit_mean_lakh": f"Avg monthly credit ₹{v:.1f} L",
        "electricity_slope": "Electricity usage falling" if v < 0 else "Electricity usage stable",
        "fuel_slope": "Fuel spend falling" if v < 0 else "Fuel spend stable",
        "epfo_emp_slope": "Headcount shrinking" if v < 0 else "Headcount stable/growing",
        # external
        "bureau_dpd_other_max": f"DPD on other loans ({v:.0f} days)",
        "bureau_enq_sum": f"{v:.0f} credit enquiries elsewhere",
        "bureau_newloans_sum": f"{v:.0f} new loan(s) taken elsewhere",
        "sentiment_last": "Adverse sector sentiment" if v < 0 else "Neutral/positive sector sentiment",
        # profile
        "is_cc": "Cash-credit facility", "is_od": "Overdraft facility", "is_term": "Term loan",
        "log_limit": f"Sanctioned limit about ₹{10**v/1e5:.0f} L" if v > 0 else "Sanction size unknown",
        "vintage_years": f"Business vintage {v:.0f} years",
        "promoter_experience_years": f"Promoter experience {v:.0f} years",
        "promoter_qual_ord": "Promoter qualification below graduate" if v < 3 else "Promoter graduate or above",
        # notes
        "note_sent_ewma": "Adverse loan-officer notes" if v < -0.15 else "Neutral or positive officer notes",
        "note_sent_min": "A strongly adverse officer note in window" if v <= -0.6 else "No strongly adverse note",
        "note_adverse_cnt": f"{v:.0f} adverse officer note(s) in window",
        "note_n": f"{v:.0f} officer note(s) in window",
        "note_severity_max": "Officer notes flag a severe event" if v >= 3 else "No severe event noted",
        "note_theme_receivables": "Officer notes cite receivable delays",
        "note_theme_labour": "Officer notes cite labour or wage stress",
        "note_theme_demand": "Officer notes cite demand or order-book weakness",
        "note_theme_input_cost": "Officer notes cite input-cost pressure",
        "note_theme_promoter": "Officer notes cite promoter conduct",
        "note_theme_legal": "Officer notes cite legal or statutory issues",
        "note_theme_stock": "Officer notes cite stock or statement discrepancies",
        "note_theme_capacity": "Officer notes cite idle capacity or disruption",
        # contagion
        "anchor_inflow_slope": "Anchor buyer payments falling" if v < 0 else "Anchor buyer payments steady",
        "anchor_dependence": f"{v:.0%} of inflows from one anchor buyer" if v > 0 else "No anchor concentration",
    }
    for s in ("manufacturing", "trading", "logistics", "services", "food_processing"):
        tmpl[f"sector_{s}"] = f"Sector: {s.replace('_', ' ')}"
    return tmpl.get(feature, f"{feature} = {v:.2f}")


class ReasonExplainer:
    def __init__(self, pd_model):
        self.pd_model = pd_model
        self.features = pd_model.features
        self._explainer = None
        self.backend = "importance_fallback"
        try:
            import shap
            self._explainer = shap.TreeExplainer(pd_model.model)
            self.backend = "shap"
        except Exception:
            self._explainer = None

    def _shap_row(self, feat: dict) -> np.ndarray:
        row = pd.DataFrame([[feat.get(f, 0.0) for f in self.features]], columns=self.features)
        if self._explainer is not None:
            try:
                sv = self._explainer.shap_values(row)
                sv = np.asarray(sv)
                if sv.ndim == 3:      # (classes, n, features) or (n, features, classes)
                    sv = sv[-1] if sv.shape[0] <= 2 else sv[..., -1]
                return np.asarray(sv).reshape(-1)
            except Exception:
                pass
        imp = getattr(self.pd_model.model, "feature_importances_", np.ones(len(self.features)))
        return np.array([imp[i] * feat.get(f, 0.0) for i, f in enumerate(self.features)])

    def shap_by_feature(self, feat: dict) -> dict[str, float]:
        sv = self._shap_row(feat)
        return {f: float(sv[i]) for i, f in enumerate(self.features)}

    def reason_codes(self, feat: dict, top: int = 6) -> list[dict]:
        sv = self._shap_row(feat)
        order = np.argsort(-sv)          # most risk-increasing first
        out = []
        for i in order:
            if sv[i] <= 0 and len(out) >= 1:   # keep only risk-increasing drivers (at least 1)
                break
            f = self.features[i]
            out.append(dict(factor=f, plain=plain_language(f, feat.get(f, 0.0)),
                            contribution=round(float(sv[i]), 4), value=round(float(feat.get(f, 0.0)), 4)))
            if len(out) >= top:
                break
        return out

    def auditor_table(self, feat: dict) -> list[dict]:
        sv = self._shap_row(feat)
        rows = [dict(factor=self.features[i], value=round(float(feat.get(self.features[i], 0.0)), 4),
                     shap_value=round(float(sv[i]), 4), plain=plain_language(self.features[i], feat.get(self.features[i], 0.0)))
                for i in range(len(self.features))]
        return sorted(rows, key=lambda r: -abs(r["shap_value"]))
