"""Deterministic Indian name generation for businesses and people.

All functions take a ``numpy.random.Generator`` so output is fully reproducible under a seed.
Names are drawn to *look* real (regionally plausible surnames, sector-appropriate business
suffixes) without colliding with the fixed demo characters, which are named in ``characters``.
"""

from __future__ import annotations

import numpy as np

# Surnames spanning north/west/south clusters (matches our MSME city weighting).
SURNAMES = [
    "Agarwal", "Gupta", "Sharma", "Verma", "Singh", "Patel", "Shah", "Mehta", "Desai", "Jain",
    "Reddy", "Naidu", "Iyer", "Nair", "Menon", "Rao", "Pillai", "Krishnan", "Chandra", "Bhat",
    "Kulkarni", "Deshpande", "Joshi", "Kale", "Chauhan", "Yadav", "Malhotra", "Kapoor", "Bansal",
    "Goel", "Mittal", "Saxena", "Trivedi", "Bose", "Ghosh", "Das", "Nanda", "Sethi", "Arora",
    "Chettiar", "Gowda", "Hegde", "Shetty", "Kamath", "Prasad", "Mohan", "Venkatesh", "Raghavan",
]

MALE_FIRST = [
    "Amit", "Rohit", "Suresh", "Rajesh", "Vikram", "Arjun", "Karan", "Manish", "Deepak", "Sanjay",
    "Anil", "Sunil", "Ramesh", "Naveen", "Praveen", "Kiran", "Ashok", "Vijay", "Harish", "Nitin",
    "Rahul", "Aditya", "Varun", "Gaurav", "Sachin", "Prakash", "Mahesh", "Girish", "Yogesh", "Dinesh",
]
FEMALE_FIRST = [
    "Priya", "Anjali", "Kavya", "Sneha", "Pooja", "Divya", "Neha", "Swati", "Meena", "Lakshmi",
    "Radha", "Sunita", "Geeta", "Rekha", "Nisha", "Deepa", "Anita", "Sushma", "Vidya", "Shreya",
    "Aishwarya", "Bhavana", "Chitra", "Kalpana", "Madhuri", "Sarita", "Usha", "Vandana", "Rashmi",
]

# Sector-appropriate business words + suffixes → "Agarwal Steels", "Krishna Textiles Pvt Ltd".
SECTOR_WORDS = {
    "manufacturing":   ["Industries", "Fabricators", "Steels", "Engineering Works", "Castings",
                        "Components", "Metals", "Forgings", "Tools", "Precision Works"],
    "trading":         ["Trading Co", "Traders", "Enterprises", "Distributors", "Agencies",
                        "Trade Links", "Mercantile", "Sales Corp", "& Sons", "Trade House"],
    "logistics":       ["Logistics", "Roadlines", "Carriers", "Transport", "Freight Movers",
                        "Cargo", "Transways", "Supply Chain", "Movers", "Express"],
    "services":        ["Services", "Solutions", "Consultancy", "Systems", "Associates",
                        "Enterprises", "Technologies", "Facilities", "& Co", "Ventures"],
    "food_processing": ["Foods", "Snacks", "Agro Foods", "Dairy", "Flour Mills",
                        "Spices", "Food Products", "Beverages", "Mills", "Provisions"],
}
BRAND_PREFIXES = ["Sri", "Shree", "New", "Om", "Jai", "Krishna", "Lakshmi", "Ganesh", "National",
                  "Bharat", "Royal", "Star", "Prime", "United", "Modern", "Sunrise", "Balaji"]
COMPANY_SUFFIXES = ["", "", "", "Pvt Ltd", "Pvt Ltd", "LLP", "& Co"]


def make_person_name(rng: np.random.Generator) -> tuple[str, str]:
    """Return (full_name, gender) where gender ∈ {'M','F'}."""
    if rng.random() < 0.62:
        first = MALE_FIRST[rng.integers(len(MALE_FIRST))]
        gender = "M"
    else:
        first = FEMALE_FIRST[rng.integers(len(FEMALE_FIRST))]
        gender = "F"
    surname = SURNAMES[rng.integers(len(SURNAMES))]
    return f"{first} {surname}", gender


def make_business_name(rng: np.random.Generator, sector: str) -> str:
    """Sector-appropriate business name, e.g. 'Shree Agarwal Fabricators Pvt Ltd'."""
    words = SECTOR_WORDS[sector]
    word = words[rng.integers(len(words))]
    r = rng.random()
    if r < 0.45:
        stem = SURNAMES[rng.integers(len(SURNAMES))]
    elif r < 0.80:
        stem = BRAND_PREFIXES[rng.integers(len(BRAND_PREFIXES))]
    else:
        stem = f"{BRAND_PREFIXES[rng.integers(len(BRAND_PREFIXES))]} {SURNAMES[rng.integers(len(SURNAMES))]}"
    suffix = COMPANY_SUFFIXES[rng.integers(len(COMPANY_SUFFIXES))]
    name = f"{stem} {word}".strip()
    if suffix:
        name = f"{name} {suffix}"
    return name
