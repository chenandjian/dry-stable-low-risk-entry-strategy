from datetime import datetime, timezone

from fastapi.testclient import TestClient
import pytest

import server
from us_market.observations import pool_view
from us_market.repository import USRepository


def _job(repo, ident, day, stocks, *, status='COMPLETED'):
    task = dict(task_id=ident, kind='job', market='US', research_only=True,
                symbols=[s['symbol'] for s in stocks], progress={}, status='RUNNING',
                context={'target_trade_date': day}, stock_storage='rows_v1')
    repo.initialize_job(task)
    repo.complete_job_stocks(task, [s for s in stocks if s['status'] != 'PENDING'])
    task.update(status=status, finished_at=datetime.now(timezone.utc).isoformat())
    repo.finish_job(task)


def _evidence(day, stamp, *, symbol='AAPL.US', state='VCP_CONFIRMED', qualified=True,
              hit=True, origin='2026-10-01', version='test-v1'):
    return dict(symbol=symbol, status='EVALUATED', evaluation_date=day, evaluated_at=stamp,
                candidate=dict(code=symbol, market='US', research_only=True,
                               evaluation_date=day, strategy_version=version, config_hash='config',
                               candidate_type='WATCH_CANDIDATE' if hit else 'REJECTED', total_score=72,
                               vcp_origin_start_date=origin, vcp_pattern_start_date='2026-10-09',
                               vcp_observation_eligible=qualified, vcp_history_qualified=qualified,
                               vcp_lifecycle_status=state, vcp_contraction_count=2,
                               vcp_breakout_date=day if state == 'VCP_BREAKOUT_CONFIRMED' else '',
                               vcp_invalidation_reason='SUPPORT_FAILED' if state == 'VCP_INVALID' else ''))


def test_daily_dedup_breakout_invalid_and_missing_data(tmp_path):
    repo = USRepository(tmp_path / 'us.db')
    d1, d2, d3 = '2026-11-04', '2026-11-05', '2026-11-06'
    _job(repo, 'first', d1, [_evidence(d1, '2026-11-05T00:00:00+00:00')])
    _job(repo, 'breakout', d2, [_evidence(d2, '2026-11-06T02:00:00+00:00', state='VCP_BREAKOUT_CONFIRMED')])
    _job(repo, 'old-rerun', d2, [_evidence(d2, '2026-11-06T01:00:00+00:00', state='VCP_INVALID', qualified=False)])
    _job(repo, 'failed', d3, [{'symbol': 'AAPL.US', 'status': 'FAILED'}], status='COMPLETED_WITH_ERRORS')
    _job(repo, 'stopped', d3, [_evidence(d3, '2026-11-07T00:00:00+00:00', state='VCP_INVALID', qualified=False)], status='CANCELED')
    tracked = pool_view(repo.path, view='vcp', as_of=d3)['rows'][0]
    assert tracked['first_seen_date'] == d1 and tracked['confirmed_days'] == 2
    assert tracked['status'] == 'VCP_BREAKOUT_CONFIRMED'
    assert tracked['breakout_date'] == d2 and tracked['last_evaluation_date'] == d2
    assert tracked['updated_on_date'] is False

    _job(repo, 'confirmed-exit', d3, [_evidence(d3, '2026-11-07T01:00:00+00:00', state='VCP_INVALID', qualified=False, hit=False)])
    assert pool_view(repo.path, view='vcp', as_of=d2)['rows'][0]['status'] == 'VCP_BREAKOUT_CONFIRMED'
    assert pool_view(repo.path, view='vcp', as_of=d3)['rows'][0]['status'] == 'VCP_INVALID'
    assert pool_view(repo.path, view='candidates', as_of=d3)['total'] == 0


