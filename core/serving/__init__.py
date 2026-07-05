"""Serving layer: loads data + models once and precomputes the tables the product APIs need."""

from __future__ import annotations

from .bundle import Bundle, get_bundle

__all__ = ["Bundle", "get_bundle"]
