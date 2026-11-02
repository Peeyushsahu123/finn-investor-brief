"""SYNTHETIC demo universe (fictional companies) so the whole app runs with no network / no keys.

Everything here is generated. It mirrors the shape of the live sources (screener tables, NSE
announcements, filing/transcript text) so the exact same pipeline code runs on it.
"""
import random
from datetime import datetime, timedelta

from ..util import fmt_period, quarter_name, shift

R = random.Random(11)

# sym, name, sector, cap, base quarterly revenue (cr), yoy growth, opm, story
CO = [
    ("KESTRELPH", "Kestrel Pharma", "Pharma", "Large", 5200, .14, 24, "steady"),
    ("NIMBUS", "Nimbus Cloudworks", "IT Services", "Large", 7400, .12, 22, "margin_miss"),
    ("ORCHARDBK", "Orchard Bank", "Banks", "Large", 9100, .16, 30, "steady"),
    ("HALCYONM", "Halcyon Motors", "Auto", "Large", 11800, .10, 13, "debt_up"),
    ("BRIGHTFLD", "Brightfield Foods", "FMCG", "Large", 4300, .09, 19, "cash_weak"),
    ("VANTAGEST", "Vantage Steel", "Metals", "Mid", 6800, .06, 16, "random"),
    ("SOLACEPWR", "Solace Power", "Power", "Mid", 3900, .11, 33, "random"),
    ("MERIDIANR", "Meridian Realty", "Real Estate", "Mid", 1700, .20, 28, "random"),
    ("QUANTACKT", "Quanta Circuits", "Electronics Mfg", "Mid", 2600, .28, 8, "beat"),
    ("LUMENRTL", "Lumen Retail", "Retail", "Mid", 3300, .17, 11, "random"),
    ("ASTERCHEM", "Aster Chemicals", "Specialty Chem", "Small", 980, .08, 18, "random"),
    ("COBALTINF", "Cobalt Infra", "Capital Goods", "Large", 8800, .15, 12, "steady"),
    ("TIDEWATER", "Tidewater Shipping", "Logistics", "Small", 720, .05, 21, "random"),
    ("ZEPHYRTEL", "Zephyr Telecom", "Telecom", "Large", 10400, .08, 45, "debt_up"),
    ("IRONBARK", "Ironbark Cement", "Cement", "Mid", 2900, .07, 17, "random"),
    ("SAFFRONH", "Saffron Hospitals", "Healthcare", "Mid", 2100, .18, 20, "beat"),
]
# Companies that have already filed Q2 FY27 (Sep 2026) results in the last few days:
FILED = {"KESTRELPH": 1, "NIMBUS": 2, "QUANTACKT": 0, "HALCYONM": 3, "SAFFRONH": 1}
LATEST_Q = "Sep 2026"
TEXTS: dict = {}
_FUND: dict = {}
_PRICES: dict = {}
_ANN: list = []
BIOS: dict = {}


def _quarters(rng, base, g, opm, story, end_label):
    """14 quarters ending at end_label. Returns table dict (screener-like)."""
    periods = [shift(end_label, -3 * k) for k in range(13, -1, -1)]
    rev, opm_l = [], []
    for i, p in enumerate(periods):
        trend = (1 + g) ** ((i - 13) / 4)
        rev.append(round(base * trend * (1 + rng.uniform(-.025, .03)), 1))
        drift = {"margin_miss": -0.42, "debt_up": -0.05, "beat": 0.18, "steady": 0.04}.get(story, 0.0)
        opm_l.append(round(opm + drift * (i - 13) + rng.uniform(-.7, .7), 1))
    rows = {"Sales": rev, "OPM %": opm_l}
    op = [round(r * o / 100, 1) for r, o in zip(rev, opm_l)]
    oi = [round(r * rng.uniform(.01, .025), 1) for r in rev]
    dep = [round(r * .035, 1) for r in rev]
    intr = [round(r * (.045 if story == "debt_up" else .015) * (1 + .03 * i if story == "debt_up" else 1), 1)
            for i, r in enumerate(rev)]
    pbt = [round(a + b - c - d, 1) for a, b, c, d in zip(op, oi, dep, intr)]
    pat = [round(x * .75, 1) for x in pbt]
    rows.update({"Expenses": [round(r - o, 1) for r, o in zip(rev, op)], "Operating Profit": op,
                 "Other Income": oi, "Interest": intr, "Depreciation": dep,
                 "Profit before tax": pbt, "Net Profit": pat})
    return {"periods": periods, "rows": rows}


