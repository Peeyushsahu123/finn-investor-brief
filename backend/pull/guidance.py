"""Guidance extraction from concall transcripts + 'promised vs delivered' scoreboard.

Cost routing: (1) regex pass is free and handles the common phrasing; (2) cheap LLM runs only on keyword-
filtered chunks of transcripts where regex found nothing; every item must carry a quote that is verified to
appear in the transcript, otherwise it is dropped. Actuals come only from the statement tables.
"""
import re

from .. import llm
from ..util import pct_change, quarter_name, shift, target_to_period
from . import metrics

TARGET = r"(Q[1-4]\s?FY\s?\d{2,4}|FY\s?\d{2,4})"
METRICS = {
    "revenue_growth": r"(?:revenue|sales|top[- ]?line)\s+growth",
    "ebitda_margin": r"(?:ebitda|operating)\s+margin",
    "pat_growth": r"(?:pat|profit(?: after tax)?|net profit)\s+growth",
    "capex": r"capex|capital expenditure",
}
NUMR = r"(\d+(?:\.\d+)?)\s*%?\s*(?:to|-|–|and)\s*(\d+(?:\.\d+)?)\s*%"
NUM1 = r"(?:around|about|approximately|approx\.?|~|of)\s*(\d+(?:\.\d+)?)\s*%"


def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def verify_quote(quote, text):
    if not isinstance(quote, str) or not isinstance(text, str):
        return False
    passage = norm(quote)
    if not passage:
        return False
    # Keep word order and negation intact while tolerating PDF line wraps.
    pattern = r"(?<!\w)" + re.escape(passage) + r"(?!\w)"
    return re.search(pattern, norm(text)) is not None



def _sentences(text):
    out = []
    for s in re.split(r"(?<=[.!?])\s+|\n", text):
        s = re.sub(r"^\s*(?:Management|Analyst|Operator|[A-Z][a-z]+(?: [A-Z][a-z]+){0,2})\s*:\s*", "", s).strip()  # drop speaker labels
        if len(s) > 25:
            out.append(s)
    return out


def regex_extract(text):
    items = []
    for sent in _sentences(text):
        tm = re.search(TARGET, sent, re.I)
        if not tm:
            continue
        target = re.sub(r"\s", "", tm.group(1)).upper()
        for metric, pat in METRICS.items():
            mm = re.search(pat, sent, re.I)
            if not mm:
                continue
            tail = sent[mm.end():]
            if metric == "capex":
                cm = re.search(r"(?:rs\.?|₹|inr)\s*([\d,]+)\s*(?:crore|cr)", sent, re.I)
                if cm:
                    v = float(cm.group(1).replace(",", ""))
                    items.append({"metric": metric, "low": v, "high": v, "target": target, "quote": sent})
                continue
            r = re.search(NUMR, tail, re.I) or re.search(NUMR, sent[mm.start():], re.I)
            if r:
                lo, hi = float(r.group(1)), float(r.group(2))
            else:
                r1 = re.search(NUM1, tail, re.I)
                if r1:
                    lo = hi = float(r1.group(1))
                elif re.search(r"double[- ]digit", sent, re.I):
                    lo, hi = 10.0, None
                else:
                    continue
            items.append({"metric": metric, "low": lo, "high": hi, "target": target, "quote": sent})
    return items


def llm_extract(text):
    chunks, cur = [], ""
    for s in _sentences(text):
        if re.search(r"expect|guid|target|aim|confident|outlook|plan|commit|margin|growth", s, re.I) and re.search(r"\d", s):
            cur += s + " "
            if len(cur) > 2500:
                chunks.append(cur)
                cur = ""
    if cur:
        chunks.append(cur)
    items = []
    for ch in chunks[:4]:
        out = llm.ask_json(
            "Extract EXPLICIT forward guidance given by management as items "
            "{\"metric\":\"revenue_growth|ebitda_margin|pat_growth|capex\",\"low\":number,\"high\":number|null,"
            "\"target\":\"Q3FY26|FY26\",\"quote\":\"exact sentence copied verbatim\"}. Percent metrics in %, capex in INR crore. "
            "Skip vague statements. Return {\"items\":[...]}.\n\n" + ch, tier="cheap")
        if out and isinstance(out.get("items"), list):
            items += [i for i in out["items"] if isinstance(i, dict) and i.get("metric") and i.get("low") is not None]
    return items


