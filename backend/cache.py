"""Tiny disk cache (json) keyed by string. TTL in seconds; None = forever."""
import hashlib
import json
import time

from .config import CACHE_DIR

STATS = {"hit": 0, "miss": 0}


def _path(key: str):
    return CACHE_DIR / (hashlib.sha1(key.encode()).hexdigest()[:24] + ".json")


def get(key: str, ttl=None):
    p = _path(key)
    if not p.exists():
        STATS["miss"] += 1
        return None
    try:
        blob = json.loads(p.read_text())
    except Exception:
        STATS["miss"] += 1
        return None
    if ttl is not None and time.time() - blob["t"] > ttl:
        STATS["miss"] += 1
        return None
    STATS["hit"] += 1
    return blob["v"]


def put(key: str, value):
    try:
        _path(key).write_text(json.dumps({"t": time.time(), "v": value}))
    except Exception:
        pass
    return value
