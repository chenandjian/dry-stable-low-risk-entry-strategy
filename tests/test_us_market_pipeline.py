from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from us_market.calendar import freshness, target_session
from us_market.repository import USRepository
from us_market.service import acquire_batch, run_research
from strategy6.engine import StrongVcpTailEngine
from strategy6.strong_start import _build_start_candidate


def bars(n=30):
    import pandas as pd
    return [dict(date=day.strftime('%Y-%m-%d'), open=20, high=21, low=19,
                 close=20, volume=1_000_000, turnover=None)
            for day in pd.bdate_range(end='2026-11-05', periods=n)]


@pytest.mark.parametrize('when,expected', [
    ('2026-11-06T20:59:00+00:00', '2026-11-05'),
    ('2026-11-06T21:09:59+00:00', '2026-11-05'),
    ('2026-11-06T21:10:00+00:00', '2026-11-06'),
    ('2026-11-07T08:00:00+00:00', '2026-11-06'),
    ('2026-11-26T22:00:00+00:00', '2026-11-25'),
    ('2026-11-27T18:09:00+00:00', '2026-11-25'),
    ('2026-11-27T18:10:00+00:00', '2026-11-27'),
    ('2026-03-09T20:10:00+00:00', '2026-03-09'),
])
def test_calendar_holidays_early_close_and_dst(when, expected):
    assert target_session(datetime.fromisoformat(when))['target_trade_date'] == expected


def test_cache_must_cover_target_and_be_fetched_after_close():
    context = target_session(datetime.fromisoformat('2026-11-06T22:00:00+00:00'))
    assert not freshness('2026-11-06', '2026-11-06T20:00:00+00:00', context)
    assert freshness('2026-11-06', '2026-11-06T21:30:00+00:00', context)
    assert not freshness('2026-11-05', '2026-11-06T22:00:00+00:00', context)
    with pytest.raises(ValueError):
        target_session(datetime(2026, 11, 6))


def test_explicit_historical_evaluation_never_changes_live_target():
    from us_market.calendar import evaluation_context
    now = datetime.fromisoformat('2026-11-07T08:00:00+00:00')
    context = evaluation_context(now, '2026-11-05')
    assert context['target_trade_date'] == '2026-11-05'
    assert context['live_target_trade_date'] == '2026-11-06'
    assert context['historical_evaluation']
    for day in ['2026-11-07', '2026-11-08', '2026-11-26']:
        with pytest.raises(ValueError):
            evaluation_context(now, day)


def test_batch_saves_each_chunk_before_next_request_and_tracks_failures(tmp_path):
    repo = USRepository(tmp_path / 'us.db')
    calls = []

    def batch(symbols, **kwargs):
        assert kwargs['adjust'] == 'forward'
        assert kwargs['batch_size'] == 2
        if calls:
            assert repo.get_history('AAPL.US')['rows'][-1]['close'] == 20
        calls.append(symbols)
        return {symbol: bars() for symbol in symbols if symbol != 'BAD.US'}

    sdk = SimpleNamespace(klines=SimpleNamespace(batch=batch))
    result = acquire_batch(repo, ['aapl', 'MSFT', 'BAD'], count=30, batch_size=2,
                           sdk=sdk, now=datetime(2026, 11, 6, 15, tzinfo=timezone.utc))
    assert calls == [['AAPL.US', 'MSFT.US'], ['BAD.US']]
    assert result['succeeded'] == 2 and result['failed'] == 1
    assert result['stocks'][-1]['symbol'] == 'BAD.US'
    assert result['stocks'][-1]['status'] == 'FAILED'
    assert repo.get_history('AAPL.US')['rows'][-1]['turnover'] is None
    row = repo.get_history('AAPL.US')['rows'][-1]
    assert row['turnover_estimated_usd'] == 20_000_000
    assert row['volume'] == 1_000_000
    assert repo.get_history('AAPL.US')['metadata']['volume_basis'] == 'PROVIDER_UNVERIFIED'
    assert repo.get_run(result['task_id']) == result


