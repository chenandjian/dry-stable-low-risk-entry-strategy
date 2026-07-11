"""Approved real-index history acquisition and coverage checks."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from scanner import db
from scanner.index_source import fetch_market_index_daily


INDEX_SYMBOLS = {
    "sh000001": "sh000001",
    "sz399001": "sz399001",
    "sz399006": "sz399006",
    "hs300": "sh000300",
}


@dataclass
class IndexHistoryResult:
    status: str
    data_by_symbol: dict[str, list[dict]] = field(default_factory=dict)
    missing_symbols: list[str] = field(default_factory=list)
    coverage: dict[str, dict] = field(default_factory=dict)


def load_index_history(start_date: str, end_date: str) -> IndexHistoryResult:
    data: dict[str, list[dict]] = {}
    missing: list[str] = []
    coverage: dict[str, dict] = {}
    for logical_symbol, stored_symbol in INDEX_SYMBOLS.items():
        info = db.get_market_index_coverage(stored_symbol)
        coverage[logical_symbol] = info
        rows = db.get_market_index_ohlc(stored_symbol, end_date=end_date)
        data[logical_symbol] = rows
        if (
            not rows
            or str(info.get("min_date") or "") > start_date
            or str(info.get("max_date") or "") < end_date
        ):
            missing.append(logical_symbol)
    return IndexHistoryResult(
        status="READY" if not missing else "BLOCKED_INDEX_HISTORY",
        data_by_symbol=data,
        missing_symbols=missing,
        coverage=coverage,
    )


def ensure_index_history(
    start_date: str,
    end_date: str,
    *,
    days: int = 1500,
    fetcher: Callable[[str, int], list[dict] | None] = fetch_market_index_daily,
) -> IndexHistoryResult:
    for stored_symbol in INDEX_SYMBOLS.values():
        rows = fetcher(stored_symbol, days) or []
        if rows:
            db.save_market_index_ohlc(stored_symbol, rows, source="sina")
    return load_index_history(start_date, end_date)
