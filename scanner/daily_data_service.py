# scanner/daily_data_service.py
"""共享日线数据拉取服务 — 从多数据源链逐级拉取、合并缓存、入库。

本模块只包含数据源选择、锁管理、重试和统一 FetchResult，
不包含任何策略判断。
策略1和策略2扫描器均通过本模块调用数据拉取能力。
"""
import json
import logging
import math
import time
from datetime import date, datetime, timedelta
from dataclasses import dataclass
from typing import Callable

import scanner.db as db
from scanner.data_source import DataSourceManager
from scanner.baidu_source import fetch_baidu_daily
from scanner.sina_source import fetch_sina_daily
from scanner.tencent_source import fetch_tencent_daily

logger = logging.getLogger(__name__)

DEFAULT_DAILY_SOURCES = ["baidu", "sina", "tencent"]
MARKET_CLOSE_TIME = "15:00:00"
MARKET_CLOSE_CONFIRM_TIME = "15:10:00"


@dataclass
class CacheFreshnessContext:
    """Cache freshness requirement for the latest completed trading day."""
    target_trade_date: str
    min_fetch_time: str | None = None
    fetched_at: str | None = None
    allow_previous_trade_date: bool = False
    quote_status: str | None = None


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
    kline_fetched_at: str | None = None
    kline_target_trade_date: str | None = None
    quote_status: str = "not_requested"

    def __post_init__(self):
        if self.source_errors is None:
            self.source_errors = {}


