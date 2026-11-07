from pathlib import Path

import pytest

from us_market.full_pool_audit import audit_full_pool
from us_market.repository import USRepository


def test_audit_distinguishes_empty_candidate_pool_from_incomplete_scan(tmp_path):
    repo = USRepository(tmp_path / 'us.db')
    repo.save_universe(dict(snapshot_id='pool', source='tickflow_free',
                            symbols=['AAPL.US', 'MSFT.US', 'XYZ.US'], provider_count=3))
    task = dict(task_id='job', kind='job', market='US', research_only=True, scope='universe',
                universe_snapshot_id='pool', symbols=['AAPL.US', 'MSFT.US', 'XYZ.US'],
                context={'target_trade_date': '2026-11-06'}, progress={}, status='RUNNING')
    repo.initialize_job(task)
    repo.complete_job_stocks(task, [
        dict(symbol='AAPL.US', status='EVALUATED', evaluation_date='2026-11-06',
             evaluated_at='2026-11-07T00:00:00+00:00',
             candidate=dict(evaluation_date='2026-11-06', market='US', research_only=True,
                            strategy_version='v1', config_hash='hash', candidate_type='REJECTED',
                            reject_reasons=['NO_STRONG_START'])),
        dict(symbol='MSFT.US', status='FAILED', error='STALE_OR_UNPUBLISHED: latest=2026-11-05'),
    ])
    partial = audit_full_pool(repo.path, 'job')
    assert (partial['evaluated'], partial['failed'], partial['pending']) == (1, 1, 1)
    assert not partial['coverage_complete']
    assert partial['failure_reasons'] == {'STALE_OR_UNPUBLISHED': 1}
    assert partial['published_evidence'] == 0

    repo.complete_job_stocks(task, [dict(symbol='XYZ.US', status='FAILED', error='MISSING_SYMBOL_IN_BATCH')])
    task['status'] = 'COMPLETED_WITH_ERRORS'
    repo.finish_job(task)
    completed = audit_full_pool(repo.path, 'job')
    assert completed['all_symbols_terminal']
    assert not completed['coverage_complete']
    assert completed['candidate_count'] == 0
    assert completed['published_evidence'] == 1
    assert completed['checks'] == []


def test_audit_is_read_only_and_rejects_nonexistent_database(tmp_path):
    path = Path(tmp_path / 'missing.db')
    with pytest.raises(FileNotFoundError):
        audit_full_pool(path, 'job')
    assert not path.exists()
