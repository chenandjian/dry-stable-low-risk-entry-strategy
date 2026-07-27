"""Shared configuration and scan preparation for market-data providers."""
from __future__ import annotations

from datetime import datetime

from scanner import db
from scanner.daily_data_service import (
    FetchResult,
    build_cache_freshness_context,
    trim_ohlc_to_target,
)

TICKFLOW_MODE = "tickflow"
LEGACY_MULTI_SOURCE_MODE = "legacy_multi_source"
SUPPORTED_ACQUISITION_MODES = {TICKFLOW_MODE, LEGACY_MULTI_SOURCE_MODE}


def resolve_acquisition_mode(config: dict) -> str:
    """Resolve the explicit provider mode while keeping old configs compatible."""
    data_config = config.get("data", {}) if isinstance(config, dict) else {}
    mode = data_config.get("acquisition_mode", LEGACY_MULTI_SOURCE_MODE)
    if mode not in SUPPORTED_ACQUISITION_MODES:
        allowed = ", ".join(sorted(SUPPORTED_ACQUISITION_MODES))
        raise ValueError(f"data.acquisition_mode must be one of: {allowed}")
    return mode


class PreparedTickFlowSession:
    """Expose one task's batch result through the scanners' fetch contract."""

    def __init__(self, *, target_trade_date: str, failures: dict[str, str]):
        self.target_trade_date = target_trade_date
        self.failures = failures

    def fetch(self, code: str, *_args, kline_days: int = 250, **_kwargs) -> FetchResult:
        error = self.failures.get(code)
        if error:
            return FetchResult(
                data=None,
                primary_source=TICKFLOW_MODE,
                fallback_source=TICKFLOW_MODE,
                primary_attempts=1,
                fallback_attempts=1,
                primary_error=error,
                fallback_error=error,
                source_errors={TICKFLOW_MODE: f"attempts=1 error={error}"},
                kline_target_trade_date=self.target_trade_date,
            )

        rows = trim_ohlc_to_target(db.get_ohlc(code) or [], self.target_trade_date)
        metadata = db.get_ohlc_metadata(code) or {}
        if not rows or metadata.get("source") != TICKFLOW_MODE:
            error = "TickFlow prepared cache is unavailable"
            return FetchResult(
                data=None,
                primary_source=TICKFLOW_MODE,
                fallback_source=TICKFLOW_MODE,
                primary_attempts=1,
                fallback_attempts=1,
                primary_error=error,
                fallback_error=error,
                source_errors={TICKFLOW_MODE: f"attempts=1 error={error}"},
                kline_target_trade_date=self.target_trade_date,
            )
        selected = rows[-kline_days:] if kline_days else rows
        quote_status = (
            "suspended" if selected[-1]["date"] < self.target_trade_date else "not_requested"
        )
        return FetchResult(
            data=selected,
            primary_source=TICKFLOW_MODE,
            fallback_source=TICKFLOW_MODE,
            primary_attempts=1,
            fallback_attempts=1,
            from_cache=True,
            kline_fetched_at=metadata.get("fetched_at"),
            kline_target_trade_date=self.target_trade_date,
            quote_status=quote_status,
        )


def _tickflow_stock_cache_is_fresh(code: str, *, target_date: str, min_fetch_time: str) -> bool:
    metadata = db.get_ohlc_metadata(code) or {}
    latest_date = str(metadata.get("latest_date") or "")
    return bool(
        latest_date
        and metadata.get("source") == TICKFLOW_MODE
        and str(metadata.get("fetched_at") or "") >= min_fetch_time
        and latest_date == target_date
    )


def _tickflow_target_date_is_available(target_date: str) -> bool:
    row = db.get_conn().execute(
        """SELECT 1 FROM daily_ohlc_metadata
           WHERE source=? AND latest_date=? LIMIT 1""",
        (TICKFLOW_MODE, target_date),
    ).fetchone()
    return row is not None


def _target_date_unavailable_error(code: str, target_date: str) -> str:
    metadata = db.get_ohlc_metadata(code) or {}
    remote_latest = metadata.get("latest_date") or "none"
    return (
        "TARGET_TRADE_DATE_UNAVAILABLE: "
        f"target={target_date} remote_latest={remote_latest}"
    )


def _tickflow_indexes_are_fresh(*, target_date: str, min_fetch_time: str) -> bool:
    from tickflow_data.indexes import MARKET_INDEX_SPECS

    conn = db.get_conn()
    for spec in MARKET_INDEX_SPECS:
        row = conn.execute(
            """SELECT date, fetched_at, source FROM market_index_ohlc
               WHERE symbol=? ORDER BY date DESC LIMIT 1""",
            (spec.local_symbol,),
        ).fetchone()
        if not row or row[0] != target_date or str(row[1] or "") < min_fetch_time:
            return False
        if row[2] != TICKFLOW_MODE:
            return False
    return True