def _annual(rng, q, story, base):
    """10 FYs ending Mar 2026 (+TTM); FY26 equals sum of last 4 quarters ending Mar 2026."""
    qp = q["periods"]

    def fy_sum(end_label, key):
        i = qp.index(end_label)
        return round(sum(q["rows"][key][i - 3:i + 1]), 1)

    fy_rev = [fy_sum("Mar 2024", "Sales"), fy_sum("Mar 2025", "Sales"), fy_sum("Mar 2026", "Sales")]
    fy_op = [fy_sum("Mar 2024", "Operating Profit"), fy_sum("Mar 2025", "Operating Profit"), fy_sum("Mar 2026", "Operating Profit")]
    fy_pat = [fy_sum("Mar 2024", "Net Profit"), fy_sum("Mar 2025", "Net Profit"), fy_sum("Mar 2026", "Net Profit")]
    for _ in range(7):
        gg = rng.uniform(.04, .18)
        fy_rev.insert(0, round(fy_rev[0] / (1 + gg), 1))
        fy_op.insert(0, round(fy_op[0] / (1 + gg * rng.uniform(.6, 1.2)), 1))
        fy_pat.insert(0, round(fy_pat[0] / (1 + gg * rng.uniform(.5, 1.3)), 1))
    periods = [f"Mar {2017 + k}" for k in range(10)]
    opm = [round(o / r * 100, 1) for o, r in zip(fy_op, fy_rev)]
    return {"periods": periods + ["TTM"], "rows": {
        "Sales": fy_rev + [round(sum(q["rows"]["Sales"][-4:]), 1)],
        "Operating Profit": fy_op + [round(sum(q["rows"]["Operating Profit"][-4:]), 1)],
        "OPM %": opm + [round(sum(q["rows"]["Operating Profit"][-4:]) / sum(q["rows"]["Sales"][-4:]) * 100, 1)],
        "Net Profit": fy_pat + [round(sum(q["rows"]["Net Profit"][-4:]), 1)]}}


def _bs_cf(rng, ann, story):
    n = 10
    pat = ann["rows"]["Net Profit"][:n]
    sales = ann["rows"]["Sales"][:n]
    eq, bor = [], []
    e = pat[0] * 6
    b = sales[0] * .25
    for k in range(n):
        e += pat[k] * .75
        b *= {"debt_up": 1.22, "steady": .93}.get(story, 1.02)
        eq.append(round(e, 1))
        bor.append(round(b, 1))
    cfo_ratio = {"cash_weak": .38, "steady": 1.05, "beat": .85}.get(story, .8)
    cfo = [round(p * (cfo_ratio + rng.uniform(-.12, .12)) + p * .25, 1) for p in pat]
    if story == "cash_weak":
        cfo = [round(c * (1 - .06 * k), 1) for k, c in enumerate(cfo)]
    capex = [round(s * rng.uniform(.035, .06), 1) for s in sales]
    periods = ann["periods"][:n]
    deb = [round(120 + 8 * k + (14 * k if story == "cash_weak" else 0), 0) for k in range(n)]
    bal = {"periods": periods, "rows": {
        "Equity Capital": [round(e * .1, 1)] * n, "Reserves": [round(x * .9, 1) for x in eq],
        "Borrowings": bor, "Other Liabilities": [round(s * .22, 1) for s in sales],
        "Total Assets": [round(a + b + s * .22, 1) for a, b, s in zip(eq, bor, sales)]}}
    cf = {"periods": periods, "rows": {
        "Cash from Operating Activity": cfo,
        "Cash from Investing Activity": [-c for c in capex],
        "Cash from Financing Activity": [round(-(c - p * .6), 1) for c, p in zip(cfo, pat)]}}
    ratios = {"periods": periods, "rows": {
        "Debtor Days": [round(deb[k] * .35, 0) for k in range(n)],
        "Inventory Days": [round(60 + rng.uniform(-6, 6) + (3 * k if story == "cash_weak" else 0), 0) for k in range(n)],
        "Days Payable": [round(55 + rng.uniform(-5, 5), 0) for _ in range(n)],
        "Cash Conversion Cycle": [round(deb[k] * .35 + 60 - 55 + (3 * k if story == "cash_weak" else 0), 0) for k in range(n)],
        "ROCE %": [round(rng.uniform(14, 22) - (0.9 * k if story == "debt_up" else 0) + (0.6 * k if story in ("beat", "steady") else 0), 1) for k in range(n)]}}
    return bal, cf, ratios


