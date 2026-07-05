"""Central configuration for the synthetic Bharat generator.

Everything that shapes the economy lives here so the demo storylines can be tuned in one
place. All values are chosen to be *causally consistent* (BUILD_SPEC §3.2) and to hit the
acceptance targets in §3.5. No wall-clock time or unseeded randomness anywhere — determinism
(§3.5) depends on it.
"""

from __future__ import annotations

# --------------------------------------------------------------------------------------
# Time window — 24 months, July 2024 → June 2026 (BUILD_SPEC §3.1)
# --------------------------------------------------------------------------------------
START_YEAR = 2024
START_MONTH = 7            # July 2024  == month_index 0
N_MONTHS_MSME = 24         # MSME behavioural series length
N_MONTHS_RETAIL = 12       # retail behavioural series length (last 12 months of the window)
DEMO_MONTH = N_MONTHS_MSME - 1   # month_index 23 == June 2026 == "as of demo"

# Retail series covers the trailing 12 months of the 24-month window.
RETAIL_START_INDEX = N_MONTHS_MSME - N_MONTHS_RETAIL   # 12

# --------------------------------------------------------------------------------------
# Entity counts (BUILD_SPEC §3.1)
# --------------------------------------------------------------------------------------
N_MSME = 3_000
N_RETAIL = 10_000
N_ANCHORS = 4
SEED_DEFAULT = 42

# --------------------------------------------------------------------------------------
# Sectors and their behavioural personalities
#   energy_intensity : electricity units per ₹ lakh of monthly turnover (the fraud triangle's
#                      GST↔electricity band). Manufacturing/food burn a lot; trading/services little.
#   fuel_intensity   : ₹ fuel spend per ₹ lakh turnover (logistics/trading heavy).
#   emp_per_lakh     : EPFO headcount per ₹ lakh monthly turnover (labour intensity).
# --------------------------------------------------------------------------------------
SECTORS = ["manufacturing", "trading", "logistics", "services", "food_processing"]
SECTOR_WEIGHTS = [0.30, 0.26, 0.14, 0.16, 0.14]

SECTOR_PROFILE = {
    # sector:          (energy_intensity, energy_band_tol, fuel_intensity, emp_per_lakh)
    "manufacturing":   (900.0,  0.35,   150.0, 0.55),
    "food_processing": (650.0,  0.35,   180.0, 0.60),
    "logistics":       (140.0,  0.45,  2200.0, 0.30),
    "trading":         (110.0,  0.45,   900.0, 0.22),
    "services":        (170.0,  0.45,   120.0, 0.45),
}

# --------------------------------------------------------------------------------------
# Geography — weighted to real MSME clusters (BUILD_SPEC §3.1)
# --------------------------------------------------------------------------------------
# Explicit ordered lists keep sampling deterministic and independent of dict iteration order.
MSME_CITIES = ["Ludhiana", "Surat", "Coimbatore", "Rajkot", "Pune", "Ahmedabad", "Tirupur", "Jaipur"]
MSME_CITY_WEIGHTS = [0.17, 0.16, 0.14, 0.12, 0.13, 0.12, 0.09, 0.07]
MSME_CITY_TO_STATE = {
    "Ludhiana": "Punjab", "Surat": "Gujarat", "Coimbatore": "Tamil Nadu", "Rajkot": "Gujarat",
    "Pune": "Maharashtra", "Ahmedabad": "Gujarat", "Tirupur": "Tamil Nadu", "Jaipur": "Rajasthan",
}

RETAIL_CITIES = ["Pune", "Mumbai", "Bengaluru", "Hyderabad", "Delhi", "Chennai", "Ahmedabad", "Jaipur"]
RETAIL_CITY_WEIGHTS = [0.16, 0.16, 0.15, 0.12, 0.13, 0.11, 0.09, 0.08]
RETAIL_CITY_TO_STATE = {
    "Pune": "Maharashtra", "Mumbai": "Maharashtra", "Bengaluru": "Karnataka",
    "Hyderabad": "Telangana", "Delhi": "Delhi", "Chennai": "Tamil Nadu",
    "Ahmedabad": "Gujarat", "Jaipur": "Rajasthan",
}

