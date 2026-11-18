"""
Currency formatting for text the backend writes (insights, assistant answers, reports).

The currency is an admin setting (Settings -> General -> currency, e.g. "USD" or "INR").
INR uses Indian digit grouping (1,23,45,678) and the ₹ symbol.
"""
from __future__ import annotations

SYMBOLS = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "AUD": "A$", "CAD": "C$", "SGD": "S$", "AED": "AED "}
_state = {"code": "USD"}


def set_currency(code: str | None) -> None:
    _state["code"] = (code or "USD").strip().upper() or "USD"


def load_currency(db) -> str:
    """Refresh the active currency from the database settings."""
    from app.services import app_settings
    set_currency(app_settings.get_section(db, "general").get("currency", "USD"))
    return _state["code"]


def money_symbol() -> str:
    code = _state["code"]
    return SYMBOLS.get(code, code + " ")


def _indian_group(int_part: str) -> str:
    """12345678 -> 1,23,45,678"""
    if len(int_part) <= 3:
        return int_part
    head, tail = int_part[:-3], int_part[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups) + "," + tail


def money(value, decimals: int = 0) -> str:
    if value is None:
        return "n/a"
    v = float(value)
    sign = "-" if v < 0 else ""
    text = f"{abs(v):,.{decimals}f}"
    if _state["code"] == "INR":
        raw = f"{abs(v):.{decimals}f}"
        int_part, _, frac = raw.partition(".")
        text = _indian_group(int_part) + (f".{frac}" if frac else "")
    return f"{sign}{money_symbol()}{text}"
