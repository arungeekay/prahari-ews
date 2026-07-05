"""Models (BUILD_SPEC §4.2): PD, survival/runway, contagion, AROGYA score, Verification
Triangle, DISHA intent / capacity / matcher. Each is trainable/computable from the synthetic
frames and serialisable to a model directory that the product backends load at boot."""

from __future__ import annotations

from .pd_model import PDModel
from .survival import RunwayModel
from .contagion import ContagionGraph
from .arogya_score import score_arogya, AROGYA_PILLARS
from .triangle import verification_triangle
from .intent_model import IntentModel
from .capacity import capacity_profile
from .matcher import match_products

__all__ = [
    "PDModel", "RunwayModel", "ContagionGraph",
    "score_arogya", "AROGYA_PILLARS", "verification_triangle",
    "IntentModel", "capacity_profile", "match_products",
]
