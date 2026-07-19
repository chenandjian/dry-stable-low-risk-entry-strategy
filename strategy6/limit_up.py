"""A-share limit-up helpers for Strategy6."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def get_limit_up_pct(stock_code: str, stock_name: str = "") -> float:
    code = str(stock_code or "").strip()
    if code.startswith(("688", "689", "300", "301")):
        return 0.20
    return 0.10


def calc_limit_up_price(prev_close: float, limit_pct: float) -> float:
    value = Decimal(str(prev_close)) * (Decimal("1") + Decimal(str(limit_pct)))
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def is_limit_up_day(stock_code: str, prev_close: float, close: float) -> bool:
    if prev_close <= 0 or close <= 0:
        return False
    limit_up_price = calc_limit_up_price(prev_close, get_limit_up_pct(stock_code))
    return close >= limit_up_price - 0.01


def is_one_word_limit_up(
    stock_code: str,
    prev_close: float,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> bool:
    if prev_close <= 0:
        return False
    limit_up_price = calc_limit_up_price(prev_close, get_limit_up_pct(stock_code))
    threshold = limit_up_price - 0.01
    return open_price >= threshold and high >= threshold and low >= threshold and close >= threshold


def is_touched_limit_up_failed(stock_code: str, prev_close: float, high: float, close: float) -> bool:
    if prev_close <= 0 or high <= 0:
        return False
    limit_up_price = calc_limit_up_price(prev_close, get_limit_up_pct(stock_code))
    touched = high >= limit_up_price - 0.01
    sealed = close >= limit_up_price - 0.01
    return touched and not sealed
