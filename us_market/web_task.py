"""Persistent, single-worker research tasks for the isolated US page."""
import logging
import threading
from concurrent.futures import CancelledError, ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timezone
from time import monotonic, perf_counter, sleep
from uuid import uuid4

from .service import WARNINGS, _symbols, acquire_batch, run_local_research_batch, run_research
from .calendar import evaluation_context
from .daily_data import _create_free_sdk

LOCAL_PARALLEL_MIN_SYMBOLS = 500


class USResearchManager:
    def __init__(self, repository, *, local_workers=1):
        self.repository = repository
        self.lock = threading.Lock()
        self.thread = None
        self.cancel = threading.Event()
        self.active_task_id = None
        self.local_workers = local_workers
        for task in repository.list_runs(10000, status='RUNNING'):
            if task['status'] == 'RUNNING':
                task.update(status='INTERRUPTED', error='Server restarted; task was not silently resumed')
                repository.save_run(task)

    def get(self, task_id):
        return self.get_page(task_id)

    def get_page(self, task_id, *, page=1, page_size=50, only_passed=False):
        return self.repository.job_page(task_id, page=page, page_size=page_size, only_passed=only_passed)

    def tasks(self):
        tasks = self.repository.list_runs(20, kind='job', summary=True)
        return [{key: value for key, value in task.items() if key not in {'stocks', 'acquisition', 'evaluation'}} for task in tasks]

    def start(self, symbols, *, count=1100, local_only=False, force=False,
              retry_of=None, resume_of=None, scope='manual', universe_snapshot_id=None,
              as_of=None, on_start=None, on_finish=None, refresh_online_universe=None):
        if isinstance(count, bool) or not isinstance(count, int) or not 500 <= count <= 3000:
            raise ValueError('research count must be between 500 and 3000')
        if not isinstance(local_only, bool) or not isinstance(force, bool):
            raise ValueError('local_only and force must be booleans')
        if scope not in {'manual', 'universe'} or (retry_of and resume_of):
            raise ValueError('invalid scope or conflicting retry/resume')
        parent_id = retry_of or resume_of
        snapshot_id = None
        context = None
        if parent_id:
            if not isinstance(parent_id, str):
                raise ValueError('parent must be a task ID')
            parent = self.repository.get_run(parent_id)
            if not parent or parent['kind'] != 'job' or parent['status'] == 'RUNNING':
                raise ValueError('parent task not found or still running')
            if resume_of:
                if parent.get('stock_storage') != 'rows_v1' or not self.repository.job_symbols(parent_id, 'PENDING'):
                    raise ValueError('no resumable unfinished stocks')
                symbols = self.repository.job_symbols(parent_id)
                count, local_only, force = parent['count'], parent['local_only'], parent['force']
            else:
                symbols = (self.repository.job_symbols(parent_id, 'FAILED') if parent.get('stock_storage') == 'rows_v1'
                           else [stock['symbol'] for stock in parent['stocks'] if stock['status'] == 'FAILED'])
                count, local_only, force = parent['count'], False, True
            as_of = parent['context']['target_trade_date']
            snapshot_id = parent.get('universe_snapshot_id')
            scope = parent.get('scope', 'manual')
        elif scope == 'universe':
            if universe_snapshot_id is not None and not isinstance(universe_snapshot_id, str):
                raise ValueError('universe_snapshot_id must be a string')
            if refresh_online_universe is not None and not local_only:
                context = evaluation_context(datetime.now(timezone.utc), as_of)
                snapshot = refresh_online_universe()
            else:
                snapshot = (self.repository.get_universe(universe_snapshot_id) if universe_snapshot_id
                            else self.repository.latest_universe())
            if snapshot is None:
                raise ValueError('refresh and save TickFlow US_Equity pool before full-pool scanning')
            symbols, snapshot_id = snapshot['symbols'], snapshot['snapshot_id']
        from strategy6.engine import StrongVcpTailEngine
        config = StrongVcpTailEngine(parent['config'] if parent_id else None,
                                    market_profile='US_RESEARCH_NO_INDEX').config
        symbols = _symbols(symbols)
        context = context or evaluation_context(datetime.now(timezone.utc), as_of)
        if len(symbols) > 200 and scope == 'manual' and not parent_id:
            raise ValueError('at most 200 symbols per research task')
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('US research task already running')
        task = {'task_id': f'us-s6-job-{uuid4().hex}', 'kind': 'job', 'market': 'US',
                'research_only': True, 'formal_scan_allowed': False, 'market_filter_enabled': False,
                'warnings': list(WARNINGS), 'symbols': symbols, 'count': count, 'local_only': local_only,
                'force': force, 'retry_of': retry_of, 'status': 'RUNNING', 'stocks': [],
                'resume_of': resume_of, 'scope': scope, 'universe_snapshot_id': snapshot_id,
                'stock_storage': 'rows_v1',
                'context': context, 'as_of': context['target_trade_date'],
                'config': config,
                'started_at': datetime.now(timezone.utc).isoformat(), 'candidates': 0,
                'progress': {'phase': 'PREPARING', 'processed': 0, 'total': len(symbols), 'symbols': []}}
        try:
            self.repository.initialize_job(task, resume_of=resume_of)
            self.cancel.clear()
            self.active_task_id = task['task_id']
            if on_start:
                on_start(task['task_id'])
            self.thread = threading.Thread(target=self._execute, args=(task, on_finish), daemon=True)
            self.thread.start()
        except Exception:
            task['status'] = 'FAILED'
            try:
                self.repository.save_run(task)
            finally:
                self.active_task_id = None
                self.lock.release()
                if on_finish:
                    on_finish()
            raise
        return task['task_id']

    def _execute(self, task, on_finish):
        sdk = None
        fetch_pool = None
        score_pool = None
        started = perf_counter()
        timings = task['timings'] = dict(acquisition_seconds=0.0, history_seconds=0.0,
                                         scoring_seconds=0.0, vcp_seconds=0.0, commit_seconds=0.0,
                                         provider_seconds=0.0, provider_requests=0)
        try:
            last_progress_write = -float('inf')
            last_progress_phase = None
            def progress(event):
                nonlocal last_progress_phase, last_progress_write
                task['progress'] = dict(event, processed=task['processed_count'], total=task['total_count'],
                                        batch_processed=event.get('processed', 0))
                task['cancel_requested'] = self.cancel.is_set()
                now = perf_counter()
                if (event['phase'] != 'EVALUATING' or event['phase'] != last_progress_phase
                        or now - last_progress_write >= 1):
                    self.repository.save_run(task)
                    last_progress_phase = event['phase']
                    last_progress_write = now
            pending = self.repository.job_symbols(task['task_id'], 'PENDING')
            next_request = 0.0
            def throttle():
                nonlocal next_request
                delay = next_request - monotonic()
                if delay > 0:
                    sleep(delay)
                if self.cancel.is_set():
                    raise CancelledError()
                next_request = monotonic() + 1.1

            def fetch(chunk, report_progress=None):
                nonlocal sdk
                if self.cancel.is_set():
                    return None, 0.0
                start = perf_counter()
                if sdk is None:
                    sdk = _create_free_sdk()
                try:
                    result = acquire_batch(self.repository, chunk, count=task['count'],
                                           force=task['force'], as_of=task['as_of'], progress=report_progress,
                                           sdk=sdk, before_request=throttle if task['scope'] == 'universe' else None,
                                           retain_histories=True)
                except CancelledError:
                    if not self.cancel.is_set():
                        raise
                    return None, 0.0
                return result, perf_counter() - start

            if task['scope'] == 'universe' and not task['local_only']:
                fetch_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='us-market-fetch')
            scoring = {}
            if task['local_only'] and self.local_workers > 1 and len(pending) >= LOCAL_PARALLEL_MIN_SYMBOLS:
                score_pool = ProcessPoolExecutor(max_workers=self.local_workers)

            def schedule_score(offset):
                scoring[offset] = score_pool.submit(run_local_research_batch, self.repository.path,
                                                    pending[offset:offset+20], task['as_of'], task['config'])

            if score_pool:
                for offset in range(0, min(len(pending), 20 * self.local_workers), 20):
                    if self.cancel.is_set():
                        break
                    schedule_score(offset)
            future = None
            for offset in range(0, len(pending), 20):
                if self.cancel.is_set():
                    break
                chunk = pending[offset:offset+20]
                ready, failures = chunk, []
                histories = None
                if not task['local_only']:
                    if fetch_pool is None:
                        acquisition, elapsed = fetch(chunk, progress)
                    else:
                        if future is None or not future.done():
                            progress({'phase': 'FETCHING', 'symbols': chunk})
                        if future is None:
                            future = fetch_pool.submit(fetch, chunk)
                        acquisition, elapsed = future.result()
                        future = None
                    if acquisition is None:
                        break
                    timings['acquisition_seconds'] += elapsed
                    timings['provider_seconds'] += acquisition.get('provider_seconds', 0.0)
                    timings['provider_requests'] += acquisition.get('provider_requests', 0)
                    task['acquisition_task_id'] = acquisition['task_id']
                    histories = acquisition.get('histories')
                    failures = [stock for stock in acquisition['stocks'] if stock['status'] == 'FAILED']
                    ready = [stock['symbol'] for stock in acquisition['stocks'] if stock['status'] != 'FAILED']
                    if fetch_pool and offset + 20 < len(pending) and not self.cancel.is_set():
                        future = fetch_pool.submit(fetch, pending[offset+20:offset+40])
                results = failures
                if ready:
                    if score_pool:
                        progress({'phase': 'EVALUATING', 'symbols': ready})
                        result = scoring.pop(offset).result()
                        self.repository.save_run(result)
                        next_offset = offset + 20 * self.local_workers
                        if next_offset < len(pending) and not self.cancel.is_set():
                            schedule_score(next_offset)
                    else:
                        result = run_research(self.repository, ready, as_of=task['as_of'], config=task['config'],
                                              progress=progress, histories=histories, batch_commit=True)
                    for key, seconds in result.get('timings', {}).items():
                        timings[key] += seconds
                    task['evaluation_task_id'] = result['task_id']
                    results = failures + result['stocks']
                if len(results) != len(chunk) or {stock['symbol'] for stock in results} != set(chunk):
                    raise RuntimeError('batch terminal results do not match frozen task symbols')
                task['progress'] = {'phase': 'BATCH_COMPLETED', 'symbols': chunk}
                start = perf_counter()
                self.repository.complete_job_stocks(task, results)
                timings['commit_seconds'] += perf_counter() - start
            task['status'] = ('CANCELED' if self.cancel.is_set() and task['pending_count'] else
                              'COMPLETED_WITH_ERRORS' if task['failed_count'] else 'COMPLETED')
            task['progress'] = {'phase': task['status'], 'processed': task['processed_count'], 'total': task['total_count'], 'symbols': []}
        except Exception as exc:
            logging.getLogger(__name__).exception('US research task failed')
            task.update(status='FAILED', error=str(exc))
        finally:
            if score_pool is not None:
                score_pool.shutdown(wait=True, cancel_futures=True)
            if fetch_pool is not None:
                fetch_pool.shutdown(wait=True, cancel_futures=True)
            if sdk is not None:
                try:
                    sdk.close()
                except Exception:
                    logging.getLogger(__name__).exception('US TickFlow client close failed')
            task['finished_at'] = datetime.now(timezone.utc).isoformat()
            try:
                timings['elapsed_before_publish_seconds'] = perf_counter() - started
                self.repository.finish_job(task)
            except Exception as exc:
                logging.getLogger(__name__).exception('US task publication failed')
                task.update(status='FAILED', error=str(exc))
                self.repository.save_run(task)
            finally:
                self.active_task_id = None
                self.lock.release()
                if on_finish:
                    on_finish()

    def stop(self, task_id):
        if self.active_task_id != task_id or not self.lock.locked():
            return False
        self.cancel.set()
        return True

    def join(self, timeout=None):
        if self.thread:
            self.thread.join(timeout)
