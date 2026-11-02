"""On-demand research for ANY ticker with data. Primary sources only: statement tables, annual-report text,
concall transcripts. Outside knowledge is never used; LLM output is accepted only with verified quotes.
"""
import re

from .. import cache, llm, provider
from ..util import quarter_name
from . import guidance, metrics

SECTIONS = ["business", "financials", "trajectory", "balance", "cash", "guidance", "narrative", "bullbear"]


# ---------------- business snapshot ----------------
def business(f):
    ar = f["docs"]["annual_reports"][:1]
    text = provider.doc_text(ar[0]["url"]) if ar else ""
    out = {"source": ar[0]["label"] if ar else None, "what": None, "segments": []}
    if text:
        m = re.search(r"Business overview:\s*(.+?)(?:Segment revenue mix|Management Discussion|\n)", text, re.S)
        seg = re.search(r"Segment revenue mix:\s*(.+?)\.\s", text)
        if m:
            out["what"] = re.sub(r"\s+", " ", m.group(1)).strip()
        if seg:
            out["segments"] = [{"name": n.strip(), "share": float(p)} for n, p in re.findall(r"([A-Za-z&\- ]+?)\s+(\d+)%", seg.group(1))]
        if not out["what"] and llm.available():
            res = llm.ask_json(
                "From this annual-report excerpt return {\"what\": one sentence on what the company does, "
                "\"segments\": [{\"name\":str,\"share\":number|null}] (share = % of revenue if stated), \"quote\": a verbatim supporting sentence}.\n"
                + text[:12000], tier="cheap")
            if res and guidance.verify_quote(res.get("quote", ""), text):
                out["what"], out["segments"] = res.get("what"), [s for s in (res.get("segments") or []) if s.get("name")]
    if not out["what"]:
        out["what"] = (f.get("about") or "")[:300] or None
    notes = []
    for pat, label in ((r"contingent liabilit[^.]*?(?:Rs\.?|₹)\s*[\d,]+\s*crore[^.]*\.", "Contingent liabilities"),
                       (r"related[- ]party[^.]*?(?:Rs\.?|₹)\s*[\d,]+\s*crore[^.]*\.", "Related-party dealings"),
                       (r"(?:emphasis of matter|qualified opinion|qualification)[^.]*\.", "Auditor flag")):
        m = re.search(pat, text, re.I)
        if m:
            notes.append({"label": label, "text": re.sub(r"\s+", " ", m.group(0)).strip()})
    out["watch_notes"] = notes
    return out


# ---------------- narrative vs numbers ----------------
def _latest_call_text(f):
    cs = f["docs"]["concalls"]
    return (cs[0]["label"], provider.doc_text(cs[0]["url"])) if cs else (None, "")


def _find_quote(text, pattern):
    for s in guidance._sentences(text):
        if re.search(pattern, s, re.I):
            return s
    return None


def narrative(f, board):
    label, text = _latest_call_text(f)
    flags = []
    tr = metrics.trajectory(f)
    bal = metrics.balance(f)
    cs = metrics.cash(f)
    # rule 1: margin talk vs margin reality
    q = _find_quote(text, r"margin (?:expansion|improvement)|expand(?:ing)? margin|margin trajectory")
    if q and tr["q_opm"] and len(tr["q_opm"]) >= 5:
        d = tr["q_opm"][-1] - tr["q_opm"][-5]
        if d < -0.5:
            flags.append({"verdict": "diverges", "topic": "Margins", "said": q,
                          "reality": f"Operating margin is {tr['q_opm'][-1]:.1f}% vs {tr['q_opm'][-5]:.1f}% a year earlier ({d * 100:+.0f} bps).", "call": label})
        elif d > 0.5:
            flags.append({"verdict": "agrees", "topic": "Margins", "said": q,
                          "reality": f"Operating margin is up {d * 100:+.0f} bps YoY to {tr['q_opm'][-1]:.1f}%.", "call": label})
    q = _find_quote(text, r"cash conversion|collections|working capital")
    if q and cs and cs["cum_conversion"] is not None:
        c = [x for x in cs["conversion"] if x is not None]
        if cs["cum_conversion"] < .75:
            flags.append({"verdict": "diverges", "topic": "Cash", "said": q,
                          "reality": f"Operating cash flow has covered only {cs['cum_conversion']:.2f}× of profit over {len(cs['periods'])} years; latest year {c[-1]:.2f}×.", "call": label})
    q = _find_quote(text, r"balance sheet.*strong|moderate net debt|deleverag|reduce debt")
    if q and bal and bal["de"][0] is not None and bal["de"][-1] is not None:
        if bal["de"][-1] > bal["de"][0] * 1.2:
            flags.append({"verdict": "diverges", "topic": "Balance sheet", "said": q,
                          "reality": f"Debt-to-equity has risen {bal['de'][0]:.2f} → {bal['de'][-1]:.2f} and interest cover is {bal['interest_cover']}×.", "call": label})
    res = [r for r in board if r["status"] != "pending"]
    if res:
        d = sum(r["status"] == "delivered" for r in res)
        n_miss = sum(r["status"] == "missed" for r in res)
        flags.append({"verdict": "agrees" if d / len(res) >= .6 else "diverges", "topic": "Guidance record",
                      "said": f"{len(res)} explicit headline targets from the last {min(4, len(f['docs']['concalls']))} calls have now resolved.",
                      "reality": f"{d} delivered, {sum(r['status'] == 'near' for r in res)} near-miss, {n_miss} missed.", "call": None})
    return flags


