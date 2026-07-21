"""TickFlow-backed broad-market index history updates."""
from __future__ import annotations

from dataclasses import dataclass

from scanner import db

from .normalize import normalize_frame


@dataclass(frozen=True)
class MarketIndexSpec:
    local_symbol: str
    tickflow_symbol: str
    name: str


MARKET_INDEX_SPECS = (
    MarketIndexSpec("sh000001", "000001.SH", "上证指数"),
    MarketIndexSpec("sz399001", "399001.SZ", "深证成指"),
    MarketIndexSpec("sz399006", "399006.SZ", "创业板指"),
    MarketIndexSpec("hs300", "000300.SH", "沪深300"),
)


def update_market_indexes(client, *, history_days: int = 1100) -> list[dict]:
    """Fetch and atomically upsert all required unadjusted market indexes."""
    symbols = [item.tickflow_symbol for item in MARKET_INDEX_SPECS]
    by_symbol = {item.tickflow_symbol: item for item in MARKET_INDEX_SPECS}
    results = []
    try:
        with client as active_client:
            fetched = active_client.fetch_indexes(symbols, count=history_days)
    except Exception as exc:
        return [
            {
                "symbol": item.local_symbol,
                "name": item.name,
                "status": "failed",
                "error": str(exc),
                "row_count": 0,
            }
            for item in MARKET_INDEX_SPECS
        ]

    missing = set(fetched.missing_symbols)
    for symbol in symbols:
        spec = by_symbol[symbol]
        try:
            if symbol in missing or symbol not in fetched.frames:
                raise ValueError("TickFlow batch response omitted this index")
            rows = normalize_frame(fetched.frames[symbol])[-history_days:]
            db.upsert_market_index_ohlc(spec.local_symbol, rows, source="tickflow")
            results.append({
                "symbol": spec.local_symbol,
                "name": spec.name,
                "status": "success",
                "error": None,
                "row_count": len(rows),
                "first_date": rows[0]["date"],
                "latest_date": rows[-1]["date"],
            })
        except Exception as exc:
            results.append({
                "symbol": spec.local_symbol,
                "name": spec.name,
                "status": "failed",
                "error": str(exc),
                "row_count": 0,
            })
    return results


__all__ = ["MARKET_INDEX_SPECS", "MarketIndexSpec", "update_market_indexes"]
