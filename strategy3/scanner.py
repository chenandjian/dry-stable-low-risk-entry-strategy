"""策略3全市场扫描编排。"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from queue import Queue

import scanner.db as db
from scanner.daily_data_service import (
    DEFAULT_DAILY_SOURCES,
    build_cache_freshness_context,
    encode_source_errors,
    fetch_with_retry,
    is_transient_source_busy,
)
from scanner.data_source import DataSourceManager
from scanner.index_source import fetch_market_index_daily
from scanner.liquidity_filter import passes_liquidity_filter
from strategy3.engine import StrongPullbackSecondBreakoutEngine

logger = logging.getLogger(__name__)

STRATEGY3_TYPE = "STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT"


def scan_strategy3_all(
    config: dict,
    progress_callback=None,
    task_id: str | None = None,
    stocks: list[dict] | None = None,
    worker_count: int = 4,
    retry_policy: str = "normal",
) -> dict:
    """执行策略3全市场扫描。"""
    from scanner.stock_pool import get_a_stock_pool

    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    if task_id is None:
        task_id = time.strftime("%Y%m%d-%H%M%S")
    if stocks is None:
        stocks = get_a_stock_pool(config)
        db.save_task_stocks(task_id, stocks)

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
    engine = StrongPullbackSecondBreakoutEngine(config)
    market_data_full, market_fallback_reason = _load_market_data(config)
    candidate_by_code = {}
    candidate_lock = threading.Lock()
    busy_retries_by_code: dict[str, int] = {}
    busy_retry_lock = threading.Lock()
    start_time = time.time()

    def _now() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

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
            progress_callback("scanning", summary["processed"], summary["total_stocks"], f"{code} {name}")

    def worker():
        while not stock_queue.empty():
            try:
                stock = stock_queue.get_nowait()
            except Exception:
                break

            code = stock["code"]
            name = stock.get("name", "")
            fetch_result = None
            try:
                freshness_context = _cache_freshness_context(code)
                db.update_task_stock(
                    task_id, code, status="fetching",
                    primary_source=daily_sources[0],
                    fallback_source=daily_sources[-1],
                    started_at=_now(),
                )
                attempts = 3 if retry_policy == "failed_only" else 2
                fetch_result = fetch_with_retry(
                    code, daily_sources[0],
                    retry_attempts=attempts,
                    fallback_attempts=attempts,
                    mgr=mgr,
                    source_chain=daily_sources,
                    kline_days=kline_days,
                    freshness_context=freshness_context,
                )
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
                if not passes_liquidity_filter(data, liquidity_cfg):
                    _finish_stock(code, name, "skipped",
                                  status_reason=suspended_reason or "LIQUIDITY_FILTER_REJECTED",
                                  kline_latest_date=latest_trade_date,
                                  fetch_result=fetch_result)
                    continue

                market_window = _select_market_window(market_data_full, latest_trade_date)
                evaluation = engine.evaluate_at(data, code=code, name=name, market_data=market_window)
                _mark_market_fallback(evaluation, market_fallback_reason, market_window)
                if evaluation.passed:
                    discovery = _build_strategy3_discovery(evaluation, fetch_result)
                    try:
                        db.upsert_strategy3_candidate(task_id, discovery)
                    except Exception as exc:
                        logger.error("Failed to upsert strategy3 candidate %s: %s", code, exc)
                        _finish_stock(code, name, "failed",
                                      status_reason="STRATEGY3_CANDIDATE_PERSIST_FAILED",
                                      error_detail=str(exc),
                                      kline_latest_date=latest_trade_date,
                                      fetch_result=fetch_result)
                        continue
                    with candidate_lock:
                        candidate_by_code[code] = evaluation
                    _finish_stock(code, name, "candidate",
                                  status_reason=suspended_reason,
                                  kline_latest_date=latest_trade_date,
                                  fetch_result=fetch_result)
                    if progress_callback:
                        progress_callback("discovery", len(candidate_by_code), len(stocks),
                                          f"{code} {name}", discovery)
                else:
                    _finish_stock(
                        code, name, "scanned",
                        status_reason=suspended_reason or evaluation.status_reason,
                        error_detail=_evaluation_debug_json(evaluation),
                        kline_latest_date=latest_trade_date,
                        fetch_result=fetch_result,
                    )
                with busy_retry_lock:
                    busy_retries_by_code.pop(code, None)
            except Exception as exc:
                logger.error("Strategy3 error scanning %s: %s", code, exc)
                _finish_stock(code, name, "failed",
                              status_reason="STRATEGY3_EVALUATION_ERROR",
                              error_detail=str(exc),
                              fetch_result=fetch_result)
                with busy_retry_lock:
                    busy_retries_by_code.pop(code, None)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(worker_count)]
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


def _build_strategy3_discovery(evaluation, fetch_result=None) -> dict:
    """Build strategy3 candidate dict for persistence and frontend."""
    ind = evaluation.indicators
    risk = evaluation.risk
    return {
        "code": evaluation.code,
        "name": evaluation.name,
        "evaluation_date": evaluation.evaluation_date,
        "total_score": evaluation.total_score,
        "level": evaluation.level,
        "trend_score": evaluation.trend_score,
        "pullback_score": evaluation.pullback_score,
        "volume_stability_score": evaluation.volume_stability_score,
        "second_breakout_score": evaluation.second_breakout_score,
        "risk_reward_score": evaluation.risk_reward_score,
        "current_close": evaluation.current_close,
        "ma5": ind.ma5,
        "ma10": ind.ma10,
        "ma20": ind.ma20,
        "ma60": ind.ma60,
        "ma120": ind.ma120,
        "recent_high": ind.recent_high,
        "pullback_pct": ind.pullback_pct,
        "relative_strength_60": ind.relative_strength_60,
        "volume_ratio_5_20": ind.volume_ratio_5_20,
        "v3": ind.v3,
        "v5": ind.v5,
        "v10": ind.v10,
        "v20": ind.v20,
        "return_5": ind.return_5,
        "min_close_5": ind.min_close_5,
        "min_close_10": ind.min_close_10,
        "no_new_low": ind.no_new_low,
        "support_price_10": ind.support_price_10,
        "support_test_count": ind.support_test_count,
        "support_valid": ind.support_valid,
        "bear_body_shrink": ind.bear_body_shrink,
        "lower_shadow_count": ind.lower_shadow_count,
        "down_volume_ratio_5": ind.down_volume_ratio_5,
        "atr_ratio_5_20": ind.atr_ratio_5_20,
        "has_big_down_volume": ind.has_big_down_volume,
        "range_5": ind.range_5,
        "close_range_5": ind.close_range_5,
        "support_price": risk.support_price,
        "stop_loss": risk.stop_loss,
        "target_1": risk.target_1,
        "risk_ratio": risk.risk_ratio,
        "rr1": risk.rr1,
        "structural_support": risk.structural_support,
        "structural_stop_loss": risk.structural_stop_loss,
        "structural_risk_ratio": risk.structural_risk_ratio,
        "structural_rr1": risk.structural_rr1,
        "tactical_support": risk.tactical_support,
        "tactical_stop_loss": risk.tactical_stop_loss,
        "tactical_risk_ratio": risk.tactical_risk_ratio,
        "tactical_rr1": risk.tactical_rr1,
        "support_quality": risk.support_quality,
        "score_reasons": evaluation.score_reasons,
        "reject_reasons": evaluation.reject_reasons,
        "data_source": fetch_result.primary_source if fetch_result else "",
    }


def re_evaluate_strategy3_task(config: dict, task_id: str, progress_callback=None) -> dict:
    """用本地缓存日线重跑策略3评估，不重新拉取数据。"""
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    stocks = db.get_task_stocks(task_id, limit=100000, offset=0)
    if not stocks:
        return {"task_id": task_id, "status": "no_stocks", "candidates_found": 0}

    liquidity_cfg = config.get("liquidity", {})
    kline_days = liquidity_cfg.get("min_listing_days", 350)
    engine = StrongPullbackSecondBreakoutEngine(config)
    market_data_full, market_fallback_reason = _load_market_data(config)
    old_candidates = {c["code"] for c in db.get_strategy3_candidates(task_id=task_id)}
    total = len(stocks)
    new_codes = set()

    for i, stock in enumerate(stocks):
        code = stock["code"]
        name = stock.get("name", "")
        data = db.get_ohlc(code, max_rows=kline_days)
        if not data:
            db.update_task_stock(
                task_id,
                code,
                status="failed",
                status_reason="MISSING_LOCAL_OHLC",
                error_detail="No local OHLC data for strategy3 re-evaluation",
                finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
            continue
        latest_trade_date = data[-1].get("date") if data else None
        try:
            if not passes_liquidity_filter(data, liquidity_cfg):
                db.update_task_stock(
                    task_id,
                    code,
                    status="skipped",
                    status_reason="LIQUIDITY_FILTER_REJECTED",
                    error_detail=None,
                    kline_latest_date=latest_trade_date,
                    finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                )
                continue
            market_window = _select_market_window(market_data_full, latest_trade_date)
            evaluation = engine.evaluate_at(data, code=code, name=name, market_data=market_window)
            _mark_market_fallback(evaluation, market_fallback_reason, market_window)
            if evaluation.passed:
                discovery = _build_strategy3_discovery(evaluation)
                db.upsert_strategy3_candidate(task_id, discovery)
                db.update_task_stock(
                    task_id,
                    code,
                    status="candidate",
                    status_reason=None,
                    error_detail=None,
                    kline_latest_date=latest_trade_date,
                    finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                )
                new_codes.add(code)
                if progress_callback:
                    progress_callback("discovery", len(new_codes), total, f"{code} {name}", discovery)
            else:
                db.update_task_stock(
                    task_id,
                    code,
                    status="scanned",
                    status_reason=evaluation.status_reason,
                    error_detail=_evaluation_debug_json(evaluation),
                    kline_latest_date=latest_trade_date,
                    finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                )
        except Exception as exc:
            logger.error("Strategy3 re-evaluate error %s: %s", code, exc)
            db.update_task_stock(
                task_id,
                code,
                status="failed",
                status_reason="STRATEGY3_EVALUATION_ERROR",
                error_detail=str(exc),
                kline_latest_date=latest_trade_date,
                finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )

        if progress_callback and (i + 1) % 100 == 0:
            progress_callback("scanning", i + 1, total, f"{code} {name}")

    removed = old_candidates - new_codes
    if removed:
        conn = db.get_conn()
        for code in removed:
            conn.execute("DELETE FROM strategy3_candidates WHERE task_id=? AND code=?", (task_id, code))
            conn.execute(
                "UPDATE task_stocks SET status='scanned', status_reason='POST_REVALUATE_REMOVED',"
                " updated_at=datetime('now') WHERE task_id=? AND code=? AND status='candidate'",
                (task_id, code),
            )
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


def _evaluation_debug_json(evaluation) -> str:
    return json.dumps({
        "totalScore": evaluation.total_score,
        "level": evaluation.level,
        "rejectReasons": evaluation.reject_reasons,
        "scoreReasons": evaluation.score_reasons,
        "pullbackPct": evaluation.indicators.pullback_pct,
        "return5": evaluation.indicators.return_5,
        "noNewLow": evaluation.indicators.no_new_low,
        "supportTestCount": evaluation.indicators.support_test_count,
        "supportValid": evaluation.indicators.support_valid,
        "downVolumeRatio5": evaluation.indicators.down_volume_ratio_5,
        "atrRatio5_20": evaluation.indicators.atr_ratio_5_20,
        "riskRatio": evaluation.risk.risk_ratio,
        "rr1": evaluation.risk.rr1,
    }, ensure_ascii=False)


def _load_market_data(config: dict) -> tuple[list[dict], str | None]:
    market_cfg = config.get("market_environment", {}) or {}
    symbol = market_cfg.get("index_symbol")
    try:
        market_data = fetch_market_index_daily(symbol) or []
    except Exception as exc:
        logger.warning("Strategy3 market index fetch failed: %s", exc)
        return [], "NO_MARKET_DATA_RELATIVE_STRENGTH_FALLBACK"
    if not market_data:
        logger.warning("Strategy3 market index unavailable, relative strength falls back to stock return")
        return [], "NO_MARKET_DATA_RELATIVE_STRENGTH_FALLBACK"
    return market_data, None


def _select_market_window(market_data: list[dict], decision_date: str | None) -> list[dict]:
    if not market_data or not decision_date:
        return []
    window = [
        row for row in market_data
        if isinstance(row, dict) and row.get("date") and row.get("date") <= decision_date
    ]
    if not window or window[-1].get("date") != decision_date:
        return []
    return window


def _mark_market_fallback(evaluation, fallback_reason: str | None, market_window: list[dict]) -> None:
    if not market_window:
        fallback_reason = fallback_reason or "NO_MARKET_DATA_RELATIVE_STRENGTH_FALLBACK"
    if fallback_reason and not market_window and fallback_reason not in evaluation.score_reasons:
        evaluation.score_reasons.append(fallback_reason)
