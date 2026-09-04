"""Named demo characters (BUILD_SPEC §9) - the storylines that must render exactly.

These are placed *first* in their respective tables with fixed ids and attributes, then the
random pool fills the rest. Their behavioural series are crafted deterministically by
``msme_series``/``retail_series`` using the ``demo`` tag on each entity so the scripted beats
land precisely (Sharma's cheque return at month 23, Gupta's broken triangle, Ravi's ₹31k, …).

Nothing here uses randomness; the fixed fields anchor the storylines and the series modules add
seeded, causally-consistent noise on top.
"""

from __future__ import annotations

from . import config as C

# --------------------------------------------------------------------------------------
# MSME demo cast (PRAHARI + AROGYA). Placed as the first borrowers.
# `demo` is the stable tag the series generator keys on.
# --------------------------------------------------------------------------------------
DEMO_MSMES = [
    # Sharma Fabricators - slow-distress, runway ≈7mo at demo (BUILD_SPEC §9.1).
    # distress_start=16 → storyline month 3 = idx 19 (GST delays), month 5 = idx 21
    # (credits −22%, util >85%), month 7 = idx 23 (first cheque return). default ≈ idx 30.
    dict(
        demo="sharma", name="Sharma Fabricators", sector="manufacturing",
        city="Ludhiana", state="Punjab", vintage_years=11,
        loan_type="CC", sanctioned_limit=1_20_00_000,
        promoter_age=52, promoter_experience_years=24, promoter_qualification="HSC",
        trajectory="distress_at_month_k", distress_start=16, drift_len=14,
    ),
    # Verma Textiles - clean twin; consistent GST/electricity/EPFO → ~712 REFER (AROGYA).
    dict(
        demo="verma", name="Verma Textiles", sector="manufacturing",
        city="Surat", state="Gujarat", vintage_years=8,
        loan_type="CC", sanctioned_limit=85_00_000,
        promoter_age=45, promoter_experience_years=17, promoter_qualification="Graduate",
        trajectory="growing",
    ),
    # Gupta Trading Co - fraud twin; identical declared GST to Verma, electricity/EPFO decoupled.
    dict(
        demo="gupta", name="Gupta Trading Co", sector="trading",
        city="Rajkot", state="Gujarat", vintage_years=7,
        loan_type="CC", sanctioned_limit=85_00_000,
        promoter_age=41, promoter_experience_years=14, promoter_qualification="Graduate",
        trajectory="fraud_pattern",
    ),
    # Nisha Snacks - thin file: only 5 months of history (BUILD_SPEC §9.2 / §6.3).
    dict(
        demo="nisha", name="Nisha Snacks", sector="food_processing",
        city="Coimbatore", state="Tamil Nadu", vintage_years=1,
        loan_type="term", sanctioned_limit=18_00_000,
        promoter_age=34, promoter_experience_years=6, promoter_qualification="Graduate",
        trajectory="stable", months_available=5,
    ),
]

# The clean/fraud twins declare the SAME GST turnover; this is their shared base turnover (₹/mo).
TWIN_BASE_TURNOVER = 42_00_000     # ₹42 lakh/month
TWIN_GST_GROWTH_PER_MONTH = 0.020  # +2%/month declared turnover (both twins, identical series)

# Anchor #1 - Bharat Auto Components Ltd (the contagion source, BUILD_SPEC §9.1).
ANCHOR1 = dict(anchor_id="ANCH1", name="Bharat Auto Components Ltd", sector="manufacturing")
OTHER_ANCHOR_NAMES = [
    "Deccan Industrial Supplies Ltd",
    "Hindustan Packaging Corp",
    "Coromandel Agri Exports Ltd",
]

# --------------------------------------------------------------------------------------
# Retail demo cast (DISHA). Placed as the first customers.
# --------------------------------------------------------------------------------------
DEMO_RETAIL = [
    # Ravi Kumar - gig worker; volatile UPI income ≈₹31k, disposable ≈₹14k, intent HOT,
    # clicked personal-loan page but capacity matches consumer-durable (BUILD_SPEC §9.3).
    dict(
        # base_income set so the *reconstructed* (volatility-discounted) monthly income lands
        # ≈₹31k and disposable ≈₹14k after ₹3k EMI + ₹6k rent + ₹8k essentials.
        demo="ravi", name="Ravi Kumar", age=29, city="Pune", state="Maharashtra",
        occupation_type="gig_worker", income_band="low", base_income=33_000,
        loan_intent="serious", capacity_score=0.55,
        clicked_page="personal_loan", existing_products=["savings", "upi"],
    ),
    # Discipline twins - same ₹60k salary, opposite day-of-month balance curves.
    dict(
        demo="discipline_saver", name="Kavya Iyer", age=33, city="Pune", state="Maharashtra",
        occupation_type="salaried", income_band="mid", base_income=60_000,
        loan_intent="serious", capacity_score=0.86, discipline="saver",
        existing_products=["salary_account", "savings", "fd", "upi"],
    ),
    dict(
        demo="discipline_spender", name="Rahul Nair", age=31, city="Pune", state="Maharashtra",
        occupation_type="salaried", income_band="mid", base_income=60_000,
        loan_intent="browsing", capacity_score=0.34, discipline="spender",
        existing_products=["salary_account", "credit_card", "upi"],
    ),
]

N_DEMO_MSME = len(DEMO_MSMES)
N_DEMO_RETAIL = len(DEMO_RETAIL)
