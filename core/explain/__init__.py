"""Explainability (BUILD_SPEC §4.3): SHAP reason codes + plain-language templates + auditor table."""

from __future__ import annotations

from .reasons import ReasonExplainer, plain_language

__all__ = ["ReasonExplainer", "plain_language"]
