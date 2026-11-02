import os
os.environ["FINN_MODE"] = "demo"

from backend.push import classify, digest, results
from backend.pull import guidance, research
from backend.util import target_to_period, shift


def test_periods():
    assert target_to_period("Q3FY27") == "Dec 2026"
    assert target_to_period("Q4FY26") == "Mar 2026"
    assert shift("Sep 2026", -12) == "Sep 2025"


def test_classifier_rules():
    f = lambda s, t="": classify.rule_classify({"subject": s, "text": t})[0]
    assert f("Updates on Rating", "CRISIL revised outlook") == "credit_rating"
    assert f("Change in Directors/ Key Managerial Personnel", "Resignation of CFO") == "management_change"
    assert f("Acquisition", "acquire 100% stake") == "M&A"
    assert f("Financial Results", "quarter ended September 30, 2026") == "results"


def test_results_extraction_three_columns():
    txt = ("Particulars | Q 30.09.2026 | Q 30.06.2026 | Q 30.09.2025\n"
           "Revenue from operations | 120.0 | 100.0 | 80.0\nFinance costs | 2 | 2 | 2\n"
           "Depreciation and amortisation expense | 5 | 5 | 5\nProfit before tax | 20 | 10 | 8\n"
           "Net profit for the period | 15 | 7.5 | 6\n"
           "unaudited results for the quarter ended September 30, 2026")
    r = results.extract(txt, None)
    rev = next(x for x in r["rows"] if x["metric"] == "Revenue")
    assert round(rev["qoq"]) == 20 and round(rev["yoy"]) == 50


def test_guidance_quote_must_be_verbatim():
    t = "We expect revenue growth of 10% to 12% in Q3 FY27 on a year-on-year basis for the company."
    items, dropped = guidance.extract_call(t)
    assert items and items[0]["low"] == 10 and items[0]["high"] == 12
    assert not guidance.verify_quote("a sentence that was never said anywhere in this transcript", t)


def test_digest_prioritises_and_collapses():
    d = digest.digest({})
    assert d["pulse"]["now"] > 0
    pr = [i["priority"] for i in d["items"]]
    assert pr == sorted(pr, reverse=True)
    assert any(i["tier"] == "routine" for i in d["items"])
    res = next(i for i in d["items"] if i["cat"] == "results" and i["enrich"])
    assert {"Revenue", "EBITDA", "PBT", "PAT"} == {r["metric"] for r in res["enrich"]["rows"]}


def test_research_is_ticker_agnostic():
    for sym in ("NIMBUS", "SOLACEPWR"):
        r = research.research(sym)
        assert {"guidance", "cash", "bullbear"} <= set(r["sections"])


def test_quote_preserves_negation_and_accepts_pdf_line_wraps():
    transcript = "We do not expect revenue growth of 12% in FY27."
    assert not guidance.verify_quote("We expect revenue growth of 12% in FY27.", transcript)
    assert guidance.verify_quote(transcript, transcript.replace("growth of", "growth\nof"))
    assert not guidance.verify_quote("   ", transcript)