def _daily_fetch_fn(ds_name: str):
    """Map data source name to fetch function."""
    fetchers = {
        "baidu": fetch_baidu_daily,
        "sina": fetch_sina_daily,
        "tencent": fetch_tencent_daily,
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


def resolve_effective_worker_count(
    configured_workers: int | str | None,
    daily_sources: list[str] | None,
) -> int:
    """Resolve scan worker count so it never exceeds the enabled data source count."""
    source_count = len(daily_sources or DEFAULT_DAILY_SOURCES)
    if configured_workers is None:
        return max(1, source_count)
    return max(1, min(int(configured_workers), source_count))


def fetch_with_retry(
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
    """从数据源链逐级拉取K线数据。

    对每个数据源：获取锁（非阻塞）→ 拉取（带重试）→ 成功则合并缓存并保存。
    全部失败返回 FetchResult(data=None)。
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
            invalid_error = _validate_ohlc_data(data)
            if invalid_error:
                logger.warning("%s  %s  %s", code, ds_name, invalid_error)
                source_errors[ds_name] = f"attempts={used_attempts} error={invalid_error}"
                failed_sources.add(ds_name)
                continue
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
            quote_status = _classify_quote_status_after_fetch(merged, freshness_context)

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
                invalid_error = _validate_ohlc_data(data)
                if invalid_error:
                    return None, attempt, invalid_error
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


def select_fresh_cached_ohlc(
    cached: list[dict] | None,
    kline_days: int = 250,
    fresh_date: str | None = None,
    *,
    freshness_context: CacheFreshnessContext | None = None,
) -> list[dict] | None:
    """Return cached OHLC only when it covers the latest completed trade date."""
    if not cached:
        return None

    if freshness_context is None:
        target_date = fresh_date or date.today().isoformat()
        freshness_context = CacheFreshnessContext(target_trade_date=target_date)
    target_date = freshness_context.target_trade_date
    cached = trim_ohlc_to_target(cached, target_date)
    if not cached:
        return None
    latest_date = cached[-1].get("date")
    if latest_date == target_date:
        if not _fetch_time_is_fresh(freshness_context):
            return None
    elif not (
        freshness_context.allow_previous_trade_date
        and freshness_context.quote_status in {"suspended", "no_trade"}
        and latest_date < target_date
        and _fetch_time_is_fresh(freshness_context)
    ):
        return None

    if kline_days:
        return cached[-kline_days:]
    return cached


def trim_ohlc_to_target(
    data: list[dict] | None,
    target_trade_date: str | None,
) -> list[dict]:
    """Drop rows after target_trade_date so intraday rows never enter strategy input."""
    if not data:
        return []
    if not target_trade_date:
        return list(data)
    return [row for row in data if row.get("date") <= target_trade_date]


def strip_zero_volume_target_row(
    data: list[dict] | None,
    target_trade_date: str | None,
) -> tuple[list[dict], str | None]:
    """Remove an untrusted zero-volume flat row on the target trade date.

    Some sources publish a target-date placeholder for suspended/no-trade stocks:
    O=H=L=C with volume=0 and turnover=0. That row must not be treated as fresh
    tradable OHLC, otherwise it blocks fallback sources and pollutes daily_ohlc.
    """
    if not data:
        return [], None
    rows = list(data)
    if not target_trade_date:
        return rows, None
    latest = rows[-1]
    if latest.get("date") == target_trade_date and _is_zero_volume_flat_row(latest):
        return rows[:-1], f"zero-volume target trade date {target_trade_date}"
    return rows, None


def source_error_confirms_no_trade(error: str | None) -> bool:
    """Return true when a source conclusively did not provide target-day trading data."""
    if not isinstance(error, str):
        return False
    return (
        "missing target trade date" in error
        or "zero-volume target trade date" in error
    )


def compute_target_trade_date(
    now: datetime | None = None,
    *,
    close_confirm_time: str = MARKET_CLOSE_CONFIRM_TIME,
) -> str:
    """Compute latest completed trading date using weekday-only A-share calendar."""
    current = now or datetime.now()
    if _is_weekday_trade_date(current.date()):
        confirm = datetime.strptime(close_confirm_time, "%H:%M:%S").time()
        if current.time() >= confirm:
            return current.date().isoformat()
        return _previous_weekday(current.date()).isoformat()
    return _previous_weekday(current.date()).isoformat()


def build_cache_freshness_context(
    *,
    now: datetime | None = None,
    fetched_at: str | None = None,
    allow_previous_trade_date: bool = False,
    quote_status: str | None = None,
    market_close_time: str = MARKET_CLOSE_TIME,
    close_confirm_time: str = MARKET_CLOSE_CONFIRM_TIME,
) -> CacheFreshnessContext:
    """Build cache requirement for the current scan moment."""
    current = now or datetime.now()
    target = compute_target_trade_date(current, close_confirm_time=close_confirm_time)
    return CacheFreshnessContext(
        target_trade_date=target,
        min_fetch_time=f"{target} {market_close_time}",
        fetched_at=fetched_at,
        allow_previous_trade_date=allow_previous_trade_date,
        quote_status=quote_status,
    )


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


def _validate_ohlc_data(data: list[dict]) -> str | None:
    """Return a stable error string when fetched OHLC rows are not trustworthy."""
    for row in data:
        try:
            open_ = float(row["open"])
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            volume = float(row["volume"])
        except (TypeError, ValueError, KeyError):
            return "invalid OHLC structure"
        if not all(math.isfinite(v) for v in (open_, high, low, close, volume)):
            return "invalid OHLC values"
        if min(open_, high, low, close) <= 0 or volume < 0:
            return "invalid OHLC values"
        turnover = row.get("turnover")
        if turnover is not None:
            try:
                turnover_value = float(turnover)
            except (TypeError, ValueError):
                return "invalid OHLC values"
            if not math.isfinite(turnover_value) or turnover_value < 0:
                return "invalid OHLC values"
        if high < max(open_, close, low) or low > min(open_, close, high):
            return "invalid OHLC relationship"
    return None


def _is_zero_volume_flat_row(row: dict) -> bool:
    try:
        open_ = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        volume = float(row["volume"])
    except (TypeError, ValueError, KeyError):
        return False
    turnover = row.get("turnover", 0)
    try:
        turnover_value = float(turnover)
    except (TypeError, ValueError):
        return False
    return (
        volume == 0
        and turnover_value == 0
        and open_ == high == low == close
    )


def _fetch_time_is_fresh(context: CacheFreshnessContext) -> bool:
    if not context.min_fetch_time:
        return True
    if not context.fetched_at:
        return False
    return context.fetched_at >= context.min_fetch_time


def _classify_quote_status_after_fetch(
    data: list[dict],
    context: CacheFreshnessContext | None,
) -> str:
    if not data or context is None:
        return "not_requested"
    latest_date = data[-1].get("date")
    if (
        latest_date
        and latest_date < context.target_trade_date
        and context.min_fetch_time
    ):
        return "suspended"
    return "not_requested"


def _is_weekday_trade_date(day: date) -> bool:
    return day.weekday() < 5


def _previous_weekday(day: date) -> date:
    candidate = day - timedelta(days=1)
    while not _is_weekday_trade_date(candidate):
        candidate -= timedelta(days=1)
    return candidate


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
