"""Single door to data. Chooses live vs demo and degrades per-call so the app never goes blank."""
import time

from . import config
from .sources import demo

_STATE = {"mode": None, "checked": 0, "reason": ""}


def mode() -> str:
    """'live' or 'demo'. In auto mode, probe Yahoo once (cached 10 min)."""
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
    return {"mode": mode(), "reason": _STATE["reason"]}


def universe():
    if mode() == "demo":
        return demo.universe()
    return [{"symbol": s, "name": n, "sector": sec, "cap": cap} for s, n, sec, cap in config.PORTFOLIO]


def eod(symbols, days=60):
    if mode() == "demo":
        return demo.eod(symbols, days)
    from .sources import prices
    return prices.fetch_eod(symbols, days)


def announcements(symbol, days=7):
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
