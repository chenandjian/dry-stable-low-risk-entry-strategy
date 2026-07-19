import pandas as pd
import pytest

from scanner.sina_source import fetch_sina_daily


class FakeAkshare:
    def __init__(self, frame=None, exc=None):
        self.frame = frame
        self.exc = exc
        self.calls = []

    def stock_zh_a_daily(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return self.frame.copy()


def _frame():
    return pd.DataFrame(
        [
            {"date": "2026-05-25", "open": 24.23, "high": 24.31, "low": 23.53, "close": 23.90, "volume": 300, "amount": 7000},
            {"date": "2026-05-20", "open": 24.53, "high": 25.56, "low": 24.20, "close": 25.38, "volume": 100, "amount": 2500},
            {"date": "2026-05-22", "open": 23.77, "high": 24.44, "low": 23.38, "close": 24.20, "volume": 200, "amount": 4800},
        ]
    )


def test_fetch_sina_daily_uses_akshare_qfq_and_returns_latest_days(monkeypatch):
    fake = FakeAkshare(_frame())
    monkeypatch.setattr("scanner.sina_source._load_akshare", lambda: fake)

    rows = fetch_sina_daily("002396", days=2)

    assert len(fake.calls) == 1
    assert fake.calls[0]["symbol"] == "sz002396"
    assert fake.calls[0]["start_date"] == "19900101"
    assert fake.calls[0]["end_date"].isdigit() and len(fake.calls[0]["end_date"]) == 8
    assert fake.calls[0]["adjust"] == "qfq"
    assert [row["date"] for row in rows] == ["2026-05-22", "2026-05-25"]
    assert rows[0] == {
        "date": "2026-05-22",
        "open": 23.77,
        "high": 24.44,
        "low": 23.38,
        "close": 24.20,
        "volume": 200.0,
        "turnover": 4800.0,
    }


@pytest.mark.parametrize(
    ("code", "symbol"),
    [("600000", "sh600000"), ("000001", "sz000001"), ("300001", "sz300001"), ("830001", "bj830001")],
)
def test_fetch_sina_daily_maps_exchange_prefix(monkeypatch, code, symbol):
    fake = FakeAkshare(_frame().tail(1))
    monkeypatch.setattr("scanner.sina_source._load_akshare", lambda: fake)

    assert fetch_sina_daily(code, days=1)
    assert fake.calls[0]["symbol"] == symbol


def test_fetch_sina_daily_returns_none_for_empty_or_invalid_frame(monkeypatch):
    fake = FakeAkshare(pd.DataFrame())
    monkeypatch.setattr("scanner.sina_source._load_akshare", lambda: fake)
    assert fetch_sina_daily("000868") is None

    invalid = FakeAkshare(pd.DataFrame([{"date": "2026-05-20", "close": 10}]))
    monkeypatch.setattr("scanner.sina_source._load_akshare", lambda: invalid)
    assert fetch_sina_daily("000868") is None


def test_fetch_sina_daily_raises_for_rate_limit_error(monkeypatch):
    fake = FakeAkshare(exc=RuntimeError("429 Too Many Requests"))
    monkeypatch.setattr("scanner.sina_source._load_akshare", lambda: fake)

    with pytest.raises(RuntimeError, match="429"):
        fetch_sina_daily("000868")


def test_fetch_sina_daily_returns_none_for_other_akshare_error(monkeypatch):
    fake = FakeAkshare(exc=ConnectionError("network down"))
    monkeypatch.setattr("scanner.sina_source._load_akshare", lambda: fake)

    assert fetch_sina_daily("000868") is None
