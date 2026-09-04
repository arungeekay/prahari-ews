"""Narrative generation: a provider-agnostic LLM layer with a deterministic template fallback.

Provider selection (first match wins):
    OPENAI_API_KEY set    -> OpenAI (model from OPENAI_MODEL, default gpt-4o-mini)
    ANTHROPIC_API_KEY set -> Anthropic (model from ANTHROPIC_MODEL, default claude-sonnet-5)
    neither               -> deterministic Jinja2 templates

The template path is what the demo runs on with zero API keys. Any LLM error silently falls back
to the template - the demo must never break because of a missing/expired/over-quota key.
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


def active_provider() -> str:
    """Which narrative backend is live: 'openai', 'anthropic', or 'template'."""
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "template"


def using_llm() -> bool:
    return active_provider() != "template"


_SYSTEM = (
    "You are a credit-risk writing assistant for an Indian bank (IDBI). Rewrite the DRAFT into a "
    "crisp, professional banker's note. Use RBI vocabulary (SMA-0/1/2, IRAC, CRILC, RAG) where "
    "appropriate. Keep every number exactly as given. Do not invent facts. Do not use em dashes. "
    "Return only the note text, no preamble."
)


def _user_prompt(narrative_type: str, context: dict, template_text: str) -> str:
    return (f"Narrative type: {narrative_type}\n"
            f"Context (JSON): {json.dumps(context, default=str)}\n\n"
            f"DRAFT:\n{template_text}")


def _render_template(narrative_type: str, context: dict) -> str:
    if narrative_type not in TEMPLATES:
        raise KeyError(f"unknown narrative_type: {narrative_type!r}")
    return _env.from_string(TEMPLATES[narrative_type]).render(**context).strip()


def _try_openai(narrative_type: str, context: dict, template_text: str) -> str | None:
    """Best-effort OpenAI polish of the template draft. Returns None on any failure."""
    try:
        from openai import OpenAI
    except ImportError:
        return None
    try:
        client = OpenAI()
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            max_tokens=900,
            temperature=0.4,
            messages=[{"role": "system", "content": _SYSTEM},
                      {"role": "user", "content": _user_prompt(narrative_type, context, template_text)}],
        )
        out = (resp.choices[0].message.content or "").strip()
        return out or None
    except Exception:
        return None


def _try_anthropic(narrative_type: str, context: dict, template_text: str) -> str | None:
    """Best-effort Anthropic polish of the template draft. Returns None on any failure."""
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic()
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
        msg = client.messages.create(
            model=model, max_tokens=900, system=_SYSTEM,
            messages=[{"role": "user", "content": _user_prompt(narrative_type, context, template_text)}],
        )
        parts = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
        out = "\n".join(parts).strip()
        return out or None
    except Exception:
        return None


def generate(narrative_type: str, context: dict, product: str = "PRAHARI") -> str:
    """Return a narrative string. Always ends with the officer-review disclaimer."""
    template_text = _render_template(narrative_type, context)
    provider = active_provider()
    body = None
    if provider == "openai":
        body = _try_openai(narrative_type, context, template_text)
    elif provider == "anthropic":
        body = _try_anthropic(narrative_type, context, template_text)
    if body is None:                     # any failure or no provider -> deterministic template
        body = template_text
    disclaimer = DISCLAIMER_TMPL.format(product=product)
    return f"{body}\n\n- {disclaimer}"
