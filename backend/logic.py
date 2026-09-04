"""PRAHARI business logic: IRAC provisioning, what-if simulator, compliance clocks, storyline
beats, movers. Kept separate from the routes so it is unit-testable and auditable by bankers.

Regulatory vocabulary comes from the interpretation framework (core/interpret) so the same
thresholds and labels appear on every screen."""

from __future__ import annotations

import pandas as pd

from core.interpret import framework as FW

_PROV = FW.provisioning_rates()
PROV_STANDARD = float(_PROV["standard"])
PROV_SUBSTANDARD = float(_PROV["sub_standard"])
PROV_RESTRUCTURED = float(_PROV["restructured_standard"])
CRILC_EXPOSURE_THRESHOLD = FW.crilc_threshold()     # 5 crore aggregate exposure
OFFICER_REVIEW_COST = 5_000                          # rupees of officer time to review one flag

# What-if actions. runway_gain figures are supervisory ASSUMPTIONS (months), not model outputs,
# and are shown as such with a sensitivity range. They are the levers a credit officer actually
# has at the SMA stage; the model quantifies the provisioning consequence of each.
WHATIF_ACTIONS = {
    "enhanced_monitoring": dict(label="Enhanced monitoring", runway_gain=1.5, sensitivity=(0.5, 3.0), lgd_factor=1.0,
                                note="Fortnightly stock and receivables checks; no capital action yet.",
                                basis="Assumption: earlier detection of the next slip buys 1 to 3 months."),
    "restructure": dict(label="Restructure / reschedule", runway_gain=8.0, sensitivity=(4.0, 12.0), lgd_factor=1.0,
                        prov_rate=PROV_RESTRUCTURED,
                        note="Reschedule EMIs to match cash-flow; standard-restructured provisioning applies.",
                        basis="Assumption: a cash-flow-matched schedule defers the 90+ DPD point by 4 to 12 months."),
    "limit_reduction": dict(label="Limit reduction", runway_gain=4.0, sensitivity=(2.0, 6.0), exposure_factor=0.80, lgd_factor=1.0,
                            note="Trim sanctioned limit to curb utilisation creep; lowers exposure at risk.",
                            basis="Assumption: 20 percent limit trim, 2 to 6 months of runway from tighter drawing discipline."),
    "collateral_topup": dict(label="Collateral top-up", runway_gain=5.0, sensitivity=(2.0, 8.0), lgd_factor=0.5,
                             note="Additional security halves loss-given-default on the exposure.",
                             basis="Assumption: security cover halves LGD; promoter commitment adds 2 to 8 months."),
}


def provision_now(exposure: float) -> float:
    return exposure * PROV_STANDARD


def provision_at_npa(exposure: float, lgd_factor: float = 1.0) -> float:
    return exposure * PROV_SUBSTANDARD * lgd_factor


def provision_saved_if_cured(exposure: float, lgd_factor: float = 1.0) -> float:
    """Rupees saved by preventing this account from reaching NPA (vs provisioning at sub-standard)."""
    return max(0.0, provision_at_npa(exposure, lgd_factor) - provision_now(exposure))


def whatif(action: str, exposure: float, runway: float, pd_value: float) -> dict:
    spec = WHATIF_ACTIONS.get(action)
    if spec is None:
        return {"error": f"unknown action {action}", "actions": list(WHATIF_ACTIONS)}
    new_exposure = exposure * spec.get("exposure_factor", 1.0)
    new_runway = min(24.0, runway + spec["runway_gain"])
    lo, hi = spec["sensitivity"]
    lgd = spec["lgd_factor"]
    prov_before = provision_now(exposure)
    prov_after = new_exposure * spec.get("prov_rate", PROV_STANDARD)
    saved_vs_npa = provision_at_npa(exposure, lgd) - prov_after
    return dict(
        action=action, label=spec["label"], note=spec["note"], basis=spec["basis"],
        runway_before=round(runway, 1), runway_after=round(new_runway, 1),
        runway_after_range=[round(min(24.0, runway + lo), 1), round(min(24.0, runway + hi), 1)],
        runway_delta=round(new_runway - runway, 1),
        exposure_before=round(exposure, 2), exposure_after=round(new_exposure, 2),
        provision_before=round(prov_before, 2), provision_after=round(prov_after, 2),
        provision_saved_vs_npa=round(max(0.0, saved_vs_npa), 2),
    )