# --------------------------------------------------------------------------------------
# Loan parameters (BUILD_SPEC §3.1)  — amounts in ₹ (rupees)
# --------------------------------------------------------------------------------------
LOAN_TYPES = ["CC", "OD", "term"]
LOAN_TYPE_WEIGHTS = [0.45, 0.25, 0.30]
LIMIT_MIN = 10_00_000        # ₹10 lakh
LIMIT_MAX = 5_00_00_000      # ₹5 crore
# turnover multiple: monthly GST turnover ≈ sanctioned_limit × U(lo,hi)
TURNOVER_MULTIPLE = (0.35, 1.10)
# fraction of turnover that flows through our bank as credits
BANK_CREDIT_SHARE = (0.60, 0.92)

# Promoter attributes
PROMOTER_QUALS = ["Below SSC", "SSC", "HSC", "Graduate", "Post-graduate", "Professional"]
PROMOTER_QUAL_WEIGHTS = [0.08, 0.18, 0.22, 0.34, 0.12, 0.06]

# --------------------------------------------------------------------------------------
# Latent health trajectories (BUILD_SPEC §3.1 / §3.3)
#   The mix is tuned so the *observed* default rate (default within the 24-month window)
#   lands at 4–6% (§3.3): ~9% distress firms, of which roughly half reach 90+ DPD by
#   month 23; the rest are still deteriorating (the red/amber watch-list, e.g. Sharma).
# --------------------------------------------------------------------------------------
# Realism note (why this isn't a toy): a world where *every* defaulter drifts predictably for a
# year yields AUC ≈ 0.99 — implausible to any evaluator (real 12-month PD models live ~0.75–0.85).
# So the population deliberately includes UNPREDICTABLE defaulters (sudden_shock) and honest
# false positives (distress_then_recover), and per-firm severity varies. Target: temporal-split
# AUC ~0.91–0.94, balanced accuracy just over 0.90 — meeting the bank's ≥0.90 bar the honest way.
TRAJECTORIES = ["stable", "growing", "slow_decline", "distress_at_month_k",
                "sudden_shock", "distress_then_recover", "fraud_pattern"]
TRAJECTORY_WEIGHTS = [0.487, 0.20, 0.12, 0.055, 0.013, 0.085, 0.04]   # sums to 1.0

# Per-firm heterogeneity in how hard a distressing account drifts. Low-severity distress firms
# drift gently (harder to catch) — not all defaulters look alike.
DISTRESS_SEVERITY_RANGE = (0.55, 1.30)
# Survivors drift mildly — overlap distress only in the moderate zone (keeps AUC honest) while
# leaving genuinely severe distress (e.g. Sharma) distinguishable for a short runway.
RECOVER_SEVERITY_RANGE = (0.35, 0.85)

# Observation noise on the behavioural series for the RANDOM population (the demo cast keeps
# noise_mult=1.0 so its scripted beats stay byte-identical). Bank data is noisy; this blurs the
# decision boundary so the model lands at a *plausible* ~0.92 AUC rather than an implausible 0.99.
FEATURE_NOISE_MULT = 2.0

# Persistent per-firm confounders (the honest source of hardness that 6-month window features
# can't average away): some healthy firms are naturally high utilisers or chronically-slightly-late
# filers, so a point-in-time snapshot genuinely overlaps early distress. Demo cast exempt.
FIRM_UTIL_BASE_SPREAD = 0.14          # std of a per-firm utilisation-level offset
FIRM_GST_BASE_DELAY_PROB = 0.18       # fraction of clean firms that chronically file a bit late
FIRM_GST_BASE_DELAY_RANGE = (3, 11)   # their habitual delay (days)

