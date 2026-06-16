# strategy2/scanner.py
"""策略2全市场扫描编排 — 只协调共享数据能力和策略2引擎，不包含指标和评分实现。

不导入 strategy2 之外的任何策略判断模块。
"""
import json
import logging
import threading
import time
from datetime import datetime
from queue import Queue

import scanner.db as db
from scanner.data_source import DataSourceManager
from scanner.liquidity_filter import passes_liquidity_filter
from scanner.daily_data_service import (
    build_cache_freshness_context,
    fetch_with_retry,
    is_transient_source_busy,
    encode_source_errors,
    DEFAULT_DAILY_SOURCES,
)
from strategy2.engine import ExtremeDryStableStrategyEngine

logger = logging.getLogger(__name__)


def scan_strategy2_all(
    config: dict,
    progress_callback=None,
    task_id: str = None,
    stocks: list[dict] = None,
    worker_count: int = 4,
    retry_policy: str = "normal",
) -> dict:
    """执行策略2全市场扫描。

    Args:
        config: 全局配置（含 strategy2、liquidity、data 段）。
        progress_callback: fn(stage, current, total, detail, discovery=None)
        task_id: 扫描任务 ID。
        stocks: 股票列表，None 时从股票池获取。
        worker_count: 工作线程数。
        retry_policy: "normal" (默认) 或 "failed_only" (提升重试次数 2→3)。

    Returns:
        dict with candidates, stats, task_id.
    """
    from scanner.stock_pool import get_a_stock_pool

    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    if task_id is None:
        task_id = time.strftime("%Y%m%d-%H%M%S")

    if stocks is None:
        stocks = get_a_stock_pool(config)
        db.save_task_stocks(task_id, stocks)

    strategy2_cfg = config.get("strategy2", {})
    liquidity_cfg = config.get("liquidity", {})
    daily_sources = config.get("data", {}).get("daily_sources") or DEFAULT_DAILY_SOURCES
    kline_days = liquidity_cfg.get("min_listing_days", 350)
    configured_workers = config.get("data", {}).get("worker_count")
    if configured_workers is not None:
        worker_count = int(configured_workers)
    worker_count = max(1, worker_count)
    max_busy_retries = config.get("data", {}).get("source_busy_max_retries", 3)

    stock_queue = Queue()
    for stock in stocks:
        stock_queue.put(stock)

    mgr = DataSourceManager()
    # RECHECK-S2-005: 传完整配置，使引擎校验跨配置关系（strategy_window_days <= min_listing_days）
    engine = ExtremeDryStableStrategyEngine(config)
    candidate_by_code = {}
    candidate_lock = threading.Lock()
    scanned_count = [0]
    skip_count = [0]
    failed_count = [0]
    stats_lock = threading.Lock()
    busy_retries_by_code = {}
    busy_retry_lock = threading.Lock()

    start_time = time.time()

    def _now() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    def _today() -> str:
        return time.strftime("%Y-%m-%d")

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

    def _finish_stock(code, name, status, status_reason=None, error_detail=None,
                      kline_latest_date=None, fetch_result=None):
        """统一终态处理 — DB更新（含数据源诊断）+ 刷新统计 + 发送 processed 进度。"""
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
            task_id, code, status=status,
            status_reason=status_reason,
            error_detail=error_detail,
            kline_latest_date=kline_latest_date,
            finished_at=_now(),
            **source_fields,
        )
        summary = db.refresh_scan_task_counts(task_id)
        if progress_callback:
            progress_callback(
                "scanning",
                summary["processed"],
                summary["total_stocks"],
                f"{code} {name}",
            )

    def worker(thread_name: str):
        while not stock_queue.empty():
            try:
                stock = stock_queue.get_nowait()
            except Exception:
                break

            code = stock["code"]
            stock_name = stock.get("name", "")
            fetch_result = None
            try:
                freshness_context = _cache_freshness_context(code)
                db.update_task_stock(
                    task_id, code, status="fetching",
                    primary_source=daily_sources[0],
                    fallback_source=daily_sources[-1],
                    started_at=_now(),
                )
                retry_attempts = 3 if retry_policy == "failed_only" else 2
                fallback_attempts = 3 if retry_policy == "failed_only" else 2
                fetch_result = fetch_with_retry(
                    code, daily_sources[0],
                    retry_attempts=retry_attempts, fallback_attempts=fallback_attempts,
                    mgr=mgr, source_chain=daily_sources, kline_days=kline_days,
                    freshness_context=freshness_context,
                )
                data = fetch_result.data
                if data is None:
                    if is_transient_source_busy(fetch_result):
                        with busy_retry_lock:
                            bc = busy_retries_by_code.get(code, 0) + 1
                            busy_retries_by_code[code] = bc
                        if bc <= max_busy_retries:
                            stock_queue.put(stock)
                            time.sleep(0.1)
                            continue
                        _finish_stock(code, stock_name, "failed",
                                       status_reason="数据源忙，超过重试次数",
                                       fetch_result=fetch_result)
                        with stats_lock:
                            failed_count[0] += 1
                            skip_count[0] += 1
                        with busy_retry_lock:
                            busy_retries_by_code.pop(code, None)
                        continue
                    _finish_stock(code, stock_name, "failed",
                                  status_reason="ALL_DATA_SOURCES_FAILED",
                                  fetch_result=fetch_result)
                    with stats_lock:
                        failed_count[0] += 1
                        skip_count[0] += 1
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

                # 全局流动性过滤
                if not passes_liquidity_filter(data, liquidity_cfg):
                    _finish_stock(code, stock_name, "skipped",
                                  status_reason=suspended_reason or "LIQUIDITY_FILTER_REJECTED",
                                  kline_latest_date=latest_trade_date,
                                  fetch_result=fetch_result)
                    with stats_lock:
                        skip_count[0] += 1
                    with busy_retry_lock:
                        busy_retries_by_code.pop(code, None)
                    continue

                # 策略2评估
                evaluation = engine.evaluate_at(data, code=code, name=stock.get("name", ""))

                if evaluation.passed:
                    # FINAL-S2-002: 持久化 → 内存候选 → _finish_stock (processed) → discovery
                    discovery = _build_strategy2_discovery(evaluation, fetch_result)
                    try:
                        db.upsert_strategy2_candidate(task_id, discovery)
                    except Exception as exc:
                        logger.error(
                            "Failed to upsert strategy2 candidate %s: %s", code, exc,
                        )
                        _finish_stock(code, stock_name, "failed",
                                      status_reason="STRATEGY2_CANDIDATE_PERSIST_FAILED",
                                      error_detail=str(exc),
                                      kline_latest_date=latest_trade_date,
                                      fetch_result=fetch_result)
                        with stats_lock:
                            failed_count[0] += 1
                            skip_count[0] += 1
                        with busy_retry_lock:
                            busy_retries_by_code.pop(code, None)
                        continue

                    with candidate_lock:
                        candidate_by_code[code] = evaluation

                    _finish_stock(code, stock_name, "candidate",
                                  status_reason=suspended_reason,
                                  kline_latest_date=latest_trade_date,
                                  fetch_result=fetch_result)

                    if progress_callback:
                        progress_callback(
                            "discovery", len(candidate_by_code), len(stocks),
                            f"{code} {stock.get('name', '')}",
                            discovery,
                        )
                else:
                    # 下降趋势过滤时，将趋势指标写入 error_detail
                    error_detail = None
                    if evaluation.status_reason == "DOWNTREND_FILTERED" and evaluation.trend is not None:
                        error_detail = json.dumps({
                            "trendType": evaluation.trend.trend_type,
                            "shortMidScore": evaluation.trend.short_mid_score,
                            "longScore": evaluation.trend.long_score,
                            "totalEvidenceScore": evaluation.trend.total_evidence_score,
                            "necessaryConditionsMet": evaluation.trend.necessary_conditions_met,
                            "ma20": evaluation.trend.ma20,
                            "ma60": evaluation.trend.ma60,
                            "ma120": evaluation.trend.ma120,
                            "ma20Slope": evaluation.trend.ma20_slope,
                            "ma60Slope": evaluation.trend.ma60_slope,
                            "drawdownFromHigh60": evaluation.trend.drawdown_from_high_60,
                            "centerShift20": evaluation.trend.center_shift_20,
                            "pricePosition60": evaluation.trend.price_position_60,
                            "linearTrend60": evaluation.trend.linear_trend_60,
                            "drawdownFromHigh120": evaluation.trend.drawdown_from_high_120,
                            "centerShift40": evaluation.trend.center_shift_40,
                            "return20": evaluation.trend.return_20,
                            "return60": evaluation.trend.return_60,
                            "conditions": evaluation.trend.downtrend_conditions,
                        })
                        logger.info(
                            "DOWNTREND_FILTERED task=%s code=%s date=%s ma20=%.2f ma60=%.2f slope=%.4f return=%.4f",
                            task_id, code, evaluation.evaluation_date,
                            evaluation.trend.ma20, evaluation.trend.ma60,
                            evaluation.trend.ma20_slope, evaluation.trend.return_20,
                        )
                    _finish_stock(code, stock_name, "scanned",
                                  status_reason=suspended_reason or evaluation.status_reason,
                                  error_detail=error_detail,
                                  kline_latest_date=latest_trade_date,
                                  fetch_result=fetch_result)

                with stats_lock:
                    scanned_count[0] += 1
                with busy_retry_lock:
                    busy_retries_by_code.pop(code, None)

            except Exception as e:
                logger.error("Strategy2 error scanning %s: %s", code, e)
                _finish_stock(code, stock_name, "failed",
                              status_reason="STRATEGY2_EVALUATION_ERROR",
                              error_detail=str(e),
                              fetch_result=fetch_result)
                with stats_lock:
                    failed_count[0] += 1
                    skip_count[0] += 1
                with busy_retry_lock:
                    busy_retries_by_code.pop(code, None)

    threads = [threading.Thread(target=worker, args=(f"t{i+1}",), daemon=True)
               for i in range(worker_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

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


def _build_strategy2_discovery(evaluation, fetch_result=None) -> dict:
    """Build discovery dict from Strategy2Evaluation for frontend/persistence."""
    ind = evaluation.indicators
    risk = evaluation.risk
    trend = evaluation.trend
    current_close = evaluation.current_close
    return {
        "code": evaluation.code,
        "name": evaluation.name,
        "evaluation_date": evaluation.evaluation_date,
        "total_score": evaluation.total_score,
        "level": evaluation.level,
        "volume_dry_score": evaluation.volume_dry_score,
        "price_stable_score": evaluation.price_stable_score,
        "current_close": current_close,
        "v3": ind.v3, "v5": ind.v5, "v10": ind.v10, "v20": ind.v20,
        "volume_ratio_5_20": ind.volume_ratio_5_20,
        "volume_percentile": ind.volume_percentile,
        "volume_percentile_days": ind.volume_percentile_days,
        "range_5": ind.range_5,
        "close_range_5": ind.close_range_5,
        "return_3": ind.return_3,
        "return_5": ind.return_5,
        "key_support": risk.key_support,
        "buy_zone_low": risk.buy_zone_low,
        "buy_zone_high": risk.buy_zone_high,
        "stop_loss": risk.stop_loss,
        "risk_ratio": risk.risk_ratio,
        "risk_level": risk.risk_level,
        "short_term_time_exit_days": getattr(evaluation, "short_term_time_exit_days", 0),
        "score_reasons": evaluation.score_reasons,
        "reject_reasons": evaluation.reject_reasons,
        "data_source": fetch_result.primary_source if fetch_result else "",
        "trend_type": trend.trend_type if trend else "",
        "short_mid_score": trend.short_mid_score if trend else 0,
        "long_score": trend.long_score if trend else 0,
        "total_evidence_score": trend.total_evidence_score if trend else 0,
        "necessary_conditions_met": 1 if (trend and trend.necessary_conditions_met) else 0,
        "ma20": trend.ma20 if trend else 0.0,
        "ma60": trend.ma60 if trend else 0.0,
        "ma120": trend.ma120 if trend else None,
        "ma20_slope": trend.ma20_slope if trend else 0.0,
        "ma60_slope": trend.ma60_slope if trend else None,
        "drawdown_from_high_60": trend.drawdown_from_high_60 if trend else 0.0,
        "center_shift_20": trend.center_shift_20 if trend else 0.0,
        "price_position_60": trend.price_position_60 if trend else 0.5,
        "linear_trend_60": trend.linear_trend_60 if trend else 0.0,
        "drawdown_from_high_120": trend.drawdown_from_high_120 if trend else 0.0,
        "center_shift_40": trend.center_shift_40 if trend else 0.0,
        "return_20": trend.return_20 if trend else 0.0,
        "return_60": trend.return_60 if trend else 0.0,
        "downtrend_conditions": json.dumps(trend.downtrend_conditions) if trend else "[]",
    }


def re_evaluate_strategy2_task(
    config: dict,
    task_id: str,
    progress_callback=None,
) -> dict:
    """用已缓存的日线数据重跑策略2评估。

    不重新拉取数据，只重新应用流动性过滤和策略2引擎评估。
    旧候选会被新候选替换。
    """
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    stocks = db.get_task_stocks(task_id, limit=100000, offset=0)
    if not stocks:
        return {"task_id": task_id, "status": "no_stocks", "candidates_found": 0}

    liquidity_cfg = config.get("liquidity", {})
    kline_days = liquidity_cfg.get("min_listing_days", 350)
    engine = ExtremeDryStableStrategyEngine(config)
    old_candidates = {c["code"] for c in db.get_strategy2_candidates(task_id=task_id)}
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

            evaluation = engine.evaluate_at(data, code=code, name=name)

            if evaluation.passed:
                discovery = _build_strategy2_discovery(evaluation)
                db.upsert_strategy2_candidate(task_id, discovery)
                new_codes.add(code)
                if progress_callback:
                    progress_callback("discovery", len(new_codes), total,
                                      f"{code} {name}", discovery)
        except Exception:
            pass

        if progress_callback and (i + 1) % 100 == 0:
            progress_callback("scanning", i + 1, total, f"{code} {name}")

    # 移除不再符合条件的旧候选，同步更新 task_stocks 状态
    removed = old_candidates - new_codes
    if removed:
        conn = db.get_conn()
        for code in removed:
            conn.execute(
                "DELETE FROM strategy2_candidates WHERE task_id=? AND code=?",
                (task_id, code),
            )
            conn.execute(
                "UPDATE task_stocks SET status='scanned',"
                "  status_reason='POST_REVALUATE_REMOVED',"
                "  updated_at=datetime('now')"
                " WHERE task_id=? AND code=? AND status='candidate'",
                (task_id, code),
            )
        conn.commit()
        logger.info(
            "Strategy2 re-evaluate %s: removed %d candidates from DB",
            task_id, len(removed),
        )

    db.refresh_scan_task_counts(task_id)
    return {
        "task_id": task_id,
        "status": "completed",
        "candidates_found": len(new_codes),
        "total_stocks": total,
        "added": len(new_codes - old_candidates),
        "removed": len(removed),
    }
