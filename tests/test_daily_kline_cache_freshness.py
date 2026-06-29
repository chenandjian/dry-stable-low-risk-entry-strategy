from datetime import datetime

from scanner.daily_data_service import (
    CacheFreshnessContext,
    build_cache_freshness_context,
    compute_target_trade_date,
    fetch_with_retry,
    is_transient_source_busy,
    resolve_effective_worker_count,
    select_fresh_cached_ohlc,
)
from scanner import db


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


def _invalid_high_row(day: str) -> dict:
    return {
        "date": day,
        "open": 10.0,
        "high": 9.8,
        "low": 9.5,
        "close": 9.9,
        "volume": 1_000_000,
        "turnover": 9_900_000,
    }


def _nan_open_row(day: str) -> dict:
    row = _row(day)
    row["open"] = float("nan")
    return row


def _infinite_turnover_row(day: str) -> dict:
    row = _row(day)
    row["turnover"] = float("inf")
    return row


def _zero_volume_flat_row(day: str, close: float = 10.0) -> dict:
    row = _row(day, close)
    row["volume"] = 0
    row["turnover"] = 0
    return row


class FakeManager:
    def __init__(self, acquire_results: dict[str, bool]):
        self.acquire_results = acquire_results
        self.acquire_calls = []
        self.release_calls = []

    def acquire(self, ds_name):
        self.acquire_calls.append(ds_name)
        return self.acquire_results.get(ds_name, False)

    def release(self, ds_name):
        self.release_calls.append(ds_name)


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


def test_cache_with_intraday_future_row_is_trimmed_to_target_trade_date():
    rows = [_row("2026-06-13"), _row("2026-06-15"), _row("2026-06-16")]
    context = CacheFreshnessContext(
        target_trade_date="2026-06-15",
        min_fetch_time="2026-06-15 15:00:00",
        fetched_at="2026-06-16 12:20:00",
    )

    selected = select_fresh_cached_ohlc(rows, kline_days=250, freshness_context=context)

    assert selected == rows[:2]


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


def test_effective_worker_count_never_exceeds_enabled_daily_source_count():
    assert resolve_effective_worker_count(4, ["baidu", "sina", "tencent"]) == 3
    assert resolve_effective_worker_count(2, ["baidu", "sina", "tencent"]) == 2
    assert resolve_effective_worker_count(None, ["baidu", "sina", "tencent"]) == 3


