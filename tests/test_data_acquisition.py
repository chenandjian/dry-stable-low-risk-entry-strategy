import pytest
import pandas as pd

from scanner import db
from scanner.data_acquisition import (
    LEGACY_MULTI_SOURCE_MODE,
    TICKFLOW_MODE,
    resolve_acquisition_mode,
    prepare_scan_daily_data,
    load_market_index_daily,
)
from tickflow_data.models import BatchFetchResult


def test_acquisition_mode_defaults_legacy_for_old_config():
    assert resolve_acquisition_mode({"data": {}}) == LEGACY_MULTI_SOURCE_MODE


def test_acquisition_mode_accepts_explicit_supported_modes():
    assert resolve_acquisition_mode({"data": {"acquisition_mode": "tickflow"}}) == TICKFLOW_MODE
    assert resolve_acquisition_mode(
        {"data": {"acquisition_mode": "legacy_multi_source"}}
    ) == LEGACY_MULTI_SOURCE_MODE


def test_acquisition_mode_rejects_unknown_value():
    with pytest.raises(ValueError, match="data.acquisition_mode"):
        resolve_acquisition_mode({"data": {"acquisition_mode": "automatic"}})


def _frame(symbol, date="2026-07-21"):
    return pd.DataFrame([{
        "trade_date": date,
        "open": 10.0,
        "high": 10.5,
        "low": 9.8,
        "close": 10.2,
        "volume": 1000,
        "amount": 1_000_000,
    }])


class _Client:
    def __init__(self, *, missing_stock=False, stock_date="2026-07-21"):
        self.missing_stock = missing_stock
        self.stock_date = stock_date
        self.stock_calls = []
        self.index_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def fetch(self, symbols, *, count):
        self.stock_calls.append((list(symbols), count))
        frames = (
            {}
            if self.missing_stock
            else {symbol: _frame(symbol, self.stock_date) for symbol in symbols}
        )
        missing = list(symbols) if self.missing_stock else []
        return BatchFetchResult(frames=frames, missing_symbols=missing)

    def fetch_indexes(self, symbols, *, count):
        self.index_calls.append((list(symbols), count))
        return BatchFetchResult(frames={symbol: _frame(symbol) for symbol in symbols})


def test_tickflow_prepare_batches_stale_stocks_and_serves_only_prepared_cache(tmp_path):
    db.init_db(str(tmp_path / "market.db"))
    client = _Client()
    client_kwargs = []
    config = {
        "data": {
            "acquisition_mode": "tickflow",
            "tickflow_api_key": "scan-secret",
        },
        "liquidity": {"min_listing_days": 1100},
    }

    session = prepare_scan_daily_data(
        config,
        [{"code": "600519", "name": "贵州茅台", "market": "SH"}],
        now="2026-07-21 16:00:00",
        client_factory=lambda **kwargs: client_kwargs.append(kwargs) or client,
    )
    result = session.fetch("600519", "tickflow", kline_days=1100)

    assert client.stock_calls == [(["600519.SH"], 1100)]
    assert result.data[-1]["date"] == "2026-07-21"
    assert result.primary_source == "tickflow"
    assert result.fallback_source == "tickflow"
    assert result.source_errors == {}
    assert db.get_ohlc_metadata("600519")["source"] == "tickflow"
    assert client_kwargs == [{
        "api_key": "scan-secret",
        "batch_size": 100,
        "max_workers": 5,
    }]


def test_tickflow_prepare_reports_batch_progress_before_strategy_scan(tmp_path):
    db.init_db(str(tmp_path / "market.db"))
    client = _Client()
    events = []

    prepare_scan_daily_data(
        {
            "data": {"acquisition_mode": "tickflow"},
            "liquidity": {"min_listing_days": 1100},
        },
        [
            {"code": "600519", "name": "贵州茅台", "market": "上证主板"},
            {"code": "000001", "name": "平安银行", "market": "深证主板"},
        ],
        now="2026-07-21 16:00:00",
        client_factory=lambda **kwargs: client,
        progress_callback=lambda stage, current, total, detail: events.append(
            (stage, current, total, detail)
        ),
    )

    stock_events = [event for event in events if event[0] == "data_acquisition"]
    assert [(event[1], event[2]) for event in stock_events] == [(0, 2), (1, 2), (2, 2)]
    assert stock_events[1][3] == "600519 贵州茅台"
    assert stock_events[2][3] == "000001 平安银行"
    assert any(event[0] == "index_acquisition" for event in events)


def test_tickflow_prepare_failure_never_falls_back_to_legacy_sources(tmp_path):
    db.init_db(str(tmp_path / "market.db"))
    client = _Client(missing_stock=True)
    config = {
        "data": {"acquisition_mode": "tickflow"},
        "liquidity": {"min_listing_days": 1100},
    }

    session = prepare_scan_daily_data(
        config,
        [{"code": "600519", "name": "贵州茅台", "market": "SH"}],
        now="2026-07-21 16:00:00",
        client_factory=lambda **kwargs: client,
    )
    result = session.fetch(
        "600519",
        "tencent",
        source_chain=["tencent", "sina", "baidu"],
        kline_days=1100,
    )

    assert result.data is None
    assert result.primary_source == "tickflow"
    assert set(result.source_errors) == {"tickflow"}


