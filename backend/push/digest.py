"""Push engine: market metrics, windowed digest (classify -> cluster -> score -> enrich), triggered alerts."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from .. import provider
from ..config import DEFAULT_RULES
from . import classify, mgmt, results

BASE = {"results": 88, "M&A": 84, "management_change": 78, "litigation": 80, "fund_raise": 70, "credit_rating": 68,
        "pledging": 66, "capex": 58, "dividend": 54, "bonus_split": 56, "insider_trading": 42, "earnings_call": 36,
        "press_release": 38, "investor_meetings": 22, "agm_egm": 16, "postal_ballot": 14, "unclassified": 4}
WHY = {
    "results": "Fresh numbers — the single biggest scheduled price driver.",
    "M&A": "Changes the company's size and capital needs; usually re-prices the stock.",
    "management_change": "Leadership change at the top; check who is stepping in and why.",
    "litigation": "Regulatory / legal exposure that can turn into a cost or a restriction.",
    "fund_raise": "New equity or debt — dilution or leverage changes.",
    "credit_rating": "Rating agencies move borrowing costs and signal balance-sheet health.",
    "pledging": "Promoter pledge shifts are a governance / risk signal.",
    "capex": "Where the company is putting its money for the next 2–3 years.",
    "dividend": "Cash returned to shareholders; note the record date.",
    "bonus_split": "Share count changes; no cash, but often a sentiment signal.",
    "insider_trading": "Insiders trading their own stock.",
    "earnings_call": "Management commentary and Q&A — where guidance lives.",
    "press_release": "General company news.",
    "investor_meetings": "Who management is meeting; mild signal.",
    "agm_egm": "Shareholder meeting logistics.",
    "postal_ballot": "Shareholder vote logistics.",
    "unclassified": "Routine paperwork.",
}


# ---------------- market metrics ----------------
def market(symbols, rules):
    px = provider.eod(symbols, days=60)
    out = {}
    for s, rows in px.items():
        if len(rows) < 3:
            continue
        look = int(rules.get("volume_lookback", 20))
        last, prev = rows[-1], rows[-2]
        hist = rows[-(look + 1):-1]
        avg_v = sum(r["v"] for r in hist) / max(len(hist), 1)
        out[s] = {
            "close": last["c"], "date": last["d"],
            "pct": round((last["c"] / prev["c"] - 1) * 100, 2),
            "pct5": round((last["c"] / rows[-6]["c"] - 1) * 100, 2) if len(rows) > 6 else None,
            "vol": last["v"], "vol_ratio": round(last["v"] / avg_v, 2) if avg_v else None,
            "spark": [r["c"] for r in rows[-30:]],
        }
    return out


# ---------------- digest ----------------
def _clean(t, n=150):
    t = re.sub(r"\s+", " ", t or "").strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


_AB = {"chief financial officer": "CFO", "chief executive officer": "CEO", "chief operating officer": "COO",
       "managing director": "MD", "chief technology officer": "CTO"}


def _abbr(role):
    return _AB.get(role.lower(), role.upper() if len(role) <= 3 else role.title())


def _headline(it, enrich):
    c = it["cat"]
    if c == "results" and enrich and enrich.get("verdict"):
        return f"{enrich['quarter']}: " + enrich["verdict"]["line"]
    if c == "management_change" and enrich:
        ex = [e for e in enrich["events"] if e["type"] == "exit"]
        jn = [e for e in enrich["events"] if e["type"] == "join"]
        bits = []
        if ex:
            bits.append(f"{_abbr(ex[0]['role'])} {mgmt._clean(ex[0]['person'])} out")
        if jn:
            bits.append(f"{mgmt._clean(jn[0]['person'])} in as {_abbr(jn[0]['role'])}")
        return "; ".join(bits)
    return _clean(it["text"] or it["subject"])


def _score(it, mk, rules):
    s = BASE.get(it["cat"], 10)
    t = f"{it['subject']} {it['text']}".lower()
    if it["cat"] == "credit_rating":
        s += 10 if re.search(r"downgrad|negative|withdrawn", t) else (4 if re.search(r"upgrad|positive", t) else 0)
    if it["cat"] == "management_change" and re.search(r"chief|ceo|cfo|managing director|chairman", t):
        s += 8
    if it["cat"] == "press_release":
        m = re.search(r"rs\.?\s*([\d,]+)\s*crore", t)
        if m and float(m.group(1).replace(",", "")) >= 1000:
            s += 14
    if it["cat"] == "pledging" and re.search(r"additional|invok", t):
        s += 8
    if it["cat"] in rules.get("watch", []):
        s += 10
    if it["cat"] in rules.get("mute", []):
        s = min(s, 10)
    m = mk.get(it["symbol"])
    ctx = None
    if m:
        pm, vr = abs(m["pct"]), m.get("vol_ratio") or 0
        if pm >= rules["price_move_pct"] or vr >= rules["volume_mult"]:
            s += 8
            ctx = f"{m['pct']:+.1f}% on {vr:.1f}× volume"
    return min(int(s), 100), ctx


def _tier(score):
    return "now" if score >= 78 else ("look" if score >= 40 else "routine")


def _is_results_family(it):
    t = f"{it['subject']} {it['text']}".lower()
    return it["cat"] == "results" or (it["cat"] in ("press_release", "earnings_call") and ("result" in t or "q2" in t or "conference call" in t))


def digest(rules=None, symbols=None):
    rules = {**DEFAULT_RULES, **(rules or {})}
    uni = provider.universe()
    names = {u["symbol"]: u for u in uni}
    symbols = symbols or list(names)
    hours = float(rules["window_hours"])
    since = datetime.now() - timedelta(hours=hours)
    days = max(1, int(hours // 24) + 1)

    items = []
    with ThreadPoolExecutor(max_workers=8) as ex:   # NSE is slow per symbol; fetch the book in parallel
        fetched = list(ex.map(lambda s: provider.announcements(s, days=days), symbols))
    for rows in fetched:
        for a in rows:
            try:
                if datetime.fromisoformat(a["ts"]) >= since:
                    items.append(dict(a))
            except Exception:
                items.append(dict(a))
    classify.classify_all(items)
    mk = market(symbols, rules)

    # cluster the results family per symbol
    groups, singles = {}, []
    for it in items:
        if _is_results_family(it):
            groups.setdefault(it["symbol"], []).append(it)
        else:
            singles.append(it)
    cards = []
    for sym, grp in groups.items():
        order = lambda x: (0 if x["subject"].lower().startswith("financial results") else
                           1 if "outcome of board" in x["subject"].lower() else 2, x["ts"])
        grp.sort(key=order)
        prim = dict(grp[0])
        prim["alt_urls"] = [g["url"] for g in grp[1:] if g["url"].startswith("demo://") or g["url"].lower().endswith(".pdf")]
        prim["cat"] = "results"
        prim["related"] = [{"subject": g["subject"], "ts": g["ts"], "url": g["url"], "text": _clean(g["text"], 110)} for g in grp if g["id"] != prim["id"]]
        cards.append(prim)
    cards += [dict(x, related=[]) for x in singles]

    out = []
    for it in cards:
        sc, ctx = _score(it, mk, rules)
        enrich = None
        if it["cat"] == "results" and sc >= 40:
            enrich = results.build(it)
            for u in it.get("alt_urls", []):
                if enrich:
                    break
                enrich = results.build({**it, "url": u})
        elif it["cat"] == "management_change":
            enrich = mgmt.build(it, names[it["symbol"]]["name"])
        out.append({
            "id": it["id"], "symbol": it["symbol"], "name": names[it["symbol"]]["name"], "ts": it["ts"],
            "cat": it["cat"], "subject": it["subject"], "headline": _headline(it, enrich),
            "why": WHY.get(it["cat"], ""), "context": ctx, "priority": sc, "tier": _tier(sc), "url": it["url"],
            "enrich": ({"kind": "results", **enrich} if it["cat"] == "results" and enrich else
                       ({"kind": "mgmt", **enrich} if it["cat"] == "management_change" and enrich else None)),
            "related": it["related"], "source": it.get("source", "NSE"),
        })
    out = [o for o in out if o["priority"] >= rules.get("min_priority", 0)]
    def _t(o):
        try:
            return datetime.fromisoformat(o["ts"]).timestamp()
        except Exception:
            return 0
    out.sort(key=lambda o: (-o["priority"], -_t(o)))

    ups = sorted(mk.items(), key=lambda kv: kv[1]["pct"])
    avg = sum(m["pct"] for m in mk.values()) / len(mk) if mk else 0
    pulse = {
        "window_hours": hours, "total": len(out), "now": sum(o["tier"] == "now" for o in out),
        "look": sum(o["tier"] == "look" for o in out), "routine": sum(o["tier"] == "routine" for o in out),
        "avg_move": round(avg, 2), "asof": mk[next(iter(mk))]["date"] if mk else None,
        "best": ({"symbol": ups[-1][0], "pct": ups[-1][1]["pct"]} if ups else None),
        "worst": ({"symbol": ups[0][0], "pct": ups[0][1]["pct"]} if ups else None),
    }
    return {"pulse": pulse, "items": out, "market": mk, "universe": uni, "data": provider.info()}


# ---------------- triggered alerts ----------------
def alerts(rules=None):
    rules = {**DEFAULT_RULES, **(rules or {})}
    d = digest(rules)
    al = []
    for s, m in d["market"].items():
        name = next((u["name"] for u in d["universe"] if u["symbol"] == s), s)
        if abs(m["pct"]) >= rules["price_move_pct"]:
            al.append({"id": f"px:{s}:{m['date']}", "kind": "price", "symbol": s, "name": name,
                       "title": f"{name} {m['pct']:+.1f}% on the day",
                       "detail": f"Beyond your ±{rules['price_move_pct']:g}% threshold. Close ₹{m['close']:,.1f} ({m['date']}).",
                       "severity": "high" if abs(m["pct"]) >= 2 * rules["price_move_pct"] else "med", "date": m["date"]})
        if (m.get("vol_ratio") or 0) >= rules["volume_mult"]:
            al.append({"id": f"vol:{s}:{m['date']}", "kind": "volume", "symbol": s, "name": name,
                       "title": f"{name} volume {m['vol_ratio']:.1f}× average",
                       "detail": f"Versus the prior {rules['volume_lookback']}-day average; your trigger is {rules['volume_mult']:g}×.",
                       "severity": "high" if m["vol_ratio"] >= 2 * rules["volume_mult"] else "med", "date": m["date"]})
    for o in d["items"]:
        if o["cat"] in rules["watch"] and o["tier"] != "routine":
            al.append({"id": f"ann:{o['id']}", "kind": "filing", "symbol": o["symbol"], "name": o["name"],
                       "title": f"{o['name']}: {o['cat'].replace('_', ' ')}", "detail": o["headline"],
                       "severity": "high" if o["tier"] == "now" else "med", "date": o["ts"]})
    rank = {"high": 0, "med": 1}
    al.sort(key=lambda a: (rank[a["severity"]], a["kind"]))
    return {"alerts": al, "rules": {k: rules[k] for k in ("price_move_pct", "volume_mult", "watch")}}
