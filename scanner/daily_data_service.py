# scanner/daily_data_service.py
"""共享日线数据拉取服务 — 从多数据源链逐级拉取、合并缓存、入库。

本模块只包含数据源选择、锁管理、重试和统一 FetchResult，
不包含任何策略判断。
策略1和策略2扫描器均通过本模块调用数据拉取能力。
"""
import json
import logging
import time
from dataclasses import dataclass
from typing import Callable

import scanner.db as db
from scanner.data_source import DataSourceManager
from scanner.baidu_source import fetch_baidu_daily
from scanner.sina_source import fetch_sina_daily
from scanner.tencent_source import fetch_tencent_daily
from scanner.yfinance_source import fetch_yfinance_daily

logger = logging.getLogger(__name__)

DEFAULT_DAILY_SOURCES = ["baidu", "sina", "tencent", "yfinance"]


@dataclass
class FetchResult:
    """统一的数据拉取结果。"""
    data: list[dict] | None
    primary_source: str
    fallback_source: str
    primary_attempts: int = 0
    fallback_attempts: int = 0
    primary_error: str | None = None
    fallback_error: str | None = None
    source_errors: dict = None
    from_cache: bool = False

    def __post_init__(self):
        if self.source_errors is None:
            self.source_errors = {}


def _daily_fetch_fn(ds_name: str):
    """Map data source name to fetch function."""
    fetchers = {
        "baidu": fetch_baidu_daily,
        "sina": fetch_sina_daily,
        "tencent": fetch_tencent_daily,
        "yfinance": fetch_yfinance_daily,
    }
    if ds_name not in fetchers:
        raise ValueError(f"Unknown daily data source: {ds_name}")
    return fetchers[ds_name]


def _normalize_source_chain(source_chain: list[str] | None, primary_ds: str) -> list[str]:
    """Build deduplicated source chain starting with primary_ds."""
    raw_chain = [primary_ds] + list(source_chain or DEFAULT_DAILY_SOURCES)
    chain = []
    for ds_name in raw_chain:
        if ds_name not in chain:
            chain.append(ds_name)
    return chain


def fetch_with_retry(
    code: str,
    primary_ds: str,
    retry_attempts: int = 2,
    fallback_attempts: int = 2,
    sleep_fn: Callable[[float], None] = time.sleep,
    mgr: DataSourceManager | None = None,
    source_chain: list[str] | None = None,
    kline_days: int = 250,
) -> FetchResult:
    """从数据源链逐级拉取K线数据。

    对每个数据源：获取锁（非阻塞）→ 拉取（带重试）→ 成功则合并缓存并保存。
    全部失败返回 FetchResult(data=None)。
    """
    chain = _normalize_source_chain(source_chain, primary_ds)
    cached = db.get_ohlc(code)
    saw_busy = False
    source_errors: dict[str, str] = {}
    failed_sources: set[str] = set()

    for i, ds_name in enumerate(chain):
        if ds_name in failed_sources:
            continue

        is_primary = (ds_name == chain[0])
        attempts = retry_attempts if is_primary else fallback_attempts

        locked = False
        if mgr is not None:
            if not mgr.acquire(ds_name):
                saw_busy = True
                source_errors[ds_name] = "busy"
                logger.debug("%s  %s  busy", code, ds_name)
                continue
            locked = True

        try:
            data, used_attempts, error = _try_fetch_source(code, ds_name, attempts, sleep_fn, kline_days)
        finally:
            if locked and mgr is not None:
                mgr.release(ds_name)

        if error:
            logger.warning("%s  %s  %s", code, ds_name, error)
            source_errors[ds_name] = f"attempts={used_attempts} error={error}"
            if "data source busy" in str(error):
                saw_busy = True
            failed_sources.add(ds_name)
            continue

        if data:
            merged = _merge_data(cached or [], data, max_rows=kline_days)
            db.save_ohlc(code, merged)

            recent = data[-1]
            prev = data[-2] if len(data) >= 2 else None
            parts = [f"{code}  {ds_name}  {len(data)}rows"]
            if prev:
                parts.append(f"{prev['date'][5:]}: O{prev['open']:.2f} H{prev['high']:.2f} L{prev['low']:.2f} C{prev['close']:.2f}")
            parts.append(f"{recent['date'][5:]}: O{recent['open']:.2f} H{recent['high']:.2f} L{recent['low']:.2f} C{recent['close']:.2f}")
            logger.info("  ".join(parts))

            result = FetchResult(
                data=merged,
                primary_source=chain[0],
                fallback_source=ds_name if ds_name != chain[0] else chain[0],
                source_errors=source_errors,
            )
            return _apply_source_compatibility_fields(
                result, chain, source_errors,
                selected_source=ds_name, selected_attempts=used_attempts,
            )

    # ACCEPT-S2-003: All sources failed — never use cache for a new scan.
    return _build_all_failed_result(chain, source_errors)


