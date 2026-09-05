"""Strategy6 scan orchestration."""
from __future__ import annotations

import copy
import logging
import threading
import time
from datetime import datetime
from queue import Queue

import scanner.db as db
from scanner.data_acquisition import load_market_index_daily, prepare_scan_daily_data
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
from strategy6.indicators import normalize_rows
from strategy6.market import build_market_snapshot
from strategy6.validation import resolve_strategy6_config
from strategy6.vcp_history import evaluate_vcp_candidate_history
from strategy6.vcp_quality import evaluate_vcp_quality

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

    prepared_session = prepare_scan_daily_data(
        config,
        stocks,
        progress_callback=progress_callback,
    )
    if fetch_daily_fn is None and prepared_session is not None:
        fetch_daily_fn = prepared_session.fetch

    daily_sources = (
        ["tickflow"] if prepared_session is not None
        else config.get("data", {}).get("daily_sources") or DEFAULT_DAILY_SOURCES
    )
    if progress_callback:
        progress_callback("scanning", 0, len(stocks), "-- 策略6计算准备中")
    kline_days = int(cfg["kline_days"])
    configured_workers = config.get("data", {}).get("worker_count")
    requested_workers = configured_workers if configured_workers is not None else worker_count
    if prepared_session is not None:
        worker_count = max(1, min(int(requested_workers), len(stocks)))
    else:
        worker_count = resolve_effective_worker_count(requested_workers, daily_sources)
    max_busy_retries = config.get("data", {}).get("source_busy_max_retries", 3)

    stock_queue: Queue = Queue()
    for stock in stocks:
        stock_queue.put(stock)

    mgr = DataSourceManager()
    engine = StrongVcpTailEngine({"strategy6": cfg})
    market_data_by_symbol = _load_market_data_by_symbol(config)
    market_target_date = build_cache_freshness_context(
        now=datetime.strptime(_now(), "%Y-%m-%d %H:%M:%S")
    ).target_trade_date
    db.save_strategy6_market_snapshot(
        task_id,
        build_market_snapshot(
            market_data_by_symbol,
            expected_trade_date=market_target_date,
        ),
    )
    prior_vcp_states = db.get_latest_strategy6_vcp_states(exclude_task_id=task_id)
    candidate_by_code: dict[str, dict] = {}
    candidate_lock = threading.Lock()
    busy_retries_by_code: dict[str, int] = {}
    busy_retry_lock = threading.Lock()
    progress_lock = threading.Lock()
    processed_count = 0
    progress_sync_interval = 50
    market_slice_cache: dict[str, dict[str, list[dict]]] = {}
    market_slice_lock = threading.Lock()
    base_freshness_context = build_cache_freshness_context(
        now=datetime.strptime(_now(), "%Y-%m-%d %H:%M:%S")
    )
    start_time = time.time()

    def _cache_freshness_context(code: str):
        context = copy.copy(base_freshness_context)
        if prepared_session is not None:
            return context
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

    def _market_context(evaluation_date: str) -> dict[str, list[dict]]:
        with market_slice_lock:
            cached = market_slice_cache.get(evaluation_date)
            if cached is None:
                cached = _market_data_until(market_data_by_symbol, evaluation_date)
                market_slice_cache[evaluation_date] = cached
            return cached

    def _finish_stock(
        code: str,
        name: str,
        status: str,
        status_reason: str | None = None,
        error_detail: str | None = None,
        kline_latest_date: str | None = None,
        fetch_result: FetchResult | None = None,
    ) -> None:
        nonlocal processed_count
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
        with progress_lock:
            processed_count += 1
            current = processed_count
            if progress_callback:
                progress_callback("scanning", current, len(stocks), f"{code} {name}")
        if current % progress_sync_interval == 0 and current < len(stocks):
            db.refresh_scan_task_counts(task_id)

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
                    market_data_by_symbol=_market_context(latest_trade_date or ""),
                )
                observation = None
                vcp = evaluation.vcp_observation
                if vcp.eligible:
                    history = evaluate_vcp_candidate_history(
                        rows=data,
                        market_data_by_symbol=market_data_by_symbol,
                        strategy_config=cfg,
                        code=code,
                        name=name,
                        origin_start_date=vcp.origin_start_date,
                        evaluation_date=evaluation.indicators.evaluation_date,
                        pattern_start_date=vcp.pattern_start_date,
                    )
                    vcp.history_qualified = history.qualified
                    vcp.history_candidate_date = history.candidate_date
                    vcp.history_candidate_type = history.candidate_type
                    vcp.history_candidate_score = history.candidate_score
                    vcp.history_source = history.source
                    vcp.history_origin_start_date = history.origin_start_date
                    if vcp.history_qualified:
                        vcp.quality = evaluate_vcp_quality(normalize_rows(data), vcp)
                vcp_exit_audit = (
                    bool(prior_vcp_states.get(code, {}).get("vcp_observation_eligible"))
                    and bool(prior_vcp_states.get(code, {}).get("vcp_history_qualified"))
                    and (
                        vcp.lifecycle_status == "VCP_INVALID"
                        or "VCP_OBSERVATION_EXPIRED" in vcp.risk_tags
                        or (bool(vcp.origin_start_date) and "VCP_BASE_FILTER_FAILED" in vcp.risk_tags)
                    )
                )
                needs_observation = (vcp.eligible and vcp.history_qualified) or vcp_exit_audit
                evaluation_record = (
                    evaluation.to_candidate_dict()
                    if evaluation.passed or evaluation.strong_trend_squeeze.passed or needs_observation
                    else None
                )
                candidate = evaluation_record if evaluation.passed else None
                trend_squeeze_candidate = (
                    dict(evaluation_record)
                    if evaluation.strong_trend_squeeze.passed
                    else None
                )
                if candidate is not None and vcp_exit_audit:
                    candidate["vcp_exit_audit"] = True
                if needs_observation:
                    observation = dict(evaluation_record)
                    observation.update({
                        "candidate_type": "REJECTED",
                        "classification": "observation",
                        "first_pool_date": "",
                        "first_seen_date": "",
                        "last_seen_date": "",
                        "days_in_pool": 0,
                        "pool_age_trading_days": 0,
                        "vcp_exit_audit": vcp_exit_audit,
                    })
                lifecycle, discovery = db.persist_strategy6_evaluation(
                    task_id,
                    code=code,
                    name=name,
                    evaluation_date=evaluation.indicators.evaluation_date,
                    candidate_type=evaluation.candidate_type,
                    lifecycle_status=evaluation.lifecycle_status,
                    event_key=_strategy6_event_key(evaluation),
                    reject_reasons=evaluation.reject_reasons,
                    max_watch_days=int(cfg["max_watch_days"]),
                    expired_cooldown_days=int(cfg["expired_cooldown_days"]),
                    failed_cooldown_days=int(cfg["failed_cooldown_days"]),
                    candidate=candidate,
                    observation_candidate=observation,
                    trend_squeeze_candidate=trend_squeeze_candidate,
                    decision_profile=cfg["decision_profile"],
                )
                if lifecycle["blocked"] and evaluation.passed:
                    _finish_stock(
                        code,
                        name,
                        "scanned",
                        status_reason=lifecycle["lifecycle_status"],
                        error_detail=lifecycle["exit_reason"] or "LIFECYCLE_COOLDOWN",
                        kline_latest_date=latest_trade_date,
                        fetch_result=fetch_result,
                    )
                    with busy_retry_lock:
                        busy_retries_by_code.pop(code, None)
                    continue
                if evaluation.passed:
                    if discovery is None:
                        raise RuntimeError("Strategy6 candidate persistence returned no discovery")
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


