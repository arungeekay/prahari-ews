"""Point-in-time feature pipeline (BUILD_SPEC §4.1).

The one inviolable rule: features at (entity, as_of) use ONLY data with month_index <= as_of.
The same builders serve PRAHARI (monitoring), AROGYA (origination snapshot) and DISHA (retail
capacity), so downstream models and the API share exactly one feature definition.
"""

from __future__ import annotations

from .pipeline import (
    MSME_FEATURES,
    msme_features_at,
    build_msme_training_matrix,
    note_sentiment,
)
from .retail import (
    RETAIL_FEATURES,
    retail_capacity_features,
    engagement_features,
)

__all__ = [
    "MSME_FEATURES", "msme_features_at", "build_msme_training_matrix", "note_sentiment",
    "RETAIL_FEATURES", "retail_capacity_features", "engagement_features",
]