def test_pool_requires_history_qualification_and_separates_new_structures(tmp_path):
    repo = USRepository(tmp_path / 'us.db')
    d1, d2, d3 = '2026-11-04', '2026-11-05', '2026-11-06'
    unqualified = _evidence(d1, '2026-11-05T00:00:00+00:00')
    unqualified['candidate']['vcp_history_qualified'] = False
    _job(repo, 'unqualified', d1, [unqualified])
    assert pool_view(repo.path, view='vcp', as_of=d1)['total'] == 0
    _job(repo, 'qualified', d2, [_evidence(d2, '2026-11-06T00:00:00+00:00')])
    _job(repo, 'new', d3, [_evidence(d3, '2026-11-07T00:00:00+00:00', origin='2026-10-02')])
    row = pool_view(repo.path, view='vcp', as_of=d3)['rows'][0]
    assert row['first_seen_date'] == d3 and row['confirmed_days'] == 1
    hit = pool_view(repo.path, view='candidates', as_of=d3)['rows'][0]
    assert hit['first_seen_date'] == d1 and hit['confirmed_days'] == 3


def test_us_pool_api_is_read_only_without_creating_database(tmp_path, monkeypatch):
    monkeypatch.setattr(server, '_us_database_path', lambda: tmp_path / 'us.db')
    def forbidden(*args, **kwargs):
        raise AssertionError('pool read must not create a task manager')
    monkeypatch.setattr(server, '_get_us_manager', forbidden)
    client = TestClient(server.app)
    response = client.get('/api/us/strategy6/observations?view=vcp')
    assert response.status_code == 200 and response.json()['total'] == 0
    assert not (tmp_path / 'us.db').exists()
    assert client.get('/api/us/strategy6/observations?as_of=2026-02-30').status_code == 400


def test_not_reconfirmed_is_not_an_exit_and_profiles_do_not_mix(tmp_path):
    repo = USRepository(tmp_path / 'us.db')
    d1, d2, d3 = '2026-11-04', '2026-11-05', '2026-11-06'
    _job(repo, 'first', d1, [_evidence(d1, '2026-11-05T00:00:00+00:00')])
    _job(repo, 'not-confirmed', d2, [_evidence(d2, '2026-11-06T00:00:00+00:00', state='VCP_NONE', qualified=False)])
    row = pool_view(repo.path, view='vcp', as_of=d2)['rows'][0]
    assert row['status'] == 'VCP_NOT_RECONFIRMED' and row['exit_date'] is None
    _job(repo, 'new-profile', d3, [_evidence(d3, '2026-11-07T00:00:00+00:00', version='test-v2')])
    row = pool_view(repo.path, view='vcp', as_of=d3)['rows'][0]
    assert row['first_seen_date'] == d3 and row['confirmed_days'] == 1


def test_expired_then_reentry_starts_new_confirmation_count(tmp_path):
    repo = USRepository(tmp_path / 'us.db')
    d1, d2, d3 = '2026-11-04', '2026-11-05', '2026-11-06'
    _job(repo, 'first', d1, [_evidence(d1, '2026-11-05T00:00:00+00:00')])
    expired = _evidence(d2, '2026-11-06T00:00:00+00:00', state='VCP_NONE', qualified=False)
    expired['candidate']['vcp_observation_risk_tags'] = ['VCP_OBSERVATION_EXPIRED']
    _job(repo, 'expired', d2, [expired])
    assert pool_view(repo.path, view='vcp', as_of=d2)['rows'][0]['status'] == 'VCP_EXPIRED'
    _job(repo, 'reenter', d3, [_evidence(d3, '2026-11-07T00:00:00+00:00')])
    row = pool_view(repo.path, view='vcp', as_of=d3)['rows'][0]
    assert row['first_seen_date'] == d3 and row['confirmed_days'] == 1


def test_evidence_is_rolled_back_if_task_completion_write_fails(tmp_path):
    repo = USRepository(tmp_path / 'us.db')
    day = '2026-11-05'
    task = dict(task_id='rollback', kind='job', market='US', research_only=True,
                symbols=['AAPL.US'], progress={}, status='RUNNING',
                context={'target_trade_date': day}, stock_storage='rows_v1')
    repo.initialize_job(task)
    repo.complete_job_stocks(task, [_evidence(day, '2026-11-06T00:00:00+00:00')])
    task.update(status='COMPLETED', broken=float('nan'))
    with pytest.raises(ValueError):
        repo.finish_job(task)
    assert repo.get_run('rollback')['status'] == 'RUNNING'
    assert pool_view(repo.path, view='candidates')['total'] == 0