def cost_of_error(confusion_matrix, avg_exposure: float) -> dict:
    """Translate the model's confusion matrix into rupees (BUILD_SPEC §5.2 cost-of-error table).

    A false negative (missed default) is costly - provisioning jumps 0.4% to 15% on the exposure
    once it hits NPA. A false positive (false alarm) costs one officer review. This asymmetry is
    WHY the model is tuned for recall, not precision."""
    (tn, fp), (fn, tp) = confusion_matrix[0], confusion_matrix[1]
    cost_fn = avg_exposure * (PROV_SUBSTANDARD - PROV_STANDARD)
    cost_fp = OFFICER_REVIEW_COST
    defaults = tp + fn
    cost_without = defaults * cost_fn
    cost_with = fn * cost_fn + fp * cost_fp
    ratio = int(round(cost_fn / cost_fp))
    return dict(
        cost_per_missed_default=round(cost_fn, 2), cost_per_false_alarm=float(cost_fp), asymmetry_ratio=ratio,
        defaults_in_validation=int(defaults), caught=int(tp), missed=int(fn), false_alarms=int(fp),
        provision_at_risk_without_ews=round(cost_without, 2), residual_cost_with_ews=round(cost_with, 2),
        provision_preserved=round(cost_without - cost_with, 2),
        note=(f"A missed default costs about {ratio}x a false alarm, so recall is prioritised over precision. "
              "Every flag carries reason codes for officer review."),
    )


def compliance_clocks(exposure: float, runway: float, bucket: str, statutory_sma: str) -> list[dict]:
    """Projected-NPA countdown for flagged accounts, plus the CRILC clock when it genuinely applies
    (aggregate exposure at or above the threshold AND a statutory SMA-2 status)."""
    clocks = []
    if bucket in ("red", "amber"):
        clocks.append(dict(name="Projected 90+ DPD (model)", window_days=int(round(runway * 30)),
                           days_remaining=int(round(runway * 30)),
                           detail="Model-projected time until 90+ DPD on current trajectory."))
    if exposure >= CRILC_EXPOSURE_THRESHOLD:
        if statutory_sma == "SMA-2":
            clocks.append(dict(name="CRILC reporting", window_days=7, days_remaining=7,
                               detail="Aggregate exposure at or above 5 crore and statutory SMA-2: report to CRILC within the stipulated timeline."))
        else:
            clocks.append(dict(name="CRILC watch", window_days=0, days_remaining=0,
                               detail="Aggregate exposure at or above 5 crore. CRILC reporting is triggered by statutory SMA-2 (days past due), not by the model flag; an early-warning note is drafted so the branch is ready."))
    return clocks


def deterioration_beats(group: pd.DataFrame) -> list[dict]:
    """Extract the timeline beats a banker would narrate from the behavioural series."""
    g = group.sort_values("month_index")
    beats = []
    seen = set()

    def once(key, r, text):
        if key not in seen:
            beats.append(dict(month=int(r.month_index), month_label=r.month_date, text=text))
            seen.add(key)

    has_dp = "drawing_power_pct" in g.columns and (g.drawing_power_pct > 0).any()
    base_dp = float(g.drawing_power_pct.head(6).mean()) if has_dp else 0.0
    for r in g.itertuples(index=False):
        if r.gst_filing_delay_days >= 5:
            once("gst", r, f"GST filing delays begin ({int(r.gst_filing_delay_days)} days late)")
        if r.limit_utilisation >= 0.85 and (not has_dp or True):
            once("util85", r, f"Limit utilisation crosses 85% (now {r.limit_utilisation:.0%})")
        if has_dp and r.drawing_power_pct > 0 and r.drawing_power_pct < base_dp - 0.08:
            once("dp", r, f"Drawing power slips to {r.drawing_power_pct:.0%} of sanction (stock and debtor margins thinning)")
        if has_dp and r.drawing_power_pct > 0 and r.limit_utilisation > r.drawing_power_pct:
            once("overdp", r, "Drawings exceed drawing power")
        if getattr(r, "stock_statement_submitted", 1) == 0:
            once("stmt", r, "Stock statement not submitted")
        if getattr(r, "lien_count", 0) >= 1:
            once("lien", r, "New lien placed on the operating account")
        if r.cheque_bounces_outward >= 1:
            once("bounce", r, "First outward cheque return")
        if r.dpd >= 1:
            once("dpd", r, f"First overdue: {int(r.dpd)} days past due")
    cred = g.credits.to_numpy()
    if len(cred) >= 8 and cred[-1] < 0.85 * cred[: len(cred) // 2].mean():
        drop = 1 - cred[-1] / (cred[: len(cred) // 2].mean() + 1)
        beats.append(dict(month=int(g.month_index.max()), month_label=g.month_date.iloc[-1],
                          text=f"Credit turnover down {drop:.0%} versus earlier months"))
    return sorted(beats, key=lambda x: x["month"])


def repayment_state(group: pd.DataFrame) -> str:
    last = group.sort_values("month_index").iloc[-1]
    if int(last.dpd) >= 90:
        return "in default (90+ DPD)"
    if str(last.repayment_status) == "missed":
        return "missed"
    if str(last.repayment_status) == "delayed" or int(last.dpd) > 0:
        return f"delayed ({int(last.dpd)} DPD)"
    return "current"
