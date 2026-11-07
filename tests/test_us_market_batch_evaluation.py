from fastapi.testclient import TestClient
import pytest

import server
from strategy6.batch_evaluator import _batch_display_metrics
from us_market.repository import USRepository


@pytest.fixture
def batch_client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'load_config', lambda: {'data': {'database_path': str(tmp_path / 'cn.db')}})
    def forbidden(*args, **kwargs):
        pytest.fail('US batch must not initialize a manager or fetch market data')
    monkeypatch.setattr(server, '_get_us_manager', forbidden)
    monkeypatch.setattr('us_market.daily_data._create_free_sdk', forbidden)
    return TestClient(server.app), tmp_path / 'us_market.db'


def test_us_batch_local_date_cutoff_and_volume_basis(batch_client):
    client, path = batch_client
    repo = USRepository(path)
    dates = ['2026-10-29', '2026-10-30', '2026-11-02', '2026-11-03',
             '2026-11-04', '2026-11-05', '2026-11-06']
    rows = [dict(date=day, open=10, high=12, low=9, close=11,
                 volume=vol, turnover=None, turnover_estimated_usd=vol * 11)
            for day, vol in zip(dates, [100, 100, 100, 100, 100, 60, 9999])]
    repo.save_history('BRK.B', rows, dict(source='tickflow_free', adjustment='forward',
                                        fetched_at='2026-11-06T22:00:00+00:00'))
    response = client.post('/api/us/strategy6/batch-evaluate', json={
        'codes': ['brk.b', 'BRK.B.US', 'MISSING'], 'as_of': '2026-11-05',
    })
    assert response.status_code == 200
    body = response.json()
    assert body['requestedCount'] == 2 and body['evaluatedCount'] == 1
    assert body['researchOnly'] and not body['marketFilterEnabled']
    assert body['errors'][0]['error'] == 'KLINE_NOT_FOUND'
    row = body['results'][0]
    assert row['code'] == 'BRK.B.US' and row['evaluationDate'] == '2026-11-05'
    assert row['latestVolume'] == 60 and row['latestVolume5Min'] is True
    assert row['latestToPrevious5VolumeRatio'] == 0.6
    assert row['latestVolumeBelowPrevious5Avg60'] is True
    assert row['latestTurnoverActual'] is None and row['latestTurnoverEstimatedUsd'] == 660
    assert 'latestTurnover5Min' not in row
    assert {'priceConvergence', 'emaCompression', 'sellingExhaustion', 'klineCollectionPatterns'} <= row.keys()
    assert repo.list_runs() == []

    # A later stored bar must not hide a missing target session.
    result = client.post('/api/us/strategy6/batch-evaluate', json={
        'codes': ['BRK.B'], 'as_of': '2026-10-28',
    }).json()
    assert result['evaluatedCount'] == 0
    assert result['errors'][0]['error'] == 'MISSING_TARGET_SESSION'


@pytest.mark.parametrize('payload', [
    {'codes': ['600519.SH']}, {'codes': []}, {'codes': ['AAPL'], 'as_of': '2026-11-07'},
    {'codes': [f'X{i}' for i in range(201)]},
])
def test_us_batch_rejects_invalid_input_without_creating_db(batch_client, payload):
    client, path = batch_client
    assert client.post('/api/us/strategy6/batch-evaluate', json=payload).status_code == 400
    assert not path.exists()


def test_zero_volume_is_displayed_but_not_confirmed_as_dry():
    metrics = _batch_display_metrics(
        [{'close': 10, 'volume': volume} for volume in [100] * 5 + [0]], use_volume=True,
    )
    assert metrics['latestVolume'] == 0
    assert metrics['latestVolume5Min'] is None
    assert metrics['latestVolumeBelowPrevious5Avg60'] is None
