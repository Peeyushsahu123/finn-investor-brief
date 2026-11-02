# FINN Investor Brief

[Open FINN](https://finn-investor-brief.onrender.com/)

I built FINN around two questions an investor might ask: “Which filings should I read first?” and “Did the company deliver what management said it would?”

The first screen shows a mock portfolio of 18 NSE-listed companies. The hosted version uses a snapshot saved on **2 November 2026 at 10:53 PM IST**, with closing prices and trading volumes from Yahoo Finance and announcements from NSE. The time filters count back from that timestamp, so anyone opening the app can explore the same trading day.

## Try it

1. Open **Today** and switch between **6h** and **24h**. Tap a filing to read its details and open the original disclosure. Routine filings are grouped at the bottom.
2. Open **Ask → Wipro**. Wipro reported 1.4% growth in IT Services revenue, but its October guidance excluded the HARMAN DTS acquisition. The card shows both figures and uses **0.6%**, the growth excluding HARMAN DTS, for the comparison. Tap that figure to open page 3 of the earnings-call transcript.
3. Open **Rules** and change the price or volume threshold. Return to **Today** to see which holdings meet your criteria.

## How it works

The backend is written in Python with FastAPI. The frontend uses HTML, CSS, and JavaScript. Filings are ranked by announcement type and the investor’s preferences. For volume alerts, FINN compares the latest session with the previous 20 sessions.

Company research uses financial statements, annual reports, and earnings-call transcripts. Python calculates the financial comparisons. When FINN extracts management guidance, it checks that the quoted passage appears in the transcript before using it.

## Run locally

From the repository folder, install the dependencies:

```bash
python -m pip install -r requirements.txt
```

To run the same portfolio snapshot as the hosted app, start the server from PowerShell:

```powershell
$env:FINN_MODE = "snapshot"
python -m uvicorn backend.main:app --port 8000
```

Open [localhost:8000](http://localhost:8000/). On macOS or Linux, use `export FINN_MODE=snapshot` in place of the PowerShell line.

Set `FINN_MODE=live` to fetch current data, or `FINN_MODE=demo` to explore the app offline with fictional companies. The snapshot runs without a model API key.
