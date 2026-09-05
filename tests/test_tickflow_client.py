import sys
import types

import pandas as pd
import pytest

from tickflow_data.client import (
    AUTHENTICATED_ACCESS_MODE,
    DEFAULT_TICKFLOW_API_KEY,
    FREE_ACCESS_MODE,
    TickFlowBatchClient,
    TickFlowClientError,
    resolve_tickflow_access_mode,
    resolve_tickflow_api_key,
)


class _Klines:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def batch(self, symbols, **kwargs):
        self.calls.append((symbols, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _Sdk:
    def __init__(self, responses):
        self.klines = _Klines(responses)
        self.closed = False

    def close(self):
        self.closed = True


def test_api_key_resolution_prefers_explicit_then_environment(monkeypatch):
    monkeypatch.setenv("TICKFLOW_API_KEY", " environment-key ")

    assert resolve_tickflow_api_key(" explicit-key ") == "explicit-key"
    assert resolve_tickflow_api_key() == "environment-key"


def test_api_key_resolution_falls_back_to_default_without_prefix_validation(monkeypatch):
    monkeypatch.delenv("TICKFLOW_API_KEY", raising=False)

    assert resolve_tickflow_api_key("   ") == DEFAULT_TICKFLOW_API_KEY
    assert resolve_tickflow_api_key("future-provider-format") == "future-provider-format"


def test_access_mode_defaults_free_and_rejects_unknown_values():
    assert resolve_tickflow_access_mode() == FREE_ACCESS_MODE
    assert resolve_tickflow_access_mode(" authenticated ") == AUTHENTICATED_ACCESS_MODE
    with pytest.raises(ValueError, match="tickflow_access_mode"):
        resolve_tickflow_access_mode("automatic")


def test_batch_client_default_free_mode_ignores_available_api_key(monkeypatch):
    calls = []

    class FakeTickFlow:
        def __new__(cls, *, api_key):
            calls.append(("authenticated", api_key))
            return _Sdk([{}])

        @classmethod
        def free(cls):
            calls.append(("free", None))
            return _Sdk([{}])

    monkeypatch.setitem(sys.modules, "tickflow", types.SimpleNamespace(TickFlow=FakeTickFlow))
    monkeypatch.setenv("TICKFLOW_API_KEY", "environment-key")

    with TickFlowBatchClient(api_key="configured-key"):
        pass

    assert calls == [("free", None)]


def test_batch_client_authenticated_mode_never_calls_free(monkeypatch):
    calls = []

    class FakeTickFlow:
        def __new__(cls, *, api_key):
            calls.append(("authenticated", api_key))
            return _Sdk([{}])

        @classmethod
        def free(cls):
            raise AssertionError("authenticated mode must never use free mode")

    monkeypatch.setitem(sys.modules, "tickflow", types.SimpleNamespace(TickFlow=FakeTickFlow))

    with TickFlowBatchClient(
        access_mode=AUTHENTICATED_ACCESS_MODE,
        api_key="authenticated-key",
    ):
        pass

    assert calls == [("authenticated", "authenticated-key")]


def test_batch_client_locks_daily_forward_additive_parameters():
    frame = pd.DataFrame([{"trade_date": "2026-07-20"}])
    sdk = _Sdk([{"600519.SH": frame, "000001.SZ": frame}])

    with TickFlowBatchClient(sdk=sdk) as client:
        result = client.fetch(["600519.SH", "000001.SZ"], count=800)

    assert sdk.klines.calls == [
        (
            ["600519.SH", "000001.SZ"],
            {
                "period": "1d",
                "count": 800,
                "adjust": "forward_additive",
                "as_dataframe": True,
                "show_progress": False,
                "max_workers": 5,
                "batch_size": 100,
            },
        )
    ]
    assert set(result.frames) == {"600519.SH", "000001.SZ"}
    assert result.missing_symbols == []
    assert sdk.closed is False


def test_batch_client_fetches_indexes_without_adjustment():
    frame = pd.DataFrame([{"trade_date": "2026-07-20"}])
    sdk = _Sdk([{"000001.SH": frame, "399006.SZ": frame}])

    result = TickFlowBatchClient(sdk=sdk).fetch_indexes(
        ["000001.SH", "399006.SZ"], count=1100
    )

    assert set(result.frames) == {"000001.SH", "399006.SZ"}
    assert sdk.klines.calls == [
        (
            ["000001.SH", "399006.SZ"],
            {
                "period": "1d",
                "count": 1100,
                "adjust": "none",
                "as_dataframe": True,
                "show_progress": False,
                "max_workers": 5,
                "batch_size": 100,
            },
        )
    ]


def test_batch_client_reports_missing_symbols_without_losing_successes():
    frame = pd.DataFrame([{"trade_date": "2026-07-20"}])
    sdk = _Sdk([{"600519.SH": frame}])

    result = TickFlowBatchClient(sdk=sdk).fetch(
        ["600519.SH", "000001.SZ"], count=10
    )

    assert result.frames == {"600519.SH": frame}
    assert result.missing_symbols == ["000001.SZ"]


def test_batch_client_retries_complete_batch_once():
    frame = pd.DataFrame([{"trade_date": "2026-07-20"}])
    sdk = _Sdk([TimeoutError("temporary"), {"600519.SH": frame}])

    result = TickFlowBatchClient(sdk=sdk, batch_retries=1).fetch(
        ["600519.SH"], count=10
    )

    assert set(result.frames) == {"600519.SH"}
    assert len(sdk.klines.calls) == 2


def test_batch_client_raises_clear_error_after_retries():
    sdk = _Sdk([TimeoutError("first"), TimeoutError("second")])

    with pytest.raises(TickFlowClientError, match="batch request failed"):
        TickFlowBatchClient(sdk=sdk, batch_retries=1).fetch(
            ["600519.SH"], count=10
        )


def test_batch_client_rejects_invalid_request():
    sdk = _Sdk([{}])

    with pytest.raises(ValueError):
        TickFlowBatchClient(sdk=sdk).fetch([], count=10)
    with pytest.raises(ValueError):
        TickFlowBatchClient(sdk=sdk).fetch(["600519.SH"], count=0)
