"""Strategy6 scan orchestration."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from queue import Queue

import scanner.db as db
from scanner.index_source import fetch_market_index_daily
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
from strategy6 import STRATEGY6_TYPE
from strategy6.engine import StrongVcpTailEngine
from strategy6.indicators import calculate_indicators
from strategy6.sector import evaluate_sector_context
from strategy6.validation import resolve_strategy6_config

logger = logging.getLogger(__name__)


def scan_strategy6_all(
    config: dict,
    progress_callback=None,
    task_id: str | None = None,
    stocks: list[dict] | None = None,
    worker_count: int = 4,
    retry_policy: str = "normal",
    fetch_daily_fn=None,
) -> dict:
    """Run Strategy6 full-market scan using shared daily data service."""
    from scanner.stock_pool import get_a_stock_pool

    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    cfg = resolve_strategy6_config(config)
    task_id = task_id or time.strftime("s6-%Y%m%d-%H%M%S")
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
    engine = StrongVcpTailEngine({"strategy6": cfg})
    market_data_by_symbol = _load_market_data_by_symbol(cfg)
    sector_cache: dict[tuple[str, str], dict] = {}
    sector_cache_lock = threading.Lock()
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
            sector_name = stock.get("sector_name") or stock.get("sector") or ""
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

                evaluation = engine.evaluate_at(
                    data,
                    code=code,
                    name=name,
                    sector_name=sector_name,
                    data_source=fetch_result.primary_source,
                    kline_fetched_at=fetch_result.kline_fetched_at or "",
                    quote_status=fetch_result.quote_status or "",
                    market_data_by_symbol=market_data_by_symbol,
                    sector_context=_load_sector_context(code, data, cfg, sector_cache, sector_cache_lock),
                )
                if evaluation.passed:
                    discovery = evaluation.to_candidate_dict()
                    db.upsert_strategy6_candidate(task_id, discovery)
                    with candidate_lock:
                        candidate_by_code[code] = discovery
                    _finish_stock(code, name, "candidate", kline_latest_date=latest_trade_date, fetch_result=fetch_result)
                    if progress_callback:
                        progress_callback("discovery", len(candidate_by_code), len(stocks), f"{code} {name}", discovery)
                else:
                    _finish_stock(
                        code,
                        name,
                        "scanned",
                        status_reason=evaluation.reject_reasons[0] if evaluation.reject_reasons else "REJECTED",
                        error_detail=";".join(evaluation.reject_reasons),
                        kline_latest_date=latest_trade_date,
                        fetch_result=fetch_result,
                    )
                with busy_retry_lock:
                    busy_retries_by_code.pop(code, None)
            except Exception as exc:
                logger.exception("Strategy6 error scanning %s: %s", code, exc)
                _finish_stock(
                    code,
                    name,
                    "failed",
                    status_reason="STRATEGY6_EVALUATION_ERROR",
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
        strategy_type=STRATEGY6_TYPE,
    )


def _load_market_data_by_symbol(cfg: dict) -> dict[str, list[dict]]:
    if not cfg.get("enable_market_filter"):
        return {}
    result: dict[str, list[dict]] = {}
    for symbol in ("sh000001", "sz399001", "sz399006", "hs300"):
        fetch_symbol = "sh000300" if symbol == "hs300" else symbol
        try:
            rows = fetch_market_index_daily(fetch_symbol, days=250) or []
        except Exception as exc:
            logger.warning("Strategy6 market index fetch failed for %s: %s", fetch_symbol, exc)
            rows = []
        result[symbol] = rows
    return result


def _load_sector_context(
    code: str,
    data: list[dict],
    cfg: dict,
    cache: dict[tuple[str, str], dict],
    cache_lock: threading.Lock,
) -> dict:
    if not cfg.get("enable_sector_filter"):
        return {}
    try:
        _, indicators = calculate_indicators(data, cfg)
        evaluation_date = indicators.evaluation_date
        cache_key = (code, evaluation_date)
        with cache_lock:
            if cache_key in cache:
                return dict(cache[cache_key])
        context = _derive_sector_context(code, indicators.return_10, evaluation_date, cfg)
        with cache_lock:
            cache[cache_key] = dict(context)
        return context
    except Exception as exc:
        logger.warning("Strategy6 sector context failed for %s: %s", code, exc)
        return {}


def _derive_sector_context(code: str, stock_return_10: float, evaluation_date: str, cfg: dict) -> dict:
    topics = db.get_strategy4_topics_for_member(code, evaluation_date=evaluation_date)
    best_context: dict | None = None
    best_score = -999.0
    for topic in topics:
        topic_id = str(topic.get("topic_id") or "")
        rows = db.get_strategy4_topic_index_ohlc(topic_id, end_date=evaluation_date, max_rows=80)
        members = db.get_strategy4_topic_members(topic_id, evaluation_date=evaluation_date)
        member_new_high_count = _count_recent_member_new_highs(members, evaluation_date)
        context = evaluate_sector_context(
            stock_return_10,
            rows,
            member_new_high_count=member_new_high_count,
            min_member_new_high_count=int(cfg.get("sector_min_member_new_high_count", 3)),
        )
        score = float(context.get("sector_return_10") or 0.0) + float(context.get("sector_return_20") or 0.0)
        if context.get("sector_strength_status") == "SECTOR_STRONG":
            score += 1.0
        if score > best_score:
            best_score = score
            best_context = {
                **context,
                "sector_topic_id": topic_id,
                "sector_topic_name": topic.get("topic_name", ""),
                "sector_membership_mode": topic.get("membership_mode", ""),
            }
    return best_context or {}


def _count_recent_member_new_highs(members: list[dict], evaluation_date: str) -> int:
    count = 0
    for member in members:
        code = str(member.get("code") or "")
        if not code:
            continue
        rows = db.get_ohlc(code, max_rows=40) or []
        rows = [row for row in rows if str(row.get("date") or "") <= evaluation_date]
        if _has_recent_20d_close_high(rows):
            count += 1
    return count


def _has_recent_20d_close_high(rows: list[dict]) -> bool:
    if len(rows) < 20:
        return False
    start = max(0, len(rows) - 5)
    for idx in range(start, len(rows)):
        lookback = rows[max(0, idx - 19):idx + 1]
        if len(lookback) < 20:
            continue
        close = float(rows[idx].get("close") or 0.0)
        prior_high = max(float(row.get("close") or 0.0) for row in lookback[:-1])
        if close > prior_high:
            return True
    return False


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")
