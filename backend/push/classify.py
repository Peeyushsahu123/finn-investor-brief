"""Announcement classifier. Rules first (free, instant); a cheap LLM only for the ambiguous remainder."""
import re

from .. import llm

CATEGORIES = ["results", "M&A", "fund_raise", "management_change", "litigation", "insider_trading",
              "earnings_call", "investor_meetings", "credit_rating", "dividend", "bonus_split", "capex",
              "press_release", "postal_ballot", "agm_egm", "pledging", "unclassified"]

# (category, regex over subject+text, confidence). Order matters: first hit wins.
RULES = [
    ("pledging", r"encumbrance|pledg", .95),
    ("insider_trading", r"insider trading|regulation 7\(2\)|sast|acquired .* shares via open market|sold .* shares", .9),
    ("credit_rating", r"credit rating|updates on rating|upgrad\w+ .*rating|downgrad|reaffirm|crisil|icra|care ratings|india ratings", .92),
    ("management_change", r"key managerial|resign|appointment of|cessation|\bcfo\b|\bceo\b|managing director|chief (financial|executive)|independent director", .9),
    ("litigation", r"orders? passed|action\(s\) initiated|penalt|show.?cause|insolvency|nclt|litigation|court|sebi order|fine of", .9),
    ("M&A", r"acquisition|acquire|merger|amalgamation|demerger|joint venture|scheme of arrangement|stake in", .9),
    ("fund_raise", r"fund.?raising|qip|rights issue|preferential|buy-?back|commercial paper|raising up to|ncd|debentures", .9),
    ("bonus_split", r"\bbonus\b|stock split|sub-?division of", .93),
    ("dividend", r"dividend", .88),
    ("capex", r"capex|capital expenditure|capacity expansion|new plant|greenfield|brownfield", .88),
    ("earnings_call", r"conference call|con\. call|earnings call|audio recording|transcript", .85),
    ("investor_meetings", r"investor meet|institutional investor|analyst meet|schedule of meeting", .85),
    ("postal_ballot", r"postal ballot", .95),
    ("agm_egm", r"annual general meeting|extraordinary general|\bagm\b|\begm\b", .92),
    ("results", r"financial results|investor presentation|outcome of board|newspaper publication|unaudited|audited results|quarter ended", .8),
    ("press_release", r"press release|order|letter of award|contract|partnership|clarification", .7),
    ("unclassified", r"esop|stock option|trading window|certificate|esg|brsr|auditor|compliance|regulation 74|regulation 40|general updates", .85),
]
_COMPILED = [(c, re.compile(p, re.I), conf) for c, p, conf in RULES]


def rule_classify(item):
    hay = f"{item['subject']} {item['text']}"
    if re.search(r"financial results|results for the quarter|quarter ended .*(unaudited|audited)|(unaudited|audited).*quarter", hay, re.I) \
            and not re.search(r"newspaper", hay, re.I):
        return "results", .92
    # an "Outcome of board meeting" that mentions dividend/fund-raise etc. is best labelled by the stronger signal
    for c, rx, conf in _COMPILED:
        if rx.search(hay):
            if c == "results" and re.search(r"dividend", hay, re.I) and "financial results" not in hay.lower():
                return "dividend", .8
            return c, conf
    return "unclassified", .3


def classify_all(items):
    """Annotate items in place with 'cat' and 'cat_conf'. Low-confidence items go to ONE batched cheap LLM call."""
    shaky = []
    for it in items:
        it["cat"], it["cat_conf"] = rule_classify(it)
        if it["cat_conf"] < .6:
            shaky.append(it)
    if shaky and llm.available():
        payload = [{"i": i, "subject": s["subject"], "text": s["text"][:300]} for i, s in enumerate(shaky[:40])]
        out = llm.ask_json(
            "Classify each corporate announcement into exactly one of: " + ", ".join(CATEGORIES) +
            ". Return JSON {\"labels\": [{\"i\": int, \"cat\": str}]}.\n" + str(payload), tier="cheap")
        if out and isinstance(out.get("labels"), list):
            for lab in out["labels"]:
                try:
                    if lab["cat"] in CATEGORIES:
                        shaky[lab["i"]]["cat"], shaky[lab["i"]]["cat_conf"] = lab["cat"], .75
                except Exception:
                    pass
    return items
