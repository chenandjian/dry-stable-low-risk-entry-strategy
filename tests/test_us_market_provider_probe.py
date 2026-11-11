from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import server
from us_market.daily_data import probe_provider_daily


@pytest.mark.parametrize('dates, expected', [
    (['2026-11-05', '2026-11-06'], 'UPDATED'),
    (['2026-11-05', '2026-11-09'], 'TARGET_MISSING'),
    ([], 'NO_DATA'),
])
def test_probe_requires_exact_completed_session(monkeypatch, dates, expected):
    closed = []

    def get(symbol, **kwargs):
        assert symbol == 'AAPL.US'
        assert kwargs == dict(period='1d', count=5, adjust='forward', as_dataframe=True)
        return [dict(date=day, open=10, high=11, low=9, close=10, volume=100) for day in dates]

    monkeypatch.setattr('us_market.daily_data._create_free_sdk', lambda: SimpleNamespace(
        klines=SimpleNamespace(get=get), close=lambda: closed.append(True)))
    result = probe_provider_daily('aapl', now=datetime(2026, 11, 9, 17, tzinfo=timezone.utc))
    assert result['status'] == expected
    assert result['target_trade_date'] == '2026-11-06'
    assert result['latest_date'] == (dates[-1] if dates else None)
    assert closed == [True]


def test_provider_probe_failure_is_not_reported_as_stale(monkeypatch):
    def offline(*args, **kwargs):
        raise TimeoutError()

    monkeypatch.setattr('us_market.daily_data.probe_provider_daily', offline)
    client = TestClient(server.app)
    assert client.post('/api/us/data/provider-freshness', json={'symbol': '600519.SH'}).status_code == 400
    response = client.post('/api/us/data/provider-freshness', json={'symbol': 'BRK.B'})
    assert response.status_code == 502
    assert response.json()['error'] == 'US_PROVIDER_PROBE_FAILED'