def test_successful_cache_reused_but_failure_retried(tmp_path, monkeypatch):
    repo = USRepository(tmp_path / 'us.db')
    def batch(symbols, **kw):
        return {symbol: bars() for symbol in symbols if symbol == 'AAPL.US'}
    now = datetime(2026, 11, 6, 15, tzinfo=timezone.utc)
    sdk = SimpleNamespace(klines=SimpleNamespace(batch=batch))
    first = acquire_batch(repo, ['AAPL', 'BAD'], count=30, sdk=sdk, now=now)
    requested = []
    sdk.klines.batch = lambda symbols, **kw: requested.extend(symbols) or {symbol: bars() for symbol in symbols}
    second = acquire_batch(repo, ['AAPL', 'BAD'], count=30, sdk=sdk, now=now, retain_histories=True)
    assert requested == ['BAD.US']
    assert second['cached'] == 1 and second['failed'] == 0
    assert first['failed'] == 1
    assert set(second['histories']) == {'AAPL.US', 'BAD.US'}
    assert 'histories' not in repo.get_run(second['task_id'])

    def forbidden(*args):
        raise AssertionError('prefetched histories must not be read again')

    monkeypatch.setattr(repo, 'get_history', forbidden)
    monkeypatch.setattr(repo, 'history_records', forbidden)
    evaluated = run_research(repo, ['AAPL', 'BAD'], now=now, histories=second['histories'], batch_commit=True)
    assert evaluated['evaluated'] == 2


def test_stale_response_does_not_overwrite_good_history_or_get_evaluated(tmp_path):
    repo = USRepository(tmp_path / 'us.db')
    sdk = SimpleNamespace(klines=SimpleNamespace(batch=lambda *a, **k: {'AAPL.US': bars()}))
    acquire_batch(repo, ['AAPL'], count=30, sdk=sdk, now=datetime(2026, 11, 6, 15, tzinfo=timezone.utc))
    result = acquire_batch(repo, ['AAPL'], count=30, sdk=sdk, force=True,
                           now=datetime(2026, 11, 7, 1, tzinfo=timezone.utc))
    assert result['failed'] == 1
    assert 'STALE' in result['stocks'][0]['error']
    assert repo.get_history('AAPL.US')['rows'][-1]['date'] == '2026-11-05'


def test_us_engine_never_uses_a_share_limit_up_or_market_and_cn_default_unchanged(monkeypatch):
    cn = StrongVcpTailEngine()
    us = StrongVcpTailEngine(market_profile='US_RESEARCH_NO_INDEX')
    assert cn.config['enable_market_filter'] is True
    assert 'market_profile' not in cn.config
    assert us.config['enable_market_filter'] is False
    assert us.config['decision_profile'] == 'formal_original'
    from strategy6.validation import strategy6_config_hash
    assert cn.config == StrongVcpTailEngine().config
    assert strategy6_config_hash(cn.config) != strategy6_config_hash(us.config)
    data = [dict(row, amount=20_000_000, prev_close=20) for row in bars()]
    data[-1].update(open=21, high=23, low=20, close=22, volume=3_000_000)
    def forbidden(*args, **kwargs):
        raise AssertionError('A-share limit-up helper called for US')
    monkeypatch.setattr('strategy6.strong_start.is_limit_up_day', forbidden)
    monkeypatch.setattr('strategy6.strong_start.is_one_word_limit_up', forbidden)
    monkeypatch.setattr('strategy6.strong_start.is_touched_limit_up_failed', forbidden)
    candidate = _build_start_candidate(data, len(data) - 1, us.config, 'AAPL.US')
    assert candidate.start_type == 'NORMAL_STRONG_BREAKOUT'
    assert not candidate.is_limit_up and candidate.limit_up_pct == 0
    assert candidate.start_day_self_amount_percentile == 0
    evaluation = us.evaluate_at(data, code='AAPL.US', rows_normalized=True)
    assert evaluation.indicators.market_status == 'UNAVAILABLE_US_RESEARCH'
    assert evaluation.selection_diagnostics.matched_market_symbol == ''
    with pytest.raises(ValueError):
        us.evaluate_at(data, code='AAPL.US', market_data_by_symbol={'sh000001': data})


