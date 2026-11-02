"""Deterministic fundamentals analytics straight from the statement tables. No LLM, no outside knowledge."""
from ..util import pct_change, quarter_name


def row(tbl, name):
    if not tbl:
        return None
    r = tbl["rows"].get(name)
    return r


def at(tbl, name, period):
    r = row(tbl, name)
    if r is None or period not in tbl["periods"]:
        return None
    return r[tbl["periods"].index(period)]


def fy_periods(tbl):
    return [p for p in tbl["periods"] if p.startswith("Mar")]


def cagr(a, b, years):
    if not a or not b or a <= 0 or b <= 0 or years <= 0:
        return None
    return ((b / a) ** (1 / years) - 1) * 100


def snapshot(f):
    q, a = f["quarters"], f["annual"]
    lastq = q["periods"][-1]
    p4 = q["periods"][-5] if len(q["periods"]) >= 5 else None
    fy = fy_periods(a)
    lfy = fy[-1]
    s = lambda t, n, p: at(t, n, p)
    snap = {
        "latest_quarter": quarter_name(lastq), "latest_period": lastq,
        "quarter": {
            "revenue": s(q, "Sales", lastq), "revenue_yoy": pct_change(s(q, "Sales", lastq), s(q, "Sales", p4)),
            "opm": s(q, "OPM %", lastq), "opm_yoy_bps": ((s(q, "OPM %", lastq) - s(q, "OPM %", p4)) * 100 if p4 and s(q, "OPM %", p4) is not None else None),
            "pat": s(q, "Net Profit", lastq), "pat_yoy": pct_change(s(q, "Net Profit", lastq), s(q, "Net Profit", p4)),
        },
        "fy": {"label": lfy, "revenue": s(a, "Sales", lfy), "opm": s(a, "OPM %", lfy), "pat": s(a, "Net Profit", lfy),
               "pat_margin": (s(a, "Net Profit", lfy) / s(a, "Sales", lfy) * 100) if s(a, "Sales", lfy) else None,
               "revenue_growth": pct_change(s(a, "Sales", lfy), s(a, "Sales", fy[-2])) if len(fy) > 1 else None},
    }
    r = f.get("ratios")
    if r and "ROCE %" in r["rows"]:
        snap["roce"] = r["rows"]["ROCE %"][-1] if r["rows"]["ROCE %"][-1] is not None else None
    b = f.get("balance")
    if b:
        eq = (at(b, "Equity Capital", b["periods"][-1]) or 0) + (at(b, "Reserves", b["periods"][-1]) or 0)
        bor = at(b, "Borrowings", b["periods"][-1])
        snap["de"] = round(bor / eq, 2) if eq and bor is not None else None
    return snap


def trajectory(f):
    a, q = f["annual"], f["quarters"]
    fy = fy_periods(a)[-6:]
    rev = [at(a, "Sales", p) for p in fy]
    opm = [at(a, "OPM %", p) for p in fy]
    pat = [at(a, "Net Profit", p) for p in fy]
    qp = q["periods"][-8:]
    yoy, qopm = [], []
    for p in qp:
        i = q["periods"].index(p)
        yoy.append(pct_change(q["rows"]["Sales"][i], q["rows"]["Sales"][i - 4]) if i >= 4 else None)
        qopm.append(q["rows"]["OPM %"][i])
    n = len(fy) - 1
    out = {
        "fy": fy, "revenue": rev, "opm": opm, "pat": pat,
        "rev_cagr": cagr(rev[0], rev[-1], n), "pat_cagr": cagr(pat[0], pat[-1], n),
        "opm_change_bps": (opm[-1] - opm[0]) * 100 if opm[0] is not None and opm[-1] is not None else None,
        "q": qp, "q_yoy": yoy, "q_opm": qopm,
    }
    flags = []
    if out["rev_cagr"] is not None and out["pat_cagr"] is not None:
        if out["pat_cagr"] > out["rev_cagr"] + 3:
            flags.append(("green", f"Profit compounding faster than sales ({out['pat_cagr']:.0f}% vs {out['rev_cagr']:.0f}% CAGR): operating leverage is working."))
        elif out["pat_cagr"] < out["rev_cagr"] - 3:
            flags.append(("amber", f"Profit growing slower than sales ({out['pat_cagr']:.0f}% vs {out['rev_cagr']:.0f}% CAGR): margins are being squeezed."))
    valid = [x for x in yoy if x is not None]
    if len(valid) >= 4 and valid[-1] < valid[0] - 4:
        flags.append(("amber", f"Growth decelerating: YoY revenue growth {valid[0]:.0f}% → {valid[-1]:.0f}% over the last {len(valid)} quarters."))
    if len(valid) >= 4 and valid[-1] > valid[0] + 4:
        flags.append(("green", f"Growth accelerating: YoY revenue growth {valid[0]:.0f}% → {valid[-1]:.0f}%."))
    out["flags"] = flags
    return out


