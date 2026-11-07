"""US-only acquisition and Strategy6 research orchestration."""
from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import CancelledError
from datetime import datetime, timezone
import logging
from time import perf_counter
from uuid import uuid4

from .calendar import freshness, evaluation_context
from .daily_data import _create_free_sdk, normalize_bars
from .instruments import provider_symbol


logger = logging.getLogger(__name__)
WARNINGS = ['MARKET_FILTER_DISABLED_NO_INDEX', 'VOLUME_BASIS_UNVERIFIED',
            'ESTIMATED_TURNOVER_NOT_ACTUAL', 'SECURITY_TYPE_NOT_VERIFIED',
            'PROVIDER_PUBLICATION_TIME_UNVERIFIED', 'RESEARCH_ONLY_CURRENT_UNIVERSE']
ESTIMATION_METHOD = 'FORWARD_CLOSE_X_PROVIDER_VOLUME_V1'


def _symbols(symbols):
    if not isinstance(symbols, (list, tuple)) or not symbols or any(not isinstance(symbol, str) for symbol in symbols):
        raise ValueError('provide a nonempty list of US symbols')
    return list(dict.fromkeys(provider_symbol(symbol) for symbol in symbols))


def _run(kind, symbols, now, context):
    return {'task_id': f'us-s6-{kind}-{uuid4().hex}', 'kind': kind, 'market': 'US',
            'research_only': True, 'formal_scan_allowed': False,
            'market_filter_enabled': False, 'warnings': list(WARNINGS),
            'started_at': now.isoformat(), 'context': context, 'symbols': symbols,
            'status': 'RUNNING', 'stocks': []}


