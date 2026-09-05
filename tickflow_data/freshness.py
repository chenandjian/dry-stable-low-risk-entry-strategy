"""Read-only TickFlow freshness diagnostics for one stock and broad indexes."""
from __future__ import annotations

import datetime as dt
import time

from scanner import db

from .client import (
    AUTHENTICATED_ACCESS_MODE,
    TickFlowBatchClient,
    resolve_tickflow_access_mode,
)
from .indexes import MARKET_INDEX_SPECS
from .normalize import normalize_frame
from .symbols import to_tickflow_symbol


def _stock_name(code: str) -> str:
    for stock in db.get_stock_pool():
        if str(stock.get("code") or "") == code:
            return str(stock.get("name") or code)
    return code


def _local_stock_date(code: str) -> str | None:
    return (db.get_ohlc_metadata(code) or {}).get("latest_date")


def _local_index_date(symbol: str) -> str | None:
    return db.get_market_index_coverage(symbol).get("max_date")


def _result_item(
    *,
    symbol: str,
    code: str,
    name: str,
    target_trade_date: str,
    local_latest_date: str | None,
    frame=None,
    elapsed_ms: int = 0,
    error: str | None = None,
) -> dict:
    remote_latest_date = None
    row_count = 0
    if error is None:
        try:
            rows = normalize_frame(frame)
            row_count = len(rows)
            remote_latest_date = rows[-1]["date"]
        except Exception as exc:
            error = str(exc)

    if error is not None:
        status = "FAILED"
    elif remote_latest_date == target_trade_date:
        status = "FRESH"
    else:
        status = "STALE"

    return {
        "symbol": symbol,
        "code": code,
        "name": name,
        "remote_latest_date": remote_latest_date,
        "local_latest_date": local_latest_date,
        "target_trade_date": target_trade_date,
        "row_count": row_count,
        "elapsed_ms": elapsed_ms,
        "status": status,
        "error": error,
    }


def _overall_status(items: list[dict]) -> str:
    failed = sum(item["status"] == "FAILED" for item in items)
    if failed == len(items):
        return "FAILED"
    if failed:
        return "PARTIAL_FAILURE"
    if any(item["status"] == "STALE" for item in items):
        return "STALE"
    return "FRESH"


def check_tickflow_freshness(
    stock_code: str,
    *,
    target_trade_date: str,
    access_mode: str | None = None,
    api_key: str | None = None,
    client_factory=TickFlowBatchClient,
    count: int = 5,
) -> dict:
    """Probe remote dates without writing stock or index history."""
    stock_symbol = to_tickflow_symbol(stock_code)
    stock_name = _stock_name(stock_code)
    index_symbols = [spec.tickflow_symbol for spec in MARKET_INDEX_SPECS]
    checked_at = dt.datetime.now().isoformat(timespec="seconds")

    stock_item = None
    index_items: list[dict] = []
    try:
        resolved_access_mode = resolve_tickflow_access_mode(access_mode)
        client_context = client_factory(
            access_mode=resolved_access_mode,
            api_key=(api_key if resolved_access_mode == AUTHENTICATED_ACCESS_MODE else None),
        )
        with client_context as client:
            started = time.perf_counter()
            try:
                fetched_stock = client.fetch([stock_symbol], count=count)
                stock_elapsed = round((time.perf_counter() - started) * 1000)
                if (
                    stock_symbol in set(fetched_stock.missing_symbols)
                    or stock_symbol not in fetched_stock.frames
                ):
                    raise ValueError("TickFlow batch response omitted this stock")
                stock_item = _result_item(
                    symbol=stock_symbol,
                    code=stock_code,
                    name=stock_name,
                    target_trade_date=target_trade_date,
                    local_latest_date=_local_stock_date(stock_code),
                    frame=fetched_stock.frames[stock_symbol],
                    elapsed_ms=stock_elapsed,
                )
            except Exception as exc:
                stock_item = _result_item(
                    symbol=stock_symbol,
                    code=stock_code,
                    name=stock_name,
                    target_trade_date=target_trade_date,
                    local_latest_date=_local_stock_date(stock_code),
                    elapsed_ms=round((time.perf_counter() - started) * 1000),
                    error=str(exc),
                )

            started = time.perf_counter()
            try:
                fetched_indexes = client.fetch_indexes(index_symbols, count=count)
                index_elapsed = round((time.perf_counter() - started) * 1000)
                missing = set(fetched_indexes.missing_symbols)
                for spec in MARKET_INDEX_SPECS:
                    if spec.tickflow_symbol in missing or spec.tickflow_symbol not in fetched_indexes.frames:
                        error = "TickFlow batch response omitted this index"
                        frame = None
                    else:
                        error = None
                        frame = fetched_indexes.frames[spec.tickflow_symbol]
                    index_items.append(_result_item(
                        symbol=spec.tickflow_symbol,
                        code=spec.local_symbol,
                        name=spec.name,
                        target_trade_date=target_trade_date,
                        local_latest_date=_local_index_date(spec.local_symbol),
                        frame=frame,
                        elapsed_ms=index_elapsed,
                        error=error,
                    ))
            except Exception as exc:
                index_elapsed = round((time.perf_counter() - started) * 1000)
                for spec in MARKET_INDEX_SPECS:
                    index_items.append(_result_item(
                        symbol=spec.tickflow_symbol,
                        code=spec.local_symbol,
                        name=spec.name,
                        target_trade_date=target_trade_date,
                        local_latest_date=_local_index_date(spec.local_symbol),
                        elapsed_ms=index_elapsed,
                        error=str(exc),
                    ))
    except Exception as exc:
        error = str(exc)
        stock_item = _result_item(
            symbol=stock_symbol,
            code=stock_code,
            name=stock_name,
            target_trade_date=target_trade_date,
            local_latest_date=_local_stock_date(stock_code),
            error=error,
        )
        index_items = [
            _result_item(
                symbol=spec.tickflow_symbol,
                code=spec.local_symbol,
                name=spec.name,
                target_trade_date=target_trade_date,
                local_latest_date=_local_index_date(spec.local_symbol),
                error=error,
            )
            for spec in MARKET_INDEX_SPECS
        ]

    items = [stock_item, *index_items]
    return {
        "checked_at": checked_at,
        "target_trade_date": target_trade_date,
        "overall_status": _overall_status(items),
        "stock": stock_item,
        "indexes": index_items,
    }


__all__ = ["check_tickflow_freshness"]
