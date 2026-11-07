import threading
from types import SimpleNamespace

import pytest

from us_market.repository import USRepository
from us_market.universe import refresh_universe
from us_market.web_task import USResearchManager


def pool(symbols):
    return {'id': 'US_Equity', 'region': 'US', 'category': 'equity',
            'symbol_count': len(symbols), 'symbols': symbols}


def test_free_universe_is_atomic_immutable_and_not_certified_common_stock(tmp_path):
    repo = USRepository(tmp_path / 'us.db')
    sdk = SimpleNamespace(universes=SimpleNamespace(get=lambda name: pool(['AAPL.US', 'BRK.B.US', 'SPY.US'])))
    snapshot = refresh_universe(repo, sdk=sdk)
    assert snapshot['symbols'] == ['AAPL.US', 'BRK.B.US', 'SPY.US']
    assert snapshot['source'] == 'tickflow_free'
    assert snapshot['security_classification'] == 'PROVIDER_POOL_MIXED_UNVERIFIED'
    assert repo.latest_universe() == snapshot
    for bad in [pool([]), pool(['AAPL.US', 'AAPL.US']), pool(['600000.SH']),
                dict(pool(['AAPL.US']), symbol_count=100)]:
        sdk.universes.get = lambda name: bad
        with pytest.raises(ValueError):
            refresh_universe(repo, sdk=sdk)
        assert repo.latest_universe() == snapshot


def test_full_pool_over_200_is_streamed_paginated_and_snapshot_frozen(tmp_path, monkeypatch):
    repo = USRepository(tmp_path / 'us.db')
    symbols = [f'T{i}.US' for i in range(245)]
    sdk = SimpleNamespace(universes=SimpleNamespace(get=lambda name: pool(symbols)))
    snapshot = refresh_universe(repo, sdk=sdk)
    seen = []
    clients = []
    closed = []
    clock, waits = [0.0], []
    def fake_sleep(delay):
        waits.append(delay)
        clock[0] += delay
    monkeypatch.setattr('us_market.web_task.monotonic', lambda: clock[0])
    monkeypatch.setattr('us_market.web_task.sleep', fake_sleep)
    def create_sdk():
        client = SimpleNamespace(close=lambda: closed.append(True))
        clients.append(client)
        return client
    monkeypatch.setattr('us_market.web_task._create_free_sdk', create_sdk)
    def acquire(repo, chunk, **kw):
        assert len(chunk) <= 20
        assert kw['sdk'] is clients[0]
        assert callable(kw['before_request'])
        kw['before_request']()
        seen.extend(chunk)
        return {'task_id': 'fetch', 'stocks': [{'symbol': code, 'status': 'CACHED'} for code in chunk]}
    def evaluate(repo, chunk, **kw):
        return {'task_id': 'eval', 'stocks': [{'symbol': code, 'status': 'EVALUATED',
                'candidate': {'candidate_type': 'WATCH_CANDIDATE', 'total_score': 75}} for code in chunk]}
    monkeypatch.setattr('us_market.web_task.acquire_batch', acquire)
    monkeypatch.setattr('us_market.web_task.run_research', evaluate)
    manager = USResearchManager(repo)
    task_id = manager.start(None, scope='universe')
    manager.join(15)
    task = manager.get_page(task_id, page=3, page_size=50)
    assert task['status'] == 'COMPLETED'
    assert task['total_count'] == task['processed_count'] == task['candidates'] == 245
    assert task['universe_snapshot_id'] == snapshot['snapshot_id']
    assert task['stocks'][0]['symbol'] == 'T100.US'
    assert len(task['stocks']) == 50
    assert task['pagination']['total'] == 245
    assert 'symbols' not in task
    assert seen == symbols
    assert len(clients) == 1 and closed == [True]
    assert len(waits) == 12 and all(wait >= 1.09 for wait in waits)
    assert repo.get_run(task_id)['stocks'] == []
    filtered = manager.get_page(task_id, page=5, page_size=50, only_passed=True)
    assert filtered['pagination']['total'] == 245 and len(filtered['stocks']) == 45


