"""Management-change enrichment: who left, who joined, and a short grounded background on the incoming person.

Bio sourcing (push-side enrichment, outside-the-company data is allowed here):
  web search snippets (DuckDuckGo HTML; LinkedIn/press results surface there) -> cheap LLM summarises ONLY from
  those snippets, with links. No LLM key: top snippets shown raw. We do not scrape LinkedIn directly (ToS).
"""
import re
import urllib.parse

import requests
from bs4 import BeautifulSoup

from .. import cache, llm, provider
from ..config import UA
from ..sources import demo

ROLE = r"(chief financial officer|chief executive officer|chief operating officer|managing director|whole[- ]time director|independent director|chairman|company secretary|chief technology officer|\bCFO\b|\bCEO\b|\bMD\b)"


def parse_change(item):
    t = f"{item['subject']}. {item['text']}"
    events = []
    for m in re.finditer(rf"(resignation|cessation|retirement)\s+of\s+((?:Mr|Ms|Mrs|Dr|Shri|Smt)\.?\s+[A-Z][\w\.\s]+?)\s+as\s+{ROLE}", t, re.I):
        events.append({"type": "exit", "person": m.group(2).strip(), "role": m.group(3).strip()})
    for m in re.finditer(rf"appointment\s+of\s+((?:Mr|Ms|Mrs|Dr|Shri|Smt)\.?\s+[A-Z][\w\.\s]+?)\s+as\s+(?:an?\s+)?{ROLE}", t, re.I):
        events.append({"type": "join", "person": m.group(1).strip(), "role": m.group(2).strip()})
    eff = re.search(r"w\.?e\.?f\.?\s+([\d]{1,2}\s+\w+\s+\d{4})", t)
    if not events and llm.available():
        out = llm.ask_json("Extract management changes from this filing: {\"events\":[{\"type\":\"exit|join\","
                           "\"person\":str,\"role\":str}],\"effective\":str|null}\n" + t[:1500], tier="cheap")
        if out:
            events = out.get("events") or []
    return events, (eff.group(1) if eff else None)


def _clean(name):
    return re.sub(r"^(Mr|Ms|Mrs|Dr|Shri|Smt)\.?\s+", "", name).strip()


def bio(person: str, role: str, company: str):
    person = _clean(person)
    if person in demo.BIOS and provider.mode() == "demo":
        b = demo.BIOS[person]
        return {"summary": b["summary"], "prev": b["prev"], "links": [], "note": "synthetic demo profile"}
    key = f"bio:{person}:{company}"
    hit = cache.get(key, ttl=30 * 86400)
    if hit:
        return hit
    try:
        q = urllib.parse.quote(f'"{person}" {role} {company}')
        r = requests.get(f"https://html.duckduckgo.com/html/?q={q}", headers={"User-Agent": UA}, timeout=10)
        soup = BeautifulSoup(r.text, "lxml")
        snips = []
        for res in soup.select(".result")[:6]:
            a = res.select_one(".result__a")
            s = res.select_one(".result__snippet")
            if a and s:
                snips.append({"title": a.get_text(strip=True), "url": a.get("href", ""), "snippet": s.get_text(" ", strip=True)})
    except Exception:
        return None
    if not snips:
        return None
    out = {"links": [{"title": s["title"], "url": s["url"]} for s in snips[:3]]}
    res = llm.ask_json(
        f"Using ONLY these search snippets, write a 2-sentence background of {person} (incoming {role} at {company}): "
        "who they are and where they worked before. If the snippets are about a different person or unclear, say so. "
        "Return {\"summary\":str,\"prev\":[str]}.\n" + str(snips), tier="cheap")
    if res:
        out.update(summary=res.get("summary"), prev=res.get("prev") or [])
    else:
        out.update(summary=snips[0]["snippet"], prev=[])
    return cache.put(key, out)


def build(item, company_name):
    events, eff = parse_change(item)
    if not events:
        return None
    out = {"events": events, "effective": eff, "incoming": []}
    for e in events:
        if e["type"] == "join":
            out["incoming"].append({"person": _clean(e["person"]), "role": e["role"], "bio": bio(e["person"], e["role"], company_name)})
    senior = any(re.search(r"chief|managing|ceo|cfo|chairman", e["role"], re.I) for e in events)
    out["senior"] = senior
    return out
