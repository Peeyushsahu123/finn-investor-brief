"""NSE corporate announcements. NSE needs a warmed-up cookie session and browser-like headers."""
import time
from datetime import datetime, timedelta

import requests

from .. import cache
from ..config import UA

_S = {"s": None, "t": 0}


def _session():
    if _S["s"] is None or time.time() - _S["t"] > 600:
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept": "application/json,text/plain,*/*",
                          "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/"})
        s.get("https://www.nseindia.com/companies-listing/corporate-filings-announcements", timeout=10)
        _S["s"], _S["t"] = s, time.time()
    return _S["s"]


def _norm(sym, r):
    ts = r.get("an_dt") or r.get("sort_date") or ""
    try:
        iso = datetime.strptime(ts, "%d-%b-%Y %H:%M:%S").isoformat()
    except Exception:
        iso = ts
    return {
        "id": f"{sym}:{r.get('seq_id') or r.get('an_dt')}:{(r.get('desc') or '')[:20]}",
        "symbol": sym,
        "ts": iso,
        "subject": (r.get("desc") or "").strip(),
        "text": (r.get("attchmtText") or "").strip(),
        "url": r.get("attchmtFile") or "",
        "source": "NSE",
    }


def fetch_announcements(symbol: str, days: int = 7):
    key = f"nse:{symbol}:{days}"
    hit = cache.get(key, ttl=900)
    if hit is not None:
        return hit
    to = datetime.now()
    frm = to - timedelta(days=days)
    r = _session().get(
        "https://www.nseindia.com/api/corporate-announcements",
        params={"index": "equities", "symbol": symbol,
                "from_date": frm.strftime("%d-%m-%Y"), "to_date": to.strftime("%d-%m-%Y")},
        timeout=15,
    )
    r.raise_for_status()
    rows = [_norm(symbol, x) for x in r.json()]
    return cache.put(key, rows)
