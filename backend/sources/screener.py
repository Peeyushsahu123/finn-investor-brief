"""screener.in: multi-year tables + links to annual reports and concall transcripts (+ PDF text).

Parsing is selector-based (section ids: quarters, profit-loss, balance-sheet, cash-flow, ratios, documents).
Screener changes markup occasionally; the parse is isolated here so it is the one place to fix.
"""
import io
import re

import requests
from bs4 import BeautifulSoup

from .. import cache
from ..config import UA
from ..util import num

BASE = "https://www.screener.in/company/{sym}/{kind}"


def _get(sym):
    for kind in ("consolidated/", ""):
        r = requests.get(BASE.format(sym=sym, kind=kind), headers={"User-Agent": UA}, timeout=20)
        if r.status_code == 200 and 'id="quarters"' in r.text:
            return r.text, bool(kind)
    raise RuntimeError(f"screener: no page for {sym}")


def _table(soup, sec_id):
    sec = soup.find("section", id=sec_id)
    if not sec:
        return None
    t = sec.find("table")
    if not t:
        return None
    periods = [th.get_text(strip=True) for th in t.find("thead").find_all("th")][1:]
    rows = {}
    for tr in t.find("tbody").find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        label = re.sub(r"[\s ]*\+?$", "", tds[0].get_text(" ", strip=True)).strip()
        rows[label] = [num(td.get_text(strip=True)) for td in tds[1:]]
    return {"periods": periods, "rows": rows}


def parse(html: str, sym: str, consolidated: bool):
    soup = BeautifulSoup(html, "lxml")
    name = (soup.find("h1") or soup.find("title")).get_text(strip=True)
    about = soup.select_one(".company-profile .sub.show-more-box.about") or soup.select_one(".about")
    docs = {"annual_reports": [], "concalls": []}
    sec = soup.find("section", id="documents")
    if sec:
        for box in sec.select("div.documents"):
            title = box.get_text(" ", strip=True)[:40].lower()
            for li in box.select("ul li"):
                a_all = li.find_all("a", href=True)
                label = li.get_text(" ", strip=True)
                if "annual report" in title:
                    if a_all:
                        docs["annual_reports"].append({"label": label[:60], "url": a_all[0]["href"]})
                elif "concall" in title or "call" in title:
                    date = re.match(r"([A-Za-z]{3}\s+\d{4})", label)
                    for a in a_all:
                        if "transcript" in a.get_text(strip=True).lower():
                            docs["concalls"].append({"label": date.group(1) if date else label[:20], "url": a["href"]})
    return {
        "symbol": sym, "name": name, "consolidated": consolidated,
        "about": about.get_text(" ", strip=True) if about else "",
        "quarters": _table(soup, "quarters"), "annual": _table(soup, "profit-loss"),
        "balance": _table(soup, "balance-sheet"), "cashflow": _table(soup, "cash-flow"),
        "ratios": _table(soup, "ratios"), "docs": docs,
    }


def fetch(sym: str):
    key = f"screener:{sym}"
    hit = cache.get(key, ttl=6 * 3600)
    if hit:
        return hit
    html, cons = _get(sym)
    return cache.put(key, parse(html, sym, cons))


def pdf_text(url: str, max_pages: int = 80) -> str:
    key = "pdf:" + url
    hit = cache.get(key)
    if hit is not None:
        return hit
    from pypdf import PdfReader

    r = requests.get(url, headers={"User-Agent": UA}, timeout=40)
    r.raise_for_status()
    rd = PdfReader(io.BytesIO(r.content))
    text = "\n".join((p.extract_text() or "") for p in rd.pages[:max_pages])
    return cache.put(key, text)
