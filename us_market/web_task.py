"""Persistent, single-worker research tasks for the isolated US page."""
import logging
import threading
from datetime import datetime, timezone
from time import monotonic, sleep
from uuid import uuid4

from .service import WARNINGS, _symbols, acquire_batch, run_research
from .calendar import evaluation_context
from .daily_data import _create_free_sdk


class USResearchManager:
    def __init__(self, repository):
        self.repository = repository
        self.lock = threading.Lock()
        self.thread = None
        self.cancel = threading.Event()
        self.active_task_id = None
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
              as_of=None, on_start=None, on_finish=None):
        if isinstance(count, bool) or not isinstance(count, int) or not 500 <= count <= 3000:
            raise ValueError('research count must be between 500 and 3000')
        if not isinstance(local_only, bool) or not isinstance(force, bool):
            raise ValueError('local_only and force must be booleans')
        if scope not in {'manual', 'universe'} or (retry_of and resume_of):
            raise ValueError('invalid scope or conflicting retry/resume')
        parent_id = retry_of or resume_of
        snapshot_id = None
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
            snapshot = (self.repository.get_universe(universe_snapshot_id) if universe_snapshot_id
                        else self.repository.latest_universe())
            if snapshot is None:
                raise ValueError('refresh and save TickFlow US_Equity pool before full-pool scanning')
            symbols, snapshot_id = snapshot['symbols'], snapshot['snapshot_id']
        from strategy6.engine import StrongVcpTailEngine
        config = StrongVcpTailEngine(parent['config'] if parent_id else None,
                                    market_profile='US_RESEARCH_NO_INDEX').config
        symbols = _symbols(symbols)
        context = evaluation_context(datetime.now(timezone.utc), as_of)
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
        try:
            def progress(event):
                task['progress'] = dict(event, processed=task['processed_count'], total=task['total_count'],
                                        batch_processed=event.get('processed', 0))
                task['cancel_requested'] = self.cancel.is_set()
                self.repository.save_run(task)
            pending = self.repository.job_symbols(task['task_id'], 'PENDING')
            next_request = 0.0
            def throttle():
                nonlocal next_request
                delay = next_request - monotonic()
                if delay > 0:
                    sleep(delay)
                next_request = monotonic() + 1.1

            for offset in range(0, len(pending), 20):
                if self.cancel.is_set():
                    break
                chunk = pending[offset:offset+20]
                ready, failures = chunk, []
                if not task['local_only']:
                    if sdk is None:
                        sdk = _create_free_sdk()
                    acquisition = acquire_batch(self.repository, chunk, count=task['count'],
                                                force=task['force'], as_of=task['as_of'], progress=progress,
                                                sdk=sdk, before_request=throttle if task['scope'] == 'universe' else None)
                    task['acquisition_task_id'] = acquisition['task_id']
                    failures = [stock for stock in acquisition['stocks'] if stock['status'] == 'FAILED']
                    ready = [stock['symbol'] for stock in acquisition['stocks'] if stock['status'] != 'FAILED']
                results = failures
                if ready:
                    result = run_research(self.repository, ready, as_of=task['as_of'], config=task['config'], progress=progress)
                    task['evaluation_task_id'] = result['task_id']
                    results = failures + result['stocks']
                if len(results) != len(chunk) or {stock['symbol'] for stock in results} != set(chunk):
                    raise RuntimeError('batch terminal results do not match frozen task symbols')
                self.repository.complete_job_stocks(task, results)
                progress({'phase': 'BATCH_COMPLETED', 'symbols': chunk})
            task['status'] = ('CANCELED' if self.cancel.is_set() and task['pending_count'] else
                              'COMPLETED_WITH_ERRORS' if task['failed_count'] else 'COMPLETED')
            task['progress'] = {'phase': task['status'], 'processed': task['processed_count'], 'total': task['total_count'], 'symbols': []}
        except Exception as exc:
            logging.getLogger(__name__).exception('US research task failed')
            task.update(status='FAILED', error=str(exc))
        finally:
            if sdk is not None:
                try:
                    sdk.close()
                except Exception:
                    logging.getLogger(__name__).exception('US TickFlow client close failed')
            task['finished_at'] = datetime.now(timezone.utc).isoformat()
            try:
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
