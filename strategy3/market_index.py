"""Strategy3 market index mapping and environment helpers."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import pstdev


INDEX_NAMES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000688": "科创50",
}

DEFAULT_INDEX_SYMBOLS = ("sh000001", "sz399001", "sz399006", "sh000688")


@dataclass(frozen=True)
class Strategy3MarketIndexSelection:
    """Resolved market index for one stock code."""

    symbol: str
    name: str
    fallback: bool = False
    fallback_reason: str = ""

    def to_metadata(self, market_data_mode: str) -> dict:
        return {
            "market_index_symbol": self.symbol,
            "market_index_name": self.name,
            "market_data_mode": market_data_mode,
            "market_index_fallback": self.fallback,
            "market_index_fallback_reason": self.fallback_reason,
        }


def resolve_strategy3_market_index(
    code: str,
    available_symbols: set[str] | list[str] | tuple[str, ...] | None = None,
) -> Strategy3MarketIndexSelection:
    """Resolve the market index used by Strategy3 for a stock code."""
    normalized = str(code or "").strip()
    symbol = "sh000001"
    fallback = False
    reason = ""

    if normalized.startswith(("600", "601", "603", "605")):
        symbol = "sh000001"
    elif normalized.startswith(("000", "001", "002", "003")):
        symbol = "sz399001"
    elif normalized.startswith(("300", "301")):
        symbol = "sz399006"
    elif normalized.startswith("688"):
        symbol = "sh000688"
    else:
        symbol = "sh000001"
        fallback = True
        reason = "UNKNOWN_PREFIX_FALLBACK_TO_SH000001"

    available = set(available_symbols or [])
    if symbol == "sh000688" and available_symbols is not None and "sh000688" not in available:
        symbol = "sh000001"
        fallback = True
        reason = "STAR_INDEX_UNAVAILABLE_FALLBACK_TO_SH000001"

    return Strategy3MarketIndexSelection(
        symbol=symbol,
        name=INDEX_NAMES.get(symbol, symbol),
        fallback=fallback,
        fallback_reason=reason,
    )


def compute_strategy3_market_context(
    market_data: list[dict] | None,
    *,
    selection: Strategy3MarketIndexSelection | None = None,
    market_data_mode: str = "",
) -> dict:
    """Compute market environment fields from an already-truncated index window."""
    selection = selection or resolve_strategy3_market_index("")
    metadata = selection.to_metadata(market_data_mode)
    rows = [row for row in (market_data or []) if isinstance(row, dict)]
    close = _last_close(rows)
    ma20 = _ma(rows, 20)
    ma60 = _ma(rows, 60)
    has_market_data = len(rows) > 60 and close > 0
    context = {
        **metadata,
        "has_market_data": has_market_data,
        "market_return_20": _return(rows, 20) if len(rows) > 20 else 0.0,
        "market_return_60": _return(rows, 60) if has_market_data else 0.0,
        "market_ma20": ma20,
        "market_ma60": ma60,
        "market_above_ma20": bool(close > 0 and ma20 > 0 and close >= ma20),
        "market_above_ma60": bool(close > 0 and ma60 > 0 and close >= ma60),
        "market_volatility_20": _volatility(rows, 20),
        "market_drawdown_60": _drawdown(rows, 60),
    }
    return context


def _last_close(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    return float(rows[-1].get("close") or 0.0)


def _ma(rows: list[dict], days: int) -> float:
    if len(rows) < days:
        return 0.0
    return sum(float(row.get("close") or 0.0) for row in rows[-days:]) / days


def _return(rows: list[dict], days: int) -> float:
    if len(rows) <= days:
        return 0.0
    base = float(rows[-days - 1].get("close") or 0.0)
    if base <= 0:
        return 0.0
    return float(rows[-1].get("close") or 0.0) / base - 1.0


def _daily_returns(rows: list[dict], days: int) -> list[float]:
    if len(rows) <= days:
        return []
    values: list[float] = []
    window = rows[-days - 1:]
    for prev, curr in zip(window[:-1], window[1:]):
        prev_close = float(prev.get("close") or 0.0)
        curr_close = float(curr.get("close") or 0.0)
        if prev_close > 0 and curr_close > 0:
            values.append(curr_close / prev_close - 1.0)
    return values


def _volatility(rows: list[dict], days: int) -> float:
    values = _daily_returns(rows, days)
    if len(values) < 2:
        return 0.0
    return pstdev(values)


def _drawdown(rows: list[dict], days: int) -> float:
    if len(rows) < days:
        return 0.0
    window = rows[-days:]
    high = max(float(row.get("close") or 0.0) for row in window)
    close = _last_close(rows)
    if high <= 0 or close <= 0:
        return 0.0
    return max(0.0, (high - close) / high)
