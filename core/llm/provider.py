"""Narrative generation: Anthropic API when configured, deterministic Jinja2 templates otherwise.

The template path is the default and is what the demo runs on with zero API keys. The LLM path
is a thin enhancement that, on any error, silently falls back to the template - the demo must
never break because of a missing/expired key.
"""

from __future__ import annotations

import json
import os

from jinja2 import Environment, StrictUndefined, Undefined

from .templates import TEMPLATES

DISCLAIMER_TMPL = "Draft prepared by {product} AI. For officer review - not a final decision."


def _inr(x) -> str:
    """Format a rupee amount in Indian lakh/crore, e.g. 41200000 -> '₹4.12 Cr'."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    a = abs(v)
    if a >= 1e7:
        return f"₹{v / 1e7:.2f} Cr"
    if a >= 1e5:
        return f"₹{v / 1e5:.2f} L"
    return f"₹{v:,.0f}"


# Lenient environment: undefined -> empty string, so partial contexts still render.
_env = Environment(undefined=Undefined, trim_blocks=True, lstrip_blocks=True)
_env.filters["inr"] = _inr
_env.globals["inr"] = _inr


def available_narratives() -> list[str]:
    return sorted(TEMPLATES.keys())


def using_llm() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _render_template(narrative_type: str, context: dict) -> str:
    if narrative_type not in TEMPLATES:
        raise KeyError(f"unknown narrative_type: {narrative_type!r}")
    return _env.from_string(TEMPLATES[narrative_type]).render(**context).strip()


def _try_llm(narrative_type: str, context: dict, template_text: str) -> str | None:
    """Best-effort Anthropic polish of the template draft. Returns None on any failure."""
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic()
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
        system = (
            "You are a credit-risk writing assistant for an Indian bank (IDBI). Rewrite the DRAFT "
            "into a crisp, professional banker's note. Use RBI vocabulary (SMA-0/1/2, IRAC, CRILC, "
            "RAG) where appropriate. Keep every number exactly as given. Do not invent facts. "
            "Return only the note text, no preamble."
        )
        msg = client.messages.create(
            model=model,
            max_tokens=900,
            system=system,
            messages=[{
                "role": "user",
                "content": (
                    f"Narrative type: {narrative_type}\n"
                    f"Context (JSON): {json.dumps(context, default=str)}\n\n"
                    f"DRAFT:\n{template_text}"
                ),
            }],
        )
        parts = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
        out = "\n".join(parts).strip()
        return out or None
    except Exception:
        return None


def generate(narrative_type: str, context: dict, product: str = "PRAHARI") -> str:
    """Return a narrative string. Always ends with the officer-review disclaimer."""
    template_text = _render_template(narrative_type, context)
    body = None
    if using_llm():
        body = _try_llm(narrative_type, context, template_text)
    if body is None:
        body = template_text
    disclaimer = DISCLAIMER_TMPL.format(product=product)
    return f"{body}\n\n- {disclaimer}"
