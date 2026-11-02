"""End-of-day price & volume via yfinance (NSE '.NS'). One batched call, cached 1h."""
from .. import cache


def yahoo_symbol(sym: str) -> str:
    return sym + ".NS"


def fetch_eod(symbols, days: int = 60):
    key = "eod:" + ",".join(sorted(symbols)) + f":{days}"
    hit = cache.get(key, ttl=3600)
    if hit:
        return hit
    import yfinance as yf  # imported lazily: keeps demo mode dependency-light

    tickers = [yahoo_symbol(s) for s in symbols]
    df = yf.download(tickers, period=f"{days + 30}d", interval="1d", group_by="ticker",
                     auto_adjust=False, progress=False, threads=True, timeout=15)
    out = {}
    for s, t in zip(symbols, tickers):
        try:
            sub = df[t].dropna(subset=["Close"])
            out[s] = [{"d": idx.strftime("%Y-%m-%d"), "c": float(r["Close"]), "v": float(r["Volume"])}
                      for idx, r in sub.tail(days).iterrows()]
        except Exception:
            out[s] = []
    if not any(out.values()):
        raise RuntimeError("yfinance returned no data")
    return cache.put(key, out)