def _try_fetch_source(
    code: str,
    ds_name: str,
    attempts: int,
    sleep_fn: Callable[[float], None],
    kline_days: int = 250,
) -> tuple[list[dict] | None, int, str | None]:
    """尝试从单一数据源拉取（带重试和退避）。"""
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


def is_transient_source_busy(fetch_result: FetchResult) -> bool:
    """判断是否是瞬时数据源忙（需requeue），而非真实拉取失败。"""
    if fetch_result.data is not None:
        return False
    return fetch_result.primary_error == "data source busy" or fetch_result.fallback_error == "data source busy"


def merge_data(cached: list[dict], fresh: list[dict], max_rows: int = 0) -> list[dict]:
    """合并缓存和新数据，去重按日期排序。"""
    return _merge_data(cached, fresh, max_rows)


def encode_source_errors(source_errors: dict | None) -> str | None:
    """将 source_errors dict 编码为稳定 JSON 字符串。"""
    if not source_errors:
        return None
    return json.dumps(source_errors, ensure_ascii=False, separators=(",", ":"))


# ── private helpers ──────────────────────────────────────────────────────────

def _merge_data(cached: list[dict], fresh: list[dict], max_rows: int = 0) -> list[dict]:
    seen = {d["date"]: d for d in cached}
    for d in fresh:
        seen[d["date"]] = d
    merged = sorted(seen.values(), key=lambda x: x["date"])
    if max_rows and len(merged) > max_rows:
        merged = merged[-max_rows:]
    return merged


def _call_fetch_fn(fetch_fn, code: str, days: int) -> list[dict] | None:
    try:
        return fetch_fn(code, days=days)
    except TypeError:
        return fetch_fn(code)


def _classify_fetch_error(exc: Exception) -> str:
    text = str(exc)
    if "456" in text or "429" in text:
        return "data source busy"
    return text


def _apply_source_compatibility_fields(
    result: FetchResult,
    chain: list[str],
    source_errors: dict[str, str],
    *,
    selected_source: str | None = None,
    selected_attempts: int = 0,
) -> FetchResult:
    primary = chain[0]
    result.primary_source = primary
    primary_entry = source_errors.get(primary)
    if primary_entry is not None:
        attempts, error = _parse_source_error_entry(primary_entry)
        result.primary_attempts = attempts
        result.primary_error = "data source busy" if primary_entry == "busy" else error
    elif selected_source == primary:
        result.primary_attempts = selected_attempts
        result.primary_error = None

    if selected_source and selected_source != primary:
        result.fallback_source = selected_source
        result.fallback_attempts = selected_attempts
        if result.data is None:
            fb_entry = source_errors.get(selected_source, "")
            if fb_entry:
                _, fb_error = _parse_source_error_entry(fb_entry)
                result.fallback_error = "data source busy" if fb_entry == "busy" else fb_error
        else:
            result.fallback_error = None
    else:
        if result.data is None:
            result.fallback_source = primary
            result.fallback_attempts = result.primary_attempts
            result.fallback_error = result.primary_error
        else:
            result.fallback_source = primary
            result.fallback_attempts = 0
            result.fallback_error = None

    return result


def _build_all_failed_result(chain: list[str], source_errors: dict[str, str]) -> FetchResult:
    result = FetchResult(data=None, primary_source=chain[0], fallback_source=chain[-1],
                         source_errors=source_errors)
    selected_source = None
    for ds_name in reversed(chain):
        entry = source_errors.get(ds_name, "")
        if entry and entry != "busy":
            selected_source = ds_name
            break

    if selected_source is None:
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

    if selected_source == chain[0] and len(chain) > 1:
        busy_fallbacks = [ds for ds in chain[1:] if source_errors.get(ds) == "busy"]
        if busy_fallbacks:
            result.fallback_source = busy_fallbacks[-1]
            result.fallback_attempts = 0
            result.fallback_error = "data source busy"
        else:
            result.fallback_source = result.primary_source
            result.fallback_attempts = result.primary_attempts
            result.fallback_error = result.primary_error

    return result


def _parse_source_error_entry(entry: str) -> tuple[int, str | None]:
    if not entry or entry == "busy":
        return 0, entry or None
    attempts = 0
    error = None
    if " error=" in entry:
        head, error = entry.split(" error=", 1)
        for part in head.split(" "):
            if part.startswith("attempts="):
                try:
                    attempts = int(part.split("=", 1)[1])
                except ValueError:
                    pass
    else:
        for part in entry.split(" "):
            if part.startswith("attempts="):
                try:
                    attempts = int(part.split("=", 1)[1])
                except ValueError:
                    pass
    return attempts, error
