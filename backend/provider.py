"""Single door to data. Chooses live vs demo and degrades per-call so the app never goes blank."""
import time
import json
import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def snapshot():
    path = Path(__file__).with_name("portfolio_snapshot.json")
    return json.loads(path.read_text(encoding="utf-8"))

from . import config
from .sources import demo

_STATE = {"mode": None, "checked": 0, "reason": ""}


def mode() -> str:
    """'live' or 'demo'. In auto mode, probe Yahoo once (cached 10 min)."""
    # Existing hosted demos use the captured real portfolio. Local demo fixtures remain reproducible.
    if config.MODE == "snapshot" or (config.MODE == "demo" and os.getenv("RENDER") == "true"):
        return "snapshot"
    if config.MODE in ("live", "demo"):
        return config.MODE
    if _STATE["mode"] and time.time() - _STATE["checked"] < 600:
        return _STATE["mode"]
    try:
        from .sources import prices
        prices.fetch_eod(["RELIANCE"], days=5)
        _STATE.update(mode="live", reason="")
    except Exception as e:
        _STATE.update(mode="demo", reason=f"live sources unreachable ({type(e).__name__})")
    _STATE["checked"] = time.time()
    return _STATE["mode"]


def info():
    if mode() == "snapshot":
        return {"mode": "snapshot", "asof": snapshot()["asof"], "reason": "Saved NSE filings and end-of-day market data"}
    return {"mode": mode(), "reason": _STATE["reason"]}


def universe():
    if mode() == "demo":
        return demo.universe()
    return [{"symbol": s, "name": n, "sector": sec, "cap": cap} for s, n, sec, cap in config.PORTFOLIO]


def eod(symbols, days=60):
    if mode() == "snapshot":
        return {s: snapshot()["prices"].get(s, [])[-days:] for s in symbols}
    if mode() == "demo":
        return demo.eod(symbols, days)
    from .sources import prices
    return prices.fetch_eod(symbols, days)


def announcements(symbol, days=7):
    if mode() == "snapshot":
        return snapshot()["filings"].get(symbol, [])
    if mode() == "demo":
        return demo.announcements(symbol, days)
    from .sources import nse
    try:
        return nse.fetch_announcements(symbol, days)
    except Exception:
        return []


def fundamentals(symbol):
    if mode() == "demo":
        return demo.fundamentals(symbol)
    from .sources import screener
    return screener.fetch(symbol)


def doc_text(url: str) -> str:
    if url.startswith("demo://"):
        return demo.text(url)
    from .sources import screener
    try:
        return screener.pdf_text(url)
    except Exception:
        return ""


def known_symbols():
    return {u["symbol"]: u for u in universe()}
