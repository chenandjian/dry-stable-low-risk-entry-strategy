# scanner/engine.py
import logging
import threading
import time
from queue import Queue

import scanner.db as db
from scanner.data_source import DataSourceManager
from scanner.sina_source import fetch_sina_daily
from scanner.tencent_source import fetch_tencent_daily
from scanner.liquidity_filter import passes_liquidity_filter
from scanner.pattern_detector import detect_cup_handle
from scanner.scorer import score_cup_handle

logger = logging.getLogger(__name__)


def scan_all(config: dict, progress_callback=None) -> dict:
    """双线程全市场扫描。

    Args:
        config: 完整配置
        progress_callback: 可选进度回调 fn(stage, current, total, detail)

    Returns:
        {"candidates": [...], "stats": {...}, "task_id": "..."}
    """
    from scanner.stock_pool import get_a_stock_pool

    # Initialize database
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    stocks = get_a_stock_pool(config)
    if not stocks:
        logger.error("Empty stock pool, aborting")
        return {"candidates": [], "stats": {"error": "empty_pool"}}

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
                # 三级回退获取数据
                data = _fetch_with_fallback(code, ds, mgr)
                if data is None:
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
                    result.score = score_cup_handle(result, scoring_cfg)
                    if result.score >= scoring_cfg.get("medium_threshold", 70) - 10:
                        with candidate_lock:
                            candidates.append((stock, result))

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


def _fetch_with_fallback(code: str, primary_ds: str, mgr: DataSourceManager):
    """三级回退：数据库缓存 → 主源 → 备用源。

    优化：先检查数据库缓存是否覆盖最近交易日。
    """
    from datetime import datetime, timedelta

    # 1. 先尝试数据库缓存
    cached = db.get_ohlc(code)
    if cached and _is_cache_fresh(cached):
        return cached

    # 2. 主数据源
    fetch_fn = fetch_sina_daily if primary_ds == "sina" else fetch_tencent_daily
    data = fetch_fn(code)

    if data:
        if cached:
            data = _merge_data(cached, data)
        db.save_ohlc(code, data)
        return data

    # 3. 回退另一个数据源
    other = "tencent" if primary_ds == "sina" else "sina"
    if mgr.acquire(other):
        try:
            fetch_fn2 = fetch_tencent_daily if other == "tencent" else fetch_sina_daily
            data = fetch_fn2(code)
            if data:
                if cached:
                    data = _merge_data(cached, data)
                db.save_ohlc(code, data)
                return data
        finally:
            mgr.release(other)

    # 4. 如果有过期缓存也返回
    if cached:
        return cached

    return None


def _is_cache_fresh(data: list[dict]) -> bool:
    """检查缓存是否覆盖最近一个交易日。"""
    if not data:
        return False
    from datetime import datetime, timedelta
    latest_date = data[-1]["date"]
    today = datetime.now()
    # 如果最新日期在最近2天内，认为缓存新鲜
    try:
        latest = datetime.strptime(latest_date, "%Y-%m-%d")
        return (today - latest).days <= 2
    except (ValueError, TypeError):
        return False


def _merge_data(cached: list[dict], fresh: list[dict]) -> list[dict]:
    """合并缓存和新数据，去重按日期排序。"""
    seen = {d["date"]: d for d in cached}
    for d in fresh:
        seen[d["date"]] = d
    merged = sorted(seen.values(), key=lambda x: x["date"])
    return merged
