from scanner.baidu_source import fetch_baidu_daily


class FakeResponse:
    def __init__(self, payload=None, exc=None):
        self.payload = payload or {}
        self.exc = exc

    def raise_for_status(self):
        if self.exc:
            raise self.exc

    def json(self):
        return self.payload


def test_fetch_baidu_daily_parses_keys_and_market_data(monkeypatch):
    payload = {
        "Result": {
            "newMarketData": {
                "keys": ["time", "open", "close", "high", "low", "volume", "amount", "ma5avgprice"],
                "marketData": "2026-06-04,10,10.2,10.5,9.8,1000,10200,10.1;2026-06-05,10.2,10.7,10.8,10.1,1200,12840,10.3",
            }
        }
    }
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return FakeResponse(payload)

    monkeypatch.setattr("scanner.baidu_source.requests.get", fake_get)

    rows = fetch_baidu_daily("000001", days=250)

    assert rows == [
        {"date": "2026-06-04", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "volume": 1000.0, "turnover": 10200.0},
        {"date": "2026-06-05", "open": 10.2, "high": 10.8, "low": 10.1, "close": 10.7, "volume": 1200.0, "turnover": 12840.0},
    ]
    assert calls[0]["params"]["code"] == "000001"
    assert calls[0]["params"]["ktype"] == "1"
    assert calls[0]["headers"]["User-Agent"] == "Mozilla/5.0"


def test_fetch_baidu_daily_limits_to_recent_days(monkeypatch):
    payload = {
        "Result": {
            "newMarketData": {
                "keys": ["time", "open", "close", "high", "low", "volume", "amount"],
                "marketData": "2026-06-03,9,9,9,9,1,9;2026-06-04,10,10,10,10,2,20;2026-06-05,11,11,11,11,3,33",
            }
        }
    }
    monkeypatch.setattr("scanner.baidu_source.requests.get", lambda *args, **kwargs: FakeResponse(payload))

    rows = fetch_baidu_daily("000001", days=2)

    assert [row["date"] for row in rows] == ["2026-06-04", "2026-06-05"]


def test_fetch_baidu_daily_returns_none_for_empty_or_bad_payload(monkeypatch):
    monkeypatch.setattr("scanner.baidu_source.requests.get", lambda *args, **kwargs: FakeResponse({}))
    assert fetch_baidu_daily("000001") is None

    payload = {"Result": {"newMarketData": {"keys": ["time", "open"], "marketData": "2026-06-05,10"}}}
    monkeypatch.setattr("scanner.baidu_source.requests.get", lambda *args, **kwargs: FakeResponse(payload))
    assert fetch_baidu_daily("000001") is None