def balance(f):
    b, q, r = f.get("balance"), f["quarters"], f.get("ratios")
    if not b:
        return None
    per = b["periods"][-6:]
    eq = [(at(b, "Equity Capital", p) or 0) + (at(b, "Reserves", p) or 0) for p in per]
    bor = [at(b, "Borrowings", p) for p in per]
    de = [round(x / e, 2) if e and x is not None else None for x, e in zip(bor, eq)]
    # interest cover from latest 4 quarters: operating profit / interest
    op = sum((q["rows"].get("Operating Profit") or [0])[-4:])
    it = sum((q["rows"].get("Interest") or [0])[-4:])
    cover = round(op / it, 1) if it else None
    out = {"periods": per, "borrowings": bor, "equity": [round(x, 1) for x in eq], "de": de, "interest_cover": cover}
    if r:
        rp = r["periods"][-6:]
        out["wc"] = {"periods": rp, "debtor_days": [at(r, "Debtor Days", p) for p in rp],
                     "inventory_days": [at(r, "Inventory Days", p) for p in rp],
                     "payable_days": [at(r, "Days Payable", p) for p in rp],
                     "ccc": [at(r, "Cash Conversion Cycle", p) for p in rp]}
    flags = []
    if de[0] is not None and de[-1] is not None:
        if de[-1] > de[0] * 1.3 and de[-1] > .3:
            flags.append(("red", f"Leverage up: debt-to-equity {de[0]:.2f} → {de[-1]:.2f} over {len(per) - 1} years."))
        elif de[-1] < de[0] * .7:
            flags.append(("green", f"Deleveraging: debt-to-equity {de[0]:.2f} → {de[-1]:.2f}."))
    if cover is not None and cover < 3:
        flags.append(("red", f"Thin interest cover: operating profit is only {cover}× interest."))
    ccc = out.get("wc", {}).get("ccc") or []
    ccc = [x for x in ccc if x is not None]
    if len(ccc) >= 2 and ccc[-1] > ccc[0] + 10:
        flags.append(("amber", f"Working-capital cycle lengthening: {ccc[0]:.0f} → {ccc[-1]:.0f} days; cash is getting tied up."))
    out["flags"] = flags
    return out


def cash(f):
    a, cf = f["annual"], f.get("cashflow")
    if not cf:
        return None
    per = [p for p in cf["periods"] if p in a["periods"]][-6:]
    cfo = [at(cf, "Cash from Operating Activity", p) for p in per]
    inv = [at(cf, "Cash from Investing Activity", p) for p in per]
    pat = [at(a, "Net Profit", p) for p in per]
    conv = [round(c / p, 2) if c is not None and p else None for c, p in zip(cfo, pat)]
    fcf = [round(c + (i or 0), 1) if c is not None else None for c, i in zip(cfo, inv)]
    tot_c = sum(x for x in cfo if x is not None)
    tot_p = sum(x for x in pat if x is not None)
    cum = round(tot_c / tot_p, 2) if tot_p else None
    out = {"periods": per, "cfo": cfo, "pat": pat, "conversion": conv, "fcf": fcf, "cum_conversion": cum,
           "fcf_note": "FCF ≈ operating cash flow + investing cash flow (investing used as a capex proxy)."}
    flags = []
    if cum is not None:
        if cum < .7:
            flags.append(("red", f"Weak cash conversion: only ₹{cum:.2f} of operating cash for every ₹1 of profit over {len(per)} years."))
        elif cum >= 1:
            flags.append(("green", f"Profits are real cash: ₹{cum:.2f} of operating cash per ₹1 of profit over {len(per)} years."))
    c = [x for x in conv if x is not None]
    if len(c) >= 3 and c[-1] < c[0] - .25:
        flags.append(("amber", f"Cash conversion deteriorating: {c[0]:.2f} → {c[-1]:.2f}."))
    neg = sum(1 for x in fcf if x is not None and x < 0)
    if neg >= 2:
        flags.append(("amber", f"Free cash flow negative in {neg} of the last {len(per)} years."))
    out["flags"] = flags
    return out
