"""Unstructured input: loan-officer note scoring (BUILD_SPEC §3.2 / Track 04 "unstructured").

Two scorers share one output contract so the feature pipeline never cares which produced it:

    score_note(text) -> {"sentiment": float in [-1, 1], "themes": [str], "severity": 0..3}

* `LexiconScorer` (default, deterministic, offline): weighted phrase lexicon plus a theme
  vocabulary a credit officer would recognise (receivables, labour, demand, input cost, promoter
  conduct, legal, stock, capacity). Keyless, reproducible, auditable.
* `LLMScorer` (optional): scores through the configured LLM provider with a strict JSON contract,
  cached to parquet keyed by note hash so scoring is a one-off offline job and serving stays
  keyless. Enabled with PRAHARI_NOTE_SCORER=llm and a provider key; falls back to the lexicon.

`note_window_features(notes)` turns the notes inside a trailing window into model features:
recency-weighted sentiment over NON-EMPTY months (fixing the dilution of averaging empty months),
worst sentiment, count of adverse notes, note count, and one flag per theme.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import numpy as np

THEMES = ["receivables", "labour", "demand", "input_cost", "promoter", "legal", "stock", "capacity"]

# phrase -> sentiment weight (negative = adverse). Multi-word phrases are matched before words.
_LEXICON = {
    # adverse
    "evasive": -0.9, "not reachable": -0.9, "unable to meet interest": -1.0, "acute cash pressure": -1.0,
    "legal notice": -0.9, "disputed": -0.6, "creditor pressure": -0.8, "wages delayed": -0.8,
    "epfo remittance pending": -0.6, "statutory dues overdue": -0.8, "gst notice": -0.6,
    "machines idle": -0.8, "idle": -0.5, "reduced activity": -0.6, "single shift": -0.6,
    "unit shut": -1.0, "operations halted": -1.0, "production stopped": -1.0, "fire": -0.9,
    "flood": -0.9, "exited abruptly": -0.9, "order book lost": -0.9, "dispute": -0.7,
    "disrupted": -0.7, "lower than book": -0.8, "materially below statement": -1.0,
    "delayed": -0.4, "delay": -0.4, "late": -0.4, "overdue": -0.6, "slowdown": -0.4,
    "seeking additional finance": -0.7, "bridge working capital": -0.5, "overlimit": -0.4,
    "edging up": -0.3, "input costs up": -0.3, "thin": -0.3, "no new orders": -0.6,
    "persistently high": -0.4, "slow collections": -0.5, "still outstanding": -0.4,
    "ageing beyond": -0.4, "some delay": -0.3, "unchanged from last year": -0.2,
    "appears modest": -0.3, "confirmations awaited": -0.2, "verification pending": -0.2,
    "stress persists": -0.4, "reduced scale": -0.5,
    # favourable
    "well stocked": 0.7, "operations normal": 0.6, "satisfactory": 0.6, "no adverse": 0.7,
    "cooperative": 0.5, "healthy": 0.6, "strong": 0.5, "expansion": 0.6, "upbeat": 0.6,
    "hiring": 0.5, "ahead of projections": 0.7, "within dp": 0.4, "current": 0.3,
    "production normal": 0.6, "serviced regularly": 0.3, "servicing dues on time": 0.3,
    "no fresh deterioration": 0.2, "unchanged": 0.0, "stable": 0.1, "normalising": 0.4,
    "improving": 0.5, "recovering": 0.5, "resolved": 0.5, "confirmed orders": 0.5,
}
_THEME_WORDS = {
    "receivables": ["receivable", "debtors", "collections", "buyer", "payment delays", "outstanding",
                    "confirmations", "distributor", "customer"],
    "labour": ["worker", "wages", "epfo", "operators", "shift", "hiring", "headcount"],
    "demand": ["order", "dispatch", "demand", "sales", "turnover", "festival", "no new orders", "exited"],
    "input_cost": ["input cost", "supplier", "credit period", "margin"],
    "promoter": ["promoter", "not reachable", "evasive", "dispute", "cooperative", "upbeat"],
    "legal": ["legal notice", "statutory", "gst notice", "court", "lien", "notice"],
    "stock": ["stock", "godown", "book value", "statement", "physical"],
    "capacity": ["machine", "capacity", "expansion", "unit", "production", "operations", "fire", "flood"],
}
_SEVERE = ["unable to meet interest", "legal notice", "unit shut", "operations halted", "production stopped",
           "materially below statement", "acute cash pressure", "not reachable", "fire", "flood", "exited abruptly"]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


# longest phrases first so "not reachable" is not double counted by "reachable"
_LEXICON_ORDER = sorted(_LEXICON, key=len, reverse=True)


class LexiconScorer:
    """Deterministic phrase-lexicon scorer. Same input, same output, no network. Scores are
    memoised per distinct note text, so a book with a few hundred distinct notes scores in
    microseconds per row."""

    name = "lexicon"

    def __init__(self):
        self._memo: dict[str, dict] = {}

    def score(self, text: str) -> dict:
        if not text or not str(text).strip():
            return dict(sentiment=0.0, themes=[], severity=0)
        key = str(text)
        hit = self._memo.get(key)
        if hit is not None:
            return hit
        out = self._score_uncached(key)
        if len(self._memo) < 50_000:
            self._memo[key] = out
        return out

    def _score_uncached(self, text: str) -> dict:
        t = _norm(text)
        total, hits = 0.0, 0
        for phrase in _LEXICON_ORDER:
            if phrase in t:
                total += _LEXICON[phrase]
                hits += 1
                t = t.replace(phrase, " ")
        sentiment = float(np.clip(total / max(1, hits) * (1.0 if hits <= 2 else 1.15), -1, 1)) if hits else 0.0
        tl = _norm(text)
        themes = [th for th, words in _THEME_WORDS.items() if any(w in tl for w in words)]
        severity = 0
        if any(s in tl for s in _SEVERE):
            severity = 3
        elif sentiment <= -0.6:
            severity = 2
        elif sentiment < -0.15:
            severity = 1
        return dict(sentiment=round(sentiment, 3), themes=themes, severity=severity)

    def score_many(self, texts) -> list[dict]:
        return [self.score(x) for x in texts]


class LLMScorer:
    """Optional LLM scorer with a parquet cache. Falls back to the lexicon on any failure so the
    pipeline is never blocked by a key, a quota, or a network."""

    name = "llm"

    def __init__(self, cache_dir: str | None = None):
        self.fallback = LexiconScorer()
        self.cache_path = Path(cache_dir or os.environ.get("DATA_DIR", "data")) / "notes_cache.json"
        self._cache: dict[str, dict] = {}
        if self.cache_path.exists():
            try:
                self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                self._cache = {}

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha1(_norm(text).encode("utf-8")).hexdigest()

    def _call_llm(self, text: str) -> dict | None:
        prompt = ("Score this Indian bank loan-officer note about an MSME borrower. Return ONLY JSON with keys "
                  "sentiment (float -1..1, negative = credit-adverse), themes (subset of "
                  f"{THEMES}), severity (0 none, 1 mild, 2 material, 3 severe).\nNOTE: {text}")
        try:
            if os.environ.get("ANTHROPIC_API_KEY"):
                import anthropic
                client = anthropic.Anthropic()
                msg = client.messages.create(model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5"),
                                             max_tokens=200, messages=[{"role": "user", "content": prompt}])
                raw = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
            elif os.environ.get("OPENAI_API_KEY"):
                from openai import OpenAI
                client = OpenAI()
                r = client.chat.completions.create(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                                                   messages=[{"role": "user", "content": prompt}], max_tokens=200)
                raw = r.choices[0].message.content or ""
            else:
                return None
            raw = raw[raw.find("{"): raw.rfind("}") + 1]
            d = json.loads(raw)
            return dict(sentiment=float(np.clip(float(d.get("sentiment", 0.0)), -1, 1)),
                        themes=[t for t in d.get("themes", []) if t in THEMES],
                        severity=int(np.clip(int(d.get("severity", 0)), 0, 3)))
        except Exception:
            return None

    def score(self, text: str) -> dict:
        if not text or not str(text).strip():
            return dict(sentiment=0.0, themes=[], severity=0)
        k = self._key(text)
        if k in self._cache:
            return self._cache[k]
        out = self._call_llm(str(text)) or self.fallback.score(text)
        self._cache[k] = out
        return out

    def score_many(self, texts) -> list[dict]:
        out = [self.score(x) for x in texts]
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self._cache), encoding="utf-8")
        except Exception:
            pass
        return out


_DEFAULT: LexiconScorer | LLMScorer | None = None


def get_scorer():
    """Process-wide scorer: lexicon unless PRAHARI_NOTE_SCORER=llm and a provider key exists."""
    global _DEFAULT
    if _DEFAULT is None:
        want_llm = os.environ.get("PRAHARI_NOTE_SCORER", "lexicon").lower() == "llm"
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))
        _DEFAULT = LLMScorer() if (want_llm and has_key) else LexiconScorer()
    return _DEFAULT


def score_note(text: str) -> dict:
    return get_scorer().score(text)


def note_sentiment(note: str) -> float:
    """Backward-compatible scalar sentiment in [-1, 1]."""
    return float(score_note(note)["sentiment"])


NOTE_FEATURES = ["note_sent_ewma", "note_sent_min", "note_adverse_cnt", "note_n", "note_severity_max"] + \
                [f"note_theme_{t}" for t in THEMES]


def note_window_features(notes: list[str], half_life: float = 2.0) -> dict:
    """Features for the notes inside one trailing window (oldest first). Empty months are ignored
    rather than averaged in as zero, and recent notes weigh more (exponential decay by position)."""
    scored = [(i, score_note(n)) for i, n in enumerate(notes) if n and str(n).strip()]
    out = {f: 0.0 for f in NOTE_FEATURES}
    if not scored:
        return out
    n = len(notes)
    w = np.array([0.5 ** ((n - 1 - i) / half_life) for i, _ in scored])
    s = np.array([d["sentiment"] for _, d in scored])
    out["note_sent_ewma"] = float(np.sum(w * s) / np.sum(w))
    out["note_sent_min"] = float(s.min())
    out["note_adverse_cnt"] = float((s < -0.15).sum())
    out["note_n"] = float(len(scored))
    out["note_severity_max"] = float(max(d["severity"] for _, d in scored))
    for th in THEMES:
        out[f"note_theme_{th}"] = float(any(th in d["themes"] for _, d in scored))
    return out