def _load_market_data_by_symbol(config: dict) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for symbol in ("sh000001", "sz399001", "sz399006", "hs300"):
        fetch_symbol = "sh000300" if symbol == "hs300" else symbol
        try:
            rows = load_market_index_daily(
                config,
                fetch_symbol,
                days=250,
                legacy_fetch_fn=fetch_market_index_daily,
            ) or []
        except Exception as exc:
            logger.warning("Strategy6 market index fetch failed for %s: %s", fetch_symbol, exc)
            rows = []
        result[symbol] = rows
    return result


def _market_data_until(market_data_by_symbol: dict[str, list[dict]], evaluation_date: str) -> dict[str, list[dict]]:
    if not evaluation_date:
        return {}
    return {
        symbol: [row for row in rows if str(row.get("date") or "") <= evaluation_date]
        for symbol, rows in market_data_by_symbol.items()
    }


def _strategy6_event_key(evaluation) -> str:
    pattern = evaluation.pattern
    lifecycle_event = "BREAKOUT_CONFIRMED" if evaluation.lifecycle_status == "BREAKOUT_CONFIRMED" else ""
    return "|".join((
        evaluation.start.start_date,
        evaluation.start.start_type,
        pattern.pattern_type,
        pattern.pattern_start_date,
        str(pattern.contraction_count),
        lifecycle_event,
    ))


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")