def test_historical_research_does_not_read_future_bars(tmp_path):
    repo = USRepository(tmp_path / 'us.db')
    data = bars(500)
    data.append(dict(data[-1], date='2026-11-06', close=20.5))
    sdk = SimpleNamespace(klines=SimpleNamespace(batch=lambda *a, **k: {'AAPL.US': data}))
    now = datetime(2026, 11, 7, 1, tzinfo=timezone.utc)
    acquire_batch(repo, ['AAPL'], count=500, sdk=sdk, now=now)
    first = run_research(repo, ['AAPL'], as_of='2026-11-05', now=now)
    history = repo.get_history('AAPL.US')
    assert len(history['rows']) == 501
    history['rows'][-1].update(open=200, high=210, low=190, close=205, turnover_estimated_usd=205_000_000)
    repo.save_history('AAPL.US', history['rows'], history['metadata'])
    second = run_research(repo, ['AAPL'], as_of='2026-11-05', now=now)
    assert first['stocks'][0]['candidate'] == second['stocks'][0]['candidate']


def test_research_calls_single_engine_and_persists_explicit_warnings(tmp_path, monkeypatch):
    repo = USRepository(tmp_path / 'us.db')
    sdk = SimpleNamespace(klines=SimpleNamespace(batch=lambda *a, **k: {'AAPL.US': bars(500)}))
    now = datetime(2026, 11, 6, 15, tzinfo=timezone.utc)
    acquire_batch(repo, ['AAPL'], count=500, sdk=sdk, now=now)
    calls = []
    original = StrongVcpTailEngine.evaluate_at
    def evaluate(self, data, **kwargs):
        calls.append(kwargs['code'])
        return original(self, data, **kwargs)
    monkeypatch.setattr(StrongVcpTailEngine, 'evaluate_at', evaluate)
    result = run_research(repo, ['AAPL', 'MISSING'], now=now)
    assert calls == ['AAPL.US']
    assert result['research_only'] and not result['market_filter_enabled']
    assert result['status'] == 'COMPLETED_WITH_ERRORS'
    assert 'MARKET_FILTER_DISABLED_NO_INDEX' in result['warnings']
    assert result['stocks'][0]['evaluation_date'] == '2026-11-05'
    assert repo.get_run(result['task_id']) == result


@pytest.mark.parametrize('replay_fails', [False, True])
def test_us_vcp_replay_uses_normalized_history_without_rejecting_core_evaluation(tmp_path, monkeypatch, replay_fails):
    from strategy6.vcp_history import Strategy6VcpCandidateHistory
    repo = USRepository(tmp_path / 'us.db')
    sdk = SimpleNamespace(klines=SimpleNamespace(batch=lambda *a, **k: {'AAPL.US': bars(500)}))
    now = datetime(2026, 11, 6, 15, tzinfo=timezone.utc)
    acquire_batch(repo, ['AAPL'], count=500, sdk=sdk, now=now)
    original = StrongVcpTailEngine.evaluate_at
    def evaluate(self, rows, **kwargs):
        result = original(self, rows, **kwargs)
        result.vcp_observation.eligible = True
        result.vcp_observation.origin_start_date = '2026-10-01'
        result.vcp_observation.pattern_start_date = '2026-10-09'
        return result
    def replay(**kwargs):
        assert kwargs['rows_normalized'] is True
        assert kwargs['rows'][-1]['amount'] == 20_000_000
        assert kwargs['rows'][-1]['date'] == '2026-11-05'
        assert kwargs['market_data_by_symbol'] == {}
        assert kwargs['engine_factory'](kwargs['strategy_config']).market_profile == 'US_RESEARCH_NO_INDEX'
        if replay_fails:
            raise RuntimeError('diagnostic error')
        return Strategy6VcpCandidateHistory(qualified=True, candidate_date='2026-11-04', candidate_type='WATCH_CANDIDATE')
    monkeypatch.setattr(StrongVcpTailEngine, 'evaluate_at', evaluate)
    monkeypatch.setattr('strategy6.vcp_history.evaluate_vcp_candidate_history', replay)
    stock = run_research(repo, ['AAPL'], now=now)['stocks'][0]
    assert stock['status'] == 'EVALUATED'
    assert stock['candidate']['vcp_history_qualified'] is not replay_fails
    assert ('VCP_REPLAY_FAILED' in stock['candidate']['vcp_observation_risk_tags']) is replay_fails
