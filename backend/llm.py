"""Provider-agnostic LLM with two tiers and content-hash caching.

cheap  -> bulk extraction / classification fallback (Gemini Flash-class or Claude Haiku-class)
strong -> only for synthesis that needs reasoning (bull/bear, narrative-vs-numbers)

No key configured => every call returns None and callers use deterministic fallbacks.
"""
import hashlib
import json
import re

import requests

from . import cache
from .config import ANTHROPIC_KEY, CHEAP_MODEL, GEMINI_KEY, STRONG_MODEL

USAGE = {"calls": {"cheap": 0, "strong": 0}, "cached": 0, "chars_in": 0, "chars_out": 0}

_DEFAULTS = {
    "gemini": {"cheap": "gemini-2.5-flash", "strong": "gemini-2.5-pro"},
    "anthropic": {"cheap": "claude-haiku-5-5", "strong": "claude-sonnet-5-5"},
}


def provider():
    if ANTHROPIC_KEY:
        return "anthropic"
    if GEMINI_KEY:
        return "gemini"
    return None


def available() -> bool:
    return provider() is not None


def _model(tier):
    p = provider()
    override = CHEAP_MODEL if tier == "cheap" else STRONG_MODEL
    return override or _DEFAULTS[p][tier]


def _extract_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                return None
    return None


def _call(prompt: str, tier: str, system: str):
    p = provider()
    model = _model(tier)
    if p == "gemini":
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": GEMINI_KEY},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
        json={"model": model, "max_tokens": 2500, "system": system,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=90,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"]


SYSTEM = ("You are a precise financial-document extraction engine. Reply with valid JSON only. "
          "Use ONLY the text provided. If something is not in the text, use null. Never use outside knowledge.")


def ask_json(prompt: str, tier: str = "cheap", system: str = SYSTEM):
    """Returns parsed JSON or None (no key / error). Cached forever by content hash."""
    if not available():
        return None
    key = "llm:" + hashlib.sha1((tier + _model(tier) + system + prompt).encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        USAGE["cached"] += 1
        return hit
    try:
        out = _call(prompt, tier, system)
    except Exception as e:  # network / quota: degrade silently
        USAGE["last_error"] = str(e)[:200]
        return None
    USAGE["calls"][tier] += 1
    USAGE["chars_in"] += len(prompt)
    USAGE["chars_out"] += len(out)
    parsed = _extract_json(out)
    if parsed is not None:
        cache.put(key, parsed)
    return parsed
