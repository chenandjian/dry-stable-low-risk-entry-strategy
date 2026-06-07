import requests

from scanner.sina_source import fetch_sina_daily


class FakeResponse:
    text = ""

    def __init__(self, exc):
        self._exc = exc

    def raise_for_status(self):
        raise self._exc


def test_fetch_sina_daily_returns_none_for_http_error(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse(requests.HTTPError("500 Server Error"))

    monkeypatch.setattr("scanner.sina_source.requests.get", fake_get)

    assert fetch_sina_daily("000868") is None


def test_fetch_sina_daily_raises_for_rate_limit_http_error(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse(requests.HTTPError("456 Client Error"))

    monkeypatch.setattr("scanner.sina_source.requests.get", fake_get)

    try:
        fetch_sina_daily("000868")
    except RuntimeError as exc:
        assert "456 Client Error" in str(exc)
    else:
        raise AssertionError("456 rate limit should be surfaced to engine")