def acquire_batch(repository, symbols, *, count=1100, batch_size=20, force=False,
                  sdk=None, now=None, as_of=None, progress=None, before_request=None,
                  retain_histories=False):
    symbols = _symbols(symbols)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 5000:
        raise ValueError('count must be between 1 and 5000')
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 100:
        raise ValueError('batch size must be between 1 and 100')
    now = now or datetime.now(timezone.utc)
    context = evaluation_context(now, as_of)
    run = _run('fetch', symbols, now, context)
    run.update(requested_count=count, batch_size=batch_size, adjustment='forward',
               estimation_method=ESTIMATION_METHOD, succeeded=0, failed=0, cached=0)
    repository.save_run(run)
    pending = []
    histories = {}
    records = repository.history_records(symbols) if retain_histories and not force else {}
    for symbol in symbols:
        history = None
        if not force:
            history = (repository.decode_history(records.pop(symbol, None))
                       if retain_histories else repository.get_history(symbol))
        if not force and history and history['metadata']['requested_count'] >= count and any(
            row['date'] == context['target_trade_date'] for row in history['rows']
        ) and freshness(
            history['rows'][-1]['date'], history['metadata']['fetched_at'], context
        ):
            run['stocks'].append({'symbol': symbol, 'status': 'CACHED', 'latest_date': history['rows'][-1]['date']})
            run['cached'] += 1
            if retain_histories:
                histories[symbol] = history
        else:
            pending.append(symbol)
    owned = sdk is None
    try:
        if pending and owned:
            sdk = _create_free_sdk()
        for start in range(0, len(pending), batch_size):
            chunk = pending[start:start + batch_size]
            if progress:
                progress({'phase': 'FETCHING', 'processed': len(run['stocks']), 'total': len(symbols), 'symbols': chunk})
            try:
                if before_request:
                    before_request()
                start = perf_counter()
                try:
                    frames = sdk.klines.batch(chunk, period='1d', count=count, adjust='forward',
                                              as_dataframe=True, batch_size=batch_size,
                                              max_workers=2, show_progress=False)
                finally:
                    run['provider_requests'] = run.get('provider_requests', 0) + 1
                    run['provider_seconds'] = run.get('provider_seconds', 0.0) + perf_counter() - start
                if not isinstance(frames, Mapping) or set(frames) - set(chunk):
                    raise ValueError('unexpected batch symbols or response type')
                error = None
            except CancelledError:
                raise
            except Exception as exc:
                frames, error = {}, str(exc)
            for symbol in chunk:
                try:
                    if symbol not in frames:
                        raise ValueError(error or 'MISSING_SYMBOL_IN_BATCH')
                    frame = frames[symbol]
                    raw = frame.to_dict('records') if hasattr(frame, 'to_dict') else frame
                    if any(item.get('symbol', symbol) != symbol for item in raw):
                        raise ValueError('response symbol mismatch')
                    rows = normalize_bars(raw)
                    rows = [row for row in rows if row['date'] <= context['live_target_trade_date']]
                    if not rows or not any(row['date'] == context['target_trade_date'] for row in rows):
                        latest = rows[-1]['date'] if rows else 'NONE'
                        raise ValueError(f'STALE_OR_UNPUBLISHED: latest={latest}, target={context["target_trade_date"]}; not assumed suspended')
                    for row in rows:
                        row['turnover_estimated_usd'] = row['close'] * row['volume']
                    metadata = {'source': 'tickflow_free', 'adjustment': 'forward',
                                'price_basis': 'PROVIDER_FORWARD', 'volume_basis': 'PROVIDER_UNVERIFIED',
                                'estimation_method': ESTIMATION_METHOD, 'currency': 'USD',
                                'fetched_at': now.isoformat(), 'requested_count': count}
                    metadata = repository.save_history(symbol, rows, metadata)
                    if retain_histories:
                        histories[symbol] = {'metadata': metadata, 'rows': rows}
                    run['stocks'].append({'symbol': symbol, 'status': 'FETCHED', 'latest_date': rows[-1]['date'], 'rows': len(rows)})
                    run['succeeded'] += 1
                except Exception as exc:
                    logger.warning('US fetch failed %s: %s', symbol, exc)
                    run['stocks'].append({'symbol': symbol, 'status': 'FAILED', 'error': str(exc)})
                    run['failed'] += 1
            repository.save_run(run)
            if progress:
                progress({'phase': 'SAVED', 'processed': len(run['stocks']), 'total': len(symbols), 'symbols': chunk})
    except CancelledError:
        run.update(status='CANCELED', finished_at=datetime.now(timezone.utc).isoformat())
        repository.save_run(run)
        raise
    except Exception as exc:
        for symbol in pending:
            if not any(stock['symbol'] == symbol for stock in run['stocks']):
                run['stocks'].append({'symbol': symbol, 'status': 'FAILED', 'error': str(exc)})
                run['failed'] += 1
    finally:
        if owned and sdk is not None:
            sdk.close()
    run['status'] = 'COMPLETED_WITH_ERRORS' if run['failed'] else 'COMPLETED'
    run['finished_at'] = datetime.now(timezone.utc).isoformat()
    repository.save_run(run)
    if retain_histories:
        run['histories'] = histories
    return run


def research_rows(history, context):
    if not history or not history['rows'] or not freshness(
        history['rows'][-1]['date'], history['metadata']['fetched_at'], context
    ):
        raise ValueError('MISSING_OR_STALE_HISTORY')
    rows, previous = [], 0.0
    for row in history['rows']:
        if row['date'] > context['target_trade_date']:
            continue
        rows.append(dict(row, amount=row['turnover_estimated_usd'], prev_close=previous))
        previous = row['close']
    if not rows or rows[-1]['date'] != context['target_trade_date']:
        raise ValueError('MISSING_TARGET_SESSION')
    return rows


def _review_vcp(evaluation, rows, symbol, engine):
    from strategy6.engine import StrongVcpTailEngine
    from strategy6.vcp_history import evaluate_vcp_candidate_history
    from strategy6.vcp_quality import evaluate_vcp_quality

    vcp = evaluation.vcp_observation
    if not vcp.eligible:
        return
    try:
        replay = evaluate_vcp_candidate_history(
            rows=rows, rows_normalized=True, market_data_by_symbol={},
            strategy_config=engine.config, code=symbol, name='',
            origin_start_date=vcp.origin_start_date, evaluation_date=rows[-1]['date'],
            pattern_start_date=vcp.pattern_start_date,
            engine_factory=lambda cfg: StrongVcpTailEngine(cfg, market_profile='US_RESEARCH_NO_INDEX'),
        )
    except Exception:
        logger.exception('US VCP history replay failed for %s', symbol)
        vcp.risk_tags.append('VCP_REPLAY_FAILED')
        return
    vcp.history_qualified = replay.qualified
    vcp.history_candidate_date = replay.candidate_date
    vcp.history_candidate_type = replay.candidate_type
    vcp.history_candidate_score = replay.candidate_score
    vcp.history_source = replay.source
    vcp.history_origin_start_date = replay.origin_start_date
    if replay.qualified:
        try:
            vcp.quality = evaluate_vcp_quality(rows, vcp)
        except Exception:
            logger.exception('US VCP quality diagnostics failed for %s', symbol)
            vcp.risk_tags.append('VCP_QUALITY_FAILED')