def _guid_lines(sym, q, ann, story, rng, call_after):
    """Management guidance as spoken on the call following quarter `call_after`."""
    nxt = shift(call_after, 3)
    qn = quarter_name(nxt).replace(" ", "")
    qn_sp = quarter_name(nxt)
    # underlying run-rate yoy for the next quarter if available
    p = q["periods"]
    rv = q["rows"]["Sales"]
    idx = p.index(call_after)
    yoy = (rv[idx] / rv[idx - 4] - 1) * 100
    o = q["rows"]["OPM %"][idx]
    # Promise is generally optimistic, except for 'beat' (sandbagged)
    opt = {"margin_miss": 2.2, "beat": -3.0, "debt_up": 1.0, "steady": 0.5}.get(story, 1.2)
    lo, hi = round(yoy + opt - 1), round(yoy + opt + 1)
    mlo, mhi = round(o + (2.3 if story == "margin_miss" else 0.4), 1), round(o + (3.3 if story == "margin_miss" else 1.1), 1)
    fy = quarter_name(shift(call_after, 3)).split()[1]
    if call_after in ("Jun 2026", "Mar 2026"):
        fy = "FY27"
    elif call_after in ("Sep 2025", "Dec 2025"):
        fy = "FY26"
    lines = [
        f"Looking ahead to {qn_sp}, we expect revenue growth of {lo}% to {hi}% year-on-year, and we are guiding for an EBITDA margin of {mlo}% to {mhi}%.",
        f"For the full year {fy}, we remain confident of delivering revenue growth of around {round(yoy + opt)}% with an EBITDA margin of about {round(o + (2.0 if story == 'margin_miss' else .6), 1)}%.",
        f"We plan capex of about Rs {int(rv[idx] * 0.45)} crore in {fy}, largely towards capacity expansion.",
    ]
    if story == "margin_miss":
        lines.append("We see clear margin expansion ahead as the operating leverage kicks in; we are very comfortable with our margin trajectory.")
    if story == "debt_up":
        lines.append("Our balance sheet remains strong and we expect to moderate net debt over the next few quarters.")
    if story == "cash_weak":
        lines.append("Cash conversion should normalise as collections improve in the second half.")
    return lines


def _transcript(name, call_after, lines, rng):
    d = shift(call_after, 1)
    fill = [
        f"Operator: Ladies and gentlemen, good day and welcome to the {name} Q{quarter_name(call_after)[1]} earnings conference call.",
        "Management: Thank you. Let me begin with a quick overview of the quarter. Demand remained resilient across our key segments and we continued to invest in capability.",
        "Management: On the cost side, input costs were broadly stable and we saw some benefit from mix.",
    ]
    qa = [
        "Analyst: Can you comment on how you see the next few quarters shaping up?",
        "Management: " + lines[0],
        "Analyst: And for the full year?",
        "Management: " + lines[1],
        "Analyst: Any update on capital allocation?",
        "Management: " + lines[2],
    ] + [("Management: " + x) for x in lines[3:]]
    return "\n".join(fill + qa)


