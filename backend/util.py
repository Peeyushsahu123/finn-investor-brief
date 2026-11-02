"""Period helpers. Indian FY: FY27 = Apr 2026 - Mar 2027. Q1=Jun, Q2=Sep, Q3=Dec, Q4=Mar."""
import re
from datetime import datetime

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_Q_END = {1: 6, 2: 9, 3: 12, 4: 3}


def parse_period(label: str):
    """'Sep 2025' -> (2025, 9)"""
    m = re.match(r"([A-Za-z]{3})\w*\s+(\d{4})", label.strip())
    if not m:
        return None
    return int(m.group(2)), MONTHS.index(m.group(1).title()) + 1


def fmt_period(y: int, m: int) -> str:
    return f"{MONTHS[m - 1]} {y}"


def shift(label: str, months: int) -> str:
    y, m = parse_period(label)
    t = y * 12 + (m - 1) + months
    return fmt_period(t // 12, t % 12 + 1)


def quarter_name(label: str) -> str:
    """'Sep 2026' -> 'Q2 FY27'"""
    y, m = parse_period(label)
    fy = y + 1 if m > 3 else y
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(m)
    return f"Q{q} FY{str(fy)[2:]}" if q else label


def target_to_period(text: str):
    """'Q3 FY27' / 'Q3FY27' -> 'Dec 2026';  'FY27' -> 'Mar 2027' (fiscal year end)."""
    t = text.upper().replace(" ", "")
    m = re.match(r"Q([1-4])FY(\d{2,4})", t)
    if m:
        q, fy = int(m.group(1)), int(m.group(2))
        fy = fy + 2000 if fy < 100 else fy
        end_m = _Q_END[q]
        y = fy if end_m == 3 else fy - 1
        return fmt_period(y, end_m)
    m = re.match(r"FY(\d{2,4})", t)
    if m:
        fy = int(m.group(1))
        fy = fy + 2000 if fy < 100 else fy
        return fmt_period(fy, 3)
    return None


def num(x):
    """Parse '1,234.5', '12%', '(45)' -> float, else None."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace(",", "").replace("%", "").replace("₹", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


def pct_change(new, old):
    if new is None or old in (None, 0):
        return None
    return (new - old) / abs(old) * 100.0


def now_iso():
    return datetime.now().isoformat(timespec="seconds")
