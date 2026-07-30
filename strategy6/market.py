"""Strategy6 market context and relative strength helpers."""
from __future__ import annotations


MARKET_INDEX_SYMBOLS = ("sh000001", "sz399001", "sz399006")
HS300_ALIASES = ("hs300", "sh000300", "sz399300")
MARKET_INDEX_NAMES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "hs300": "沪深300",
    "sh000300": "沪深300",
    "sz399300": "沪深300",
}


def evaluate_market_context(
    market_data_by_symbol: dict[str, list[dict]] | None,
    *,
    expected_trade_date: str = "",
) -> dict:
    """Evaluate broad market status from already-truncated index rows."""
    data = market_data_by_symbol or {}
    statuses = [
        _index_status(data.get(symbol) or [], expected_trade_date=expected_trade_date)
        for symbol in MARKET_INDEX_SYMBOLS
    ]
    observed = [status for status in statuses if status["observed"]]
    if not observed:
        return {
            "market_status": "UNKNOWN",
            "market_reasons": ["MARKET_DATA_UNAVAILABLE"],
            "market_return_20": _market_return_20(
                data,
                expected_trade_date=expected_trade_date,
            ),
        }
    if len(observed) < 2:
        return {
            "market_status": "UNKNOWN",
            "market_reasons": ["MARKET_DATA_PARTIAL", f"observed_indexes={len(observed)}"],
            "market_return_20": _market_return_20(
                data,
                expected_trade_date=expected_trade_date,
            ),
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
        "market_return_20": _market_return_20(data, expected_trade_date=expected_trade_date),
    }


def build_market_snapshot(
    market_data_by_symbol: dict[str, list[dict]] | None,
    *,
    expected_trade_date: str = "",
) -> dict:
    """Build a task-level market snapshot for audit display."""
    data = market_data_by_symbol or {}
    context = evaluate_market_context(data, expected_trade_date=expected_trade_date)
    indexes = []
    for symbol in ("sh000001", "sz399001", "sz399006", "hs300"):
        rows = [row for row in data.get(symbol, []) if isinstance(row, dict)]
        status = _index_status(rows, expected_trade_date=expected_trade_date)
        indexes.append({
            "symbol": symbol,
            "name": MARKET_INDEX_NAMES.get(symbol, symbol),
            "latest_date": str(rows[-1].get("date") or "") if rows else "",
            "latest_close": _last_close(rows),
            "ma20": _ma(rows, 20),
            "ma50": _ma(rows, 50),
            "return_20": _return(rows, 20),
            "above_ma20": bool(status["above_ma20"]),
            "ma20_above_ma50": bool(status["ma20_above_ma50"]),
            "volume_down_risk": bool(status["volume_down_risk"]),
            "weak": bool(status["weak"]),
            "rows_count": len(rows),
            "source": str(rows[-1].get("source") or "sina") if rows else "",
            "data_status": status["data_status"],
        })
    return {
        "market_status": context["market_status"],
        "market_reasons": context["market_reasons"],
        "market_return_20": context["market_return_20"],
        "indexes": indexes,
    }


def compute_relative_strength_20(
    stock_return_20: float,
    market_data_by_symbol: dict[str, list[dict]] | None,
    *,
    expected_trade_date: str = "",
) -> float:
    rows = _hs300_rows(market_data_by_symbol or {}, expected_trade_date)
    if not rows:
        return 0.0
    market_return = _return(rows, 20)
    return round(stock_return_20 - market_return, 6)


def has_relative_strength_20_market(
    market_data_by_symbol: dict[str, list[dict]] | None,
    *,
    expected_trade_date: str = "",
) -> bool:
    return bool(_hs300_rows(market_data_by_symbol or {}, expected_trade_date))


def compute_relative_strength_periods(
    stock_rows: list[dict],
    market_data_by_symbol: dict[str, list[dict]] | None,
    *,
    expected_trade_date: str = "",
) -> dict[int, float] | None:
    """Return stock minus same-day HS300 returns for 5/10/20/60 days."""
    market_rows = _hs300_rows(market_data_by_symbol or {}, expected_trade_date)
    if not market_rows or len(stock_rows) <= 20 or len(market_rows) <= 20:
        return None
    periods = {
        days: round(_return(stock_rows, days) - _return(market_rows, days), 6)
        for days in (5, 10, 20)
    }
    if len(stock_rows) > 60 and len(market_rows) > 60:
        periods[60] = round(_return(stock_rows, 60) - _return(market_rows, 60), 6)
    return periods


def evaluate_single_index_context(
    symbol: str,
    market_data_by_symbol: dict[str, list[dict]] | None,
    *,
    expected_trade_date: str = "",
) -> str:
    """Evaluate one broad index for board-matched diagnostic use."""
    rows = (market_data_by_symbol or {}).get(symbol) or []
    status = _index_status(rows, expected_trade_date=expected_trade_date)
    if not status["observed"]:
        return "UNKNOWN"
    if status["volume_down_risk"]:
        return "MARKET_RISK"
    if status["weak"]:
        return "MARKET_WEAK"
    if status["above_ma20"] and status["ma20_above_ma50"]:
        return "MARKET_STRONG"
    return "MARKET_NEUTRAL"


def _market_return_20(data: dict[str, list[dict]], *, expected_trade_date: str = "") -> float:
    rows = _hs300_rows(data, expected_trade_date)
    return _return(rows, 20) if rows else 0.0


def _index_status(rows: list[dict], *, expected_trade_date: str = "") -> dict:
    normalized = [row for row in rows if isinstance(row, dict)]
    data_status = _data_status(normalized, expected_trade_date)
    close = _last_close(normalized)
    ma20 = _ma(normalized, 20)
    ma50 = _ma(normalized, 50)
    above_ma20 = close > 0 and ma20 > 0 and close >= ma20
    ma20_above_ma50 = ma20 > 0 and ma50 > 0 and ma20 >= ma50
    weak = close > 0 and ma20 > 0 and close < ma20 and _ma_slope_down(normalized, 20)
    return {
        "observed": len(normalized) >= 50 and data_status == "FRESH",
        "data_status": data_status,
        "above_ma20": above_ma20,
        "ma20_above_ma50": ma20_above_ma50,
        "weak": weak,
        "volume_down_risk": _volume_down_risk(normalized),
    }


def _hs300_rows(data: dict[str, list[dict]], expected_trade_date: str) -> list[dict]:
    for symbol in HS300_ALIASES:
        rows = [row for row in (data.get(symbol) or []) if isinstance(row, dict)]
        if len(rows) > 20 and _data_status(rows, expected_trade_date) == "FRESH":
            return rows
    return []


def _data_status(rows: list[dict], expected_trade_date: str) -> str:
    if not rows:
        return "MISSING"
    if expected_trade_date and str(rows[-1].get("date") or "") != expected_trade_date:
        return "STALE"
    return "FRESH"


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
