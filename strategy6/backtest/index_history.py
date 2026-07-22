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

INDEX_STORAGE_ALIASES = {
    "sh000001": ("sh000001",),
    "sz399001": ("sz399001",),
    "sz399006": ("sz399006",),
    "hs300": ("hs300", "sh000300"),
}


@dataclass
class IndexHistoryResult:
    status: str
    data_by_symbol: dict[str, list[dict]] = field(default_factory=dict)
    missing_symbols: list[str] = field(default_factory=list)
    coverage: dict[str, dict] = field(default_factory=dict)


def load_index_history(start_date: str, end_date: str) -> IndexHistoryResult:
    data: dict[str, list[dict]] = {}
    coverage: dict[str, dict] = {}
    for logical_symbol in INDEX_SYMBOLS:
        stored_symbol, rows, info = _load_best_storage_alias(
            logical_symbol,
            start_date=start_date,
            end_date=end_date,
        )
        coverage[logical_symbol] = {**info, "stored_symbol": stored_symbol}
        data[logical_symbol] = rows
    return validate_index_history_data(
        data,
        start_date=start_date,
        end_date=end_date,
        base_coverage=coverage,
    )


def _load_best_storage_alias(
    logical_symbol: str,
    *,
    start_date: str,
    end_date: str,
) -> tuple[str, list[dict], dict]:
    candidates = []
    for stored_symbol in INDEX_STORAGE_ALIASES[logical_symbol]:
        info = db.get_market_index_coverage(stored_symbol)
        rows = db.get_market_index_ohlc(stored_symbol, end_date=end_date)
        dates = [str(row.get("date") or "") for row in rows if row.get("date")]
        covers_range = bool(
            dates and dates[0] <= start_date and dates[-1] >= end_date
        )
        candidates.append((covers_range, len(rows), stored_symbol, rows, info))
    _, _, stored_symbol, rows, info = max(
        candidates,
        key=lambda item: (item[0], item[1]),
    )
    return stored_symbol, rows, info


def validate_index_history_data(
    data_by_symbol: dict[str, list[dict]],
    *,
    start_date: str,
    end_date: str,
    base_coverage: dict[str, dict] | None = None,
    reference_dates: list[str] | tuple[str, ...] | None = None,
) -> IndexHistoryResult:
    """Validate the four real broad indexes without reading or fetching data."""
    data = {
        logical_symbol: list(
            data_by_symbol.get(logical_symbol)
            or data_by_symbol.get(stored_symbol)
            or []
        )
        for logical_symbol, stored_symbol in INDEX_SYMBOLS.items()
    }
    missing: list[str] = []
    coverage: dict[str, dict] = {}
    expected_dates = {
        str(row.get("date") or "")
        for rows in data.values()
        for row in rows
        if start_date <= str(row.get("date") or "") <= end_date
    }
    expected_dates.update(
        str(value)
        for value in (reference_dates or [])
        if start_date <= str(value) <= end_date
    )
    for logical_symbol, rows in data.items():
        dates = sorted(
            str(row.get("date") or "")
            for row in rows
            if row.get("date")
        )
        actual_dates = {
            str(row.get("date") or "")
            for row in rows
            if start_date <= str(row.get("date") or "") <= end_date
        }
        missing_dates = sorted(expected_dates - actual_dates)
        coverage[logical_symbol] = {
            **((base_coverage or {}).get(logical_symbol) or {}),
            "min_date": dates[0] if dates else "",
            "max_date": dates[-1] if dates else "",
            "rows_count": len(rows),
            "missing_dates": missing_dates,
        }
        if (
            not dates
            or dates[0] > start_date
            or dates[-1] < end_date
            or missing_dates
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
            db.upsert_market_index_ohlc(stored_symbol, rows, source="sina")
    return load_index_history(start_date, end_date)