def _ar(sym, name, sector, story, rng):
    seg = sorted([rng.randint(15, 55) for _ in range(3)], reverse=True)
    tot = sum(seg)
    seg = [round(x * 100 / tot) for x in seg]
    seg[-1] = 100 - seg[0] - seg[1]
    segn = {"Pharma": ["Branded Generics", "Specialty", "API"], "IT Services": ["Cloud & Infra", "Digital Engineering", "Data & AI"],
            "Banks": ["Retail", "Corporate", "Treasury"], "Auto": ["Passenger", "Commercial", "Exports"]}.get(sector, ["Core", "Adjacent", "Other"])
    txt = (f"{name} Annual Report FY26. Business overview: {name} is a {sector.lower()} company serving domestic and export customers "
           f"through three reporting segments. Segment revenue mix: {segn[0]} {seg[0]}%, {segn[1]} {seg[1]}%, {segn[2]} {seg[2]}%. "
           f"Management Discussion: the company continues to invest in capacity and talent.\n")
    if story == "cash_weak":
        txt += "Notes: Contingent liabilities not provided for amount to Rs 640 crore, mainly disputed indirect tax demands. Trade receivables increased during the year.\n"
    if story == "debt_up":
        txt += "Notes: Related party transactions with promoter group entities amounted to Rs 410 crore during the year, including loans and guarantees.\n"
    if story == "margin_miss":
        txt += "Auditor's report: Emphasis of matter regarding recoverability of certain long-outstanding customer balances.\n"
    return txt, segn, seg


def _build():
    rng = random.Random(5)
    for sym, name, sector, cap, base, g, opm, story in CO:
        # Companies that already filed in last days: screener table not yet updated (ends Jun 2026), filing carries Sep 2026.
        # Others that reported earlier: table includes Sep 2026 (reported earlier in the season).
        reported_earlier = sym in ("ORCHARDBK", "COBALTINF", "BRIGHTFLD")
        end = LATEST_Q if reported_earlier else "Jun 2026"
        q = _quarters(rng, base, g, opm, story, end)
        # Ensure full 14 quarters incl. Mar 2026 for annual
        ann = _annual(rng, q, story, base)
        bal, cf, ratios = _bs_cf(rng, ann, story)
        txt_ar, segn, seg = _ar(sym, name, sector, story, rng)
        docs = {"annual_reports": [{"label": "Financial Year 2026", "url": f"demo://{sym}/ar"}], "concalls": []}
        TEXTS[f"demo://{sym}/ar"] = txt_ar
        for ca in ("Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026"):
            lines = _guid_lines(sym, q, ann, story, rng, ca)
            url = f"demo://{sym}/concall/{ca.replace(' ', '')}"
            TEXTS[url] = _transcript(name, ca, lines, rng)
            docs["concalls"].append({"label": shift(ca, 1), "url": url, "after": ca})
        docs["concalls"].reverse()
        _FUND[sym] = {"symbol": sym, "name": name, "consolidated": True, "about": txt_ar.split("Segment")[0],
                      "quarters": q, "annual": ann, "balance": bal, "cashflow": cf, "ratios": ratios, "docs": docs,
                      "_segments": dict(zip(segn, seg))}