def test_stop_resume_and_retry_keep_original_date_config_and_universe(tmp_path, monkeypatch):
    repo = USRepository(tmp_path / 'us.db')
    sdk = SimpleNamespace(universes=SimpleNamespace(get=lambda name: pool([f'T{i}.US' for i in range(45)])))
    snapshot = refresh_universe(repo, sdk=sdk)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def acquire(repo, chunk, **kw):
        calls.extend(chunk)
        entered.set()
        release.wait(5)
        return {'task_id': 'fetch', 'stocks': [{'symbol': c, 'status': 'FAILED', 'error': 'test'} if c == 'T0.US'
                else {'symbol': c, 'status': 'CACHED'} for c in chunk]}
    def evaluate(repo, chunk, **kw):
        return {'task_id': 'eval', 'stocks': [{'symbol': c, 'status': 'EVALUATED', 'candidate': {'candidate_type': 'REJECTED'}} for c in chunk]}
    monkeypatch.setattr('us_market.web_task.acquire_batch', acquire)
    monkeypatch.setattr('us_market.web_task.run_research', evaluate)
    manager = USResearchManager(repo)
    first = manager.start(None, scope='universe', as_of='2026-11-05')
    assert entered.wait(2)
    assert manager.stop(first)
    release.set()
    manager.join(10)
    stopped = manager.get_page(first)
    assert stopped['status'] == 'CANCELED'
    assert stopped['processed_count'] == 20 and stopped['pending_count'] == 25
    sdk.universes.get = lambda name: pool(['NEW.US'])
    refresh_universe(repo, sdk=sdk)
    second = manager.start(None, resume_of=first)
    manager.join(10)
    result = manager.get_page(second)
    assert result['processed_count'] == 45 and result['failed_count'] == 1
    assert result['universe_snapshot_id'] == snapshot['snapshot_id']
    assert result['context']['target_trade_date'] == '2026-11-05'
    assert calls == [f'T{i}.US' for i in range(45)]
    third = manager.start(None, retry_of=second)
    manager.join(10)
    assert calls[-1] == 'T0.US'
    assert manager.get_page(third)['total_count'] == 1


