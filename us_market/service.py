"""US-only acquisition and Strategy6 research orchestration."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import logging
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
                  sdk=None, now=None, as_of=None, progress=None, before_request=None):
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
    for symbol in symbols:
        history = repository.get_history(symbol)
        if not force and history and history['metadata']['requested_count'] >= count and any(
            row['date'] == context['target_trade_date'] for row in history['rows']
        ) and freshness(
            history['rows'][-1]['date'], history['metadata']['fetched_at'], context
        ):
            run['stocks'].append({'symbol': symbol, 'status': 'CACHED', 'latest_date': history['rows'][-1]['date']})
            run['cached'] += 1
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
                frames = sdk.klines.batch(chunk, period='1d', count=count, adjust='forward',
                                          as_dataframe=True, batch_size=batch_size,
                                          max_workers=2, show_progress=False)
                if not isinstance(frames, Mapping) or set(frames) - set(chunk):
                    raise ValueError('unexpected batch symbols or response type')
                error = None
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
                    repository.save_history(symbol, rows, metadata)
                    run['stocks'].append({'symbol': symbol, 'status': 'FETCHED', 'latest_date': rows[-1]['date'], 'rows': len(rows)})
                    run['succeeded'] += 1
                except Exception as exc:
                    logger.warning('US fetch failed %s: %s', symbol, exc)
                    run['stocks'].append({'symbol': symbol, 'status': 'FAILED', 'error': str(exc)})
                    run['failed'] += 1
            repository.save_run(run)
            if progress:
                progress({'phase': 'SAVED', 'processed': len(run['stocks']), 'total': len(symbols), 'symbols': chunk})
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


def run_research(repository, symbols, *, now=None, as_of=None, config=None, progress=None):
    from strategy6.engine import StrongVcpTailEngine
    symbols = _symbols(symbols)
    now = now or datetime.now(timezone.utc)
    context = evaluation_context(now, as_of)
    run = _run('research', symbols, now, context)
    engine = StrongVcpTailEngine(config, market_profile='US_RESEARCH_NO_INDEX')
    run.update(config=engine.config, evaluated=0, failed=0, candidates=0)
    repository.save_run(run)
    for symbol in symbols:
        try:
            history = repository.get_history(symbol)
            rows = research_rows(history, context)
            evaluation = engine.evaluate_at(rows, code=symbol, rows_normalized=True,
                                             data_source='tickflow_free', kline_fetched_at=history['metadata']['fetched_at'])
            candidate = evaluation.to_candidate_dict()
            candidate.update(market='US', research_only=True, formal_scan_allowed=False,
                             currency='USD', market_profile='US_RESEARCH_NO_INDEX',
                             turnover_estimation_method=ESTIMATION_METHOD,
                             legacy_amount_unit='1e8_USD_ESTIMATED',
                             latest_turnover_actual=rows[-1]['turnover'],
                             latest_turnover_estimated_usd=rows[-1]['turnover_estimated_usd'],
                             latest_volume=rows[-1]['volume'])
            run['stocks'].append({'symbol': symbol, 'status': 'EVALUATED',
                                  'evaluation_date': rows[-1]['date'], 'data_hash': history['metadata']['data_hash'],
                                  'metadata': history['metadata'], 'candidate': candidate})
            run['evaluated'] += 1
            run['candidates'] += int(evaluation.passed)
        except Exception as exc:
            logger.warning('US research failed %s: %s', symbol, exc)
            run['stocks'].append({'symbol': symbol, 'status': 'FAILED', 'error': str(exc)})
            run['failed'] += 1
        repository.save_run(run)
        if progress:
            progress({'phase': 'EVALUATING', 'processed': len(run['stocks']), 'total': len(symbols), 'symbols': [symbol]})
    run['status'] = 'COMPLETED_WITH_ERRORS' if run['failed'] else 'COMPLETED'
    run['finished_at'] = datetime.now(timezone.utc).isoformat()
    repository.save_run(run)
    return run
