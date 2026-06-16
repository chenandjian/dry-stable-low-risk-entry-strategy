from datetime import datetime

from scanner.daily_data_service import (
    CacheFreshnessContext,
    build_cache_freshness_context,
    compute_target_trade_date,
    select_fresh_cached_ohlc,
)


def _row(day: str, close: float = 10.0) -> dict:
    return {
        "date": day,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1_000_000,
        "turnover": close * 1_000_000,
    }


def test_target_trade_date_before_close_confirm_uses_previous_weekday():
    now = datetime(2026, 6, 15, 14, 0, 0)  # Monday

    assert compute_target_trade_date(now) == "2026-06-12"


def test_target_trade_date_after_close_confirm_uses_today():
    now = datetime(2026, 6, 15, 15, 10, 0)  # Monday

    assert compute_target_trade_date(now) == "2026-06-15"


def test_target_trade_date_on_weekend_uses_last_weekday():
    now = datetime(2026, 6, 20, 10, 0, 0)  # Saturday

    assert compute_target_trade_date(now) == "2026-06-19"


def test_cache_covering_target_is_rejected_when_fetched_before_close():
    rows = [_row("2026-06-15")]
    context = CacheFreshnessContext(
        target_trade_date="2026-06-15",
        min_fetch_time="2026-06-15 15:00:00",
        fetched_at="2026-06-15 14:58:00",
    )

    assert select_fresh_cached_ohlc(rows, kline_days=250, freshness_context=context) is None


def test_cache_covering_target_is_reused_when_fetched_after_close():
    rows = [_row("2026-06-13"), _row("2026-06-15")]
    context = CacheFreshnessContext(
        target_trade_date="2026-06-15",
        min_fetch_time="2026-06-15 15:00:00",
        fetched_at="2026-06-15 15:01:00",
    )

    assert select_fresh_cached_ohlc(rows, kline_days=1, freshness_context=context) == rows[-1:]


def test_cache_before_target_is_reused_for_marked_suspended_stock():
    rows = [_row("2026-06-12")]
    context = CacheFreshnessContext(
        target_trade_date="2026-06-15",
        min_fetch_time="2026-06-15 15:00:00",
        fetched_at="2026-06-15 15:12:00",
        allow_previous_trade_date=True,
        quote_status="suspended",
    )

    assert select_fresh_cached_ohlc(rows, kline_days=250, freshness_context=context) == rows


def test_build_cache_context_uses_weekday_calendar_only():
    context = build_cache_freshness_context(
        now=datetime(2026, 6, 15, 15, 15, 0),
        fetched_at="2026-06-15 15:11:00",
    )

    assert context.target_trade_date == "2026-06-15"
    assert context.min_fetch_time == "2026-06-15 15:00:00"
