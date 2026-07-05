"""DISHA product matcher (BUILD_SPEC §4.2): rule-based match to home / auto / consumer-durable /
personal loans, with eligibility band and serviceable ticket size (EMI ≤ 50% of disposable at
product rates). Transparent rules — the RM sees exactly why a product was matched.
"""

from __future__ import annotations

PRODUCTS = {
    # product:            (annual_rate, tenure_months, min_disposable, label)
    "home_loan":            (0.086, 240, 25_000, "Home Loan"),
    "auto_loan":            (0.095, 60, 12_000, "Auto Loan"),
    "consumer_durable_loan": (0.140, 18, 4_000, "Consumer Durable Loan"),
    "personal_loan":        (0.160, 36, 15_000, "Personal Loan"),
}


def _max_ticket(emi: float, annual_rate: float, tenure: int) -> float:
    r = annual_rate / 12
    if r <= 0:
        return emi * tenure
    return emi * (1 - (1 + r) ** (-tenure)) / r


def match_products(capacity: dict, customer_row=None) -> dict:
    disposable = capacity["disposable_income"]
    serviceable_emi = capacity["serviceable_emi"]
    income_type = capacity["income_type"]
    discipline = capacity["discipline_score"]

    matches = []
    for key, (rate, tenure, min_disp, label) in PRODUCTS.items():
        eligible = disposable >= min_disp
        reasons = []
        if not eligible:
            reasons.append(f"disposable ₹{disposable:,} below ₹{min_disp:,} threshold")
        # product-specific eligibility nuances
        if key == "personal_loan" and income_type == "gig_worker":
            eligible = False; reasons.append("unsecured personal loan not advised for volatile gig income")
        if key == "personal_loan" and discipline < 30:
            eligible = False; reasons.append("discipline score below unsecured-lending bar")
        if key == "home_loan" and discipline < 30:
            eligible = False; reasons.append("discipline score below long-tenure bar")
        # long-tenure secured loans need stable income — not a volatile gig profile with low buffer
        if key == "auto_loan" and income_type == "gig_worker" and discipline < 60:
            eligible = False; reasons.append("60-month tenure not advised for volatile gig income")

        ticket = _max_ticket(serviceable_emi, rate, tenure)
        # suitability: prefer shorter tenure for volatile income; reward headroom
        tenure_penalty = (tenure / 240) * (1.5 if income_type in ("gig_worker", "self_employed") else 0.6)
        suitability = (1.0 if eligible else 0.0) * (0.5 + 0.5 * min(1.0, ticket / 200_000)) - tenure_penalty * 0.3
        matches.append(dict(
            product=key, label=label, eligible=eligible,
            rate=rate, tenure_months=tenure,
            ticket_size=int(round(ticket)) if eligible else 0,
            emi=int(round(serviceable_emi)) if eligible else 0,
            suitability=round(suitability, 3),
            reasons=reasons,
        ))

    eligible_sorted = sorted([m for m in matches if m["eligible"]], key=lambda m: -m["suitability"])
    best = eligible_sorted[0] if eligible_sorted else None
    return dict(best_match=best, all_matches=sorted(matches, key=lambda m: -m["suitability"]))
