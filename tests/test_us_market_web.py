import threading
import pytest
from fastapi.testclient import TestClient
import server
from us_market.web_task import USResearchManager
from us_market.repository import USRepository


def test_manager_progress_failure_retry_and_no_concurrent_start(tmp_path, monkeypatch):
    repo = USRepository(tmp_path / 'us.db')
    manager = USResearchManager(repo)
    entered, release = threading.Event(), threading.Event()
    def fetch(repo, symbols, **kwargs):
        kwargs['progress']({'phase': 'FETCHING', 'processed': 0, 'total': len(symbols), 'symbols': symbols})
        entered.set()
        release.wait(5)
        return {'task_id': 'fetch-id', 'failed': 1, 'stocks': [{'symbol': symbols[0], 'status': 'FAILED', 'error': 'MISSING_TARGET_SESSION'}]}
    monkeypatch.setattr('us_market.web_task.acquire_batch', fetch)
    first = manager.start(['AAPL'], count=1100)
    assert entered.wait(2)
    assert manager.get(first)['progress']['phase'] == 'FETCHING'
    try:
        manager.start(['MSFT'])
        assert False, 'concurrent task was allowed'
    except RuntimeError:
        pass
    release.set()
    manager.join(5)
    result = manager.get(first)
    assert result['status'] == 'COMPLETED_WITH_ERRORS'
    assert result['stocks'][0]['error'] == 'MISSING_TARGET_SESSION'
    assert result['research_only'] and not result['market_filter_enabled']


def test_us_api_validates_and_never_initializes_cn_database(tmp_path, monkeypatch):
    manager = USResearchManager(USRepository(tmp_path / 'us.db'))
    monkeypatch.setattr(server, '_get_us_manager', lambda: manager)
    monkeypatch.setattr(server, '_scan_conflict_response', lambda: None)
    monkeypatch.setattr(server, '_set_running', lambda *a, **kw: None)
    monkeypatch.setattr(server, '_clear_running', lambda: None)
    monkeypatch.setattr('us_market.web_task.acquire_batch', lambda *a, **k: {'task_id': 'fetch-id', 'failed': 1, 'stocks': [{'symbol': 'AAPL.US', 'status': 'FAILED', 'error': 'network error'}]})
    client = TestClient(server.app)
    assert client.post('/api/us/strategy6/research', json={'symbols': ['600000.SH']}).status_code == 400
    assert client.post('/api/us/strategy6/research', json={'symbols': ['AAPL'], 'count': True}).status_code == 400
    response = client.post('/api/us/strategy6/research', json={'symbols': ['AAPL']})
    assert response.status_code == 200
    task_id = response.json()['task_id']
    manager.join(5)
    task = client.get(f'/api/us/strategy6/tasks/{task_id}').json()['task']
    assert task['stocks'][0]['status'] == 'FAILED'
    assert client.get('/api/us/strategy6/tasks/s6-cn-task').status_code == 404
    assert client.get('/api/us/strategy6/tasks').json()['tasks'][0]['task_id'] == task_id


def test_manager_marks_previous_unfinished_jobs_interrupted(tmp_path):
    repo = USRepository(tmp_path / 'us.db')
    repo.save_run({'task_id': 'us-old', 'kind': 'job', 'market': 'US', 'research_only': True,
                   'status': 'RUNNING', 'stocks': []})
    manager = USResearchManager(repo)
    assert manager.get('us-old')['status'] == 'INTERRUPTED'


def test_startup_storage_error_always_releases_task_lock(tmp_path, monkeypatch):
    repo = USRepository(tmp_path / 'us.db')
    manager = USResearchManager(repo)
    released = []
    def fail(*args):
        raise OSError('disk write failed')
    monkeypatch.setattr(repo, 'save_run', fail)
    with pytest.raises(OSError):
        manager.start(['AAPL'], on_finish=lambda: released.append(True))
    assert not manager.lock.locked()
    assert released == [True]