def _filing_text(sym, name):
    """Results filing text with the 3 comparative columns, as Indian filings present them."""
    q = _FUND[sym]["quarters"]
    p = q["periods"]
    last = p[-1]
    # When the table already contains Sep 2026, use it; otherwise project one quarter forward from the table.
    def val(label, row):
        return q["rows"][row][p.index(label)] if label in p else None

    cur = "Sep 2026"
    prev, yoy = "Jun 2026", "Sep 2025"
    r = random.Random(sum(map(ord, sym)))
    def proj(row):
        a = val(prev, row)
        b = val(yoy, row)
        base = a * (1 + r.uniform(.0, .045))
        if row == "Sales":
            base = max(base, (b or a) * (1 + r.uniform(.05, .22)))
        return round(base, 1)
    sales = proj("Sales")
    shock = {"KESTRELPH": 1.012, "NIMBUS": .975, "QUANTACKT": 1.09, "HALCYONM": .96, "SAFFRONH": 1.03}.get(sym, 1)
    sales = round(sales * shock, 1)
    opm_cur = val(prev, "OPM %") + {"NIMBUS": -1.1, "QUANTACKT": 1.4, "KESTRELPH": .3, "HALCYONM": -.6, "SAFFRONH": .5}.get(sym, 0)
    op = round(sales * opm_cur / 100, 1)
    oi = round(sales * .017, 1)
    dep = round(sales * .035, 1)
    fin = round(sales * (.05 if sym == "HALCYONM" else .015), 1)
    pbt = round(op + oi - fin - dep, 1)
    pat = round(pbt * .75, 1)

    def pq(label, row, fn=lambda x: x):
        v = val(label, row)
        return f"{fn(v):,.1f}" if v is not None else "-"
    pb_prev = val(prev, "Profit before tax")
    lines = [
        f"{name} Limited - Unaudited Standalone Financial Results for the quarter ended September 30, 2026 (Rs in crore)",
        "Particulars | Quarter ended 30.09.2026 | Quarter ended 30.06.2026 | Quarter ended 30.09.2025",
        f"Revenue from operations | {sales:,.1f} | {pq(prev, 'Sales')} | {pq(yoy, 'Sales')}",
        f"Other income | {oi:,.1f} | {pq(prev, 'Other Income')} | {pq(yoy, 'Other Income')}",
        f"Finance costs | {fin:,.1f} | {pq(prev, 'Interest')} | {pq(yoy, 'Interest')}",
        f"Depreciation and amortisation expense | {dep:,.1f} | {pq(prev, 'Depreciation')} | {pq(yoy, 'Depreciation')}",
        f"Profit before tax | {pbt:,.1f} | {pq(prev, 'Profit before tax')} | {pq(yoy, 'Profit before tax')}",
        f"Net profit for the period | {pat:,.1f} | {pq(prev, 'Net Profit')} | {pq(yoy, 'Net Profit')}",
    ]
    return "\n".join(lines)


def _prices():
    rng = random.Random(21)
    today = datetime.now().date()
    last = today - timedelta(days=1)
    while last.weekday() >= 5:
        last -= timedelta(days=1)
    days = []
    d = last
    while len(days) < 60:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    special = {"QUANTACKT": (5.6, 3.2), "HALCYONM": (-4.4, 2.5), "NIMBUS": (1.9, 2.1), "ZEPHYRTEL": (-2.1, 1.1)}
    for sym, *_ in CO:
        px = rng.uniform(300, 4200)
        vol_base = rng.uniform(8e5, 6e6)
        series = []
        for i, d in enumerate(days):
            move = rng.gauss(.0004, .013)
            v = vol_base * rng.uniform(.7, 1.3)
            if i == len(days) - 1 and sym in special:
                move, vm = special[sym][0] / 100, special[sym][1]
                v = vol_base * vm * 1.0
            px *= 1 + move
            series.append({"d": d.isoformat(), "c": round(px, 2), "v": round(v)})
        _PRICES[sym] = series


