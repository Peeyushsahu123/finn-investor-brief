# FINN — financial investment agent (mobile-first)

[Open FINN](https://finn-investor-brief.onrender.com/). The hosted portfolio is a saved view of 18 real NSE holdings as of 2 November 2026, 22:53 IST. Time filters end at that timestamp. Prices and volumes come from Yahoo Finance, and filing links open the NSE disclosure. The snapshot covers ten days of filings. Research requests outside the saved examples depend on access to the upstream sites. Set FINN_MODE=snapshot to reproduce the hosted brief locally.


Push (what changed, ranked) + Pull (grounded research) in one phone-sized web app. FastAPI backend, no-build vanilla-JS frontend.

## Run
```bash
pip install -r requirements.txt
uvicorn backend.main:app --port 8000      # open on your phone / devtools mobile view
```
Optional: `GEMINI_API_KEY` or `ANTHROPIC_API_KEY`. With no key everything still runs (deterministic mode).

**Data modes** (`FINN_MODE=auto|live|demo`). `auto` probes Yahoo at startup:
- **live** — yfinance (EOD), NSE corporate-announcements API, screener.in (tables + annual report / concall links, PDF text via pypdf). Portfolio of 18 real NSE names in `backend/config.py`.
- **demo** — synthetic, fictional companies with realistic filings/transcripts so the full product is demoable offline. Badge in the header always says which mode you're in.

> Honest status: the live connectors were written to the public endpoints' documented shapes but could **not be run end-to-end from the build sandbox** (egress to Yahoo/NSE/screener was blocked). Everything shown in the demo mode is exercised by tests and screenshots; live mode is the first thing to verify on a normal network. Parsing for screener lives in one file (`sources/screener.py`) for easy fixing.

## Product
- **Today (push):** pick any window (6h/24h/3d/7d/custom). Filings are classified, results-family filings are clustered into one card, scored, and tiered *Needs you / Worth a look / Routine (collapsed)*. Price/volume context is attached to each card.
- **Results card:** Revenue, EBITDA, PBT, PAT — QoQ and YoY — parsed from the filing's own comparative columns.
- **Management change:** who left, who joined, effective date, background of the incoming person (web snippets → cheap LLM, only from snippets, with links).
- **Triggered alerts:** configurable ±price move, volume × 20-day average, and watched filing types; in-app toast + browser notification.
- **Ask (pull):** chat or voice → structured cards, not paragraphs. Any NSE ticker.
- **Research:** business, financial snapshot, trajectory, balance sheet, cash quality, guidance scoreboard (promised vs delivered), narrative vs numbers, bull vs bear.
- **Rules:** thresholds and per-category Watch / Normal / Mute.

## Decisions
- **Numbers are computed, words are verified.** All ratios, trends and flags are deterministic from statement tables. Guidance items are accepted only if the quote appears in the transcript; actuals come only from tables. Narrative-vs-numbers is rule-checked, not model opinion.
- **Primary sources only on pull.** No news/broker/model-memory.
- **Cost routing.** Regex first → cheap model for ambiguous classification/extraction → strong model only for bull/bear synthesis. All LLM calls cached by content hash; data cached on disk. The Rules tab shows call and cache counters.
- **Degrades, never blanks.** No key → deterministic; no network → demo; one failing source → that panel only.

## Left out / next
Intraday data, BSE source, portfolio P&L weighting, server push (FCM/web-push) for alerts when the app is closed, OCR for scanned filings, per-segment tables from annual reports, evals for extraction accuracy on real filings.
