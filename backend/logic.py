"""PRAHARI business logic: IRAC provisioning, what-if simulator, compliance clocks, storyline
beats. Kept separate from the routes so it is unit-testable and auditable by bankers."""

from __future__ import annotations

import pandas as pd

# IRAC provisioning (BUILD_SPEC design rules): standard 0.4%, sub-standard (NPA) 15%.
PROV_STANDARD = 0.004
PROV_SUBSTANDARD = 0.15
PROV_RESTRUCTURED = 0.05
CRILC_EXPOSURE_THRESHOLD = 5_00_00_000     # ₹5 crore aggregate exposure
OFFICER_REVIEW_COST = 5_000                # ₹ officer time to review one flagged account

WHATIF_ACTIONS = {
    "enhanced_monitoring": dict(label="Enhanced monitoring", runway_gain=1.5, lgd_factor=1.0,
                                note="Fortnightly stock & receivables checks; no capital action yet."),
    "restructure": dict(label="Restructure / reschedule", runway_gain=8.0, lgd_factor=1.0,
                        prov_rate=PROV_RESTRUCTURED,
                        note="Reschedule EMIs to match cash-flow; standard-restructured provisioning applies."),
    "limit_reduction": dict(label="Limit reduction", runway_gain=4.0, exposure_factor=0.80, lgd_factor=1.0,
                            note="Trim sanctioned limit to curb utilisation creep; lowers exposure at risk."),
    "collateral_topup": dict(label="Collateral top-up", runway_gain=5.0, lgd_factor=0.5,
                             note="Additional security halves loss-given-default on the exposure."),
}


def provision_now(exposure: float) -> float:
    return exposure * PROV_STANDARD


def provision_at_npa(exposure: float, lgd_factor: float = 1.0) -> float:
    return exposure * PROV_SUBSTANDARD * lgd_factor


def provision_saved_if_cured(exposure: float, lgd_factor: float = 1.0) -> float:
    """₹ saved by preventing this account from reaching NPA (vs provisioning at sub-standard)."""
    return max(0.0, provision_at_npa(exposure, lgd_factor) - provision_now(exposure))


def whatif(action: str, exposure: float, runway: float, pd_value: float) -> dict:
    spec = WHATIF_ACTIONS.get(action)
    if spec is None:
        return {"error": f"unknown action {action}", "actions": list(WHATIF_ACTIONS)}
    new_exposure = exposure * spec.get("exposure_factor", 1.0)
    new_runway = min(24.0, runway + spec["runway_gain"])
    lgd = spec["lgd_factor"]
    prov_before = provision_now(exposure)
    # after the action the account is expected to stay standard (avoid NPA) → provision at the
    # relevant standard/restructured rate on the (possibly reduced) exposure
    prov_after = new_exposure * spec.get("prov_rate", PROV_STANDARD)
    saved_vs_npa = provision_at_npa(exposure, lgd) - prov_after
    return dict(
        action=action, label=spec["label"], note=spec["note"],
        runway_before=round(runway, 1), runway_after=round(new_runway, 1),
        runway_delta=round(new_runway - runway, 1),
        exposure_before=round(exposure, 2), exposure_after=round(new_exposure, 2),
        provision_before=round(prov_before, 2), provision_after=round(prov_after, 2),
        provision_saved_vs_npa=round(max(0.0, saved_vs_npa), 2),
    )


def cost_of_error(confusion_matrix, avg_exposure: float) -> dict:
    """Translate the model's confusion matrix into rupees (BUILD_SPEC §5.2 cost-of-error table).

    A false negative (missed default) is catastrophic - provisioning jumps 0.4% → 15% on the
    exposure once it hits NPA. A false positive (false alarm) costs only one officer review. This
    ~2,900:1 asymmetry is WHY the model is tuned for recall, not precision - and why a modest
    precision is the correct, honest operating point, not a weakness."""
    cm = confusion_matrix
    (tn, fp), (fn, tp) = cm[0], cm[1]
    cost_fn = avg_exposure * (PROV_SUBSTANDARD - PROV_STANDARD)   # extra provision if it defaults
    cost_fp = OFFICER_REVIEW_COST
    defaults = tp + fn
    # without an EWS every default is a surprise NPA; with the model, only the missed ones hurt
    cost_without = defaults * cost_fn
    cost_with = fn * cost_fn + fp * cost_fp
    return dict(
        cost_per_missed_default=round(cost_fn, 2),
        cost_per_false_alarm=float(cost_fp),
        asymmetry_ratio=int(round(cost_fn / cost_fp)),
        defaults_in_validation=int(defaults),
        caught=int(tp), missed=int(fn), false_alarms=int(fp),
        provision_at_risk_without_ews=round(cost_without, 2),
        residual_cost_with_ews=round(cost_with, 2),
        provision_preserved=round(cost_without - cost_with, 2),
        note=("A missed default costs ~%dx a false alarm, so recall is prioritised over precision. "
              "Every flag carries reason codes for officer review." % int(round(cost_fn / cost_fp))),
    )


def compliance_clocks(exposure: float, runway: float, bucket: str) -> list[dict]:
    """CRILC (7-day) and projected-NPA countdowns for flagged accounts (BUILD_SPEC §5.2)."""
    clocks = []
    if bucket == "red":
        if exposure >= CRILC_EXPOSURE_THRESHOLD:
            clocks.append(dict(name="CRILC reporting", window_days=7, days_remaining=7,
                               detail="Aggregate exposure ≥ ₹5 Cr in the red bucket - CRILC report due."))
        clocks.append(dict(name="Projected NPA (90+ DPD)", window_days=int(round(runway * 30)),
                           days_remaining=int(round(runway * 30)),
                           detail="Model-projected time until 90+ DPD on current trajectory."))
    return clocks


def deterioration_beats(group: pd.DataFrame) -> list[dict]:
    """Extract the timeline beats a banker would narrate from the behavioural series."""
    g = group.sort_values("month_index")
    beats = []
    prev_util = None
    first_delay = first_bounce = first_util85 = False
    for r in g.itertuples(index=False):
        if not first_delay and r.gst_filing_delay_days >= 5:
            beats.append(dict(month=int(r.month_index), month_label=r.month_date,
                              text=f"GST filing delays begin ({int(r.gst_filing_delay_days)} days late)"))
            first_delay = True
        if not first_util85 and r.limit_utilisation >= 0.85:
            beats.append(dict(month=int(r.month_index), month_label=r.month_date,
                              text=f"Limit utilisation crosses 85% (now {r.limit_utilisation:.0%})"))
            first_util85 = True
        if not first_bounce and r.cheque_bounces_outward >= 1:
            beats.append(dict(month=int(r.month_index), month_label=r.month_date,
                              text="First outward cheque return"))
            first_bounce = True
        prev_util = r.limit_utilisation
    # credit decline beat
    cred = g.credits.to_numpy()
    if len(cred) >= 8 and cred[-1] < 0.85 * cred[: len(cred) // 2].mean():
        drop = 1 - cred[-1] / (cred[: len(cred) // 2].mean() + 1)
        beats.append(dict(month=int(g.month_index.max()), month_label=g.month_date.iloc[-1],
                          text=f"Credit turnover down {drop:.0%} versus earlier months"))
    return sorted(beats, key=lambda x: x["month"])