def test_fetch_after_close_skips_source_missing_target_and_uses_fallback(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    stale_sina = [_row("2026-06-15", close=10.0)]
    fresh_tencent = [_row("2026-06-16", close=11.0)]
    calls = []

    def fake_try_fetch(code, ds_name, attempts, sleep_fn, kline_days):
        calls.append(ds_name)
        if ds_name == "sina":
            return stale_sina, 1, None
        if ds_name == "tencent":
            return fresh_tencent, 1, None
        return None, 1, "empty response"

    monkeypatch.setattr("scanner.daily_data_service._try_fetch_source", fake_try_fetch)
    context = CacheFreshnessContext(
        target_trade_date="2026-06-16",
        min_fetch_time="2026-06-16 15:00:00",
    )

    result = fetch_with_retry(
        "000831",
        "sina",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["sina", "tencent"],
        kline_days=250,
        freshness_context=context,
    )

    assert calls == ["sina", "tencent"]
    assert result.data[-1]["date"] == "2026-06-16"
    assert result.fallback_source == "tencent"
    assert result.quote_status == "not_requested"


def test_fetch_after_close_does_not_return_stale_intraday_cached_target_when_all_sources_miss(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("000831", [_row("2026-06-15", close=10.0), _row("2026-06-16", close=99.0)])

    def fake_try_fetch(code, ds_name, attempts, sleep_fn, kline_days):
        return [_row("2026-06-15", close=10.0)], 1, None

    monkeypatch.setattr("scanner.daily_data_service._try_fetch_source", fake_try_fetch)
    context = CacheFreshnessContext(
        target_trade_date="2026-06-16",
        min_fetch_time="2026-06-16 15:00:00",
    )

    result = fetch_with_retry(
        "000831",
        "sina",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["sina", "tencent"],
        kline_days=250,
        freshness_context=context,
    )

    assert result.quote_status == "suspended"
    assert result.data[-1]["date"] == "2026-06-15"
    assert db.get_ohlc("000831")[-1]["date"] == "2026-06-15"


def test_fetch_after_close_does_not_mark_suspended_when_other_sources_are_busy(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    calls = []
    mgr = FakeManager({"baidu": False, "sina": True, "tencent": False})

    def fake_try_fetch(code, ds_name, attempts, sleep_fn, kline_days):
        calls.append(ds_name)
        return [_row("2026-06-26", close=10.0)], 1, None

    monkeypatch.setattr("scanner.daily_data_service._try_fetch_source", fake_try_fetch)
    context = CacheFreshnessContext(
        target_trade_date="2026-06-29",
        min_fetch_time="2026-06-29 15:00:00",
    )

    result = fetch_with_retry(
        "000921",
        "baidu",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        mgr=mgr,
        source_chain=["baidu", "sina", "tencent"],
        kline_days=250,
        freshness_context=context,
    )

    assert calls == ["sina"]
    assert result.data is None
    assert is_transient_source_busy(result) is True
    assert result.primary_error == "data source busy"
    assert "missing target trade date 2026-06-29" in result.fallback_error
    assert result.source_errors == {
        "baidu": "busy",
        "sina": "attempts=1 error=missing target trade date 2026-06-29",
        "tencent": "busy",
    }
    assert not db.get_ohlc("000921")


def test_fetch_after_close_skips_zero_volume_target_row_and_uses_fallback(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    zero_volume_sina = [
        _row("2026-06-26", close=14.14),
        _zero_volume_flat_row("2026-06-29", close=14.14),
    ]
    fresh_tencent = [_row("2026-06-26", close=14.14), _row("2026-06-29", close=14.5)]
    calls = []

    def fake_try_fetch(code, ds_name, attempts, sleep_fn, kline_days):
        calls.append(ds_name)
        if ds_name == "sina":
            return zero_volume_sina, 1, None
        if ds_name == "tencent":
            return fresh_tencent, 1, None
        return None, 1, "empty response"

    monkeypatch.setattr("scanner.daily_data_service._try_fetch_source", fake_try_fetch)
    context = CacheFreshnessContext(
        target_trade_date="2026-06-29",
        min_fetch_time="2026-06-29 15:00:00",
    )

    result = fetch_with_retry(
        "603001",
        "sina",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["sina", "tencent"],
        kline_days=250,
        freshness_context=context,
    )

    assert calls == ["sina", "tencent"]
    assert result.data[-1]["date"] == "2026-06-29"
    assert result.data[-1]["volume"] > 0
    assert result.fallback_source == "tencent"
    assert "zero-volume target trade date 2026-06-29" in result.source_errors["sina"]
    assert db.get_ohlc("603001")[-1]["volume"] > 0


def test_fetch_after_close_strips_zero_volume_target_when_all_sources_have_no_trade(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("603722", [_row("2026-06-26", close=39.6)])

    def fake_try_fetch(code, ds_name, attempts, sleep_fn, kline_days):
        return [
            _row("2026-06-26", close=39.6),
            _zero_volume_flat_row("2026-06-29", close=39.6),
        ], 1, None

    monkeypatch.setattr("scanner.daily_data_service._try_fetch_source", fake_try_fetch)
    context = CacheFreshnessContext(
        target_trade_date="2026-06-29",
        min_fetch_time="2026-06-29 15:00:00",
    )

    result = fetch_with_retry(
        "603722",
        "sina",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["sina", "tencent"],
        kline_days=250,
        freshness_context=context,
    )

    assert result.quote_status == "suspended"
    assert result.data[-1]["date"] == "2026-06-26"
    assert all("zero-volume target trade date 2026-06-29" in error for error in result.source_errors.values())
    assert db.get_ohlc("603722")[-1]["date"] == "2026-06-26"


def test_fetch_rejects_invalid_ohlc_source_and_uses_fallback(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    calls = []

    def fake_try_fetch(code, ds_name, attempts, sleep_fn, kline_days):
        calls.append(ds_name)
        if ds_name == "sina":
            return [_invalid_high_row("2026-06-16")], 1, None
        if ds_name == "tencent":
            return [_row("2026-06-16", close=11.0)], 1, None
        return None, 1, "empty response"

    monkeypatch.setattr("scanner.daily_data_service._try_fetch_source", fake_try_fetch)
    context = CacheFreshnessContext(
        target_trade_date="2026-06-16",
        min_fetch_time="2026-06-16 15:00:00",
    )

    result = fetch_with_retry(
        "000831",
        "sina",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["sina", "tencent"],
        kline_days=250,
        freshness_context=context,
    )

    assert calls == ["sina", "tencent"]
    assert result.data[-1]["close"] == 11.0
    assert result.fallback_source == "tencent"
    assert "invalid OHLC" in result.source_errors["sina"]
    assert db.get_ohlc("000831")[-1]["close"] == 11.0


def test_fetch_returns_failed_result_when_all_sources_have_invalid_ohlc(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))

    def fake_try_fetch(code, ds_name, attempts, sleep_fn, kline_days):
        return [_invalid_high_row("2026-06-16")], 1, None

    monkeypatch.setattr("scanner.daily_data_service._try_fetch_source", fake_try_fetch)
    context = CacheFreshnessContext(
        target_trade_date="2026-06-16",
        min_fetch_time="2026-06-16 15:00:00",
    )

    result = fetch_with_retry(
        "000831",
        "sina",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["sina", "tencent"],
        kline_days=250,
        freshness_context=context,
    )

    assert result.data is None
    assert result.primary_error == "invalid OHLC relationship"
    assert result.fallback_error == "invalid OHLC relationship"
    assert not db.get_ohlc("000831")


def test_fetch_rejects_non_finite_ohlc_values(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))

    def fake_try_fetch(code, ds_name, attempts, sleep_fn, kline_days):
        return [_nan_open_row("2026-06-16")], 1, None

    monkeypatch.setattr("scanner.daily_data_service._try_fetch_source", fake_try_fetch)
    context = CacheFreshnessContext(
        target_trade_date="2026-06-16",
        min_fetch_time="2026-06-16 15:00:00",
    )

    result = fetch_with_retry(
        "000831",
        "sina",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["sina"],
        kline_days=250,
        freshness_context=context,
    )

    assert result.data is None
    assert result.primary_error == "invalid OHLC values"
    assert not db.get_ohlc("000831")


def test_fetch_rejects_non_finite_turnover_when_present(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))

    def fake_try_fetch(code, ds_name, attempts, sleep_fn, kline_days):
        return [_infinite_turnover_row("2026-06-16")], 1, None

    monkeypatch.setattr("scanner.daily_data_service._try_fetch_source", fake_try_fetch)
    result = fetch_with_retry(
        "000831",
        "sina",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["sina"],
        kline_days=250,
        freshness_context=CacheFreshnessContext(target_trade_date="2026-06-16"),
    )

    assert result.data is None
    assert result.primary_error == "invalid OHLC values"
    assert not db.get_ohlc("000831")
