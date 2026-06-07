from scanner.mootdx_source import fetch_mootdx_daily


class FakeBars:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient="records"):
        assert orient == "records"
        return self._rows


class FakeClient:
    def __init__(self, rows=None, exc=None):
        self.rows = rows or []
        self.exc = exc
        self.calls = []

    def bars(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return FakeBars(self.rows)


def test_fetch_mootdx_daily_normalizes_rows(monkeypatch):
    client = FakeClient([
        {
            "datetime": "2026-06-04 15:00",
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.2,
            "vol": 1000,
            "amount": 10200,
        },
        {
            "datetime": "2026-06-05 15:00",
            "open": 10.2,
            "high": 10.8,
            "low": 10.1,
            "close": 10.7,
            "vol": 1200,
            "amount": 12840,
        },
    ])

    class FakeQuotes:
        @staticmethod
        def factory(market="std"):
            assert market == "std"
            return client

    monkeypatch.setattr("scanner.mootdx_source.Quotes", FakeQuotes)

    rows = fetch_mootdx_daily("000001", days=250)

    assert rows == [
        {"date": "2026-06-04", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "volume": 1000.0, "turnover": 10200.0},
        {"date": "2026-06-05", "open": 10.2, "high": 10.8, "low": 10.1, "close": 10.7, "volume": 1200.0, "turnover": 12840.0},
    ]
    assert client.calls == [{"symbol": "000001", "category": 4, "market": 0, "offset": 250}]


def test_fetch_mootdx_daily_uses_sh_market_for_6_prefix(monkeypatch):
    client = FakeClient([
        {"datetime": "2026-06-05", "open": 10, "high": 11, "low": 9, "close": 10.5, "vol": 1, "amount": 10.5}
    ])

    class FakeQuotes:
        @staticmethod
        def factory(market="std"):
            return client

    monkeypatch.setattr("scanner.mootdx_source.Quotes", FakeQuotes)

    assert fetch_mootdx_daily("600000") is not None
    assert client.calls[0]["market"] == 1


def test_fetch_mootdx_daily_skips_bad_rows(monkeypatch):
    client = FakeClient([
        {"datetime": "", "open": 10, "high": 11, "low": 9, "close": 10.5, "vol": 1, "amount": 10.5},
        {"datetime": "2026-06-05", "open": 10, "high": 11, "low": 9, "close": 10.5, "vol": 1, "amount": 10.5},
    ])

    class FakeQuotes:
        @staticmethod
        def factory(market="std"):
            return client

    monkeypatch.setattr("scanner.mootdx_source.Quotes", FakeQuotes)

    assert fetch_mootdx_daily("000001") == [
        {"date": "2026-06-05", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5, "volume": 1.0, "turnover": 10.5}
    ]


def test_fetch_mootdx_daily_returns_none_when_dependency_missing(monkeypatch):
    monkeypatch.setattr("scanner.mootdx_source.Quotes", None)

    assert fetch_mootdx_daily("000001") is None


def test_fetch_mootdx_daily_returns_none_on_empty_or_exception(monkeypatch):
    class EmptyQuotes:
        @staticmethod
        def factory(market="std"):
            return FakeClient([])

    monkeypatch.setattr("scanner.mootdx_source.Quotes", EmptyQuotes)
    assert fetch_mootdx_daily("000001") is None

    class FailingQuotes:
        @staticmethod
        def factory(market="std"):
            return FakeClient(exc=RuntimeError("tdx down"))

    monkeypatch.setattr("scanner.mootdx_source.Quotes", FailingQuotes)
    assert fetch_mootdx_daily("000001") is None
