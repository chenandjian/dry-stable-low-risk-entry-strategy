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


def test_us_screen_import_uses_completed_research_and_limits_results(tmp_path, monkeypatch):
    monkeypatch.setattr('us_market.batch_evaluator.MAX_BATCH_SYMBOLS', 1)
    repo = USRepository(tmp_path / 'us.db')
    monkeypatch.setattr(server, '_us_database_path', lambda: repo.path)
    day = '2026-11-05'
    for task_id, scope, status, symbol in [
        ('full', 'universe', 'COMPLETED', 'AAPL.US'),
        ('manual', 'manual', 'COMPLETED', 'MSFT.US'),
        ('unfinished', 'universe', 'RUNNING', 'NVDA.US'),
    ]:
        symbols = [symbol, 'AMZN.US'] if task_id == 'full' else [symbol]
        task = dict(task_id=task_id, kind='job', market='US', research_only=True,
                    status='RUNNING', scope=scope, context={'target_trade_date': day},
                    progress={}, symbols=symbols, stock_storage='rows_v1')
        repo.initialize_job(task)
        repo.complete_job_stocks(task, [dict(symbol=code, status='EVALUATED', evaluation_date=day,
            candidate=dict(evaluation_date=day, market='US', research_only=True,
                           strong_trend_squeeze_pass=True, total_score=70 if code == symbol else 60))
            for code in symbols])
        task['status'] = status
        repo.finish_job(task)
    client = TestClient(server.app)
    response = client.get(f'/api/us/strategy6/trend-squeeze-screen?as_of={day}')
    assert response.status_code == 200
    assert response.json() == dict(taskId='full', evaluationDate=day, total=2, stocks=[dict(code='AAPL.US')])
    assert client.get('/api/us/strategy6/trend-squeeze-screen?as_of=2026-11-04').json()['taskId'] is None


def test_us_screen_import_does_not_create_database(batch_client):
    client, path = batch_client
    assert client.get('/api/us/strategy6/trend-squeeze-screen').json()['stocks'] == []
    assert client.get('/api/us/strategy6/trend-squeeze-screen?as_of=2026-02-30').status_code == 400
    assert not path.exists()
