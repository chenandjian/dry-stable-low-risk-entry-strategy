"""Offline comparison of local scan workers against frozen real US history."""
import argparse
from contextlib import closing
from hashlib import sha256
import json
import logging
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from time import perf_counter

from .repository import USRepository
from .web_task import LOCAL_PARALLEL_MIN_SYMBOLS, USResearchManager


def compare(source, day, limit, worker_counts):
    with TemporaryDirectory(prefix='us-scan-benchmark-') as directory:
        repo = USRepository(Path(directory) / 'benchmark.db')
        with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as original, repo.connection() as dest:
            dest.executemany('INSERT INTO us_stock_history VALUES (?, ?, ?, ?)', original.execute(
                'SELECT symbol, adjustment, metadata, rows_json FROM us_stock_history ORDER BY symbol LIMIT ?', (limit,)))
            symbols = [row[0] for row in dest.execute('SELECT symbol FROM us_stock_history ORDER BY symbol')]
            snapshot = json.loads(original.execute('SELECT payload FROM us_universes ORDER BY rowid DESC LIMIT 1').fetchone()[0])
        if len(symbols) < LOCAL_PARALLEL_MIN_SYMBOLS:
            raise ValueError(f'at least {LOCAL_PARALLEL_MIN_SYMBOLS} stored symbols required to compare process counts')
        if limit < 0:
            symbols = snapshot['symbols']
        else:
            with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as original:
                present = {row[0] for row in original.execute('SELECT symbol FROM us_stock_history')}
            symbols += [symbol for symbol in snapshot['symbols'] if symbol not in present][:5]
        repo.save_universe(dict(snapshot_id='benchmark', source='tickflow_free',
                                symbols=symbols, provider_count=len(symbols)))
        baseline = None
        for workers in worker_counts:
            manager = USResearchManager(repo, local_workers=workers)
            started = perf_counter()
            task_id = manager.start(None, scope='universe', as_of=day, local_only=True)
            manager.join()
            elapsed = perf_counter() - started
            run = repo.get_run(task_id)
            if run['status'] not in {'COMPLETED', 'COMPLETED_WITH_ERRORS'} or run['processed_count'] != len(symbols):
                raise RuntimeError(f"benchmark task did not complete: {run['status']} {run.get('error')}")
            digest = sha256()
            with repo.connection() as conn:
                for (raw,) in conn.execute(
                        'SELECT payload FROM us_job_stocks WHERE task_id=? ORDER BY position', (task_id,)):
                    row = json.loads(raw)
                    row.pop('evaluated_at', None)
                    digest.update(json.dumps(row, sort_keys=True).encode())
            signature = digest.hexdigest()
            if baseline is None:
                baseline = signature
            elif baseline != signature:
                raise RuntimeError(f'scoring differs with {workers} workers')
            print(json.dumps(dict(workers=workers, elapsed_seconds=elapsed, symbols=len(symbols),
                                  evaluated=run['evaluated_count'], failed=run['failed_count'],
                                  candidates=run['candidates'], digest=signature, timings=run['timings'])), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('as_of')
    parser.add_argument('--limit', type=int, default=1200)
    parser.add_argument('--workers', type=int, nargs='+', choices=(1, 2, 4), default=(1, 2, 4))
    args = parser.parse_args()
    logging.basicConfig(level=logging.ERROR)
    compare(args.source, args.as_of, args.limit, args.workers)


if __name__ == '__main__':
    main()