# ---------------- bull / bear ----------------
def bullbear(f, snap, tr, bal, cs, board, narr):
    bull, bear = [], []
    for lvl, t in tr["flags"] + (bal["flags"] if bal else []) + (cs["flags"] if cs else []):
        (bull if lvl == "green" else bear if lvl in ("red", "amber") else []).append({"point": t, "evidence": "Statement tables"})
    for n in narr:
        if n["verdict"] == "diverges":
            bear.append({"point": f"{n['topic']}: management's story doesn't match the numbers.", "evidence": n["reality"]})
        elif n["topic"] == "Guidance record":
            bull.append({"point": "Management has a credible record on its headline guidance.", "evidence": n["reality"]})
    if snap["quarter"]["revenue_yoy"] is not None and snap["quarter"]["revenue_yoy"] > 12:
        bull.append({"point": f"Revenue growing {snap['quarter']['revenue_yoy']:.0f}% YoY in {snap['latest_quarter']}.", "evidence": "Quarterly table"})
    pend = [r for r in board if r["status"] == "pending"]
    if pend:
        bear.append({"point": f"{len(pend)} guidance targets are still unproven; the thesis leans on them.", "evidence": "Concall transcripts"})
    facts = {"snapshot": snap, "trajectory_flags": tr["flags"], "balance_flags": bal["flags"] if bal else [],
             "cash_flags": cs["flags"] if cs else [], "scoreboard": [{k: r[k] for k in ("target", "metric", "lo", "hi", "actual", "status")} for r in board],
             "narrative": narr}
    if llm.available():
        res = llm.ask_json(
            "You are an equity analyst. From ONLY these facts, write the tightest bull case and bear case (max 3 each). "
            "Each point must cite the specific number from the facts in 'evidence'. No outside knowledge. "
            "Return {\"bull\":[{\"point\":str,\"evidence\":str}],\"bear\":[...]}\n" + str(facts)[:7000], tier="strong")
        if res and res.get("bull") and res.get("bear"):
            return {"bull": res["bull"][:3], "bear": res["bear"][:3], "by": "strong model, grounded in computed facts"}
    return {"bull": bull[:4], "bear": bear[:4], "by": "rules over computed facts"}


# ---------------- assemble ----------------
def research(symbol: str, sections=None):
    symbol = symbol.upper()
    sections = [s for s in (sections or SECTIONS) if s in SECTIONS] or SECTIONS
    key = f"research:{provider.mode()}:{symbol}:{','.join(sections)}:{llm.provider()}"
    hit = cache.get(key, ttl=6 * 3600)
    if hit:
        return hit
    f = provider.fundamentals(symbol)
    out = {"symbol": symbol, "name": f.get("name", symbol), "consolidated": f.get("consolidated"), "sections": {},
           "data": provider.info(), "grounding": {"llm": llm.provider(), "sources": []}}
    snap = metrics.snapshot(f)
    tr = metrics.trajectory(f)
    bal = metrics.balance(f)
    cs = metrics.cash(f)
    need_board = any(s in sections for s in ("guidance", "narrative", "bullbear"))
    board, gmeta = ([], {})
    if need_board:
        board, gmeta = guidance.scoreboard(f, provider.doc_text)
    S = out["sections"]
    if "business" in sections:
        S["business"] = business(f)
    if "financials" in sections:
        S["financials"] = snap
    if "trajectory" in sections:
        S["trajectory"] = tr
    if "balance" in sections:
        S["balance"] = bal
    if "cash" in sections:
        S["cash"] = cs
    narr = []
    if need_board:
        narr = narrative(f, board)
    if "guidance" in sections:
        S["guidance"] = {"scoreboard": board, "capex": guidance.capex_guidance(f, provider.doc_text), "meta": gmeta,
                         "calls": [c["label"] for c in f["docs"]["concalls"][:4]]}
    if "narrative" in sections:
        S["narrative"] = narr
    if "bullbear" in sections:
        S["bullbear"] = bullbear(f, snap, tr, bal, cs, board, narr)
    out["grounding"]["sources"] = ([f"Annual report · {d['label']}" for d in f["docs"]["annual_reports"][:1]] +
                                   [f"Concall transcript · {c['label']}" for c in f["docs"]["concalls"][:4]] +
                                   ["Screener statement tables (quarterly, annual, balance sheet, cash flow, ratios)"])
    out["grounding"].update(gmeta)
    return cache.put(key, out)
