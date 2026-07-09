"""Strategy6 market context and relative strength helpers."""
from __future__ import annotations


MARKET_INDEX_SYMBOLS = ("sh000001", "sz399001", "sz399006")
HS300_ALIASES = ("hs300", "sh000300", "sz399300")


def evaluate_market_context(market_data_by_symbol: dict[str, list[dict]] | None) -> dict:
    """Evaluate broad market status from already-truncated index rows."""
    data = market_data_by_symbol or {}
    statuses = [_index_status(data.get(symbol) or []) for symbol in MARKET_INDEX_SYMBOLS]
    observed = [status for status in statuses if status["observed"]]
    if not observed:
        return {
            "market_status": "UNKNOWN",
            "market_reasons": ["MARKET_DATA_UNAVAILABLE"],
            "market_return_20": 0.0,
        }

    above_ma20 = sum(1 for status in observed if status["above_ma20"])
    ma20_above_ma50 = sum(1 for status in observed if status["ma20_above_ma50"])
    risk_count = sum(1 for status in observed if status["volume_down_risk"])
    weak_count = sum(1 for status in observed if status["weak"])

    if risk_count >= 1:
        market_status = "MARKET_RISK"
    elif weak_count >= max(1, len(observed) // 2 + 1):
        market_status = "MARKET_WEAK"
    elif above_ma20 >= 2 and ma20_above_ma50 >= 1:
        market_status = "MARKET_STRONG"
    else:
        market_status = "MARKET_NEUTRAL"

    return {
        "market_status": market_status,
        "market_reasons": [
            f"above_ma20={above_ma20}",
            f"ma20_above_ma50={ma20_above_ma50}",
            f"risk_count={risk_count}",
        ],
        "market_return_20": _market_return_20(data),
    }


def compute_relative_strength_20(stock_return_20: float, market_data_by_symbol: dict[str, list[dict]] | None) -> float:
    market_return = _market_return_20(market_data_by_symbol or {})
    return round(stock_return_20 - market_return, 6)


def _market_return_20(data: dict[str, list[dict]]) -> float:
    for symbol in HS300_ALIASES:
        rows = data.get(symbol)
        if rows:
            return _return(rows, 20)
    rows = data.get("sh000001") or []
    return _return(rows, 20)


def _index_status(rows: list[dict]) -> dict:
    normalized = [row for row in rows if isinstance(row, dict)]
    close = _last_close(normalized)
    ma20 = _ma(normalized, 20)
    ma50 = _ma(normalized, 50)
    above_ma20 = close > 0 and ma20 > 0 and close >= ma20
    ma20_above_ma50 = ma20 > 0 and ma50 > 0 and ma20 >= ma50
    weak = close > 0 and ma20 > 0 and close < ma20 and _ma_slope_down(normalized, 20)
    return {
        "observed": len(normalized) >= 50,
        "above_ma20": above_ma20,
        "ma20_above_ma50": ma20_above_ma50,
        "weak": weak,
        "volume_down_risk": _volume_down_risk(normalized),
    }


def _last_close(rows: list[dict]) -> float:
    return float(rows[-1].get("close") or 0.0) if rows else 0.0


def _ma(rows: list[dict], days: int, end: int | None = None) -> float:
    end = len(rows) if end is None else end
    if end < days:
        return 0.0
    window = rows[end - days:end]
    return sum(float(row.get("close") or 0.0) for row in window) / days


def _return(rows: list[dict], days: int) -> float:
    if len(rows) <= days:
        return 0.0
    base = float(rows[-days - 1].get("close") or 0.0)
    close = float(rows[-1].get("close") or 0.0)
    return close / base - 1.0 if base > 0 and close > 0 else 0.0


def _ma_slope_down(rows: list[dict], days: int) -> bool:
    if len(rows) < days + 5:
        return False
    return _ma(rows, days) < _ma(rows, days, end=len(rows) - 5)


def _volume_down_risk(rows: list[dict]) -> bool:
    if len(rows) < 25:
        return False
    v20 = sum(float(row.get("volume") or 0.0) for row in rows[-25:-5]) / 20
    if v20 <= 0:
        return False
    risk_days = 0
    for prev, curr in zip(rows[-6:-1], rows[-5:]):
        prev_close = float(prev.get("close") or 0.0)
        close = float(curr.get("close") or 0.0)
        volume = float(curr.get("volume") or 0.0)
        if prev_close > 0 and close / prev_close - 1 <= -0.015 and volume >= v20 * 1.2:
            risk_days += 1
    return risk_days >= 3