def test_tickflow_prepare_converts_top_level_sdk_failure_to_per_stock_failure(tmp_path):
    db.init_db(str(tmp_path / "market.db"))

    class BrokenClient:
        def __enter__(self):
            raise RuntimeError("TickFlow SDK unavailable")

        def __exit__(self, exc_type, exc, traceback):
            return None

    session = prepare_scan_daily_data(
        {
            "data": {"acquisition_mode": "tickflow"},
            "liquidity": {"min_listing_days": 1100},
        },
        [{"code": "600519", "name": "贵州茅台", "market": "SH"}],
        now="2026-07-21 16:00:00",
        client_factory=lambda **kwargs: BrokenClient(),
    )

    result = session.fetch("600519", "tickflow", kline_days=1100)
    assert result.data is None
    assert "SDK unavailable" in result.primary_error


def test_legacy_mode_keeps_existing_scanner_fetch_path():
    assert prepare_scan_daily_data(
        {"data": {"acquisition_mode": "legacy_multi_source"}},
        [{"code": "600519"}],
    ) is None


def test_tickflow_freshness_check_does_not_load_full_ohlc_history(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "market.db"))
    db.replace_ohlc_with_metadata(
        "600519",
        [{"date": "2026-07-21", "open": 10, "high": 11, "low": 9,
          "close": 10.5, "volume": 1000, "turnover": 10000}],
        source="tickflow",
        fetched_at="2026-07-21 16:00:00",
    )
    monkeypatch.setattr(
        db,
        "get_ohlc",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("full OHLC loaded")),
    )

    from scanner.data_acquisition import _tickflow_stock_cache_is_fresh

    assert _tickflow_stock_cache_is_fresh(
        "600519",
        target_date="2026-07-21",
        min_fetch_time="2026-07-21 15:00:00",
    ) is True


def test_tickflow_cache_requires_exact_target_trade_date(tmp_path):
    db.init_db(str(tmp_path / "market.db"))

    from scanner.data_acquisition import _tickflow_stock_cache_is_fresh

    for latest_date, expected in (
        ("2026-07-22", False),
        ("2026-07-23", True),
        ("2026-07-24", False),
    ):
        db.replace_ohlc_with_metadata(
            "600519",
            [{"date": latest_date, "open": 10, "high": 11, "low": 9,
              "close": 10.5, "volume": 1000, "turnover": 10000}],
            source="tickflow",
            fetched_at="2026-07-23 16:00:00",
        )
        assert _tickflow_stock_cache_is_fresh(
            "600519",
            target_date="2026-07-23",
            min_fetch_time="2026-07-23 15:00:00",
        ) is expected


def test_tickflow_prepare_fails_stale_stocks_when_target_date_has_zero_coverage(tmp_path):
    db.init_db(str(tmp_path / "market.db"))
    client = _Client(stock_date="2026-07-22")

    session = prepare_scan_daily_data(
        {
            "data": {"acquisition_mode": "tickflow"},
            "liquidity": {"min_listing_days": 1100},
        },
        [{"code": "600519", "name": "贵州茅台", "market": "上证主板"}],
        now="2026-07-23 16:00:00",
        client_factory=lambda **kwargs: client,
    )

    result = session.fetch("600519", "tickflow", kline_days=1100)

    assert result.data is None
    assert result.quote_status != "suspended"
    assert "TARGET_TRADE_DATE_UNAVAILABLE" in result.primary_error
    assert "target=2026-07-23" in result.primary_error
    assert "remote_latest=2026-07-22" in result.primary_error


def test_tickflow_prepare_keeps_individual_suspension_after_target_date_is_available(tmp_path):
    db.init_db(str(tmp_path / "market.db"))
    db.replace_ohlc_with_metadata(
        "000001",
        [{"date": "2026-07-23", "open": 10, "high": 11, "low": 9,
          "close": 10.5, "volume": 1000, "turnover": 10000}],
        source="tickflow",
        fetched_at="2026-07-23 16:00:00",
    )
    client = _Client(stock_date="2026-07-22")

    session = prepare_scan_daily_data(
        {
            "data": {"acquisition_mode": "tickflow"},
            "liquidity": {"min_listing_days": 1100},
        },
        [{"code": "600519", "name": "贵州茅台", "market": "上证主板"}],
        now="2026-07-23 16:00:00",
        client_factory=lambda **kwargs: client,
    )

    result = session.fetch("600519", "tickflow", kline_days=1100)

    assert result.data[-1]["date"] == "2026-07-22"
    assert result.quote_status == "suspended"
    assert result.source_errors == {}


def test_tickflow_mode_loads_market_index_only_from_local_tickflow_cache(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "market.db"))
    db.upsert_market_index_ohlc(
        "hs300",
        [{"date": "2026-07-21", "open": 4000, "high": 4050, "low": 3980,
          "close": 4030, "volume": 100, "turnover": 1000}],
        source="tickflow",
    )
    monkeypatch.setattr(
        "scanner.index_source.fetch_market_index_daily",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy index source used")),
    )

    rows = load_market_index_daily(
        {"data": {"acquisition_mode": "tickflow"}},
        "sh000300",
        days=250,
        now="2026-07-21 16:00:00",
    )

    assert rows[-1]["date"] == "2026-07-21"


def test_tickflow_mode_rejects_stale_market_index_cache(tmp_path):
    db.init_db(str(tmp_path / "market.db"))
    db.upsert_market_index_ohlc(
        "sh000001",
        [{"date": "2026-07-20", "open": 3000, "high": 3050, "low": 2980,
          "close": 3030, "volume": 100, "turnover": 1000}],
        source="tickflow",
        fetched_at="2026-07-21 16:00:00",
    )

    rows = load_market_index_daily(
        {"data": {"acquisition_mode": "tickflow"}},
        "sh000001",
        days=250,
        now="2026-07-21 16:00:00",
    )

    assert rows == []