def prepare_scan_daily_data(
    config: dict,
    stocks: list[dict],
    *,
    now: str | datetime | None = None,
    client_factory=None,
    progress_callback=None,
) -> PreparedTickFlowSession | None:
    """Batch-refresh TickFlow data once before a scan, or keep legacy behavior."""
    if resolve_acquisition_mode(config) == LEGACY_MULTI_SOURCE_MODE:
        return None

    from tickflow_data.client import (
        AUTHENTICATED_ACCESS_MODE,
        TickFlowBatchClient,
        resolve_tickflow_access_mode,
    )
    from tickflow_data.indexes import update_market_indexes
    from tickflow_data.service import TickFlowDailyUpdateService

    if isinstance(now, str):
        current = datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
    else:
        current = now or datetime.now()
    freshness = build_cache_freshness_context(now=current)
    target_date = freshness.target_trade_date
    min_fetch_time = freshness.min_fetch_time or f"{target_date} 15:00:00"
    stale_stocks = [
        stock for stock in stocks
        if not _tickflow_stock_cache_is_fresh(
            str(stock.get("code", "")),
            target_date=target_date,
            min_fetch_time=min_fetch_time,
        )
    ]
    indexes_fresh = _tickflow_indexes_are_fresh(
        target_date=target_date,
        min_fetch_time=min_fetch_time,
    )
    failures: dict[str, str] = {}
    if stale_stocks or not indexes_fresh:
        factory = client_factory or TickFlowBatchClient
        data_config = config.get("data", {})
        access_mode = resolve_tickflow_access_mode(
            data_config.get("tickflow_access_mode")
        )
        client = factory(
            access_mode=access_mode,
            api_key=(
                data_config.get("tickflow_api_key")
                if access_mode == AUTHENTICATED_ACCESS_MODE
                else None
            ),
            batch_size=100,
            max_workers=5,
        )
        if stale_stocks:
            stock_names = {
                str(stock.get("code", "")): str(stock.get("name", ""))
                for stock in stale_stocks
            }
            data_processed = 0
            if progress_callback:
                progress_callback(
                    "data_acquisition",
                    0,
                    len(stale_stocks),
                    "-- TickFlow批量行情准备中",
                )

            def report_data_progress(item) -> None:
                nonlocal data_processed
                data_processed += 1
                if progress_callback:
                    name = stock_names.get(item.code, "")
                    progress_callback(
                        "data_acquisition",
                        data_processed,
                        len(stale_stocks),
                        f"{item.code} {name}".strip(),
                    )

            history_days = max(
                1100,
                int(config.get("liquidity", {}).get("min_listing_days") or 0),
                int(config.get("strategy5", {}).get("kline_days") or 0),
                int(config.get("strategy6", {}).get("kline_days") or 0),
            )
            service = TickFlowDailyUpdateService(
                client,
                history_days=history_days,
                overlap_days=10,
                request_chunk_size=100,
            )
            try:
                result = service.run(
                    stale_stocks,
                    dry_run=False,
                    mode="update",
                    on_result=report_data_progress,
                )
            except Exception as exc:
                failures.update({
                    str(stock.get("code", "")): f"TickFlow preparation failed: {exc}"
                    for stock in stale_stocks
                })
                if progress_callback and data_processed < len(stale_stocks):
                    progress_callback(
                        "data_acquisition",
                        len(stale_stocks),
                        len(stale_stocks),
                        "-- TickFlow批量行情拉取失败",
                    )
            else:
                failures.update({
                    item.code: item.error or item.status
                    for item in result.results
                    if item.status != "success"
                })
                if not _tickflow_target_date_is_available(target_date):
                    for stock in stale_stocks:
                        code = str(stock.get("code", ""))
                        metadata = db.get_ohlc_metadata(code) or {}
                        if metadata.get("latest_date") != target_date:
                            failures.setdefault(
                                code,
                                _target_date_unavailable_error(code, target_date),
                            )
        if not indexes_fresh:
            from tickflow_data.indexes import MARKET_INDEX_SPECS

            if progress_callback:
                progress_callback(
                    "index_acquisition",
                    0,
                    len(MARKET_INDEX_SPECS),
                    "-- TickFlow宽基指数准备中",
                )
            index_results = update_market_indexes(client, history_days=1100)
            if progress_callback:
                for current_index, item in enumerate(index_results, start=1):
                    progress_callback(
                        "index_acquisition",
                        current_index,
                        len(MARKET_INDEX_SPECS),
                        f"-- {item.get('name') or item.get('symbol') or '宽基指数'}",
                    )

    return PreparedTickFlowSession(
        target_trade_date=target_date,
        failures=failures,
    )


def load_market_index_daily(
    config: dict,
    symbol: str,
    *,
    days: int = 250,
    legacy_fetch_fn=None,
    now: str | datetime | None = None,
) -> list[dict]:
    """Load an index through the selected provider without cross-mode fallback."""
    if resolve_acquisition_mode(config) == TICKFLOW_MODE:
        local_symbol = "hs300" if symbol in {"sh000300", "sz399300", "hs300"} else symbol
        if isinstance(now, str):
            current = datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
        else:
            current = now or datetime.now()
        freshness = build_cache_freshness_context(now=current)
        latest = db.get_conn().execute(
            """SELECT date, source, fetched_at FROM market_index_ohlc
               WHERE symbol=? ORDER BY date DESC LIMIT 1""",
            (local_symbol,),
        ).fetchone()
        if not latest:
            return []
        if (
            latest[0] != freshness.target_trade_date
            or latest[1] != TICKFLOW_MODE
            or str(latest[2] or "") < str(freshness.min_fetch_time or "")
        ):
            return []
        return db.get_market_index_ohlc(local_symbol, max_rows=days)

    if legacy_fetch_fn is None:
        from scanner.index_source import fetch_market_index_daily as legacy_fetch_fn

    try:
        rows = legacy_fetch_fn(symbol, days=days) or []
    except TypeError:
        rows = legacy_fetch_fn(symbol) or []
    if rows:
        db.upsert_market_index_ohlc(symbol, rows, source="sina")
    return rows


__all__ = [
    "LEGACY_MULTI_SOURCE_MODE",
    "TICKFLOW_MODE",
    "PreparedTickFlowSession",
    "prepare_scan_daily_data",
    "load_market_index_daily",
    "resolve_acquisition_mode",
]
