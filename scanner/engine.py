# scanner/engine.py
import logging
import threading
import time
from dataclasses import dataclass
from queue import Queue
from typing import Callable

import scanner.db as db
from scanner.data_source import DataSourceManager
from scanner.sina_source import fetch_sina_daily
from scanner.tencent_source import fetch_tencent_daily
from scanner.index_source import fetch_market_index_daily
from scanner.liquidity_filter import passes_liquidity_filter
from scanner.pattern_detector import detect_cup_handle
from scanner.pattern_detector import CupHandleResult
from scanner.scorer import score_cup_handle_advanced
from analyzer.dry_stable import analyze_dry_stable

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
    from_cache: bool = False


def scan_all(config: dict, progress_callback=None, resume_task_id: str = None) -> dict:
    """双线程全市场扫描。

    Args:
        config: 完整配置
        progress_callback: 可选进度回调 fn(stage, current, total, detail)
        resume_task_id: 中断任务 ID，恢复时跳过已扫股票

    Returns:
        {"candidates": [...], "stats": {...}, "task_id": "..."}
    """
    from scanner.stock_pool import get_a_stock_pool

    # Initialize database
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    # 股票池加载（支持恢复模式）
    start_offset = 0
    stocks = None
    if resume_task_id:
        info = db.get_interrupted_task()
        if info:
            start_offset = info.get("scanned", 0)
            stocks = db.get_pending_stocks(resume_task_id, from_idx=start_offset)
    if not stocks:
        stocks = get_a_stock_pool(config)
        start_offset = 0
        # 保存股票列表供续扫
        if not resume_task_id:
            task_id = __import__('time').strftime("%Y%m%d-%H%M%S")
            db.save_task_stocks(task_id, stocks)

    stock_queue = Queue()
    for s in stocks:
        stock_queue.put(s)

    mgr = DataSourceManager()
    candidates = []
    candidate_lock = threading.Lock()
    scanned_count = [0]
    skip_count = [0]
    stats_lock = threading.Lock()

    # Merge config sections with handle key prefixing
    cup_cfg = config.get("cup", {})
    handle_cfg = config.get("handle", {})
    breakout_cfg = config.get("breakout", {})
    handle_prefixed = {f"handle_{k}": v for k, v in handle_cfg.items()}
    pattern_cfg = {**cup_cfg, **handle_prefixed, **breakout_cfg}
    liquidity_cfg = config.get("liquidity", {})
    scoring_cfg = config.get("scoring", {})
    market_data = fetch_market_index_daily()

    start_time = time.time()

    def worker(thread_name: str):
        while not stock_queue.empty():
            try:
                stock = stock_queue.get_nowait()
            except Exception:
                break

            ds = mgr.try_acquire_any()
            if ds is None:
                time.sleep(0.1)
                stock_queue.put(stock)
                continue

            code = stock["code"]
            try:
                # 优先拉取新鲜数据，缓存仅用于补齐历史
                fetch_result = _fetch_with_retry(code, ds, mgr=mgr)
                data = fetch_result.data
                if data is None:
                    if _is_transient_source_busy(fetch_result):
                        stock_queue.put(stock)
                        time.sleep(0.1)
                        continue
                    with stats_lock:
                        skip_count[0] += 1
                    continue

                # 上市天数过滤（日线数据不足即视为新股）
                min_listing = liquidity_cfg.get("min_listing_days", 250)
                if len(data) < min_listing:
                    with stats_lock:
                        skip_count[0] += 1
                    continue

                # 存储最新价等元数据
                stock["latest_close"] = data[-1]["close"]
                stock["latest_turnover"] = data[-1].get("turnover") or (data[-1]["volume"] * data[-1]["close"])

                # 流动性过滤
                if not passes_liquidity_filter(data, liquidity_cfg):
                    with stats_lock:
                        skip_count[0] += 1
                    continue

                # 杯柄检测
                result = detect_cup_handle(data, pattern_cfg)
                if result.found:
                    result.code = code
                    result.name = stock.get("name", "")
                    result.score = score_cup_handle_advanced(result, data, scoring_cfg)
                    dry_stable = analyze_dry_stable(result, data, market_data=market_data)
                else:
                    result = CupHandleResult(found=False, code=code, name=stock.get("name", ""))
                    dry_stable = analyze_dry_stable(result, data, market_data=market_data)
                    pattern20 = dry_stable["pattern_score"]["score"]
                    if dry_stable["pattern_score"].get("key_pattern_type") != "vcp" or pattern20 < 13:
                        dry_stable = None

                if dry_stable:
                    if result.score == 0:
                        result.score = min(100, dry_stable["pattern_score"]["score"] * 5)
                    stock["dry_stable"] = dry_stable
                    strategy_verdict = dry_stable["decision"]["verdict"]
                    if result.score >= scoring_cfg.get("medium_threshold", 70) - 10 and strategy_verdict != "不建议买入":
                        with candidate_lock:
                            candidates.append((stock, result))
                        # 通知发现新候选
                        if progress_callback:
                            progress_callback("discovery", len(candidates), len(stocks),
                                              f"{code} {stock.get('name','')}",
                                              {"code": code, "name": stock.get("name", ""),
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
                                               "market_position_advice": dry_stable["market_environment"]["position_advice"]})

                with stats_lock:
                    scanned_count[0] += 1

                if progress_callback:
                    progress_callback("scanning", scanned_count[0], len(stocks),
                                      f"{code} {stock.get('name','')}")

            except Exception as e:
                logger.error(f"Error scanning {code}: {e}")
                with stats_lock:
                    skip_count[0] += 1
            finally:
                mgr.release(ds)

    # 启动双线程
    t1 = threading.Thread(target=worker, args=("t1",), daemon=True)
    t2 = threading.Thread(target=worker, args=("t2",), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    elapsed = time.time() - start_time

    # 按评分排序
    candidates.sort(key=lambda x: x[1].score, reverse=True)

    return {
        "candidates": candidates,
        "stats": {
            "total_stocks": len(stocks),
            "scanned": scanned_count[0],
            "skipped": skip_count[0],
            "candidates_found": len(candidates),
            "elapsed_seconds": round(elapsed, 1),
            "speed": round(scanned_count[0] / elapsed, 1) if elapsed > 0 else 0,
        },
        "task_id": time.strftime("%Y%m%d-%H%M%S"),
    }


def _fetch_with_retry(
    code: str,
    primary_ds: str,
    retry_attempts: int = 2,
    fallback_attempts: int = 2,
    sleep_fn: Callable[[float], None] = time.sleep,
    mgr: DataSourceManager | None = None,
) -> FetchResult:
    """Fetch fresh K-line data first; cache is only used to merge history."""
    fallback_ds = "tencent" if primary_ds == "sina" else "sina"
    cached = db.get_ohlc(code)
    result = FetchResult(data=None, primary_source=primary_ds, fallback_source=fallback_ds)
    held_sources = {primary_ds} if mgr is not None else None

    data, attempts, error = _try_fetch_source(
        code,
        primary_ds,
        retry_attempts,
        sleep_fn,
        mgr=mgr,
        held_sources=held_sources,
    )
    result.primary_attempts = attempts
    result.primary_error = error
    if data:
        merged = _merge_data(cached or [], data)
        db.save_ohlc(code, merged)
        result.data = merged
        return result

    if mgr is not None:
        if not mgr.acquire(fallback_ds):
            result.fallback_attempts = 0
            result.fallback_error = "data source busy"
            return result
        try:
            data, attempts, error = _try_fetch_source(
                code,
                fallback_ds,
                fallback_attempts,
                sleep_fn,
                mgr=mgr,
                held_sources={primary_ds, fallback_ds},
            )
        finally:
            mgr.release(fallback_ds)
    else:
        data, attempts, error = _try_fetch_source(code, fallback_ds, fallback_attempts, sleep_fn)
    result.fallback_attempts = attempts
    result.fallback_error = error
    if data:
        merged = _merge_data(cached or [], data)
        db.save_ohlc(code, merged)
        result.data = merged
        return result

    return result


def _is_transient_source_busy(fetch_result: FetchResult) -> bool:
    if fetch_result.data is not None:
        return False
    return fetch_result.primary_error == "data source busy" or fetch_result.fallback_error == "data source busy"


def _try_fetch_source(
    code: str,
    ds_name: str,
    attempts: int,
    sleep_fn: Callable[[float], None],
    mgr: DataSourceManager | None = None,
    held_sources: set[str] | None = None,
) -> tuple[list[dict] | None, int, str | None]:
    fetch_fn = fetch_sina_daily if ds_name == "sina" else fetch_tencent_daily
    extra_sina_lock = False
    held_sources = held_sources or set()

    if mgr is not None and ds_name == "tencent" and "sina" not in held_sources:
        if not mgr.acquire("sina"):
            return None, 0, "data source busy"
        extra_sina_lock = True

    last_error = None
    try:
        for attempt in range(1, attempts + 1):
            try:
                data = fetch_fn(code)
                if data:
                    return data, attempt, None
                last_error = "empty response"
            except Exception as exc:
                last_error = str(exc)
            if attempt < attempts:
                sleep_fn(min(0.5 * attempt, 2.0))
        return None, attempts, last_error
    finally:
        if extra_sina_lock:
            mgr.release("sina")


def _merge_data(cached: list[dict], fresh: list[dict]) -> list[dict]:
    """合并缓存和新数据，去重按日期排序。"""
    seen = {d["date"]: d for d in cached}
    for d in fresh:
        seen[d["date"]] = d
    merged = sorted(seen.values(), key=lambda x: x["date"])
    return merged
