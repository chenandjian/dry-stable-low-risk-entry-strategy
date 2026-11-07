"""Research evidence from completed jobs, separate from production lifecycle."""
import json
import sqlite3
from contextlib import closing
from datetime import date

from .instruments import provider_symbol


CANDIDATE_TYPES = {'READY_CANDIDATE', 'KEY_CANDIDATE', 'WATCH_CANDIDATE'}


def init_observations(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS us_research_daily (
        profile TEXT NOT NULL, symbol TEXT NOT NULL, trade_date TEXT NOT NULL,
        evaluated_at TEXT NOT NULL, task_id TEXT NOT NULL,
        hit INTEGER NOT NULL, vcp_key TEXT NOT NULL, qualified INTEGER NOT NULL,
        terminal TEXT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY (profile, symbol, trade_date)
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS us_research_daily_date ON us_research_daily(trade_date, evaluated_at)')
    conn.execute('CREATE INDEX IF NOT EXISTS us_research_daily_hits ON us_research_daily(profile, trade_date, symbol) WHERE hit=1')
    conn.execute('CREATE INDEX IF NOT EXISTS us_research_daily_vcp ON us_research_daily(profile, symbol, trade_date) WHERE qualified=1')


def publish_observations(conn, task):
    if (task.get('status') not in {'COMPLETED', 'COMPLETED_WITH_ERRORS'}
            or task.get('kind') != 'job' or task.get('pending_count') != 0):
        return
    day = task['context']['target_trade_date']
    stocks = conn.execute("SELECT payload FROM us_job_stocks WHERE task_id=? AND status='EVALUATED'", (task['task_id'],))
    for (raw,) in stocks:
        stock = json.loads(raw)
        row = stock.get('candidate') or {}
        stamp = stock.get('evaluated_at')
        if (not stamp or row.get('market') != 'US' or row.get('research_only') is not True
                or row.get('evaluation_date') != day or stock.get('evaluation_date') != day
                or not row.get('strategy_version') or not row.get('config_hash')):
            continue
        profile = f"{row['strategy_version']}:{row['config_hash']}"
        origin, start = row.get('vcp_origin_start_date'), row.get('vcp_pattern_start_date')
        key = f'{origin}|{start}' if origin and start else ''
        qualified = bool(key and row.get('vcp_observation_eligible') is True and row.get('vcp_history_qualified') is True)
        terminal = ''
        if key and row.get('vcp_lifecycle_status') == 'VCP_INVALID':
            terminal = 'VCP_INVALID'
        elif key and 'VCP_OBSERVATION_EXPIRED' in (row.get('vcp_observation_risk_tags') or []):
            terminal = 'VCP_EXPIRED'
        data = {key: row[key] for key in (
            'candidate_type', 'total_score', 'tail_score', 'lifecycle_status', 'reject_reasons',
            'vcp_lifecycle_status', 'vcp_origin_start_date', 'vcp_pattern_start_date',
            'vcp_contraction_count', 'vcp_contractions', 'vcp_pivot_price', 'vcp_structure_low',
            'vcp_breakout_date', 'vcp_quality_score', 'vcp_quality_grade',
            'vcp_history_candidate_date', 'vcp_invalidation_reason', 'vcp_observation_risk_tags',
        ) if key in row}
        data['data_hash'] = stock.get('data_hash')
        conn.execute('''INSERT INTO us_research_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile, symbol, trade_date) DO UPDATE SET
                evaluated_at=excluded.evaluated_at, task_id=excluded.task_id,
                hit=excluded.hit, vcp_key=excluded.vcp_key, qualified=excluded.qualified,
                terminal=excluded.terminal, payload=excluded.payload
            WHERE (excluded.evaluated_at, excluded.task_id) >
                  (us_research_daily.evaluated_at, us_research_daily.task_id)''',
                     (profile, stock['symbol'], day, stamp, task['task_id'],
                      int(row.get('candidate_type') in CANDIDATE_TYPES), key,
                      int(qualified and not terminal), terminal, json.dumps(data, allow_nan=False)))


def pool_view(path, *, view='candidates', as_of=None, symbol=None, page=1, page_size=50):
    if view not in {'candidates', 'vcp'} or not 1 <= page <= 50000 or not 1 <= page_size <= 100:
        raise ValueError('invalid view or pagination')
    if as_of and date.fromisoformat(as_of).isoformat() != as_of:
        raise ValueError('as_of must use YYYY-MM-DD')
    symbol = provider_symbol(symbol) if symbol else None
    result = dict(view=view, as_of=as_of, profile=None, latest_evaluation_date=None,
                  rows=[], total=0, page=page, page_size=page_size, research_only=True)
    if not path.is_file():
        return result
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('BEGIN')
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='us_research_daily'").fetchone():
            return result
        latest = conn.execute('SELECT max(trade_date) FROM us_research_daily').fetchone()[0]
        result['latest_evaluation_date'] = latest
        day = as_of or latest
        if not day:
            return result
        selected = conn.execute('''SELECT profile FROM us_research_daily WHERE trade_date<=?
            ORDER BY trade_date DESC, evaluated_at DESC, task_id DESC LIMIT 1''', (day,)).fetchone()
        result['as_of'] = day
        if not selected:
            return result
        profile = selected['profile']
        result['profile'] = profile
        where = 'profile=? AND ' + ('trade_date=? AND hit=1' if view == 'candidates' else 'trade_date<=? AND qualified=1')
        args = [profile, day]
        if symbol:
            where += ' AND symbol=?'
            args.append(symbol)
        start = (page - 1) * page_size
        if view == 'candidates':
            result['total'] = conn.execute(f'SELECT count(*) FROM us_research_daily WHERE {where}', args).fetchone()[0]
            picked = conn.execute(f'''SELECT * FROM us_research_daily WHERE {where}
                ORDER BY json_extract(payload, '$.total_score') DESC, symbol LIMIT ? OFFSET ?''',
                                  (*args, page_size, start)).fetchall()
            result['rows'] = [_candidate_row(conn, row) for row in picked]
        else:
            result['total'] = conn.execute(f'SELECT count(DISTINCT symbol) FROM us_research_daily WHERE {where}', args).fetchone()[0]
            picked = conn.execute(f'''WITH picked AS (
                SELECT symbol, max(trade_date) AS trade_date FROM us_research_daily WHERE {where} GROUP BY symbol
            ) SELECT d.* FROM picked JOIN us_research_daily d USING(symbol, trade_date)
              WHERE d.profile=? ORDER BY d.trade_date DESC,
                json_extract(d.payload, '$.vcp_quality_score') DESC, d.symbol LIMIT ? OFFSET ?''',
                                  (*args, profile, page_size, start)).fetchall()
            result['rows'] = [_vcp_row(conn, row, day) for row in picked]
    return result


def _candidate_row(conn, row):
    first, count = conn.execute('''SELECT min(trade_date), count(*) FROM us_research_daily
        WHERE profile=? AND symbol=? AND hit=1 AND trade_date<=?
          AND trade_date>coalesce((SELECT max(trade_date) FROM us_research_daily
            WHERE profile=? AND symbol=? AND hit=0 AND trade_date<?), '')''',
                                (row['profile'], row['symbol'], row['trade_date'],
                                 row['profile'], row['symbol'], row['trade_date'])).fetchone()
    return dict(json.loads(row['payload']), symbol=row['symbol'], task_id=row['task_id'],
                first_seen_date=first, last_seen_date=row['trade_date'], confirmed_days=count,
                status='NEW' if count == 1 else 'CONTINUING')


def _vcp_row(conn, row, day):
    identity = (row['profile'], row['symbol'])
    latest = conn.execute('''SELECT trade_date FROM us_research_daily WHERE profile=? AND symbol=? AND trade_date<=?
        ORDER BY trade_date DESC LIMIT 1''', (*identity, day)).fetchone()['trade_date']
    terminal = conn.execute('''SELECT terminal, trade_date, task_id, payload FROM us_research_daily
        WHERE profile=? AND symbol=? AND vcp_key=? AND terminal<>'' AND trade_date>? AND trade_date<=?
        ORDER BY trade_date DESC LIMIT 1''', (*identity, row['vcp_key'], row['trade_date'], day)).fetchone()
    first, count = conn.execute('''SELECT min(trade_date), count(*) FROM us_research_daily
        WHERE profile=? AND symbol=? AND vcp_key=? AND qualified=1 AND trade_date<=?
          AND trade_date>coalesce((SELECT max(trade_date) FROM us_research_daily
            WHERE profile=? AND symbol=? AND vcp_key=? AND terminal<>'' AND trade_date<?), '')''',
                                (*identity, row['vcp_key'], row['trade_date'],
                                 *identity, row['vcp_key'], row['trade_date'])).fetchone()
    data = json.loads(row['payload'])
    status = data.get('vcp_lifecycle_status') or 'VCP_CONFIRMED'
    if terminal:
        status = terminal['terminal']
    elif latest > row['trade_date']:
        status = 'VCP_NOT_RECONFIRMED'
    return dict(data, symbol=row['symbol'], task_id=row['task_id'], status=status,
                first_seen_date=first, last_seen_date=row['trade_date'], confirmed_days=count,
                last_evaluation_date=latest, updated_on_date=latest == day,
                breakout_date=data.get('vcp_breakout_date') or None,
                exit_date=terminal['trade_date'] if terminal else None,
                exit_task_id=terminal['task_id'] if terminal else None,
                exit_reason=(json.loads(terminal['payload']).get('vcp_invalidation_reason') or status) if terminal else None)