def run_research(repository, symbols, *, now=None, as_of=None, config=None, progress=None,
                 histories=None, batch_commit=False, persist=True):
    from strategy6.engine import StrongVcpTailEngine
    symbols = _symbols(symbols)
    now = now or datetime.now(timezone.utc)
    context = evaluation_context(now, as_of)
    run = _run('research', symbols, now, context)
    engine = StrongVcpTailEngine(config, market_profile='US_RESEARCH_NO_INDEX')
    run.update(config=engine.config, evaluated=0, failed=0, candidates=0)
    timings = dict(history_seconds=0.0, scoring_seconds=0.0, vcp_seconds=0.0)
    start = perf_counter()
    batched_read = batch_commit or not persist
    records = repository.history_records(symbols) if histories is None and batched_read else {}
    timings['history_seconds'] += perf_counter() - start
    if persist and not batch_commit:
        repository.save_run(run)
    for symbol in symbols:
        try:
            start = perf_counter()
            try:
                if histories is not None:
                    history = histories.get(symbol)
                elif batched_read:
                    history = repository.decode_history(records.pop(symbol, None))
                else:
                    history = repository.get_history(symbol)
                rows = research_rows(history, context)
            finally:
                timings['history_seconds'] += perf_counter() - start
            start = perf_counter()
            try:
                evaluation = engine.evaluate_at(rows, code=symbol, rows_normalized=True,
                                                 data_source='tickflow_free', kline_fetched_at=history['metadata']['fetched_at'])
            finally:
                timings['scoring_seconds'] += perf_counter() - start
            start = perf_counter()
            try:
                _review_vcp(evaluation, rows, symbol, engine)
            finally:
                timings['vcp_seconds'] += perf_counter() - start
            candidate = evaluation.to_candidate_dict()
            candidate.update(market='US', research_only=True, formal_scan_allowed=False,
                             currency='USD', market_profile='US_RESEARCH_NO_INDEX',
                             turnover_estimation_method=ESTIMATION_METHOD,
                             legacy_amount_unit='1e8_USD_ESTIMATED',
                             latest_turnover_actual=rows[-1]['turnover'],
                             latest_turnover_estimated_usd=rows[-1]['turnover_estimated_usd'],
                             latest_volume=rows[-1]['volume'])
            run['stocks'].append({'symbol': symbol, 'status': 'EVALUATED',
                                  'evaluation_date': rows[-1]['date'], 'evaluated_at': datetime.now(timezone.utc).isoformat(),
                                  'data_hash': history['metadata']['data_hash'],
                                  'metadata': history['metadata'], 'candidate': candidate})
            run['evaluated'] += 1
            run['candidates'] += int(evaluation.passed)
        except Exception as exc:
            logger.warning('US research failed %s: %s', symbol, exc)
            run['stocks'].append({'symbol': symbol, 'status': 'FAILED', 'error': str(exc)})
            run['failed'] += 1
        if persist and not batch_commit:
            repository.save_run(run)
        if progress:
            progress({'phase': 'EVALUATING', 'processed': len(run['stocks']), 'total': len(symbols), 'symbols': [symbol]})
    run['status'] = 'COMPLETED_WITH_ERRORS' if run['failed'] else 'COMPLETED'
    run['finished_at'] = datetime.now(timezone.utc).isoformat()
    run['timings'] = timings
    if persist:
        repository.save_run(run)
    return run


def run_local_research_batch(path, symbols, as_of, config):
    from .repository import USRepository
    return run_research(USRepository(path, read_only=True), symbols, as_of=as_of,
                        config=config, persist=False)
