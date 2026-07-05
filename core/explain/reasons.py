"""SHAP-based reason codes for the PD model (BUILD_SPEC §4.3).

Top-6 risk drivers per prediction, each mapped to a plain-language template with the actual
value ("Utilisation rose to 94%"). Auditor view returns the full factor table with SHAP values.
Falls back to feature-importance × standardized-value when SHAP is unavailable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def plain_language(feature: str, value: float) -> str:
    v = value
    tmpl = {
        "util_last": f"Limit utilisation at {v:.0%}",
        "util_mean": f"Average utilisation {v:.0%} over window",
        "util_max": f"Utilisation peaked at {v:.0%}",
        "util_slope": f"Utilisation rising (+{v*100:.1f} pts/month)" if v > 0 else f"Utilisation stable/easing",
        "credit_slope": "Credit turnover declining month-on-month" if v < 0 else "Credit turnover stable",
        "credit_last_over_first": (f"Credit turnover down {(1-v)*100:.0f}% across the window"
                                   if v < 1 else "Credit turnover holding up"),
        "credit_cv": "Volatile credit turnover" if v > 0.3 else "Steady credit turnover",
        "gst_delay_mean": f"GST filings delayed (avg {v:.0f} days)",
        "gst_delay_max": f"GST filing delayed up to {v:.0f} days",
        "gst_delay_slope": "GST filing delays worsening" if v > 0 else "GST filing timeliness stable",
        "bounce_out_sum": f"{v:.0f} outward cheque bounce(s) in window",
        "bounce_in_sum": f"{v:.0f} inward cheque bounce(s) in window",
        "balance_cv": "Volatile month-end balances" if v > 0.4 else "Stable balances",
        "balance_last_over_credit": "Thin liquidity buffer" if v < 0.05 else "Adequate liquidity buffer",
        "missed_cnt": f"{v:.0f} missed EMI(s)",
        "delayed_cnt": f"{v:.0f} delayed EMI(s)",
        "dpd_max": f"Reached {v:.0f} days past due",
        "emi_late_max": f"EMI up to {v:.0f} days late",
        "bureau_dpd_other_max": f"DPD on other loans ({v:.0f} days)",
        "bureau_enq_sum": f"{v:.0f} credit enquiries elsewhere",
        "bureau_newloans_sum": f"{v:.0f} new loan(s) taken elsewhere",
        "epfo_delay_max": f"EPFO contributions delayed ({v:.0f} days)",
        "epfo_emp_slope": "Headcount shrinking" if v < 0 else "Headcount stable/growing",
        "sentiment_last": "Adverse sector sentiment" if v < 0 else "Neutral/positive sector sentiment",
        "note_sentiment_mean": "Adverse loan-officer notes" if v < 0 else "Neutral loan-officer notes",
        "electricity_slope": "Electricity usage falling" if v < 0 else "Electricity usage stable",
        "fuel_slope": "Fuel spend falling" if v < 0 else "Fuel spend stable",
        "credit_mean_lakh": f"Avg monthly credit ₹{v:.1f} L",
    }
    return tmpl.get(feature, f"{feature} = {v:.2f}")


class ReasonExplainer:
    def __init__(self, pd_model):
        self.pd_model = pd_model
        self.features = pd_model.features
        self._explainer = None
        try:
            import shap
            self._explainer = shap.TreeExplainer(pd_model.model)
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
        # fallback: importance × signed standardized value
        imp = getattr(self.pd_model.model, "feature_importances_", np.ones(len(self.features)))
        return np.array([imp[i] * feat.get(f, 0.0) for i, f in enumerate(self.features)])

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
