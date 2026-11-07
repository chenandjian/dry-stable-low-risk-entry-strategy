"""Persistent, single-worker research tasks for the isolated US page."""
import logging
import threading
from datetime import datetime, timezone
from uuid import uuid4

from .service import WARNINGS, _symbols, acquire_batch, run_research
from .calendar import evaluation_context


class USResearchManager:
    def __init__(self, repository):
        self.repository = repository
        self.lock = threading.Lock()
        self.thread = None
        for task in repository.list_runs(10000, status='RUNNING'):
            if task['status'] == 'RUNNING':
                task.update(status='INTERRUPTED', error='Server restarted; task was not silently resumed')
                repository.save_run(task)

    def get(self, task_id):
        task = self.repository.get_run(task_id)
        return task if task and task['kind'] == 'job' else None

    def tasks(self):
        tasks = self.repository.list_runs(20, kind='job', summary=True)
        return [{key: value for key, value in task.items() if key not in {'stocks', 'acquisition', 'evaluation'}} for task in tasks]

    def start(self, symbols, *, count=1100, local_only=False, force=False,
              retry_of=None, as_of=None, on_start=None, on_finish=None):
        if isinstance(count, bool) or not isinstance(count, int) or not 500 <= count <= 3000:
            raise ValueError('research count must be between 500 and 3000')
        if not isinstance(local_only, bool) or not isinstance(force, bool):
            raise ValueError('local_only and force must be booleans')
        if retry_of:
            if not isinstance(retry_of, str):
                raise ValueError('retry_of must be a task ID')
            parent = self.get(retry_of)
            if not parent or parent['status'] == 'RUNNING':
                raise ValueError('retry task not found or still running')
            symbols = [stock['symbol'] for stock in parent['stocks'] if stock['status'] == 'FAILED']
            count, local_only, force = parent['count'], False, True
            as_of = parent['context']['target_trade_date']
        from strategy6.engine import StrongVcpTailEngine
        config = StrongVcpTailEngine(parent['config'] if retry_of else None,
                                    market_profile='US_RESEARCH_NO_INDEX').config
        symbols = _symbols(symbols)
        context = evaluation_context(datetime.now(timezone.utc), as_of)
        if len(symbols) > 200:
            raise ValueError('at most 200 symbols per research task')
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('US research task already running')
        task = {'task_id': f'us-s6-job-{uuid4().hex}', 'kind': 'job', 'market': 'US',
                'research_only': True, 'formal_scan_allowed': False, 'market_filter_enabled': False,
                'warnings': list(WARNINGS), 'symbols': symbols, 'count': count, 'local_only': local_only,
                'force': force, 'retry_of': retry_of, 'status': 'RUNNING', 'stocks': [],
                'context': context, 'as_of': context['target_trade_date'],
                'config': config,
                'started_at': datetime.now(timezone.utc).isoformat(), 'candidates': 0,
                'progress': {'phase': 'PREPARING', 'processed': 0, 'total': len(symbols), 'symbols': []}}
        try:
            self.repository.save_run(task)
            if on_start:
                on_start(task['task_id'])
            self.thread = threading.Thread(target=self._execute, args=(task, on_finish), daemon=True)
            self.thread.start()
        except Exception:
            task['status'] = 'FAILED'
            try:
                self.repository.save_run(task)
            finally:
                self.lock.release()
                if on_finish:
                    on_finish()
            raise
        return task['task_id']

    def _execute(self, task, on_finish):
        try:
            def progress(event):
                task['progress'] = event
                self.repository.save_run(task)
            symbols = task['symbols']
            failures = []
            if not task['local_only']:
                acquisition = acquire_batch(self.repository, symbols, count=task['count'],
                                            force=task['force'], as_of=task['as_of'], progress=progress)
                task['acquisition_task_id'] = acquisition['task_id']
                failures = [stock for stock in acquisition['stocks'] if stock['status'] == 'FAILED']
                symbols = [stock['symbol'] for stock in acquisition['stocks'] if stock['status'] != 'FAILED']
            if symbols:
                result = run_research(self.repository, symbols, as_of=task['as_of'],
                                      config=task['config'], progress=progress)
                task['evaluation_task_id'] = result['task_id']
                task['stocks'] = failures + result['stocks']
                task['candidates'] = result['candidates']
                task['context'] = result['context']
            else:
                task['stocks'] = failures
            task['status'] = 'COMPLETED_WITH_ERRORS' if any(stock['status'] == 'FAILED' for stock in task['stocks']) else 'COMPLETED'
            task['progress'] = {'phase': 'FINISHED', 'processed': len(task['stocks']), 'total': len(task['symbols']), 'symbols': []}
        except Exception as exc:
            logging.getLogger(__name__).exception('US research task failed')
            task.update(status='FAILED', error=str(exc))
        finally:
            task['finished_at'] = datetime.now(timezone.utc).isoformat()
            try:
                self.repository.save_run(task)
            finally:
                self.lock.release()
                if on_finish:
                    on_finish()

    def join(self, timeout=None):
        if self.thread:
            self.thread.join(timeout)