# Distress cascade timing (months). Behavioural drift begins 10–14 months before default (§3.3).
DISTRESS_START_RANGE = (2, 16)     # month_index at which the slow-distress storyline begins
# Months from onset to 90+ DPD default. A WIDE spread is what makes the world honest: long-drift
# firms (like Sharma, ~14) are catchable a year out — the product's headline — while short-fuse
# firms (~6) only reveal themselves ~4–6 months ahead and are genuine far-horizon misses. This
# spread, not tidy uniformity, is what lands AUC in a plausible ~0.92 band (spec "~10–14 months"
# is the *upper* cluster; real books also carry shorter fuses).
DISTRESS_DRIFT_RANGE = (8, 15)
DEFAULT_DPD = 90                   # 90+ DPD == default == NPA (§3.3)

# Distress cascade shape (all relative to d = month_index - distress_start):
#   GST filing delay begins at d≥3, utilisation creeps from d≥1, credits decline from d≥3,
#   cheque bounces from d≥7, repayment breaks only in the final ~3 months before default.
DISTRESS = dict(
    gst_delay_start=3, gst_delay_per_month=6.0, gst_delay_max=60.0,
    util_base=0.62, util_creep_per_month=0.05, util_max=0.99,
    credit_decline_start=3, credit_decline_per_month=0.073, credit_floor=0.20,
    bounce_start=7, bounce_rate=0.4,
    elec_track=0.9,          # electricity follows credit factor this strongly
    emp_decline_start=4, emp_decline_per_month=0.02,
    repay_break_months=3,    # repayment turns delayed/missed only this many months pre-default
)

# slow_decline: mild, bounded deterioration that stabilises — the "amber survivor" hard negatives.
# slow_decline: chronically stressed firms that limp along for years and DON'T default — the
# big, safe reservoir of honest false positives (they look risky point-in-time but survive).
SLOW_DECLINE = dict(
    start_range=(4, 14),
    util_base=0.60, util_creep_per_month=0.028, util_cap=0.86,
    credit_decline_per_month=0.022, credit_floor=0.66,
    gst_delay_per_month=3.0, gst_delay_max=30.0,
    occasional_bounce_prob=0.12,
    delayed_emi_months=(4, 8),   # a couple of delayed (cured) EMIs relative to onset
    delayed_dpd=22,              # DPD on those delayed-but-cured EMIs
)

GROWING = dict(turnover_growth=(0.010, 0.030), util_base=0.45)
STABLE = dict(util_base=0.50)

# sudden_shock: healthy until a shock (fire / partner dispute / key-customer loss) then abrupt
# default with NO behavioural precursor — the unpredictable ~15–20% of defaulters.
SHOCK = dict(
    start_range=(8, 22),        # month the shock lands
    dpd_ramp_months=3,          # 0→90 DPD over 3 months after the shock (default = start+3)
    collapse_factor=(0.30, 0.55),  # inflows crater to this fraction at the shock
    util_spike=0.95,            # limit maxed out trying to survive
)

# distress_then_recover: genuine 4–6 month distress drift (util creep, GST delays, credit dip)
# that then RECOVERS — the honest false positives that keep precision realistic.
# distress_then_recover: a "stressed survivor" — genuine deterioration (utilisation high, GST
# delays, depressed credit turnover) that then PLATEAUS at a stressed level and rides it out
# without ever defaulting (SMA-2 that never becomes NPA). The soft signals mirror a distress
# firm mid-drift, but with no DPD escalation — so point-in-time it is genuinely indistinguishable
# from a firm heading to default. This aleatoric overlap is what honestly caps AUC ~0.92.
# distress_then_recover: a chronic decliner that keeps SERVICING its EMI and does not default in
# the window. It SHARES the distress soft cascade (utilisation, credit, GST, bounces, EPFO,
# bureau DPD — see msme_series._SOFT_DISTRESS) driven by onset + severity, differing ONLY in the
# terminal repayment outcome (DPD never ramps to 90). So a far-from-default distress firm and one
# of these are indistinguishable point-in-time — the deliberate overlap that caps AUC ~0.94.
RECOVER = dict(start_range=(3, 12))   # onset of the shared soft decline

