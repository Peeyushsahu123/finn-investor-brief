Subject: ENAM - IIT screening - 2027

Hi team,

Please find my submission for the FINN challenge.

- Prototype (mobile web): <DEPLOYED LINK>
- Repository: <GITHUB LINK>
- AI build history: <CLAUDE CONVERSATION SHARE LINK(S)>

**What I built.** FINN, a phone-first investor cockpit with a point of view: the investor shouldn't read filings, they should be told which three things need them. Push: a windowed digest (any period) that classifies, clusters (a results filing plus its five sibling filings become one card), scores and tiers everything, collapsing routine filings; results cards show Revenue/EBITDA/PBT/PAT QoQ and YoY from the filing itself; management-change cards show who left, who joined and the newcomer's background; alerts fire on user-set price, volume and filing-type rules. Pull: chat/voice that returns structured cards for any NSE ticker, centred on a "promised vs delivered" scoreboard that checks management's explicit guidance from the last four calls against reported actuals, plus narrative-vs-numbers, cash quality, balance sheet, trajectory and bull/bear.

**Key decisions.** (1) Numbers are computed deterministically; the LLM never does arithmetic. (2) Every guidance claim must carry a quote verified verbatim in the transcript, or it is dropped. The check permits differences in whitespace and capitalisation. (3) Pull is grounded only in annual reports, transcripts and statement tables. (4) Cost: regex before LLM, a cheap model for bulk extraction, a strong model only for bull/bear synthesis, content-hash caching everywhere; the app works with no API key at all. (5) Interaction: a ranked feed as the default home, with conversation as the escape hatch, since most days the right answer is "here are the 3 things".

**Honest limitations.** My build environment blocked egress to Yahoo, NSE and screener.in, so the live connectors are written but unverified end to end; the app auto-falls back to a clearly-labelled synthetic demo universe (fictional companies) that runs the identical pipeline. Please treat the demo mode as the reliable experience while live-source validation remains pending.

**Left out.** Intraday data, BSE, real server-side push, OCR for scanned filings, extraction-accuracy evals on real filings.

**Next.** Verify and harden live sources, add web-push, build a small eval set of real results filings and concalls to measure extraction precision, and weight everything by portfolio position size.

Thanks,
Peeyush
