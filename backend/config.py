"""Central config: portfolio, defaults, env."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE_DIR = DATA / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# live | demo | auto  (auto = probe live sources at startup, fall back to demo)
MODE = os.getenv("FINN_MODE", "auto").lower()

# ---- Real mock portfolio (18 names, mixed sector / size). Verify tickers before live use. ----
PORTFOLIO = [
    ("RELIANCE", "Reliance Industries", "Energy & Conglomerate", "Large"),
    ("HDFCBANK", "HDFC Bank", "Banks", "Large"),
    ("TCS", "Tata Consultancy Services", "IT Services", "Large"),
    ("INFY", "Infosys", "IT Services", "Large"),
    ("ITC", "ITC", "FMCG", "Large"),
    ("SUNPHARMA", "Sun Pharmaceutical", "Pharma", "Large"),
    ("M&M", "Mahindra & Mahindra", "Auto", "Large"),
    ("LT", "Larsen & Toubro", "Capital Goods", "Large"),
    ("BAJFINANCE", "Bajaj Finance", "NBFC", "Large"),
    ("TITAN", "Titan Company", "Consumer", "Large"),
    ("DIXON", "Dixon Technologies", "Electronics Mfg", "Mid"),
    ("POLYCAB", "Polycab India", "Cables", "Mid"),
    ("PERSISTENT", "Persistent Systems", "IT Services", "Mid"),
    ("KPITTECH", "KPIT Technologies", "Auto Software", "Mid"),
    ("APOLLOHOSP", "Apollo Hospitals", "Healthcare", "Large"),
    ("CDSL", "Central Depository Services", "Capital Markets", "Small"),
    ("AARTIIND", "Aarti Industries", "Specialty Chem", "Small"),
    ("TRENT", "Trent", "Retail", "Large"),
]
ADHOC_LIVE = ["ASIANPAINT", "PIDILITIND", "BAJAJ-AUTO", "HAL"]

# ---- Defaults for user-tunable rules (UI overrides per request) ----
DEFAULT_RULES = {
    "window_hours": 24,
    "price_move_pct": 3.0,
    "volume_mult": 2.0,
    "volume_lookback": 20,
    "min_priority": 0,
    "watch": ["results", "M&A", "management_change", "litigation", "credit_rating", "fund_raise", "pledging"],
}

# ---- LLM routing (all optional; app degrades to deterministic mode with no key) ----
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CHEAP_MODEL = os.getenv("FINN_CHEAP_MODEL", "")
STRONG_MODEL = os.getenv("FINN_STRONG_MODEL", "")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
