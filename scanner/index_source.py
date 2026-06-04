"""Index OHLC data source for market environment analysis."""

import logging

from scanner.sina_source import fetch_sina_daily

logger = logging.getLogger(__name__)

DEFAULT_MARKET_INDEX = "000001"


def fetch_market_index_daily(code: str = DEFAULT_MARKET_INDEX) -> list[dict] | None:
    """Fetch market index daily OHLC data.

    The current implementation reuses the existing Sina daily fetcher. If the
    upstream index symbol format differs or data is unavailable, callers get
    None and the market filter defaults to "一般".
    """
    try:
        data = fetch_sina_daily(code)
    except Exception as exc:
        logger.warning("Market index fetch failed for %s: %s", code, exc)
        return None
    if not data:
        return None
    return normalize_index_ohlc(data)


def normalize_index_ohlc(raw: list[dict]) -> list[dict]:
    """Normalize index OHLC rows to the analyzer's expected schema."""
    normalized = []
    for d in raw or []:
        if not all(k in d for k in ("date", "open", "high", "low", "close")):
            continue
        normalized.append({
            "date": d["date"],
            "open": float(d["open"]),
            "high": float(d["high"]),
            "low": float(d["low"]),
            "close": float(d["close"]),
            "volume": float(d.get("volume", 0) or 0),
        })
    return sorted(normalized, key=lambda x: x["date"])
