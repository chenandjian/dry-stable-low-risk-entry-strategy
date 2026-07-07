"""Strategy5 scan orchestration."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from queue import Queue

import scanner.db as db
from scanner.daily_data_service import (
    DEFAULT_DAILY_SOURCES,
    FetchResult,
    build_cache_freshness_context,
    encode_source_errors,
    fetch_with_retry,
    is_transient_source_busy,
    resolve_effective_worker_count,
)
from scanner.data_source import DataSourceManager
from strategy5.engine import ShortSprintSupportEngine
from strategy5.validation import resolve_strategy5_config

logger = logging.getLogger(__name__)

STRATEGY5_TYPE = "STRATEGY_5_SHORT_SPRINT_SUPPORT"


def scan_strategy5_all(
    config: dict,
    progress_callback=None,
    task_id: str | None = None,
    stocks: list[dict] | None = None,
    worker_count: int = 4,
    retry_policy: str = "normal",
    fetch_daily_fn=None,
) -> dict:
    """Run Strategy5 full-market scan using the existing daily data service."""
    from scanner.stock_pool import get_a_stock_pool

    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    cfg = resolve_strategy5_config(config)
    task_id = task_id or time.strftime("s5-%Y%m%d-%H%M%S")
    _ensure_scan_task(task_id)

    if stocks is None:
        stocks = get_a_stock_pool(config)
    db.save_task_stocks(task_id, stocks)

    daily_sources = config.get("data", {}).get("daily_sources") or DEFAULT_DAILY_SOURCES
    kline_days = int(cfg["kline_days"])
    configured_workers = config.get("data", {}).get("worker_count")
    worker_count = resolve_effective_worker_count(
        configured_workers if configured_workers is not None else worker_count,
        daily_sources,
    )
    max_busy_retries = config.get("data", {}).get("source_busy_max_retries", 3)

    stock_queue: Queue = Queue()
    for stock in stocks:
        stock_queue.put(stock)

    mgr = DataSourceManager()
    engine = ShortSprintSupportEngine({"strategy5": cfg})
    candidate_by_code: dict[str, dict] = {}
    candidate_lock = threading.Lock()
    busy_retries_by_code: dict[str, int] = {}
    busy_retry_lock = threading.Lock()
    start_time = time.time()

    def _cache_freshness_context(code: str):
        now = datetime.strptime(_now(), "%Y-%m-%d %H:%M:%S")
        context = build_cache_freshness_context(now=now)
        prior = db.get_reusable_task_stock_kline_context(
            code,
            context.target_trade_date,
            context.min_fetch_time,
            exclude_task_id=task_id,
        )
        if prior:
            context.fetched_at = prior.get("kline_fetched_at")
            context.quote_status = prior.get("quote_status")
            context.allow_previous_trade_date = context.quote_status in {"suspended", "no_trade"}
        return context

    def _finish_stock(
        code: str,
        name: str,
        status: str,
        status_reason: str | None = None,
        error_detail: str | None = None,
        kline_latest_date: str | None = None,
        fetch_result: FetchResult | None = None,
    ) -> None:
        source_fields = {}
        if fetch_result is not None:
            source_fields = {
                "primary_source": fetch_result.primary_source,
                "fallback_source": fetch_result.fallback_source,
                "primary_attempts": fetch_result.primary_attempts,
                "fallback_attempts": fetch_result.fallback_attempts,
                "primary_error": fetch_result.primary_error,
                "fallback_error": fetch_result.fallback_error,
                "source_errors": encode_source_errors(fetch_result.source_errors),
                "kline_fetched_at": fetch_result.kline_fetched_at,
                "kline_target_trade_date": fetch_result.kline_target_trade_date,
                "quote_status": fetch_result.quote_status,
            }
        db.update_task_stock(
            task_id,
            code,
            status=status,
            status_reason=status_reason,
            error_detail=error_detail,
            kline_latest_date=kline_latest_date,
            finished_at=_now(),
            **source_fields,
        )
        summary = db.refresh_scan_task_counts(task_id)
        if progress_callback:
            progress_callback("scanning", summary["processed"], summary["total_stocks"], f"{code} {name}")

    def worker():
        while not stock_queue.empty():
            try:
                stock = stock_queue.get_nowait()
            except Exception:
                break

            code = stock["code"]
            name = stock.get("name", "")
            fetch_result: FetchResult | None = None
            try:
                freshness_context = _cache_freshness_context(code)
                db.update_task_stock(
                    task_id,
                    code,
                    status="fetching",
                    primary_source=daily_sources[0],
                    fallback_source=daily_sources[-1],
                    started_at=_now(),
                )
                attempts = 3 if retry_policy == "failed_only" else 2
                fetcher = fetch_daily_fn or fetch_with_retry
                fetch_result = fetcher(
                    code,
                    primary_ds=daily_sources[0],
                    retry_attempts=attempts,
                    fallback_attempts=attempts,
                    mgr=mgr,
                    source_chain=daily_sources,
                    kline_days=kline_days,
                    freshness_context=freshness_context,
                )
                if not isinstance(fetch_result, FetchResult):
                    fetch_result = FetchResult(data=fetch_result, primary_source="custom", fallback_source="custom")

                data = fetch_result.data
                if data is None:
                    if is_transient_source_busy(fetch_result):
                        with busy_retry_lock:
                            count = busy_retries_by_code.get(code, 0) + 1
                            busy_retries_by_code[code] = count
                        if count <= max_busy_retries:
                            stock_queue.put(stock)
                            time.sleep(0.1)
                            continue
                        _finish_stock(code, name, "failed", "SOURCE_BUSY_RETRY_EXCEEDED", fetch_result=fetch_result)
                    else:
                        _finish_stock(code, name, "failed", "ALL_DATA_SOURCES_FAILED", fetch_result=fetch_result)
                    with busy_retry_lock:
                        busy_retries_by_code.pop(code, None)
                    continue

                latest_trade_date = data[-1].get("date") if data else None
                if not fetch_result.kline_fetched_at:
                    fetch_result.kline_fetched_at = _now()
                if not fetch_result.kline_target_trade_date:
                    fetch_result.kline_target_trade_date = freshness_context.target_trade_date

                suspended_reason = (
                    "SUSPENDED_OR_NO_TRADE_ON_TARGET_DATE"
                    if fetch_result.quote_status == "suspended"
                    else None
                )
                evaluation = engine.evaluate_at(
                    data,
                    code=code,
                    name=name,
                    data_source=fetch_result.primary_source,
                    kline_fetched_at=fetch_result.kline_fetched_at or "",
                    quote_status=fetch_result.quote_status or "",
                )
                if evaluation.passed:
                    discovery = evaluation.to_candidate_dict()
                    db.upsert_strategy5_candidate(task_id, discovery)
                    with candidate_lock:
                        candidate_by_code[code] = discovery
                    _finish_stock(
                        code,
                        name,
                        "candidate",
                        status_reason=suspended_reason,
                        kline_latest_date=latest_trade_date,
                        fetch_result=fetch_result,
                    )
                    if progress_callback:
                        progress_callback("discovery", len(candidate_by_code), len(stocks), f"{code} {name}", discovery)
                else:
                    _finish_stock(
                        code,
                        name,
                        "scanned",
                        status_reason=suspended_reason or evaluation.status_reason,
                        error_detail=";".join(evaluation.reject_reasons),
                        kline_latest_date=latest_trade_date,
                        fetch_result=fetch_result,
                    )
                with busy_retry_lock:
                    busy_retries_by_code.pop(code, None)
            except Exception as exc:
                logger.exception("Strategy5 error scanning %s: %s", code, exc)
                _finish_stock(
                    code,
                    name,
                    "failed",
                    status_reason="STRATEGY5_EVALUATION_ERROR",
                    error_detail=str(exc),
                    fetch_result=fetch_result,
                )
                with busy_retry_lock:
                    busy_retries_by_code.pop(code, None)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, worker_count))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    elapsed = time.time() - start_time
    summary = db.refresh_scan_task_counts(task_id)
    candidates = list(candidate_by_code.values())
    return {
        "candidates": candidates,
        "stats": {
            "total": summary["total_stocks"],
            "total_stocks": summary["total_stocks"],
            "scanned": summary["processed"],
            "processed": summary["processed"],
            "skipped": summary["skipped"],
            "failed": summary["failed"],
            "candidates_found": len(candidates),
            "latest_trade_date": summary.get("latest_trade_date"),
            "elapsed_seconds": round(elapsed, 1),
            "speed": round(summary["processed"] / elapsed, 1) if elapsed > 0 else 0,
        },
        "task_id": task_id,
    }


def _ensure_scan_task(task_id: str) -> None:
    if db.get_scan_task(task_id):
        return
    db.create_scan_task(
        task_id,
        _now(),
        total_stocks=0,
        retry_mode="full",
        strategy_type=STRATEGY5_TYPE,
    )


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")
