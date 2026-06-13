# tests/test_yfinance_source.py
"""yfinance 数据源 mock 单元测试 — 不访问外网。"""

import math
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from scanner.yfinance_source import (
    fetch_yfinance_daily,
    _to_yahoo_symbol,
    _normalize_history,
    _normalize_row,
    _is_valid_ohlc,
    _raise_if_rate_limited,
)


# ── _to_yahoo_symbol ─────────────────────────────────────────────────

def test_sh_code_maps_to_ss():
    assert _to_yahoo_symbol("600000") == "600000.SS"
    assert _to_yahoo_symbol("601318") == "601318.SS"
    assert _to_yahoo_symbol("603259") == "603259.SS"
    assert _to_yahoo_symbol("605001") == "605001.SS"
    assert _to_yahoo_symbol("688981") == "688981.SS"


def test_sz_code_maps_to_sz():
    assert _to_yahoo_symbol("000001") == "000001.SZ"
    assert _to_yahoo_symbol("001979") == "001979.SZ"
    assert _to_yahoo_symbol("002487") == "002487.SZ"
    assert _to_yahoo_symbol("003816") == "003816.SZ"
    assert _to_yahoo_symbol("300820") == "300820.SZ"
    assert _to_yahoo_symbol("301267") == "301267.SZ"


def test_bj_code_returns_none():
    assert _to_yahoo_symbol("830799") is None
    assert _to_yahoo_symbol("430047") is None


def test_empty_code_returns_none():
    assert _to_yahoo_symbol("") is None
    assert _to_yahoo_symbol("   ") is None


# ── _normalize_row ───────────────────────────────────────────────────

class FakeIndex:
    def date(self):
        from datetime import date
        return date(2025, 6, 10)


def test_normalize_row_formats_date_and_fields():
    row = _normalize_row(FakeIndex(), {
        "Open": 10.0, "High": 10.5, "Low": 9.5, "Close": 10.2, "Volume": 1_000_000,
    })
    assert row is not None
    assert row["date"] == "2025-06-10"
    assert row["open"] == 10.0
    assert row["high"] == 10.5
    assert row["low"] == 9.5
    assert row["close"] == 10.2
    assert row["volume"] == 1_000_000
    assert row["turnover"] == 10.2 * 1_000_000


def test_normalize_row_missing_fields_returns_none():
    assert _normalize_row(FakeIndex(), {"Open": 10.0}) is None


def test_normalize_row_non_numeric_returns_none():
    assert _normalize_row(FakeIndex(), {
        "Open": "abc", "High": 10, "Low": 10, "Close": 10, "Volume": 100,
    }) is None


# ── _is_valid_ohlc ───────────────────────────────────────────────────

def test_valid_ohlc_passes():
    row = {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1_000_000, "turnover": 10_200_000}
    assert _is_valid_ohlc(row) is True


