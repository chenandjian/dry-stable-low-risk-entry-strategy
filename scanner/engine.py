# scanner/engine.py
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from queue import Queue
from typing import Callable

import scanner.db as db
from scanner.data_source import DataSourceManager
from scanner.baidu_source import fetch_baidu_daily
from scanner.sina_source import fetch_sina_daily
from scanner.tencent_source import fetch_tencent_daily
from scanner.index_source import fetch_market_index_daily
from scanner.liquidity_filter import passes_liquidity_filter
from scanner.daily_data_service import (
    CacheFreshnessContext,
    build_cache_freshness_context,
    select_fresh_cached_ohlc,
    source_error_confirms_no_trade,
    strip_zero_volume_target_row,
    trim_ohlc_to_target,
)
from scanner.pattern_detector import CupHandleResult
from analyzer.dry_stable import analyze_dry_stable
from scanner.strategy_engine import (
    CupHandleStrategyEngine,
    resolve_strategy_windows,
    select_market_window,
    select_strategy_window,
)

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    data: list[dict] | None
    primary_source: str
    fallback_source: str
    primary_attempts: int = 0
    fallback_attempts: int = 0
    primary_error: str | None = None
    fallback_error: str | None = None
    source_errors: dict = None  # ds_name -> error string for ALL attempted sources
    from_cache: bool = False
    kline_fetched_at: str | None = None
    kline_target_trade_date: str | None = None
    quote_status: str = "not_requested"

    def __post_init__(self):
        if self.source_errors is None:
            self.source_errors = {}