def test_online_prefetch_overlaps_evaluation_without_early_publication(tmp_path, monkeypatch):
    repo = USRepository(tmp_path / 'us.db')
    symbols = [f'T{i}.US' for i in range(41)]
    snapshot = refresh_universe(repo, sdk=SimpleNamespace(universes=SimpleNamespace(get=lambda _: pool(symbols))))
    second_fetch = threading.Event()
    release = threading.Event()
    requests = []

    def acquire(repo, chunk, **kwargs):
        requests.append(chunk[0])
        if chunk[0] == 'T20.US':
            second_fetch.set()
        return {'task_id': chunk[0], 'stocks': [{'symbol': code, 'status': 'CACHED'} for code in chunk]}

    def evaluate(repo, chunk, **kwargs):
        if chunk[0] == 'T0.US' and not release.wait(5):
            raise RuntimeError('first evaluation timed out')
        return {'task_id': chunk[0], 'stocks': [{'symbol': code, 'status': 'EVALUATED',
                'candidate': {'candidate_type': 'REJECTED'}} for code in chunk]}

    monkeypatch.setattr('us_market.web_task._create_free_sdk', lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr('us_market.web_task.acquire_batch', acquire)
    monkeypatch.setattr('us_market.web_task.run_research', evaluate)
    manager = USResearchManager(repo)
    task_id = manager.start(None, scope='universe', universe_snapshot_id=snapshot['snapshot_id'])
    try:
        assert second_fetch.wait(2)
        assert manager.get(task_id)['processed_count'] == 0
        assert manager.stop(task_id)
    finally:
        release.set()
        manager.join(10)
    assert requests == ['T0.US', 'T20.US']
    assert manager.get(task_id)['processed_count'] == 20
    assert manager.get(task_id)['status'] == 'CANCELED'


def test_stop_during_prefetch_throttle_does_not_mark_unrequested_batch_failed(tmp_path, monkeypatch):
    repo = USRepository(tmp_path / 'us.db')
    symbols = [f'T{i}.US' for i in range(40)]
    refresh_universe(repo, sdk=SimpleNamespace(universes=SimpleNamespace(get=lambda _: pool(symbols))))
    awaiting_second, release = threading.Event(), threading.Event()
    requests = []
    save_run = repo.save_run

    def save(task):
        save_run(task)
        if task.get('progress', {}).get('phase') == 'FETCHING' and task.get('processed_count') == 20:
            awaiting_second.set()

    def fetch(chunk, **kwargs):
        requests.append(chunk)
        return {}

    monkeypatch.setattr(repo, 'save_run', save)
    monkeypatch.setattr('us_market.web_task.monotonic', lambda: 0)
    monkeypatch.setattr('us_market.web_task.sleep', lambda _: release.wait(5))
    monkeypatch.setattr('us_market.web_task._create_free_sdk', lambda: SimpleNamespace(
        klines=SimpleNamespace(batch=fetch), close=lambda: None))
    manager = USResearchManager(repo)
    task_id = manager.start(None, scope='universe')
    try:
        assert awaiting_second.wait(3)
        assert manager.stop(task_id)
    finally:
        release.set()
        manager.join(10)
    result = manager.get(task_id)
    assert requests == [symbols[:20]]
    assert (result['status'], result['failed_count'], result['pending_count']) == ('CANCELED', 20, 20)


def test_manual_limit_remains_and_universe_must_exist(tmp_path):
    manager = USResearchManager(USRepository(tmp_path / 'us.db'))
    with pytest.raises(ValueError):
        manager.start(None, scope='universe')
    with pytest.raises(ValueError):
        manager.start([f'T{i}' for i in range(201)])


def test_explicit_old_pool_snapshot_is_used_after_latest_pool_changes(tmp_path, monkeypatch):
    repo = USRepository(tmp_path / 'us.db')
    sdk = SimpleNamespace(universes=SimpleNamespace(get=lambda _: pool(['AAPL.US'])))
    original = refresh_universe(repo, sdk=sdk)
    sdk.universes.get = lambda _: pool(['MSFT.US'])
    refresh_universe(repo, sdk=sdk)
    monkeypatch.setattr('us_market.web_task.acquire_batch', lambda repo, chunk, **kw:
                        {'task_id': 'fetch', 'stocks': [{'symbol': c, 'status': 'FAILED', 'error': 'test'} for c in chunk]})
    manager = USResearchManager(repo)
    task_id = manager.start(None, scope='universe', universe_snapshot_id=original['snapshot_id'])
    manager.join(5)
    assert manager.get_page(task_id)['stocks'][0]['symbol'] == 'AAPL.US'


def test_batch_stock_transaction_rolls_back_all_rows_on_invalid_result(tmp_path):
    repo = USRepository(tmp_path / 'us.db')
    task = {'task_id': 'atomic', 'market': 'US', 'research_only': True, 'symbols': ['AAPL.US', 'MSFT.US'], 'progress': {}}
    repo.initialize_job(task)
    with pytest.raises(ValueError):
        repo.complete_job_stocks(task, [{'symbol': 'AAPL.US', 'status': 'FAILED'}, {'symbol': 'UNKNOWN.US', 'status': 'FAILED'}])
    assert repo.job_symbols('atomic', 'PENDING') == ['AAPL.US', 'MSFT.US']


def test_large_pool_sql_pagination_without_unbounded_json_results(tmp_path, monkeypatch):
    repo = USRepository(tmp_path / 'us.db')
    sdk = SimpleNamespace(universes=SimpleNamespace(get=lambda _: pool([f'T{i}.US' for i in range(12412)])))
    refresh_universe(repo, sdk=sdk)
    monkeypatch.setattr('us_market.web_task.acquire_batch', lambda repo, chunk, **kw:
                        {'task_id': 'fetch', 'stocks': [{'symbol': c, 'status': 'FAILED', 'error': 'synthetic failure'} for c in chunk]})
    manager = USResearchManager(repo)
    task_id = manager.start(None, scope='universe')
    manager.join(60)
    page = manager.get_page(task_id, page=249)
    assert page['status'] == 'COMPLETED_WITH_ERRORS'
    assert page['processed_count'] == page['failed_count'] == 12412
    assert len(page['stocks']) == 12
    assert page['pagination']['total'] == 12412
    assert 'symbols' not in manager.tasks()[0]


def test_universe_api_uses_cached_pool_and_paginates_over_200(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import server
    repo = USRepository(tmp_path / 'us.db')
    sdk = SimpleNamespace(universes=SimpleNamespace(get=lambda _: pool([f'T{i}.US' for i in range(245)])))
    snapshot = refresh_universe(repo, sdk=sdk)
    manager = USResearchManager(repo)
    monkeypatch.setattr(server, '_get_us_manager', lambda: manager)
    monkeypatch.setattr(server, '_scan_conflict_response', lambda: None)
    monkeypatch.setattr(server, '_set_running', lambda *a, **kw: None)
    monkeypatch.setattr(server, '_clear_running', lambda: None)
    monkeypatch.setattr('us_market.web_task.acquire_batch', lambda repo, chunk, **kw:
                        {'task_id': 'fetch', 'stocks': [{'symbol': c, 'status': 'FAILED', 'error': 'mock error'} for c in chunk]})
    client = TestClient(server.app)
    response = client.get('/api/us/data/universe').json()['universe']
    assert response['usable_count'] == 245 and 'symbols' not in response
    response = client.post('/api/us/strategy6/research', json={'scope': 'universe', 'universe_snapshot_id': snapshot['snapshot_id']})
    assert response.status_code == 200
    task_id = response.json()['task_id']
    manager.join(10)
    page = client.get(f'/api/us/strategy6/tasks/{task_id}?page=2&page_size=50').json()['task']
    assert page['stocks'][0]['symbol'] == 'T50.US' and len(page['stocks']) == 50
    assert page['failed_count'] == 245
    assert client.get(f'/api/us/strategy6/tasks/{task_id}?page=0').status_code == 400
    assert client.get(f'/api/us/strategy6/tasks/{task_id}?only_passed=true').json()['task']['stocks'] == []
    assert client.post(f'/api/us/strategy6/tasks/{task_id}/stop').status_code == 409


def test_task_summary_and_rows_are_read_from_same_snapshot(tmp_path, monkeypatch):
    from contextlib import contextmanager
    repo = USRepository(tmp_path / 'us.db')
    writer = USRepository(repo.path)
    task = {'task_id': 'snapshot-read', 'kind': 'job', 'market': 'US', 'research_only': True,
            'symbols': ['AAPL.US'], 'stock_storage': 'rows_v1', 'progress': {}}
    writer.initialize_job(task)
    connect = repo.connection

    @contextmanager
    def intercepted():
        with connect() as conn:
            class Reader:
                def execute(self, sql, args=()):
                    cursor = conn.execute(sql, args)
                    if sql.startswith('SELECT payload FROM us_runs'):
                        writer.complete_job_stocks(task, [{'symbol': 'AAPL.US', 'status': 'FAILED'}])
                    return cursor
            yield Reader()
    monkeypatch.setattr(repo, 'connection', intercepted)
    view = repo.job_page(task['task_id'])
    assert view['processed_count'] == 0 and view['stocks'][0]['status'] == 'PENDING'
    assert writer.job_page(task['task_id'])['processed_count'] == 1
