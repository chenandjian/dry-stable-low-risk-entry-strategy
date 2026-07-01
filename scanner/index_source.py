"""Index OHLC data source for market environment analysis."""

import logging
import json
import requests

logger = logging.getLogger(__name__)

DEFAULT_MARKET_INDEX = "sh000001"  # 上证指数


def _fetch_sina_index_raw(symbol: str, days: int = 250) -> list[dict] | None:
    """Dedicated index fetcher — uses Sina symbol directly without stock code mapping.

    Symbol format: sh000001 (上证指数), sz399001 (深证成指), etc.
    """
    url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/data/CN_MarketDataService.getKLineData"
    params = {"symbol": symbol, "scale": "240", "datalen": str(days)}
    try:
        resp = requests.get(url, params=params, timeout=10, headers={
            "Referer": "https://finance.sina.com.cn",
        })
        resp.raise_for_status()
        text = resp.text
        marker = "data("
        if marker in text:
            start = text.index(marker) + len(marker)
            end = text.rfind(");")
            if end < start:
                end = text.rfind(")")
            text = text[start:end]
        elif "(" in text:
            start = text.index("(") + 1
            end = text.rindex(")")
            text = text[start:end]
        data = json.loads(text)
        if not data or not isinstance(data, list):
            return None
        return data
    except Exception as exc:
        logger.warning("Index fetch failed for %s: %s", symbol, exc)
        return None


def fetch_market_index_daily(symbol: str | None = None, days: int = 250) -> list[dict] | None:
    """Fetch market index daily OHLC data.

    Uses dedicated index API (not the stock-oriented fetch_sina_daily),
    so the symbol is passed directly to Sina without stock code mapping.

    Args:
        symbol: Sina index symbol, e.g. "sh000001".  Defaults to 上证指数.
        days: Number of daily index rows to request.
    """
    if symbol is None:
        symbol = DEFAULT_MARKET_INDEX
    data = _fetch_sina_index_raw(symbol, days=days)
    if not data:
        logger.warning("Market index data unavailable for %s, market filter defaults to 一般", symbol)
        return None
    return normalize_index_ohlc(data)


def normalize_index_ohlc(raw: list[dict]) -> list[dict]:
    """Normalize index OHLC rows to the analyzer's expected schema."""
    normalized = []
    for d in raw or []:
        date_value = d.get("date") or d.get("day")
        if not date_value or not all(k in d for k in ("open", "high", "low", "close")):
            continue
        normalized.append({
            "date": date_value,
            "open": float(d["open"]),
            "high": float(d["high"]),
            "low": float(d["low"]),
            "close": float(d["close"]),
            "volume": float(d.get("volume", 0) or 0),
        })
    return sorted(normalized, key=lambda x: x["date"])