def extract_call(text):
    items = regex_extract(text)
    if not items and llm.available():
        items = llm_extract(text)
    good, dropped = [], 0
    for i in items:
        if verify_quote(i.get("quote", ""), text) and i.get("target") and target_to_period(str(i["target"])):
            good.append(i)
        else:
            dropped += 1
    return good, dropped


# ------------ actuals -------------
def actual_for(f, metric, target):
    period = target_to_period(target)
    if not period:
        return None, None
    is_q = target.upper().startswith("Q")
    tbl = f["quarters"] if is_q else f["annual"]
    if period not in tbl["periods"]:
        return None, period
    i = tbl["periods"].index(period)
    if metric == "revenue_growth":
        base = shift(period, -12) if is_q else shift(period, -12)
        if base not in tbl["periods"]:
            return None, period
        return pct_change(tbl["rows"]["Sales"][i], tbl["rows"]["Sales"][tbl["periods"].index(base)]), period
    if metric == "ebitda_margin":
        return tbl["rows"]["OPM %"][i], period
    if metric == "pat_growth":
        base = shift(period, -12)
        if base not in tbl["periods"]:
            return None, period
        return pct_change(tbl["rows"]["Net Profit"][i], tbl["rows"]["Net Profit"][tbl["periods"].index(base)]), period
    return None, period


def judge(metric, lo, hi, actual):
    tol = .5 if metric == "ebitda_margin" else 1.0
    if actual >= lo:
        return "delivered", actual - ((lo + hi) / 2 if hi else lo)
    if actual >= lo - tol * 2:
        return "near", actual - ((lo + hi) / 2 if hi else lo)
    return "missed", actual - ((lo + hi) / 2 if hi else lo)


def scoreboard(f, provider_doc_text, n_calls=4):
    calls = f["docs"]["concalls"][:n_calls]
    rows, dropped_total, quotes = [], 0, 0
    seen = {}
    for c in calls:
        text = provider_doc_text(c["url"])
        if not text:
            continue
        items, dropped = extract_call(text)
        dropped_total += dropped
        for it in items:
            if it["metric"] == "capex":
                continue
            quotes += 1
            key = (it["metric"], it["target"])
            row = {"call": c["label"], "metric": it["metric"], "target": it["target"].replace("FY", " FY") if it["target"].startswith("Q") else it["target"],
                   "lo": it["low"], "hi": it["high"], "quote": it["quote"]}
            act, period = actual_for(f, it["metric"], it["target"])
            if act is None:
                row.update(status="pending", actual=None, gap=None)
            else:
                st, gap = judge(it["metric"], it["low"], it["high"], act)
                row.update(status=st, actual=round(act, 1), gap=round(gap, 1))
            row["period"] = period
            # keep the latest call's statement for each (metric, target); earlier statements recorded in history
            if key in seen:
                seen[key]["history"].append({"call": row["call"], "lo": row["lo"], "hi": row["hi"]})
                continue
            row["history"] = []
            seen[key] = row
            rows.append(row)
    return rows, {"quotes_verified": quotes, "dropped_unverified": dropped_total}


def capex_guidance(f, provider_doc_text, n_calls=2):
    out = []
    for c in f["docs"]["concalls"][:n_calls]:
        items, _ = extract_call(provider_doc_text(c["url"]))
        out += [{"call": c["label"], "target": i["target"], "value": i["low"], "quote": i["quote"]} for i in items if i["metric"] == "capex"]
    return out