# Noise on the clean majority so stable/growing firms aren't implausibly pristine.
CLEAN_NOISE = dict(
    oneoff_bounce_prob=0.020,       # per month: a single stray outward cheque bounce
    oneoff_gst_delay_prob=0.05,     # per month: a one-off filing delay...
    oneoff_gst_delay_range=(5, 18), # ...of this many days
    lumpy_prob=0.06,                # per month: a lumpy (spike/dip) credit month
    lumpy_range=(0.65, 1.35),
)

# --------------------------------------------------------------------------------------
# Contagion event (BUILD_SPEC §3.3 / §9.1) — the scripted demo reveal
# --------------------------------------------------------------------------------------
CONTAGION = dict(
    event_month=16,             # Anchor #1 slows payments at month 16
    payment_cut=0.40,           # −40% to its suppliers
    supplier_lag_range=(1, 2),  # suppliers' inflows fall with a 1–2 month lag
    n_suppliers_per_anchor=(10, 20),
    anchor1_n_suppliers=14,     # Bharat Auto Components has exactly 14 suppliers
    n_induced_distress=5,       # 5 of the 14 enter distress trajectories...
    induced_distress_delay=(2, 4),   # ...2–4 months after the event
    anchor_inflow_share=(0.30, 0.55),  # anchor payment as a share of a supplier's inflows
)

# --------------------------------------------------------------------------------------
# Fraud pattern (BUILD_SPEC §3.3) — GST grows while electricity/EPFO stay flat or fall.
# --------------------------------------------------------------------------------------
FRAUD = dict(
    gst_growth_per_month=(0.020, 0.040),   # declared turnover balloons
    elec_change_per_month=(-0.004, 0.002), # electricity flat-to-falling
    emp_change_per_month=(-0.002, 0.001),  # headcount flat-to-falling
    bank_credit_lag=0.55,                  # actual receipts grow far slower than declared GST
)

# --------------------------------------------------------------------------------------
# Sector news/sentiment (BUILD_SPEC §3.2) — score in [-1, 1] per sector-month.
# --------------------------------------------------------------------------------------
SENTIMENT = dict(base=(-0.1, 0.35), month_vol=0.12)

# --------------------------------------------------------------------------------------
# Retail (DISHA) — occupations and intent (BUILD_SPEC §3.1 / §3.4)
# --------------------------------------------------------------------------------------
OCCUPATIONS = ["salaried", "self_employed", "gig_worker"]
OCCUPATION_WEIGHTS = [0.52, 0.28, 0.20]
INCOME_BANDS = {
    # band: (monthly_income_lo, monthly_income_hi)  in ₹
    "low":        (15_000, 35_000),
    "mid":        (35_000, 75_000),
    "upper_mid":  (75_000, 150_000),
    "high":       (150_000, 350_000),
}
INCOME_BAND_NAMES = ["low", "mid", "upper_mid", "high"]
INCOME_BAND_WEIGHTS = [0.34, 0.40, 0.19, 0.07]

LOAN_INTENTS = ["none", "browsing", "serious"]
LOAN_INTENT_WEIGHTS = [0.78, 0.15, 0.07]

RETAIL_PRODUCTS = ["savings", "salary_account", "fd", "credit_card", "upi"]

# Digital engagement generated causally from intent (BUILD_SPEC §3.4)
ENGAGEMENT = dict(
    serious_sessions=(4, 9),      # repeat evening sessions
    browsing_sessions=(1, 3),     # one-off shallow visits
    none_sessions=(0, 1),
    serious_evening_prob=0.75,
    browsing_evening_prob=0.35,
    serious_depth=(4, 9),         # pages per session
    browsing_depth=(1, 3),
    calc_use_prob_serious=0.85,   # EMI-calculator interaction probability
    calc_use_prob_browsing=0.25,
    loan_pages=["home_loan", "auto_loan", "personal_loan", "consumer_durable_loan"],
    dropoff_stages=["landing", "eligibility", "documents", "otp", "submitted"],
)

# Historical conversion target for the DISHA funnel (BUILD_SPEC §9.3):
# 10,000 enquiries → 96 conversions (<1%).
RETAIL_HISTORICAL_CONVERSIONS = 96
