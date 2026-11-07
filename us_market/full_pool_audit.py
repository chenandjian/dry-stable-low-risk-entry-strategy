"""Read-only reconciliation of a US_Equity research task and its published evidence."""
import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3

from .observations import CANDIDATE_TYPES


def audit_full_pool(path, task_id):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
        conn.execute('BEGIN')
        record = conn.execute('SELECT payload FROM us_runs WHERE task_id=?', (task_id,)).fetchone()
        task = json.loads(record[0]) if record else {}
        if task.get('kind') != 'job' or task.get('scope') != 'universe' or task.get('retry_of'):
            raise ValueError('expected a full-universe research task, not a failed-symbol retry')
        snapshot_id = task['universe_snapshot_id']
        record = conn.execute('SELECT payload FROM us_universes WHERE snapshot_id=?', (snapshot_id,)).fetchone()
        if record is None:
            raise ValueError('frozen universe snapshot not found')
        snapshot = json.loads(record[0])
        day = task['context']['target_trade_date']
        evidence = {(p, s): (stamp, source, hit, qualified) for p, s, stamp, source, hit, qualified in conn.execute(
            'SELECT profile, symbol, evaluated_at, task_id, hit, qualified FROM us_research_daily WHERE trade_date=?',
            (day,))}
        stocks = conn.execute('SELECT symbol, status, passed, payload FROM us_job_stocks WHERE task_id=?', (task_id,))
        checks, symbols, statuses, failures, rejections = [], set(), Counter(), Counter(), Counter()
        candidates, vcp = [], []
        published = superseded = missing = invalid = 0
        terminal_job = task['status'] in {'COMPLETED', 'COMPLETED_WITH_ERRORS'}
        for symbol, status, passed, payload in stocks:
            symbols.add(symbol)
            statuses[status] += 1
            stock = json.loads(payload)
            if status == 'FAILED':
                reason = stock.get('error') or 'UNKNOWN'
                # Keep reason groups stable even when the provider includes dates or URLs.
                prefix = re.match(r'^[A-Z][A-Z_]+(?=:|$)', reason)
                group = prefix[0] if prefix else re.sub(r' on \d{4}-\d{2}-\d{2}$', '', reason)
                failures[group] += 1
            if status != 'EVALUATED':
                continue
            row = stock.get('candidate') or {}
            hit = row.get('candidate_type') in CANDIDATE_TYPES
            if hit:
                candidates.append({'symbol': symbol, 'type': row['candidate_type'], 'score': row.get('total_score')})
            else:
                rejections.update(set(row.get('reject_reasons') or []))
            qualified = bool(row.get('vcp_origin_start_date') and row.get('vcp_pattern_start_date')
                             and row.get('vcp_observation_eligible') is True
                             and row.get('vcp_history_qualified') is True
                             and row.get('vcp_lifecycle_status') != 'VCP_INVALID'
                             and 'VCP_OBSERVATION_EXPIRED' not in (row.get('vcp_observation_risk_tags') or []))
            if qualified:
                vcp.append({'symbol': symbol, 'status': row.get('vcp_lifecycle_status'),
                            'rounds': row.get('vcp_contraction_count')})
            if (passed != int(hit) or stock.get('evaluation_date') != day
                    or row.get('evaluation_date') != day or stock.get('symbol') != symbol
                    or not stock.get('evaluated_at') or not row.get('strategy_version') or not row.get('config_hash')):
                invalid += 1
                continue
            profile = f"{row['strategy_version']}:{row['config_hash']}"
            projected = evidence.get((profile, symbol))
            expected = (stock['evaluated_at'], task_id, int(hit), int(qualified))
            if projected == expected:
                published += 1
            elif projected and projected[:2] > expected[:2]:
                superseded += 1
            else:
                missing += 1

        evaluated, failed, pending = (statuses[k] for k in ('EVALUATED', 'FAILED', 'PENDING'))
        same_pool = symbols == set(snapshot['symbols'])
        if not same_pool:
            checks.append('FROZEN_UNIVERSE_MISMATCH')
        if (len(symbols), evaluated, failed, pending, len(candidates)) != tuple(task.get(k) for k in (
                'total_count', 'evaluated_count', 'failed_count', 'pending_count', 'candidates')):
            checks.append('TASK_COUNTS_MISMATCH')
        if invalid:
            checks.append('INVALID_DAILY_EVALUATIONS')
        if terminal_job and (pending or missing):
            checks.append('INCOMPLETE_PUBLICATION')
        if not terminal_job and any(row[1] == task_id for row in evidence.values()):
            checks.append('PREMATURE_PUBLICATION')
        all_terminal = same_pool and pending == 0 and evaluated + failed == len(symbols)
        return dict(task_id=task_id, status=task['status'], target_date=day, universe_snapshot_id=snapshot_id,
                    provider_count=snapshot['provider_count'], scheduled=len(symbols), evaluated=evaluated,
                    failed=failed, pending=pending, all_symbols_terminal=all_terminal,
                    coverage_complete=terminal_job and all_terminal and not failed and not checks,
                    coverage_ratio=evaluated / len(snapshot['symbols']),
                    published_evidence=published, superseded_evidence=superseded,
                    failure_reasons=dict(failures.most_common()), rejection_reasons=dict(rejections.most_common()),
                    candidate_count=len(candidates), candidates=sorted(candidates, key=lambda r: r['symbol']),
                    vcp_count=len(vcp), vcp=sorted(vcp, key=lambda r: r['symbol']), checks=checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('task_id')
    args = parser.parse_args()
    report = audit_full_pool(args.database, args.task_id)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report['checks'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
