# scanner/engine.py
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from queue import Queue
from typing import Callable

import scanner.db as db
from scanner.data_source import DataSourceManager
from scanner.mootdx_source import fetch_mootdx_daily
from scanner.baidu_source import fetch_baidu_daily
from scanner.sina_source import fetch_sina_daily
from scanner.tencent_source import fetch_tencent_daily
from scanner.index_source import fetch_market_index_daily
from scanner.liquidity_filter import passes_liquidity_filter
from scanner.pattern_detector import CupHandleResult
from analyzer.dry_stable import analyze_dry_stable
from scanner.strategy_engine import CupHandleStrategyEngine, CANDIDATE_KEYS, REJECT_KEYS

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


def scan_all(
    config: dict,
    progress_callback=None,
    resume_task_id: str = None,
    task_id: str = None,
    stocks: list[dict] = None,
    retry_policy: str = "normal",
    worker_count: int = 2,
) -> dict:
    """双线程全市场扫描。"""
    from scanner.stock_pool import get_a_stock_pool

    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    if task_id is None:
        task_id = resume_task_id or time.strftime("%Y%m%d-%H%M%S")

    start_offset = 0
    if stocks is None and resume_task_id:
        info = db.get_interrupted_task()
        if info:
            start_offset = info.get("scanned", 0)
            stocks = db.get_pending_stocks(resume_task_id, from_idx=start_offset)

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
    if configured_workers is not None and worker_count == 2:
        worker_count = configured_workers
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
    scoring_cfg = config.get("scoring", {})
    daily_sources = config.get("data", {}).get("daily_sources") or DEFAULT_DAILY_SOURCES
    kline_days = config.get("data", {}).get("daily_kline_days") or liquidity_cfg.get("min_listing_days", 250)
    strategy_engine = CupHandleStrategyEngine(config)
    max_busy_retries = config.get("data", {}).get("source_busy_max_retries", 3)
    market_data = fetch_market_index_daily()

    start_time = time.time()

    def _now() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    def worker(thread_name: str):
        while not stock_queue.empty():
            try:
                stock = stock_queue.get_nowait()
            except Exception:
                break

            code = stock["code"]
            try:
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
                min_listing = liquidity_cfg.get("min_listing_days", 250)
                if len(data) < min_listing:
                    db.update_task_stock(
                        task_id,
                        code,
                        status="skipped",
                        status_reason="上市天数不足",
                        kline_latest_date=latest_trade_date,
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

                evaluation = strategy_engine.evaluate_at(
                    data,
                    code=code,
                    name=stock.get("name", ""),
                    market_data=market_data,
                )
                result = evaluation.result
                dry_stable = evaluation.dry_stable
                if not result.found:
                    result = CupHandleResult(found=False, code=code, name=stock.get("name", ""))
                    dry_stable = analyze_dry_stable(result, data, market_data=market_data, config=config)
                    pattern20 = dry_stable["pattern_score"]["score"]
                    if dry_stable["pattern_score"].get("key_pattern_type") != "vcp" or pattern20 < 13:
                        dry_stable = None

                is_candidate = False
                if dry_stable:
                    if result.score == 0:
                        result.score = min(100, dry_stable["pattern_score"]["score"] * 5)
                    stock["dry_stable"] = dry_stable
                    strategy_verdict = dry_stable["decision"]["verdict"]
                    verdict_key = dry_stable["decision"].get("verdict_key", "")
                    if result.score >= scoring_cfg.get("medium_threshold", 70) - 10 and strategy_verdict not in REJECT_KEYS and verdict_key in CANDIDATE_KEYS:
                        with candidate_lock:
                            candidate_by_code[code] = (stock, result)
                            unique_candidates = len(candidate_by_code)
                        is_candidate = True
                        db.update_task_stock(
                            task_id,
                            code,
                            status="candidate",
                            kline_latest_date=latest_trade_date,
                            quote_status="not_requested",
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

                if not is_candidate:
                    db.update_task_stock(
                        task_id,
                        code,
                        status="scanned",
                        kline_latest_date=latest_trade_date,
                        quote_status="not_requested",
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
    scoring_cfg = config.get("scoring", {})
    kline_days = config.get("data", {}).get("daily_kline_days") or liquidity_cfg.get("min_listing_days", 250)
    strategy_engine = CupHandleStrategyEngine(config)
    market_data = fetch_market_index_daily()
    old_candidates = {c["code"] for c in db.get_candidates(task_id=task_id)}
    min_score = scoring_cfg.get("medium_threshold", 70) - 10
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

            evaluation = strategy_engine.evaluate_at(
                data, code=code, name=name, market_data=market_data,
            )
            result = evaluation.result
            dry_stable = evaluation.dry_stable

            if not result.found:
                result = CupHandleResult(found=False, code=code, name=name)
                dry_stable = analyze_dry_stable(result, data, market_data=market_data, config=config)
                pat20 = dry_stable["pattern_score"]["score"]
                if dry_stable["pattern_score"].get("key_pattern_type") != "vcp" or pat20 < 13:
                    dry_stable = None

            if dry_stable:
                if result.score == 0:
                    result.score = min(100, dry_stable["pattern_score"]["score"] * 5)
                verdict = dry_stable["decision"]["verdict"]
                verdict_key = dry_stable["decision"].get("verdict_key", "")
                if result.score >= min_score and verdict not in REJECT_KEYS and verdict_key in CANDIDATE_KEYS:
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
        "mootdx": fetch_mootdx_daily,
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


def _manager_handles_source(mgr: DataSourceManager | None, ds_name: str) -> bool:
    if mgr is None:
        return False
    locks = getattr(mgr, "_locks", None)
    if isinstance(locks, dict):
        return ds_name in locks
    acquire_results = getattr(mgr, "acquire_results", None)
    if isinstance(acquire_results, dict):
        return ds_name in acquire_results
    return True


def _try_source_with_lock(
    code: str,
    ds_name: str,
    attempts: int,
    sleep_fn: Callable[[float], None],
    kline_days: int,
    mgr: DataSourceManager | None,
) -> tuple[str, list[dict] | None, int, str | None]:
    """Try a single source, acquiring/releasing its lock if managed."""
    if _manager_handles_source(mgr, ds_name):
        if not mgr.acquire(ds_name):
            return ds_name, None, 0, "data source busy"
        try:
            data, attempts, error = _try_fetch_source(code, ds_name, attempts, sleep_fn, kline_days)
        finally:
            mgr.release(ds_name)
    else:
        data, attempts, error = _try_fetch_source(code, ds_name, attempts, sleep_fn, kline_days)
    return ds_name, data, attempts, error


def _fetch_with_retry(
    code: str,
    primary_ds: str,
    retry_attempts: int = 2,
    fallback_attempts: int = 2,
    sleep_fn: Callable[[float], None] = time.sleep,
    mgr: DataSourceManager | None = None,
    source_chain: list[str] | None = None,
    kline_days: int = 250,
) -> FetchResult:
    """Fetch fresh K-line data concurrently from all configured sources."""
    chain = _normalize_source_chain(source_chain, primary_ds)
    cached = db.get_ohlc(code)
    fetched_source = chain[0]

    with ThreadPoolExecutor(max_workers=len(chain)) as executor:
        futures = {}
        for ds_name in chain:
            attempts = retry_attempts if ds_name == chain[0] else fallback_attempts
            futures[executor.submit(
                _try_source_with_lock, code, ds_name, attempts, sleep_fn, kline_days, mgr
            )] = ds_name

        saw_source_busy = False
        for future in as_completed(futures):
            ds_name = futures[future]
            try:
                _, data, attempts, error = future.result()
            except Exception:
                logger.warning("%s  %s  ✗ exception", code, ds_name)
                continue

            if error == "data source busy":
                saw_source_busy = True
                logger.debug("%s  %s  ⏳ busy", code, ds_name)
                continue

            if data:
                merged = _merge_data(cached or [], data, max_rows=kline_days)
                db.save_ohlc(code, merged)
                fetched_source = ds_name
                for f in futures:
                    f.cancel()

                recent = data[-1]
                prev = data[-2] if len(data) >= 2 else None
                parts = [f"{code}  {ds_name}  {len(data)}行"]
                if prev:
                    parts.append(f"{prev['date'][5:]}: O{prev['open']:.2f} H{prev['high']:.2f} L{prev['low']:.2f} C{prev['close']:.2f}")
                parts.append(f"{recent['date'][5:]}: O{recent['open']:.2f} H{recent['high']:.2f} L{recent['low']:.2f} C{recent['close']:.2f}")
                # Log which sources were skipped
                skipped = [n for n in chain if n != ds_name]
                if skipped:
                    parts.append(f"(跳过: {','.join(skipped)})")
                logger.info("  ".join(parts))

                return FetchResult(
                    data=merged,
                    primary_source=chain[0],
                    fallback_source=ds_name if ds_name != chain[0] else chain[0],
                    primary_attempts=attempts if ds_name == chain[0] else 0,
                    fallback_attempts=attempts if ds_name != chain[0] else 0,
                )
            else:
                logger.warning("%s  %s  ✗ %s", code, ds_name, error)

    result = FetchResult(data=None, primary_source=chain[0], fallback_source=chain[-1])
    if saw_source_busy:
        result.fallback_error = "data source busy"
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



def _classify_fetch_error(exc: Exception) -> str:
    text = str(exc)
    if "456" in text or "429" in text:
        return "data source busy"
    return text


def _call_fetch_fn(fetch_fn, code: str, days: int) -> list[dict] | None:
    try:
        return fetch_fn(code, days=days)
    except TypeError:
        return fetch_fn(code)


def _merge_data(cached: list[dict], fresh: list[dict], max_rows: int = 0) -> list[dict]:
    """合并缓存和新数据，去重按日期排序。可限制最大行数。"""
    seen = {d["date"]: d for d in cached}
    for d in fresh:
        seen[d["date"]] = d
    merged = sorted(seen.values(), key=lambda x: x["date"])
    if max_rows and len(merged) > max_rows:
        merged = merged[-max_rows:]
    return merged
