"""FINN API + static frontend.  Run:  uvicorn backend.main:app --port 8000"""
import re
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import cache, config, llm, provider
from .push import digest as pdigest
from .pull import research as pres

app = FastAPI(title="FINN")
FRONT = Path(__file__).resolve().parent.parent / "frontend"


def _rules(hours, price, vol, watch, mute, minp):
    r = {}
    if hours is not None:
        r["window_hours"] = hours
    if price is not None:
        r["price_move_pct"] = price
    if vol is not None:
        r["volume_mult"] = vol
    if watch is not None:
        r["watch"] = [w for w in watch.split(",") if w]
    if mute:
        r["mute"] = [w for w in mute.split(",") if w]
    if minp is not None:
        r["min_priority"] = minp
    return r


@app.get("/api/meta")
def meta():
    uni = provider.universe()
    sug = ["QUANTACKT", "NIMBUS", "HALCYONM", "BRIGHTFLD"] if provider.mode() == "demo" else config.ADHOC_LIVE
    return {"data": provider.info(), "universe": uni, "suggested": sug, "defaults": config.DEFAULT_RULES,
            "categories": __import__("backend.push.classify", fromlist=["x"]).CATEGORIES, "llm": llm.provider()}


@app.get("/api/digest")
def digest(hours: float | None = None, price: float | None = None, vol: float | None = None,
           watch: str | None = None, mute: str | None = None, minp: int | None = None):
    return pdigest.digest(_rules(hours, price, vol, watch, mute, minp))


@app.get("/api/alerts")
def alerts(hours: float | None = None, price: float | None = None, vol: float | None = None,
           watch: str | None = None, mute: str | None = None):
    return pdigest.alerts(_rules(hours, price, vol, watch, mute, None))


@app.get("/api/research/{symbol}")
def research(symbol: str, sections: str | None = None):
    try:
        return pres.research(symbol, sections.split(",") if sections else None)
    except KeyError:
        return JSONResponse({"error": f"No fundamentals available for {symbol.upper()} in this data mode."}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": f"Could not research {symbol.upper()}: {type(e).__name__}: {str(e)[:160]}"}, status_code=502)


# ---------------- Ask: natural language -> structured cards ----------------
SECTION_KEYS = [
    ("business", r"what does|business|segment|revenue mix|model"),
    ("financials", r"number|financial|snapshot|margin|profit|revenue|roce|results"),
    ("trajectory", r"trajector|trend|growing|growth|direction|compress"),
    ("balance", r"debt|leverage|balance|borrow|working.?capital|interest"),
    ("cash", r"cash|fcf|conversion"),
    ("guidance", r"guid|promis|deliver|target|forecast|outlook"),
    ("narrative", r"narrative|story|credib|say vs|said|honest|trust|numbers? vs"),
    ("bullbear", r"bull|bear|thesis|buy|should i|case for|risk"),
]


def _resolve_symbol(q, hint=None):
    uni = provider.known_symbols()
    ql = q.lower()
    for s, u in uni.items():
        if re.search(rf"\b{re.escape(s.lower())}\b", ql) or u["name"].lower() in ql or u["name"].lower().split()[0] in ql.split():
            return s
    if provider.mode() == "live":
        for tok in re.findall(r"\b[A-Z][A-Z&\-]{1,14}\b", q):
            if tok not in {"I", "FY", "QOQ", "YOY", "PAT", "PBT", "EBITDA", "FCF", "AR", "ROCE", "NSE", "BSE", "VS", "THE"}:
                return tok
    return hint


@app.post("/api/ask")
def ask(body: dict):
    q = (body.get("q") or "").strip()
    hint = body.get("symbol")
    rules = body.get("rules") or {}
    ql = q.lower()
    sym = _resolve_symbol(q, hint)

    if not sym and re.search(r"alert|unusual|spike|volume|big move|moving|mover", ql):
        a = pdigest.alerts(rules)
        return {"intent": "alerts", "title": "What's unusual right now", "alerts": a["alerts"][:8], "rules": a["rules"]}
    if not sym and re.search(r"what.*(changed|happened|new)|today|overnight|digest|since|this week|last \d+|matter", ql):
        h = 24
        m = re.search(r"last (\d+)\s*(hour|day|week)", ql)
        if m:
            h = int(m.group(1)) * {"hour": 1, "day": 24, "week": 168}[m.group(2)]
        elif "week" in ql:
            h = 168
        d = pdigest.digest({**rules, "window_hours": h})
        top = [i for i in d["items"] if i["tier"] != "routine"][:6]
        return {"intent": "digest", "title": f"What mattered in the last {h if h < 48 else h // 24}{'h' if h < 48 else ' days'}",
                "pulse": d["pulse"], "items": top}
    if not sym:
        return {"intent": "clarify", "title": "Which company?", "message": "Tell me a company (e.g. “Nimbus guidance vs delivery”) or ask “what changed today?”."}

    secs = [k for k, pat in SECTION_KEYS if re.search(pat, ql)]
    if "guidance" in secs and "narrative" not in secs:
        secs.append("narrative")
    if not secs or len(secs) > 4:
        secs = ["financials", "guidance", "narrative", "bullbear"]
    # make sure research is stable-cached: always compute the full set, return only the requested slice
    r = pres.research(sym, None) if provider.mode() == "demo" or True else None
    return {"intent": "research", "symbol": sym, "name": r["name"], "title": r["name"], "ask": secs,
            "research": {**r, "sections": {k: v for k, v in r["sections"].items() if k in secs}}}


@app.get("/api/stats")
def stats():
    return {"llm": llm.USAGE, "cache": cache.STATS, "provider": llm.provider(), "data": provider.info()}


app.mount("/", StaticFiles(directory=str(FRONT), html=True), name="front")