def _announcements():
    rng = random.Random(33)
    now = datetime.now()
    mk = []

    def add(sym, hrs_ago, subject, text, url=None):
        ts = now - timedelta(hours=hrs_ago)
        mk.append({"id": f"{sym}:{ts.isoformat()}:{subject[:10]}", "symbol": sym, "ts": ts.isoformat(timespec="seconds"),
                   "subject": subject, "text": text, "url": url or f"https://www.nseindia.com/demo/{sym}/{len(mk)}.pdf",
                   "source": "DEMO"})

    # Results cluster: a filing + board outcome + press release + investor deck + newspaper ad, per filer
    for sym, h in FILED.items():
        name = dict((c[0], c[1]) for c in CO)[sym]
        base_h = 2 + h * 5 + rng.random() * 2
        f_url = f"demo://{sym}/filing/q2fy27"
        TEXTS[f_url] = _filing_text(sym, name)
        add(sym, base_h + 1.0, "Outcome of Board Meeting", f"Board approved unaudited financial results for the quarter ended September 30, 2026 and recommended interim dividend", f_url)
        add(sym, base_h + 0.8, "Financial Results", "Unaudited Financial Results for the quarter and half year ended September 30, 2026", f_url)
        add(sym, base_h + 0.4, "Investor Presentation", "Investor presentation Q2 FY27")
        add(sym, base_h, "Press Release", f"{name} reports Q2 FY27 results")
        add(sym, base_h - 0.2 if base_h > 0.2 else 0.1, "Analysts/Institutional Investor Meet/Con. Call Updates", "Earnings conference call scheduled; audio recording link and transcript will follow")
        add(sym, base_h + 20, "Newspaper Publication", "Financial results published in newspapers")
    add("NIMBUS", 5.5, "Change in Directors/ Key Managerial Personnel",
        "Resignation of Mr. Vikram Sethi as Chief Financial Officer; Board approves appointment of Ms. Ananya Rao as Chief Financial Officer w.e.f. 15 November 2026")
    BIOS["Ananya Rao"] = {"summary": "Finance leader with ~18 years across IT services and consumer tech; previously Group Controller at a global software major and Deputy CFO at a listed IT peer. Chartered Accountant.",
                          "prev": ["Deputy CFO, listed IT services peer (2021-26)", "Group Controller, global software major (2015-21)"], "synthetic": True}
    add("HALCYONM", 9.0, "Updates on Rating", "CRISIL has revised outlook on long-term bank facilities to Negative from Stable; rating AA reaffirmed")
    add("HALCYONM", 30.0, "Encumbrance", "Promoter pledged additional 2.4% of total shares in favour of lender")
    add("BRIGHTFLD", 12.0, "Change in Directors/ Key Managerial Personnel", "Appointment of Mr. Rohan Mehta as Independent Director for a term of five years")
    BIOS["Rohan Mehta"] = {"summary": "Former operating partner at a mid-market PE fund; 12 years in FMCG brand management.", "prev": ["Operating Partner, PE fund"], "synthetic": True}
    add("ZEPHYRTEL", 26.0, "Fund Raising", "Board approves raising up to Rs 3,500 crore via Qualified Institutional Placement")
    add("COBALTINF", 20.0, "Acquisition", "Company to acquire 100% stake in a transmission EPC business for Rs 1,150 crore, subject to approvals")
    add("VANTAGEST", 15.0, "Order", "Letter of award received for supply of 4.2 lakh tonnes of HR coil valued at Rs 2,300 crore")
    add("SOLACEPWR", 40.0, "Capacity Expansion", "Board approved capex of Rs 2,800 crore for 1.2 GW renewable capacity")
    add("MERIDIANR", 60.0, "Action(s) initiated or orders passed", "SEBI order imposing penalty of Rs 5 crore on company for disclosure lapses; company to appeal")
    add("LUMENRTL", 70.0, "Dividend", "Interim dividend of Rs 6 per share; record date 7 November 2026")
    add("ASTERCHEM", 18.0, "Credit Rating", "ICRA upgrades long-term rating to AA- from A+")
    add("IRONBARK", 35.0, "Trading Window", "Intimation of closure of trading window")
    add("TIDEWATER", 10.0, "Employee Stock Option Scheme", "Allotment of 41,200 equity shares under ESOP 2019")
    add("KESTRELPH", 22.0, "Disclosure under Regulation 7(2) - Insider Trading", "Promoter acquired 1,50,000 shares via open market")
    add("SAFFRONH", 55.0, "Postal Ballot", "Postal ballot notice for approval of related party transaction limits")
    add("ORCHARDBK", 48.0, "Analysts/Institutional Investor Meet/Con. Call Updates", "Schedule of meetings with institutional investors on 3-4 November")
    add("TIDEWATER", 90.0, "General Updates", "Certificate under SEBI (Depositories and Participants) Regulations, 2018")
    add("ZEPHYRTEL", 100.0, "Annual General Meeting", "Notice of 28th AGM and e-voting details")
    add("QUANTACKT", 28.0, "Bonus", "Board recommends issue of bonus shares in the ratio 1:2")
    mk.sort(key=lambda r: r["ts"], reverse=True)
    _ANN.extend(mk)


_build()
_prices()
_announcements()


def universe():
    return [{"symbol": s, "name": n, "sector": sec, "cap": cap} for s, n, sec, cap, *_ in CO]


def eod(symbols, days=60):
    return {s: _PRICES.get(s, [])[-days:] for s in symbols}


def announcements(symbol, days=7):
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    return [a for a in _ANN if a["symbol"] == symbol and a["ts"] >= cutoff]


def fundamentals(symbol):
    if symbol not in _FUND:
        raise KeyError(symbol)
    return _FUND[symbol]


def text(url):
    return TEXTS.get(url, "")