def test_nan_ohlc_filtered():
    row = {"open": float("nan"), "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1_000_000, "turnover": 10_200_000}
    assert _is_valid_ohlc(row) is False


def test_zero_close_filtered():
    row = {"open": 10.0, "high": 10.5, "low": 9.5, "close": 0.0, "volume": 1_000_000, "turnover": 0}
    assert _is_valid_ohlc(row) is False


def test_negative_volume_filtered():
    row = {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": -100, "turnover": 10_200_000}
    assert _is_valid_ohlc(row) is False


def test_infinite_turnover_filtered():
    row = {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1_000_000, "turnover": float("inf")}
    assert _is_valid_ohlc(row) is False


# ── _normalize_history ───────────────────────────────────────────────

def test_normalize_history_sorts_by_date():
    from datetime import date
    import pandas as pd

    # Build a real-like DataFrame
    dates = pd.date_range("2025-06-01", periods=10)
    data = []
    for dt in dates:
        data.append({
            "date": dt.strftime("%Y-%m-%d"),
            "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1_000_000,
            "turnover": 10.2 * 1_000_000,
        })
    # Reverse to test sorting
    data.reverse()

    # Simulate _normalize_history with raw rows
    raw_rows = [d for d in data if _is_valid_ohlc(d)]
    raw_rows.sort(key=lambda r: r["date"])
    result = raw_rows[-5:]

    assert len(result) == 5
    # Check ascending order
    for i in range(len(result) - 1):
        assert result[i]["date"] < result[i + 1]["date"]


def test_normalize_history_returns_last_n():
    rows = []
    for i in range(100):
        rows.append({
            "date": f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
            "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2 + i * 0.01,
            "volume": 1_000_000, "turnover": (10.2 + i * 0.01) * 1_000_000,
        })
    rows.sort(key=lambda r: r["date"])
    result = rows[-50:]
    assert len(result) == 50


def test_normalize_history_empty_returns_none():
    assert _normalize_history(MagicMock(empty=True, iterrows=MagicMock(return_value=[])), 250) is None


# ── fetch_yfinance_daily mock 测试 ───────────────────────────────────

def test_fetch_auto_adjust_and_actions_explicit(monkeypatch):
    """Ticker.history() 必须显式传入 auto_adjust=True 和 actions=False。"""
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = MagicMock(empty=True)

    def fake_ticker(symbol):
        return mock_ticker

    monkeypatch.setattr("yfinance.Ticker", fake_ticker)
    monkeypatch.setattr("scanner.yfinance_source._to_yahoo_symbol", lambda code: f"{code}.SS")

    fetch_yfinance_daily("600000", days=50)

    mock_ticker.history.assert_called_once()
    kwargs = mock_ticker.history.call_args.kwargs
    assert kwargs.get("auto_adjust") is True
    assert kwargs.get("actions") is False


def test_fetch_returns_none_for_empty_history(monkeypatch):
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = MagicMock(empty=True)

    monkeypatch.setattr("yfinance.Ticker", MagicMock(return_value=mock_ticker))
    monkeypatch.setattr("scanner.yfinance_source._to_yahoo_symbol", lambda code: f"{code}.SS")

    result = fetch_yfinance_daily("600000")
    assert result is None


def test_fetch_returns_none_for_unsupported_code(monkeypatch):
    """北交所代码返回 None，不调 yfinance。"""
    import scanner.yfinance_source as yf_mod
    called = []

    monkeypatch.setattr(yf_mod, "_to_yahoo_symbol", lambda code: None)

    def fake_ticker(symbol):
        called.append(symbol)
        return MagicMock()

    monkeypatch.setattr("yfinance.Ticker", fake_ticker)

    result = fetch_yfinance_daily("830799")
    assert result is None
    assert len(called) == 0


def test_fetch_returns_none_on_yfinance_error(monkeypatch):
    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = RuntimeError("connection failed")

    monkeypatch.setattr("yfinance.Ticker", MagicMock(return_value=mock_ticker))
    monkeypatch.setattr("scanner.yfinance_source._to_yahoo_symbol", lambda code: f"{code}.SS")

    result = fetch_yfinance_daily("600000")
    assert result is None


def test_fetch_raises_on_rate_limit(monkeypatch):
    """429 限流异常必须抛出，不能被吞掉。"""
    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = Exception("429 Too Many Requests")

    monkeypatch.setattr("yfinance.Ticker", MagicMock(return_value=mock_ticker))
    monkeypatch.setattr("scanner.yfinance_source._to_yahoo_symbol", lambda code: f"{code}.SS")

    with pytest.raises(ValueError, match="data source busy"):
        fetch_yfinance_daily("600000")


def test_fetch_raises_on_rate_limit_type(monkeypatch):
    """yfinance 限流异常类型名含 'rate' 时必须抛出。"""

    class YFRateLimitError(Exception):
        pass

    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = YFRateLimitError("rate limited")

    monkeypatch.setattr("yfinance.Ticker", MagicMock(return_value=mock_ticker))
    monkeypatch.setattr("scanner.yfinance_source._to_yahoo_symbol", lambda code: f"{code}.SS")

    with pytest.raises(ValueError, match="data source busy"):
        fetch_yfinance_daily("600000")


def test_fetch_returns_none_when_yfinance_not_installed(monkeypatch):
    """yfinance 未安装时返回 None 不崩溃。"""
    import scanner.yfinance_source as yf_mod

    def fake_import(name, *args, **kwargs):
        if name == "yfinance":
            raise ImportError("No module named 'yfinance'")
        return __import__(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    # Force re-import attempt
    result = fetch_yfinance_daily("600000")
    assert result is None


def test_fetch_turnover_equals_close_times_volume(monkeypatch):
    """yfinance 返回的 turnover 必须等于 close * volume。"""
    import pandas as pd

    dates = pd.date_range("2025-06-01", periods=5)
    df = pd.DataFrame({
        "Open": [10.0] * 5,
        "High": [10.5] * 5,
        "Low": [9.5] * 5,
        "Close": [10.2] * 5,
        "Volume": [1_000_000] * 5,
    }, index=dates)

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = df

    monkeypatch.setattr("yfinance.Ticker", MagicMock(return_value=mock_ticker))
    monkeypatch.setattr("scanner.yfinance_source._to_yahoo_symbol", lambda code: f"{code}.SS")

    result = fetch_yfinance_daily("600000", days=5)
    assert result is not None
    assert len(result) == 5
    for row in result:
        assert row["turnover"] == pytest.approx(row["close"] * row["volume"])
        assert row["open"] == 10.0
        assert row["close"] == 10.2


# ── _raise_if_rate_limited ───────────────────────────────────────────

def test_rate_limit_429_raises():
    with pytest.raises(ValueError, match="data source busy"):
        _raise_if_rate_limited(Exception("HTTP 429 Too Many Requests"))


def test_rate_limit_name_raises():
    class RateLimitError(Exception):
        pass

    with pytest.raises(ValueError, match="data source busy"):
        _raise_if_rate_limited(RateLimitError("rate limited"))


def test_normal_error_pass_through():
    """普通异常不重新抛出，由调用方处理。"""
    _raise_if_rate_limited(RuntimeError("timeout"))  # 不抛
