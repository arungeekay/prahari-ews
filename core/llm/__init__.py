"""Provider-agnostic narrative layer (BUILD_SPEC §4.4).

`generate(narrative_type, context)` returns text from the Anthropic API when ANTHROPIC_API_KEY
is set, otherwise from deterministic Jinja2 templates so the demo always works keyless. Every
generated document ends with the officer-review disclaimer.
"""

from __future__ import annotations

from .provider import generate, available_narratives, using_llm, DISCLAIMER_TMPL

__all__ = ["generate", "available_narratives", "using_llm", "DISCLAIMER_TMPL"]
