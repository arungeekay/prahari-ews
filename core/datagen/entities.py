"""Static entities: MSME borrowers, anchor corporates + payment graph, retail customers.

Produces the non-time-series tables plus the *latent* fields the monthly-series generators need
(trajectory onset, default month, anchor payment component, discipline). Demo characters are
placed first with fixed ids so their storylines are stable across runs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import characters as CH
from . import names as N
from .util import month_index_to_date, weighted_choice, clip


# ======================================================================================
# MSME borrowers
# ======================================================================================
def _latent_turnover(rng, sanctioned_limit):
    mult = rng.uniform(*C.TURNOVER_MULTIPLE)
    return float(sanctioned_limit * mult)


def _assign_trajectory_timing(rng, trajectory):
    """Return (traj_start, drift_len, default_month) for a trajectory."""
    if trajectory == "distress_at_month_k":
        start = int(rng.integers(C.DISTRESS_START_RANGE[0], C.DISTRESS_START_RANGE[1] + 1))
        drift = int(rng.integers(C.DISTRESS_DRIFT_RANGE[0], C.DISTRESS_DRIFT_RANGE[1] + 1))
        return start, drift, start + drift
    if trajectory == "sudden_shock":
        start = int(rng.integers(C.SHOCK["start_range"][0], C.SHOCK["start_range"][1] + 1))
        return start, C.SHOCK["dpd_ramp_months"], start + C.SHOCK["dpd_ramp_months"]
    if trajectory == "distress_then_recover":
        start = int(rng.integers(C.RECOVER["start_range"][0], C.RECOVER["start_range"][1] + 1))
        return start, -1, -1        # chronic decliner → never defaults in the window
    if trajectory == "slow_decline":
        start = int(rng.integers(C.SLOW_DECLINE["start_range"][0], C.SLOW_DECLINE["start_range"][1] + 1))
        return start, -1, -1
    return -1, -1, -1


def _severity(rng, trajectory):
    """Per-firm drift severity (heterogeneity so defaulters don't all look identical).

    Survivors (distress_then_recover) drift MILDLY - they overlap distress in the moderate zone
    (keeping AUC honest) but rarely hit the extremes, so a genuinely severe distress firm like
    Sharma stays distinguishable (short runway)."""
    if trajectory == "distress_at_month_k":
        return float(rng.uniform(*C.DISTRESS_SEVERITY_RANGE))
    if trajectory == "distress_then_recover":
        return float(rng.uniform(*C.RECOVER_SEVERITY_RANGE))
    return 1.0


def _promoter(rng):
    age = int(clip(rng.normal(46, 9), 26, 72))
    exp = int(clip(rng.normal(age - 26, 5), 1, age - 20))
    qual = weighted_choice(rng, C.PROMOTER_QUALS, C.PROMOTER_QUAL_WEIGHTS)
    return age, exp, qual


def _months_available(rng, vintage_years):
    """Most accounts have full 24-month history; young units are thin files."""
    if vintage_years <= 2 and rng.random() < 0.35:
        return int(rng.integers(4, 16))
    if rng.random() < 0.02:            # a few random thin files regardless of vintage
        return int(rng.integers(6, 18))
    return C.N_MONTHS_MSME


def _make_random_borrower(rng, idx):
    sector = weighted_choice(rng, C.SECTORS, C.SECTOR_WEIGHTS)
    city = weighted_choice(rng, C.MSME_CITIES, C.MSME_CITY_WEIGHTS)
    state = C.MSME_CITY_TO_STATE[city]
    vintage = int(clip(rng.normal(9, 5), 1, 30))
    loan_type = weighted_choice(rng, C.LOAN_TYPES, C.LOAN_TYPE_WEIGHTS)
    # sanctioned limit - log-uniform between ₹10L and ₹5Cr so small firms dominate
    lo, hi = np.log(C.LIMIT_MIN), np.log(C.LIMIT_MAX)
    limit = float(np.exp(rng.uniform(lo, hi)))
    limit = round(limit / 1_00_000) * 1_00_000          # round to nearest ₹1 lakh
    age, exp, qual = _promoter(rng)
    trajectory = weighted_choice(rng, C.TRAJECTORIES, C.TRAJECTORY_WEIGHTS)
    traj_start, drift, default_month = _assign_trajectory_timing(rng, trajectory)
    severity = _severity(rng, trajectory)
    months_avail = _months_available(rng, vintage)
    loan_start_idx = (C.N_MONTHS_MSME - months_avail) if months_avail < C.N_MONTHS_MSME \
        else -int(rng.integers(0, max(1, (vintage - 2)) * 12 + 1))
    return dict(
        borrower_id=f"MSME{idx:05d}",
        name=N.make_business_name(rng, sector),
        sector=sector, city=city, state=state, vintage_years=vintage,
        promoter_age=age, promoter_experience_years=exp, promoter_qualification=qual,
        loan_type=loan_type, sanctioned_limit=limit,
        loan_start_month=loan_start_idx,
        loan_start_date=month_index_to_date(loan_start_idx).isoformat(),
        health_trajectory=trajectory,
        traj_start=traj_start, drift_len=drift, default_month=default_month, severity=severity,
        months_available=months_avail,
        base_turnover=_latent_turnover(rng, limit),
        bank_credit_share=float(rng.uniform(*C.BANK_CREDIT_SHARE)),
        is_anchor_supplier=False, anchor_id="", anchor_payment=0.0, anchor_share=0.0, anchor_lag=0,
        contagion_induced=False, demo="",
    )


def _make_demo_borrower(rng, idx, spec):
    traj = spec["trajectory"]
    if traj == "distress_at_month_k":
        traj_start = spec["distress_start"]
        drift = spec.get("drift_len", int(rng.integers(*C.DISTRESS_DRIFT_RANGE)))
        default_month = traj_start + drift
    else:
        traj_start, drift, default_month = _assign_trajectory_timing(rng, traj)
    months_avail = spec.get("months_available", C.N_MONTHS_MSME)
    loan_start_idx = (C.N_MONTHS_MSME - months_avail) if months_avail < C.N_MONTHS_MSME \
        else -(spec["vintage_years"] - 1) * 12
    # twins share an identical declared-GST base turnover
    if spec["demo"] in ("verma", "gupta"):
        base_turnover = float(CH.TWIN_BASE_TURNOVER)
    else:
        base_turnover = _latent_turnover(rng, spec["sanctioned_limit"])
    return dict(
        borrower_id=f"MSME{idx:05d}",
        name=spec["name"], sector=spec["sector"], city=spec["city"], state=spec["state"],
        vintage_years=spec["vintage_years"],
        promoter_age=spec["promoter_age"], promoter_experience_years=spec["promoter_experience_years"],
        promoter_qualification=spec["promoter_qualification"],
        loan_type=spec["loan_type"], sanctioned_limit=float(spec["sanctioned_limit"]),
        loan_start_month=loan_start_idx,
        loan_start_date=month_index_to_date(loan_start_idx).isoformat(),
        health_trajectory=traj, traj_start=traj_start, drift_len=drift, default_month=default_month,
        severity=1.0,   # demo cast is pinned - no severity jitter (keeps Sharma's beats exact)
        months_available=months_avail,
        base_turnover=base_turnover,
        bank_credit_share=0.82,
        is_anchor_supplier=False, anchor_id="", anchor_payment=0.0, anchor_share=0.0, anchor_lag=0,
        contagion_induced=False, demo=spec["demo"],
    )


def build_borrowers(rng) -> pd.DataFrame:
    rows = []
    # 1..N_DEMO_MSME → demo cast (fixed ids)
    for i, spec in enumerate(CH.DEMO_MSMES, start=1):
        rows.append(_make_demo_borrower(rng, i, spec))
    # rest → random pool
    for idx in range(CH.N_DEMO_MSME + 1, C.N_MSME + 1):
        rows.append(_make_random_borrower(rng, idx))
    return pd.DataFrame(rows)


# ======================================================================================
# Anchor corporates + anchor→supplier payment graph (edges.parquet)
# ======================================================================================
def build_anchors_and_edges(rng, borrowers: pd.DataFrame):
    """Assign suppliers to anchors, build edges, and flip 5 of Anchor #1's suppliers into
    contagion-induced distress. Mutates `borrowers` in place (anchor + contagion columns)."""
    anchors = [CH.ANCHOR1] + [
        dict(anchor_id=f"ANCH{i+2}", name=nm, sector="manufacturing")
        for i, nm in enumerate(CH.OTHER_ANCHOR_NAMES)
    ]

    # eligible suppliers: the random pool (exclude demo cast); sample without replacement
    eligible = borrowers.index[borrowers["demo"] == ""].to_numpy()
    perm = rng.permutation(eligible)
    cursor = 0

    edge_rows = []
    anchor_rows = []
    for a_i, anchor in enumerate(anchors):
        if anchor["anchor_id"] == "ANCH1":
            n_sup = C.CONTAGION["anchor1_n_suppliers"]
        else:
            n_sup = int(rng.integers(*C.CONTAGION["n_suppliers_per_anchor"]))
        picks = perm[cursor:cursor + n_sup]
        cursor += n_sup
        for bi in picks:
            share = float(rng.uniform(*C.CONTAGION["anchor_inflow_share"]))
            credit_base = borrowers.at[bi, "base_turnover"] * borrowers.at[bi, "bank_credit_share"]
            avg_amount = float(credit_base * share)
            lag = int(rng.integers(C.CONTAGION["supplier_lag_range"][0],
                                   C.CONTAGION["supplier_lag_range"][1] + 1))
            borrowers.at[bi, "is_anchor_supplier"] = True
            borrowers.at[bi, "anchor_id"] = anchor["anchor_id"]
            borrowers.at[bi, "anchor_payment"] = avg_amount
            borrowers.at[bi, "anchor_share"] = share
            borrowers.at[bi, "anchor_lag"] = lag
            edge_rows.append(dict(
                payer=anchor["anchor_id"], payer_name=anchor["name"],
                payee=borrowers.at[bi, "borrower_id"], payee_name=borrowers.at[bi, "name"],
                avg_monthly_amount=round(avg_amount, 2),
                regularity=round(float(rng.uniform(0.80, 0.98)), 3),
                inflow_share=round(share, 3),
            ))
        anchor_rows.append(dict(
            anchor_id=anchor["anchor_id"], name=anchor["name"],
            sector=anchor["sector"], n_suppliers=len(picks),
        ))

    # ---- contagion: flip 5 of Anchor #1's suppliers into distress (2–4 months post-event) ----
    a1_suppliers = borrowers.index[borrowers["anchor_id"] == "ANCH1"].to_numpy()
    # prefer currently-healthy suppliers so the flip is a genuine contagion effect
    healthy = [bi for bi in a1_suppliers
               if borrowers.at[bi, "health_trajectory"] in ("stable", "growing", "slow_decline")]
    ordered = healthy + [bi for bi in a1_suppliers if bi not in healthy]
    n_induce = C.CONTAGION["n_induced_distress"]
    for bi in ordered[:n_induce]:
        delay = int(rng.integers(C.CONTAGION["induced_distress_delay"][0],
                                 C.CONTAGION["induced_distress_delay"][1] + 1))
        start = C.CONTAGION["event_month"] + delay
        drift = int(rng.integers(*C.DISTRESS_DRIFT_RANGE))
        borrowers.at[bi, "health_trajectory"] = "distress_at_month_k"
        borrowers.at[bi, "traj_start"] = start
        borrowers.at[bi, "drift_len"] = drift
        borrowers.at[bi, "default_month"] = start + drift
        borrowers.at[bi, "severity"] = float(rng.uniform(*C.DISTRESS_SEVERITY_RANGE))
        borrowers.at[bi, "contagion_induced"] = True

    # observed default (within the 24-month window)
    dm = borrowers["default_month"].to_numpy()
    borrowers["observed_default"] = ((dm >= 0) & (dm <= C.DEMO_MONTH)).astype(int)

    anchors_df = pd.DataFrame(anchor_rows)
    edges_df = pd.DataFrame(edge_rows)
    return anchors_df, edges_df


# ======================================================================================
# Retail customers (DISHA) + bureau snapshot
# ======================================================================================
def _capacity_from(rng, occupation, income_band):
    base = {"low": 0.30, "mid": 0.50, "upper_mid": 0.68, "high": 0.80}[income_band]
    occ_adj = {"salaried": 0.10, "self_employed": 0.0, "gig_worker": -0.10}[occupation]
    return float(clip(base + occ_adj + rng.normal(0, 0.10), 0.05, 0.98))


def _discipline_from(rng, occupation):
    base = {"salaried": 0.60, "self_employed": 0.50, "gig_worker": 0.45}[occupation]
    return float(clip(base + rng.normal(0, 0.22), 0.02, 0.98))


def _make_random_customer(rng, idx):
    occ = weighted_choice(rng, C.OCCUPATIONS, C.OCCUPATION_WEIGHTS)
    band = weighted_choice(rng, C.INCOME_BAND_NAMES, C.INCOME_BAND_WEIGHTS)
    lo, hi = C.INCOME_BANDS[band]
    base_income = float(round(rng.uniform(lo, hi) / 500) * 500)
    city = weighted_choice(rng, C.RETAIL_CITIES, C.RETAIL_CITY_WEIGHTS)
    state = C.RETAIL_CITY_TO_STATE[city]
    name, _ = N.make_person_name(rng)
    intent = weighted_choice(rng, C.LOAN_INTENTS, C.LOAN_INTENT_WEIGHTS)
    # existing products: everyone has UPI + savings; sample extras
    prods = ["savings", "upi"]
    for p in ["salary_account", "fd", "credit_card"]:
        if rng.random() < (0.55 if (p == "salary_account" and occ == "salaried") else 0.28):
            prods.append(p)
    existing_loans = int(rng.integers(0, 3))
    return dict(
        customer_id=f"CUST{idx:05d}",
        name=name, age=int(clip(rng.normal(37, 10), 21, 68)),
        city=city, state=state, occupation_type=occ,
        income_band=band, base_income=base_income,
        existing_products=";".join(prods),
        loan_intent=intent,
        capacity_score=_capacity_from(rng, occ, band),
        discipline_score_latent=_discipline_from(rng, occ),
        clicked_page="",
        bureau_existing_loans=existing_loans,
        bureau_enquiries=int(rng.integers(0, 5)),
        bureau_other_bank_flag=bool(rng.random() < 0.42),
        demo="",
    )


def _make_demo_customer(rng, idx, spec):
    prods = spec.get("existing_products", ["savings", "upi"])
    return dict(
        customer_id=f"CUST{idx:05d}",
        name=spec["name"], age=spec["age"], city=spec["city"], state=spec["state"],
        occupation_type=spec["occupation_type"], income_band=spec["income_band"],
        base_income=float(spec["base_income"]),
        existing_products=";".join(prods),
        loan_intent=spec["loan_intent"],
        capacity_score=float(spec["capacity_score"]),
        discipline_score_latent={"saver": 0.88, "spender": 0.12}.get(spec.get("discipline"), 0.50),
        clicked_page=spec.get("clicked_page", ""),
        bureau_existing_loans=1 if spec["demo"] != "ravi" else 0,
        bureau_enquiries=3 if spec["demo"] == "ravi" else 1,
        bureau_other_bank_flag=bool(spec["demo"] == "discipline_spender"),
        demo=spec["demo"],
    )


def build_customers(rng) -> pd.DataFrame:
    rows = []
    for i, spec in enumerate(CH.DEMO_RETAIL, start=1):
        rows.append(_make_demo_customer(rng, i, spec))
    for idx in range(CH.N_DEMO_RETAIL + 1, C.N_RETAIL + 1):
        rows.append(_make_random_customer(rng, idx))
    return pd.DataFrame(rows)
