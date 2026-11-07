from fastapi.testclient import TestClient
import pytest

import server
from us_market.repository import USRepository


@pytest.fixture
def history_client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'load_config', lambda: {'data': {'database_path': str(tmp_path / 'cn.db')}})
    def forbidden():
        pytest.fail('history query must not initialize the task manager')
    monkeypatch.setattr(server, '_get_us_manager', forbidden)
    monkeypatch.setattr('us_market.daily_data._create_free_sdk', forbidden)
    return TestClient(server.app), tmp_path / 'us_market.db'


def test_us_history_paginates_without_writing_or_fetching(history_client, monkeypatch):
    client, path = history_client
    repo = USRepository(path)
    dates = ['2026-11-03', '2026-11-04', '2026-11-05']
    repo.save_history('BRK.B', [
        dict(date=day, open=10, high=12, low=9, close=11, volume=123,
             turnover=None, turnover_estimated_usd=1353) for day in dates
    ], dict(source='tickflow_free', adjustment='forward', currency='USD',
            fetched_at='2026-11-06T22:00:00+00:00'))
    monkeypatch.setattr('us_market.calendar.target_session', lambda: {
        'target_trade_date': '2026-11-06', 'target_close_at': '2026-11-06T21:00:00+00:00',
    })
    response = client.get('/api/us/data/BRK.B/kline-history', params={
        'start_date': dates[0], 'end_date': dates[1], 'page': 2, 'page_size': 1,
    })
    assert response.status_code == 200
    result = response.json()
    assert result['symbol'] == 'BRK.B.US'
    assert result['total'] == 2 and result['page'] == 2
    assert result['rows'][0]['date'] == dates[0]
    assert result['rows'][0]['volume'] == 123
    assert result['rows'][0]['turnover'] is None
    assert result['rows'][0]['turnover_estimated_usd'] == 1353
    assert result['summary']['latest_kline_date'] == dates[-1]
    assert result['summary']['row_count'] == 3
    assert not result['summary']['is_fresh']
    assert repo.get_history('BRK.B')['rows'][-1]['date'] == dates[-1]


def test_missing_history_does_not_create_database(history_client):
    client, path = history_client
    response = client.get('/api/us/data/AAPL.US/kline-history')
    assert response.status_code == 200
    assert response.json()['rows'] == []
    assert response.json()['summary']['row_count'] == 0
    assert not path.exists()


@pytest.mark.parametrize('url', [
    '/api/us/data/600519.SH/kline-history',
    '/api/us/data/AAPL/kline-history?start_date=2026-02-30',
    '/api/us/data/AAPL/kline-history?start_date=2026-11-06&end_date=2026-11-05',
    '/api/us/data/AAPL/kline-history?page_size=101',
])
def test_invalid_us_history_parameters(history_client, url):
    client, path = history_client
    assert client.get(url).status_code == 400
    assert not path.exists()