def scan_all(
    config: dict,
    progress_callback=None,
    resume_task_id: str = None,
    task_id: str = None,
    stocks: list[dict] = None,
    retry_policy: str = "normal",
    worker_count: int = 4,
) -> dict:
    """多线程全市场扫描。"""
    from scanner.stock_pool import get_a_stock_pool

    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    if task_id is None:
        task_id = resume_task_id or time.strftime("%Y%m%d-%H%M%S")

    start_offset = 0
    if stocks is None and resume_task_id:
        # 直接按 resume_task_id 查询，不依赖 get_interrupted_task() 的最新任务匹配
        stocks = db.get_pending_stocks(resume_task_id, from_idx=start_offset)
        if stocks:
            # 估算已扫描数：总数 - 剩余待处理数
            total = len(db.get_task_stocks(resume_task_id, limit=100000))
            start_offset = max(0, total - len(stocks))

    if stocks is None:
        stocks = get_a_stock_pool(config)
        if not resume_task_id:
            db.save_task_stocks(task_id, stocks)

    if retry_policy == "failed_only":
        primary_attempts = 3
        fallback_attempts = 3
    else:
        primary_attempts = 2
        fallback_attempts = 2

    configured_workers = config.get("data", {}).get("worker_count")
    if configured_workers is not None:
        worker_count = int(configured_workers)
    worker_count = max(1, worker_count)

    stock_queue = Queue()
    for stock in stocks:
        stock_queue.put(stock)

    mgr = DataSourceManager()
    candidate_by_code = {}
    candidate_lock = threading.Lock()
    scanned_count = [0]
    skip_count = [0]
    failed_count = [0]
    stats_lock = threading.Lock()
    busy_retries_by_code = {}
    busy_retry_lock = threading.Lock()

    liquidity_cfg = config.get("liquidity", {})
    daily_sources = config.get("data", {}).get("daily_sources") or DEFAULT_DAILY_SOURCES
    windows = resolve_strategy_windows(config)

    # 并发不足警告
    num_sources = len(daily_sources)
    if worker_count < num_sources:
        logger.warning(
            "工作线程数 %d 小于启用数据源数 %d，无法保证所有数据源同时参与拉取。",
            worker_count, num_sources,
        )
    logger.info("数据源列表: %s, 工作线程: %d", daily_sources, worker_count)
    kline_days = windows.min_listing_days
    scan_window_days = windows.scan_window_days
    logger.info(
        "窗口配置: min_listing_days=%s, scan_window_days=%s, backtest_window_days=%s",
        windows.min_listing_days, windows.scan_window_days, windows.backtest_window_days,
    )
    strategy_engine = CupHandleStrategyEngine(config)
    max_busy_retries = config.get("data", {}).get("source_busy_max_retries", 3)
    market_cfg = config.get("market_environment", {})
    market_data = fetch_market_index_daily(market_cfg.get("index_symbol"))

    start_time = time.time()

    def _now() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    def _today() -> str:
        return time.strftime("%Y-%m-%d")

    def _cache_freshness_context(code: str) -> CacheFreshnessContext:
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

    def worker(thread_name: str):
        while not stock_queue.empty():
            try:
                stock = stock_queue.get_nowait()
            except Exception:
                break

            code = stock["code"]
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
                fetch_result = _fetch_with_retry(
                    code,
                    daily_sources[0],
                    retry_attempts=primary_attempts,
                    fallback_attempts=fallback_attempts,
                    mgr=mgr,
                    source_chain=daily_sources,
                    kline_days=kline_days,
                    freshness_context=freshness_context,
                )
                data = fetch_result.data
                if data is None:
                    if _is_transient_source_busy(fetch_result):
                        with busy_retry_lock:
                            busy_count = busy_retries_by_code.get(code, 0) + 1
                            busy_retries_by_code[code] = busy_count
                        if busy_count <= max_busy_retries:
                            stock_queue.put(stock)
                            time.sleep(0.1)
                            continue
                        db.update_task_stock(
                            task_id,
                            code,
                            status="failed",
                            status_reason="数据源忙，超过重试次数",
                            primary_source=fetch_result.primary_source,
                            fallback_source=fetch_result.fallback_source,
                            primary_attempts=fetch_result.primary_attempts,
                            fallback_attempts=fetch_result.fallback_attempts,
                            primary_error=fetch_result.primary_error,
                            fallback_error=fetch_result.fallback_error,
                            source_errors=_encode_source_errors(fetch_result.source_errors),
                            finished_at=_now(),
                        )
                        db.refresh_scan_task_counts(task_id)
                        with stats_lock:
                            failed_count[0] += 1
                            skip_count[0] += 1
                        with busy_retry_lock:
                            busy_retries_by_code.pop(code, None)
                        if progress_callback:
                            progress_callback("scanning", start_offset + failed_count[0] + skip_count[0] + scanned_count[0], start_offset + len(stocks), f"{code} {stock.get('name', '')}")
                        continue
                    db.update_task_stock(
                        task_id,
                        code,
                        status="failed",
                        status_reason="数据源全部失败，未使用旧缓存扫描",
                        primary_source=fetch_result.primary_source,
                        fallback_source=fetch_result.fallback_source,
                        primary_attempts=fetch_result.primary_attempts,
                        fallback_attempts=fetch_result.fallback_attempts,
                        primary_error=fetch_result.primary_error,
                        fallback_error=fetch_result.fallback_error,
                        source_errors=_encode_source_errors(fetch_result.source_errors),
                        finished_at=_now(),
                    )
                    db.refresh_scan_task_counts(task_id)
                    with stats_lock:
                        failed_count[0] += 1
                        skip_count[0] += 1
                    with busy_retry_lock:
                        busy_retries_by_code.pop(code, None)
                    if progress_callback:
                        progress_callback("scanning", start_offset + failed_count[0] + skip_count[0] + scanned_count[0], start_offset + len(stocks), f"{code} {stock.get('name', '')}")
                    continue

                latest_trade_date = data[-1].get("date") if data else None
                kline_fetched_at = fetch_result.kline_fetched_at or _now()
                kline_target_trade_date = (
                    fetch_result.kline_target_trade_date
                    or freshness_context.target_trade_date
                )
                quote_status = fetch_result.quote_status or "not_requested"
                status_reason_suffix = None
                if quote_status == "suspended":
                    status_reason_suffix = "SUSPENDED_OR_NO_TRADE_ON_TARGET_DATE"
                if len(data) < kline_days:
                    db.update_task_stock(
                        task_id,
                        code,
                        status="skipped",
                        status_reason=status_reason_suffix or "上市天数不足",
                        kline_latest_date=latest_trade_date,
                        kline_fetched_at=kline_fetched_at,
                        kline_target_trade_date=kline_target_trade_date,
                        quote_status=quote_status,
                        source_errors=_encode_source_errors(fetch_result.source_errors),
                        finished_at=_now(),
                    )
                    db.refresh_scan_task_counts(task_id)
                    with stats_lock:
                        skip_count[0] += 1
                    with busy_retry_lock:
                        busy_retries_by_code.pop(code, None)
                    if progress_callback:
                        progress_callback("scanning", start_offset + failed_count[0] + skip_count[0] + scanned_count[0], start_offset + len(stocks), f"{code} {stock.get('name', '')}")
                    continue

                stock["latest_close"] = data[-1]["close"]
                stock["latest_turnover"] = data[-1].get("turnover") or (data[-1]["volume"] * data[-1]["close"])

                if not passes_liquidity_filter(data, liquidity_cfg):
                    db.update_task_stock(
                        task_id,
                        code,
                        status="skipped",
                        status_reason="流动性过滤未通过",
                        kline_latest_date=latest_trade_date,
                        kline_fetched_at=kline_fetched_at,
                        kline_target_trade_date=kline_target_trade_date,
                        quote_status=quote_status,
                        source_errors=_encode_source_errors(fetch_result.source_errors),
                        finished_at=_now(),
                    )
                    db.refresh_scan_task_counts(task_id)
                    with stats_lock:
                        skip_count[0] += 1
                    with busy_retry_lock:
                        busy_retries_by_code.pop(code, None)
                    if progress_callback:
                        progress_callback("scanning", start_offset + failed_count[0] + skip_count[0] + scanned_count[0], start_offset + len(stocks), f"{code} {stock.get('name', '')}")
                    continue

                # 截取固定策略窗口
                strategy_data = select_strategy_window(data, scan_window_days)
                if strategy_data is None:
                    db.update_task_stock(
                        task_id,
                        code,
                        status="skipped",
                        status_reason=f"策略计算数据不足：需要 {scan_window_days} 日，实际 {len(data)} 日",
                        kline_latest_date=latest_trade_date,
                        kline_fetched_at=kline_fetched_at,
                        kline_target_trade_date=kline_target_trade_date,
                        quote_status=quote_status,
                        source_errors=_encode_source_errors(fetch_result.source_errors),
                        finished_at=_now(),
                    )
                    db.refresh_scan_task_counts(task_id)
                    with stats_lock:
                        skip_count[0] += 1
                    with busy_retry_lock:
                        busy_retries_by_code.pop(code, None)
                    if progress_callback:
                        progress_callback("scanning", start_offset + failed_count[0] + skip_count[0] + scanned_count[0], start_offset + len(stocks), f"{code} {stock.get('name', '')}")
                    continue

                decision_date = strategy_data[-1]["date"]
                market_window = select_market_window(market_data, decision_date)
                evaluation = strategy_engine.evaluate_at(
                    strategy_data,
                    code=code,
                    name=stock.get("name", ""),
                    market_data=market_window,
                )
                result = evaluation.result
                dry_stable = evaluation.dry_stable

                if evaluation.passed:
                    if result.score == 0:
                        result.score = min(100, dry_stable["pattern_score"]["score"] * 5)
                    stock["dry_stable"] = dry_stable
                    strategy_verdict = dry_stable["decision"]["verdict"]
                    with candidate_lock:
                        candidate_by_code[code] = (stock, result)
                        unique_candidates = len(candidate_by_code)
                    db.update_task_stock(
                        task_id,
                        code,
                        status="candidate",
                        kline_latest_date=latest_trade_date,
                        kline_fetched_at=kline_fetched_at,
                        kline_target_trade_date=kline_target_trade_date,
                        quote_status=quote_status,
                        status_reason=status_reason_suffix,
                        source_errors=_encode_source_errors(fetch_result.source_errors),
                        finished_at=_now(),
                    )
                    if progress_callback:
                        progress_callback(
                            "discovery",
                            start_offset + unique_candidates,
                            start_offset + len(stocks),
                            f"{code} {stock.get('name', '')}",
                            {
                                "code": code,
                                "name": stock.get("name", ""),
                                "score": result.score,
                                "is_breakout": result.is_breakout,
                                "is_volume_breakout": result.is_volume_breakout,
                                "breakout_price": result.breakout_price,
                                "cup_depth_pct": result.cup_depth_pct,
                                "cup_duration": result.cup_duration,
                                "handle_depth_pct": result.handle_depth_pct,
                                "vol_multiplier": result.vol_multiplier,
                                "latest_close": stock.get("latest_close", 0),
                                "dry_stable_verdict": strategy_verdict,
                                "dry_stable_summary": dry_stable["decision"]["summary"],
                                "volume_dry_score": dry_stable["volume_dry"]["score"],
                                "price_stable_score": dry_stable["price_stable"]["score"],
                                "pattern_score_20": dry_stable["pattern_score"]["score"],
                                "pattern_type": dry_stable["pattern_score"]["type"],
                                "key_pattern_type": dry_stable["pattern_score"]["key_pattern_type"],
                                "risk_percent": dry_stable["risk_reward"]["risk_percent"],
                                "rr1": dry_stable["risk_reward"]["rr1"],
                                "position_advice": dry_stable["risk_reward"]["position_advice"],
                                "entry_zone_low": dry_stable["key_prices"]["entry_zone_low"],
                                "entry_zone_high": dry_stable["key_prices"]["entry_zone_high"],
                                "pivot": dry_stable["key_prices"]["pivot"],
                                "stop_loss": dry_stable["key_prices"]["stop_loss"],
                                "target_1": dry_stable["key_prices"]["target_1"],
                                "target_2": dry_stable["key_prices"]["target_2"],
                                "market_status": dry_stable["market_environment"]["status"],
                                "market_position_advice": dry_stable["market_environment"]["position_advice"],
                            },
                        )
                else:
                    db.update_task_stock(
                        task_id,
                        code,
                        status="scanned",
                        kline_latest_date=latest_trade_date,
                        kline_fetched_at=kline_fetched_at,
                        kline_target_trade_date=kline_target_trade_date,
                        quote_status=quote_status,
                        status_reason=status_reason_suffix,
                        source_errors=_encode_source_errors(fetch_result.source_errors),
                        finished_at=_now(),
                    )

                db.refresh_scan_task_counts(task_id)
                with stats_lock:
                    scanned_count[0] += 1
                with busy_retry_lock:
                    busy_retries_by_code.pop(code, None)

                if progress_callback:
                    progress_callback("scanning", start_offset + scanned_count[0], start_offset + len(stocks), f"{code} {stock.get('name', '')}")

            except Exception as e:
                logger.error(f"Error scanning {code}: {e}")
                db.update_task_stock(
                    task_id,
                    code,
                    status="failed",
                    status_reason="扫描异常",
                    error_detail=str(e),
                    finished_at=_now(),
                )
                db.refresh_scan_task_counts(task_id)
                with stats_lock:
                    failed_count[0] += 1
                    skip_count[0] += 1
                with busy_retry_lock:
                    busy_retries_by_code.pop(code, None)
                if progress_callback:
                    progress_callback("scanning", start_offset + failed_count[0] + skip_count[0] + scanned_count[0], start_offset + len(stocks), f"{code} {stock.get('name', '')}")
            finally:
                pass

    threads = [threading.Thread(target=worker, args=(f"t{i+1}",), daemon=True) for i in range(worker_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    elapsed = time.time() - start_time
    candidates = list(candidate_by_code.values())
    candidates.sort(key=lambda x: x[1].score, reverse=True)
    summary = db.refresh_scan_task_counts(task_id)

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


def _build_discovery(code: str, name: str, result, dry_stable: dict, latest_close: float) -> dict:
    """Build a discovery dict in the same format as the scan progress callback."""
    return {
        "code": code,
        "name": name,
        "score": result.score,
        "is_breakout": result.is_breakout,
        "is_volume_breakout": result.is_volume_breakout,
        "breakout_price": result.breakout_price,
        "cup_depth_pct": result.cup_depth_pct,
        "cup_duration": result.cup_duration,
        "handle_depth_pct": result.handle_depth_pct,
        "vol_multiplier": result.vol_multiplier,
        "latest_close": latest_close,
        "dry_stable_verdict": dry_stable["decision"]["verdict"],
        "verdict_key": dry_stable["decision"].get("verdict_key", ""),
        "positive_factors": dry_stable["decision"].get("positive_factors", []),
        "warnings": dry_stable["decision"].get("warnings", []),
        "reject_reasons": dry_stable["decision"].get("reject_reasons", []),
        "raw_volume_dry_score": dry_stable["volume_dry"].get("raw_score", 0),
        "raw_price_stable_score": dry_stable["price_stable"].get("raw_score", 0),
        "score_caps": dry_stable["volume_dry"].get("caps", []) + dry_stable["price_stable"].get("caps", []),
        "dry_stable_summary": dry_stable["decision"]["summary"],
        "volume_dry_score": dry_stable["volume_dry"]["score"],
        "price_stable_score": dry_stable["price_stable"]["score"],
        "pattern_score_20": dry_stable["pattern_score"]["score"],
        "pattern_type": dry_stable["pattern_score"]["type"],
        "key_pattern_type": dry_stable["pattern_score"]["key_pattern_type"],
        "cup_handle_score": dry_stable["pattern_score"].get("cup_handle_score", 0),
        "vcp_score": dry_stable["pattern_score"].get("vcp_score", 0),
        "vcp_contractions": dry_stable["pattern_score"].get("vcp_contractions", 0),
        "risk_percent": dry_stable["risk_reward"]["risk_percent"],
        "rr1": dry_stable["risk_reward"]["rr1"],
        "position_advice": dry_stable["risk_reward"]["position_advice"],
        "entry_zone_low": dry_stable["key_prices"]["entry_zone_low"],
        "entry_zone_high": dry_stable["key_prices"]["entry_zone_high"],
        "pivot": dry_stable["key_prices"]["pivot"],
        "stop_loss": dry_stable["key_prices"]["stop_loss"],
        "target_1": dry_stable["key_prices"]["target_1"],
        "target_2": dry_stable["key_prices"]["target_2"],
        "market_status": dry_stable["market_environment"]["status"],
        "market_position_advice": dry_stable["market_environment"]["position_advice"],
        # Pattern detail fields
        "handle_duration": result.handle_duration,
        "lip_deviation_pct": result.lip_deviation_pct,
        "left_high_price": result.left_high_price,
        "cup_low_price": result.cup_low_price,
        "right_high_price": result.right_high_price,
        "handle_low_price": result.handle_low_price,
        "left_high_date": result.left_high_date or "",
        "cup_low_date": result.cup_low_date or "",
        "right_high_date": result.right_high_date or "",
        "handle_low_date": result.handle_low_date or "",
    }


def re_evaluate_task(
    config: dict,
    task_id: str,
    progress_callback=None,
) -> dict:
    """Re-run strategy evaluation on existing OHLC data for a completed task.

    Does NOT re-fetch stock data — only re-applies liquidity filter, pattern
    detection and dry-stable analysis using the current config.  Old candidates
    are replaced with new ones.
    """
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    stocks = db.get_task_stocks(task_id, limit=100000, offset=0)
    if not stocks:
        return {"task_id": task_id, "status": "no_stocks", "candidates_found": 0}

    liquidity_cfg = config.get("liquidity", {})
    windows = resolve_strategy_windows(config)
    kline_days = windows.min_listing_days
    scan_window_days = windows.scan_window_days
    strategy_engine = CupHandleStrategyEngine(config)
    market_cfg = config.get("market_environment", {})
    market_data = fetch_market_index_daily(market_cfg.get("index_symbol"))
    old_candidates = {c["code"] for c in db.get_candidates(task_id=task_id)}
    total = len(stocks)
    new_codes = set()

    for i, stock in enumerate(stocks):
        code = stock["code"]
        name = stock.get("name", "")
        data = db.get_ohlc(code, max_rows=kline_days)
        if not data:
            continue

        try:
            if not passes_liquidity_filter(data, liquidity_cfg):
                continue

            # 截取固定策略窗口
            strategy_data = select_strategy_window(data, scan_window_days)
            if strategy_data is None:
                continue

            decision_date = strategy_data[-1]["date"]
            market_window = select_market_window(market_data, decision_date)
            evaluation = strategy_engine.evaluate_at(
                strategy_data, code=code, name=name, market_data=market_window,
            )
            result = evaluation.result
            dry_stable = evaluation.dry_stable

            if evaluation.passed:
                if result.score == 0:
                    result.score = min(100, dry_stable["pattern_score"]["score"] * 5)
                latest_close = data[-1]["close"]
                discovery = _build_discovery(code, name, result, dry_stable, latest_close)
                db.upsert_candidate(task_id, discovery)
                new_codes.add(code)
                if progress_callback:
                    progress_callback("discovery", len(new_codes), total,
                                      f"{code} {name}", discovery)
        except Exception:
            pass

        if progress_callback and (i + 1) % 100 == 0:
            progress_callback("scanning", i + 1, total, f"{code} {name}")

    # Remove candidates that no longer qualify
    removed = old_candidates - new_codes
    if removed:
        conn = db.get_conn()
        for code in removed:
            conn.execute("DELETE FROM candidates WHERE task_id=? AND code=?", (task_id, code))
        conn.commit()

    db.refresh_scan_task_counts(task_id)
    return {
        "task_id": task_id,
        "status": "completed",
        "candidates_found": len(new_codes),
        "total_stocks": total,
        "added": len(new_codes - old_candidates),
        "removed": len(removed),
    }


DEFAULT_DAILY_SOURCES = ["baidu", "sina", "tencent"]


def _daily_fetch_fn(ds_name: str):
    fetchers = {
        "baidu": fetch_baidu_daily,
        "sina": fetch_sina_daily,
        "tencent": fetch_tencent_daily,
    }
    if ds_name not in fetchers:
        raise ValueError(f"Unknown daily data source: {ds_name}")
    return fetchers[ds_name]


def _normalize_source_chain(source_chain: list[str] | None, primary_ds: str) -> list[str]:
    raw_chain = [primary_ds] + list(source_chain or DEFAULT_DAILY_SOURCES)
    chain = []
    for ds_name in raw_chain:
        if ds_name not in chain:
            chain.append(ds_name)
    return chain


def _fetch_with_retry(
    code: str,
    primary_ds: str,
    retry_attempts: int = 2,
    fallback_attempts: int = 2,
    sleep_fn: Callable[[float], None] = time.sleep,
    mgr: DataSourceManager | None = None,
    source_chain: list[str] | None = None,
    kline_days: int = 250,
    cache_fresh_date: str | None = None,
    freshness_context: CacheFreshnessContext | None = None,
) -> FetchResult:
    """Fetch K-line by trying sources in config order.

    Iterates source_chain in order.  For each source:
    - Acquire lock (non-blocking).  Busy → skip, try next.
    - Lock acquired → fetch with retries (primary: retry_attempts, fallback: fallback_attempts).
    - Success → merge cache, save, return.
    - Failure → mark failed, release lock, try next.
    - All busy → data source busy (requeue).
    - All failed → None (no cache fallback).

    This respects config priority while letting different threads
    naturally use different sources via lock contention.
    """
    chain = _normalize_source_chain(source_chain, primary_ds)
    cached = db.get_ohlc(code)
    if freshness_context is None and cache_fresh_date:
        freshness_context = CacheFreshnessContext(target_trade_date=cache_fresh_date)
    fresh_cached = select_fresh_cached_ohlc(
        cached, kline_days, cache_fresh_date, freshness_context=freshness_context,
    )
    if fresh_cached is not None:
        return FetchResult(
            data=fresh_cached,
            primary_source="cache",
            fallback_source="cache",
            from_cache=True,
            kline_fetched_at=freshness_context.fetched_at if freshness_context else None,
            kline_target_trade_date=freshness_context.target_trade_date if freshness_context else cache_fresh_date,
            quote_status=freshness_context.quote_status if freshness_context else "not_requested",
        )

    saw_busy = False
    source_errors: dict[str, str] = {}
    failed_sources: set[str] = set()
    stale_success: tuple[list[dict], str, int] | None = None

    for i, ds_name in enumerate(chain):
        if ds_name in failed_sources:
            continue

        is_primary = (ds_name == chain[0])
        attempts = retry_attempts if is_primary else fallback_attempts

        # Try to acquire this source's lock
        locked = False
        if mgr is not None:
            if not mgr.acquire(ds_name):
                saw_busy = True
                source_errors[ds_name] = "busy"
                logger.debug("%s  %s  ⏳ busy", code, ds_name)
                continue
            locked = True

        try:
            data, used_attempts, error = _try_fetch_source(code, ds_name, attempts, sleep_fn, kline_days)
        finally:
            if locked and mgr is not None:
                mgr.release(ds_name)

        if error:
            logger.warning("%s  %s  ✗ %s", code, ds_name, error)
            source_errors[ds_name] = f"attempts={used_attempts} error={error}"
            if "data source busy" in str(error):
                saw_busy = True
            failed_sources.add(ds_name)
            continue

        if data:
            target_date = freshness_context.target_trade_date if freshness_context else None
            effective_cached = trim_ohlc_to_target(cached or [], target_date)
            effective_data = trim_ohlc_to_target(data, target_date)
            effective_data, no_trade_error = strip_zero_volume_target_row(effective_data, target_date)
            if no_trade_error:
                source_errors[ds_name] = f"attempts={used_attempts} error={no_trade_error}"
                stale_candidate = effective_data or effective_cached
                if stale_candidate:
                    latest_date = stale_candidate[-1].get("date")
                    if stale_success is None or latest_date > stale_success[0][-1].get("date"):
                        stale_success = (stale_candidate, ds_name, used_attempts)
                failed_sources.add(ds_name)
                continue
            if not effective_data:
                source_errors[ds_name] = f"attempts={used_attempts} error=missing target trade date"
                failed_sources.add(ds_name)
                continue
            latest_date = effective_data[-1].get("date")
            if target_date and latest_date < target_date:
                source_errors[ds_name] = (
                    f"attempts={used_attempts} error=missing target trade date {target_date}"
                )
                if stale_success is None or latest_date > stale_success[0][-1].get("date"):
                    stale_success = (effective_data, ds_name, used_attempts)
                failed_sources.add(ds_name)
                continue

            merged = _merge_data(effective_cached, effective_data, max_rows=kline_days)
            db.save_ohlc(code, merged)
            fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            quote_status = "not_requested"
            if (
                freshness_context is not None
                and merged
                and merged[-1].get("date") < freshness_context.target_trade_date
            ):
                quote_status = "suspended"

            recent = data[-1]
            prev = data[-2] if len(data) >= 2 else None
            parts = [f"{code}  {ds_name}  {len(data)}行"]
            if prev:
                parts.append(f"{prev['date'][5:]}: O{prev['open']:.2f} H{prev['high']:.2f} L{prev['low']:.2f} C{prev['close']:.2f}")
            parts.append(f"{recent['date'][5:]}: O{recent['open']:.2f} H{recent['high']:.2f} L{recent['low']:.2f} C{recent['close']:.2f}")
            logger.info("  ".join(parts))

            result = FetchResult(
                data=merged,
                primary_source=chain[0],
                fallback_source=ds_name if ds_name != chain[0] else chain[0],
                source_errors=source_errors,
                kline_fetched_at=fetched_at,
                kline_target_trade_date=(
                    freshness_context.target_trade_date if freshness_context else None
                ),
                quote_status=quote_status,
            )
            return _apply_source_compatibility_fields(
                result, chain, source_errors,
                selected_source=ds_name, selected_attempts=used_attempts,
            )

    if (
        stale_success is not None
        and not saw_busy
        and _stale_success_is_conclusive_no_trade(chain, source_errors)
    ):
        stale_data, stale_source, stale_attempts = stale_success
        target_date = freshness_context.target_trade_date if freshness_context else None
        stale_latest_date = stale_data[-1].get("date")
        effective_cached = trim_ohlc_to_target(cached or [], stale_latest_date)
        merged = _merge_data(effective_cached, stale_data, max_rows=kline_days)
        db.save_ohlc(code, merged)
        result = FetchResult(
            data=merged,
            primary_source=chain[0],
            fallback_source=stale_source if stale_source != chain[0] else chain[0],
            source_errors=source_errors,
            kline_fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            kline_target_trade_date=target_date,
            quote_status="suspended",
        )
        return _apply_source_compatibility_fields(
            result, chain, source_errors,
            selected_source=stale_source, selected_attempts=stale_attempts,
        )

    return _build_all_failed_result(chain, source_errors)


def _is_transient_source_busy(fetch_result: FetchResult) -> bool:
    if fetch_result.data is not None:
        return False
    return fetch_result.primary_error == "data source busy" or fetch_result.fallback_error == "data source busy"


def _try_fetch_source(
    code: str,
    ds_name: str,
    attempts: int,
    sleep_fn: Callable[[float], None],
    kline_days: int = 250,
) -> tuple[list[dict] | None, int, str | None]:
    """Try fetching from a data source with retries and backoff."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            fetch_fn = _daily_fetch_fn(ds_name)
            data = _call_fetch_fn(fetch_fn, code, kline_days)
            if data:
                return data, attempt, None
            last_error = "empty response"
        except ValueError as exc:
            return None, attempt, str(exc)
        except Exception as exc:
            last_error = _classify_fetch_error(exc)
        if attempt < attempts:
            sleep_fn(min(0.5 * attempt, 2.0))
    return None, attempts, last_error



def _apply_source_compatibility_fields(
    result: FetchResult,
    chain: list[str],
    source_errors: dict[str, str],
    *,
    selected_source: str | None = None,
    selected_attempts: int = 0,
) -> FetchResult:
    """Fill primary_*/fallback_* fields consistently from source_errors and actual result.

    Args:
        result: FetchResult to fill (data and source_errors already set).
        chain: ordered source names.
        source_errors: per-source error/busy entries.
        selected_source: the source that produced data (success) or the last
            actual-failure source (all-failed).  None means all-busy.
        selected_attempts: network attempts for selected_source.
    """
    primary = chain[0]

    # --- primary fields from chain[0] ---
    result.primary_source = primary
    primary_entry = source_errors.get(primary)
    if primary_entry is not None:
        attempts, error = _parse_source_error_entry(primary_entry)
        result.primary_attempts = attempts
        result.primary_error = "data source busy" if primary_entry == "busy" else error
    elif selected_source == primary:
        result.primary_attempts = selected_attempts
        result.primary_error = None  # success

    # --- fallback fields from selected_source (if different from primary) ---
    if selected_source and selected_source != primary:
        result.fallback_source = selected_source
        result.fallback_attempts = selected_attempts
        # For failed path, parse the actual error from source_errors
        if result.data is None:
            fb_entry = source_errors.get(selected_source, "")
            if fb_entry:
                _, fb_error = _parse_source_error_entry(fb_entry)
                result.fallback_error = "data source busy" if fb_entry == "busy" else fb_error
        else:
            result.fallback_error = None  # success
    else:
        # No distinct fallback; when data is None, this is a total failure
        # with no separate fallback — truly mirror primary
        if result.data is None:
            result.fallback_source = primary
            result.fallback_attempts = result.primary_attempts
            result.fallback_error = result.primary_error
        else:
            # Success — fallback was never needed
            result.fallback_source = primary
            result.fallback_attempts = 0
            result.fallback_error = None

    return result


def _build_all_failed_result(
    chain: list[str],
    source_errors: dict[str, str],
) -> FetchResult:
    """Build FetchResult when all sources failed, using unified compatibility helper."""
    result = FetchResult(data=None, primary_source=chain[0], fallback_source=chain[-1],
                         source_errors=source_errors)

    # Find the last source that actually attempted a fetch (not just busy)
    selected_source = None
    for ds_name in reversed(chain):
        entry = source_errors.get(ds_name, "")
        if entry and entry != "busy":
            selected_source = ds_name
            break

    if selected_source is None:
        # All sources busy
        result.primary_source = chain[0]
        result.primary_error = "data source busy"
        result.fallback_source = chain[-1] if len(chain) > 1 else chain[0]
        result.fallback_attempts = 0
        result.fallback_error = "data source busy"
        return result

    selected_attempts, _ = _parse_source_error_entry(source_errors.get(selected_source, ""))
    result = _apply_source_compatibility_fields(
        result, chain, source_errors,
        selected_source=selected_source, selected_attempts=selected_attempts,
    )

    # FINAL-001: If primary is the only actual failure and all fallbacks are busy,
    # the else-branch would set fallback to mirror primary with 0/Nothing.
    # Instead, point fallback at the last busy fallback source.
    if selected_source == chain[0] and len(chain) > 1:
        busy_fallbacks = [
            ds for ds in chain[1:]
            if source_errors.get(ds) == "busy"
        ]
        if busy_fallbacks:
            result.fallback_source = busy_fallbacks[-1]
            result.fallback_attempts = 0
            result.fallback_error = "data source busy"
        else:
            # Single-source chain edge case: truly mirror primary
            result.fallback_source = result.primary_source
            result.fallback_attempts = result.primary_attempts
            result.fallback_error = result.primary_error

    return result


def _parse_source_error_entry(entry: str) -> tuple[int, str | None]:
    """Parse a source_errors value like 'attempts=3 error=timeout' into (3, 'timeout').

    Handles multi-word error messages like 'attempts=1 error=data source busy'.
    """
    if not entry or entry == "busy":
        return 0, entry or None
    attempts = 0
    error = None
    # Split on " error=" first to separate attempts from the error message
    if " error=" in entry:
        head, error = entry.split(" error=", 1)
        for part in head.split(" "):
            if part.startswith("attempts="):
                try:
                    attempts = int(part.split("=", 1)[1])
                except ValueError:
                    pass
    else:
        # Fallback: parse space-delimited parts
        for part in entry.split(" "):
            if part.startswith("attempts="):
                try:
                    attempts = int(part.split("=", 1)[1])
                except ValueError:
                    pass
    return attempts, error


def _encode_source_errors(source_errors: dict | None) -> str | None:
    """Encode source_errors dict as a stable JSON string for persistence."""
    if not source_errors:
        return None
    return json.dumps(source_errors, ensure_ascii=False, separators=(",", ":"))


def _call_fetch_fn(fetch_fn, code: str, days: int) -> list[dict] | None:
    try:
        return fetch_fn(code, days=days)
    except TypeError:
        return fetch_fn(code)


def _stale_success_is_conclusive_no_trade(
    chain: list[str],
    source_errors: dict[str, str],
) -> bool:
    """Only classify stale rows as no-trade when every source has conclusive no-trade evidence."""
    return all(source_error_confirms_no_trade(source_errors.get(ds_name)) for ds_name in chain)


def _classify_fetch_error(exc: Exception) -> str:
    text = str(exc)
    if "456" in text or "429" in text:
        return "data source busy"
    return text


def _merge_data(cached: list[dict], fresh: list[dict], max_rows: int = 0) -> list[dict]:
    """合并缓存和新数据，去重按日期排序。可限制最大行数。"""
    seen = {d["date"]: d for d in cached}
    for d in fresh:
        seen[d["date"]] = d
    merged = sorted(seen.values(), key=lambda x: x["date"])
    if max_rows and len(merged) > max_rows:
        merged = merged[-max_rows:]
    return merged
