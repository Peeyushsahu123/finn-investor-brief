"""Quarterly results -> Revenue / EBITDA / PBT / PAT, this quarter vs previous (QoQ) and year-ago (YoY).

Order of attack (cheapest first):
 1. regex over the filing's own comparative columns (filings print current, previous, year-ago quarter)
 2. cheap LLM extraction when the table is messy
 3. screener quarterly table fills any gaps (earlier quarters are already there)
EBITDA is derived: PBT + finance cost + depreciation - other income  (screener 'Operating Profit' is the cross-check).
"""
import re

from .. import llm, provider
from ..util import num, pct_change, quarter_name, shift

LINES = {
    "revenue": r"(?:revenue from operations|total revenue from operations|net sales|total income from operations|revenue)",
    "other_income": r"other income",
    "finance": r"finance costs?|interest expense",
    "dep": r"depreciation(?: and amortisation(?: expense)?)?",
    "pbt": r"profit(?:/\(loss\))? before (?:exceptional items and )?tax|profit before tax",
    "pat": r"net profit(?: for the period)?|profit after tax|profit for the (?:period|year)",
}
_NUM = r"\(?-?[\d,]+\.?\d*\)?"


def _regex_extract(text: str):
    out = {}
    for key, pat in LINES.items():
        m = re.search(rf"(?im)^\s*(?:{pat})[^\d\n\-\(]*((?:[|\s]*{_NUM}){{1,3}})", text)
        if m:
            vals = [num(v) for v in re.findall(_NUM, m.group(1))]
            if vals:
                out[key] = (vals + [None, None, None])[:3]
    return out


def _llm_extract(text: str):
    res = llm.ask_json(
        "From this quarterly results filing, extract (in INR crore, as printed) for the three comparative columns "
        "[current quarter, previous quarter, same quarter last year]: revenue, other_income, finance, dep, pbt, pat. "
        "Return {\"revenue\":[c,p,y],\"other_income\":[..],\"finance\":[..],\"dep\":[..],\"pbt\":[..],\"pat\":[..],"
        "\"quarter_end\":\"Mon YYYY\"}.\n\n" + text[:9000], tier="cheap")
    return res or {}


def extract(text: str, fund: dict | None):
    raw = _regex_extract(text)
    if len(raw) < 4:
        raw.update({k: v for k, v in _llm_extract(text).items() if k in LINES and v})
    if not raw.get("revenue") or not raw.get("pat"):
        return None
    cur_label = "Sep 2026"
    m = re.search(r"quarter(?:\s+and\s+\w+\s+\w+)?\s+ended\s+(?:on\s+)?(\w+)\s+(\d{1,2}),?\s+(\d{4})", text, re.I)
    if m:
        cur_label = f"{m.group(1)[:3].title()} {m.group(3)}"
    else:
        m = re.search(r"ended\s+(\d{2})[./](\d{2})[./](\d{4})", text)
        if m:
            from ..util import fmt_period
            cur_label = fmt_period(int(m.group(3)), int(m.group(2)))

    def ebitda(i):
        g = lambda k: (raw.get(k) or [None] * 3)[i]
        pbt, fin, dep, oi = g("pbt"), g("finance"), g("dep"), g("other_income")
        if None in (pbt, fin, dep):
            return None
        return round(pbt + fin + dep - (oi or 0), 1)

    cols = []
    for i in range(3):
        cols.append({"revenue": (raw["revenue"] + [None] * 3)[i], "ebitda": ebitda(i),
                     "pbt": (raw.get("pbt") or [None] * 3)[i], "pat": (raw["pat"] + [None] * 3)[i]})
    # gap-fill prev / yoy from screener table if the filing didn't carry them
    q = (fund or {}).get("quarters")
    if q:
        for idx, lab in ((1, shift(cur_label, -3)), (2, shift(cur_label, -12))):
            if lab in q["periods"]:
                j = q["periods"].index(lab)
                fill = {"revenue": "Sales", "ebitda": "Operating Profit", "pbt": "Profit before tax", "pat": "Net Profit"}
                for k, row in fill.items():
                    if cols[idx][k] is None and row in q["rows"]:
                        cols[idx][k] = q["rows"][row][j]
    cur, prev, yoy = cols
    rows = []
    for k, label in (("revenue", "Revenue"), ("ebitda", "EBITDA"), ("pbt", "PBT"), ("pat", "PAT")):
        rows.append({"metric": label, "cur": cur[k], "prev": prev[k], "yoy_base": yoy[k],
                     "qoq": pct_change(cur[k], prev[k]), "yoy": pct_change(cur[k], yoy[k])})
    margin = None
    if cur["revenue"] and cur["ebitda"] is not None:
        margin = {"cur": round(cur["ebitda"] / cur["revenue"] * 100, 1),
                  "prev": round(prev["ebitda"] / prev["revenue"] * 100, 1) if prev["revenue"] and prev["ebitda"] is not None else None,
                  "yoy": round(yoy["ebitda"] / yoy["revenue"] * 100, 1) if yoy["revenue"] and yoy["ebitda"] is not None else None}
    return {"quarter": quarter_name(cur_label), "period": cur_label, "rows": rows, "ebitda_margin": margin,
            "basis": "As printed in the filing; EBITDA derived (PBT + finance cost + depreciation - other income). INR crore."}


def verdict(res):
    """One-line read: the 'first cut' an investor wants."""
    if not res:
        return None
    r = {x["metric"]: x for x in res["rows"]}
    y = lambda m: r[m]["yoy"]
    parts = []
    if y("Revenue") is not None:
        parts.append(f"Revenue {y('Revenue'):+.0f}% YoY")
    if r["PAT"]["yoy"] is not None:
        parts.append(f"PAT {r['PAT']['yoy']:+.0f}%")
    mg = res.get("ebitda_margin")
    if mg and mg.get("yoy") is not None:
        d = (mg["cur"] - mg["yoy"]) * 100
        parts.append(f"EBITDA margin {mg['cur']:.1f}% ({d:+.0f} bps YoY)")
    tone = "neutral"
    if y("Revenue") is not None and r["PAT"]["yoy"] is not None:
        if y("Revenue") > 8 and r["PAT"]["yoy"] > y("Revenue"):
            tone = "strong"
        elif r["PAT"]["yoy"] < 0 or (mg and mg.get("yoy") and mg["cur"] < mg["yoy"] - 1):
            tone = "soft"
    return {"line": " · ".join(parts), "tone": tone}


def build(item):
    fund = None
    try:
        fund = provider.fundamentals(item["symbol"])
    except Exception:
        pass
    text = provider.doc_text(item["url"])
    if not text:
        return None
    res = extract(text, fund)
    if res:
        res["verdict"] = verdict(res)
    return res
