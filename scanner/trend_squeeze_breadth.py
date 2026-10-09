"""Independent, causal trend/squeeze breadth reconstruction from local OHLC."""
from bisect import bisect_right
from contextlib import closing
from datetime import datetime
import hashlib
from itertools import groupby
import json
from pathlib import Path
import sqlite3
import threading
from zoneinfo import ZoneInfo

from scanner import db
from scanner.market_breadth import MarketBreadthDataChanging, _validate_date
from strategy6.strong_trend_squeeze import evaluate_strong_trend_squeeze_history, main_chain_trend_reasons

MODEL_VERSION = 'S6_TREND_SQUEEZE_BREADTH_V1'
_LOCK = threading.Lock()
_MEMORY = None


def _file_token(path):
    return tuple((p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None
                 for p in (path, Path(str(path)+'-wal')))


def _enrich(rows):
    for i, item in enumerate(rows):
        reliable = item['data_quality'] == 'RELIABLE'
        previous = rows[i-1] if i else None
        item['screen_change'] = (item['screen_count']-previous['screen_count']
                                 if reliable and previous and previous['data_quality'] == 'RELIABLE' else None)
        for field in ('screen', 'strong'):
            for size in (5, 20):
                window = rows[max(0, i-size+1):i+1]
                item[f'{field}_ma{size}'] = (sum(r[f'{field}_ratio'] for r in window)/size
                                           if len(window) == size and all(r['data_quality'] == 'RELIABLE' for r in window) else None)
            history = rows[max(0, i-119):i+1]
            item[f'{field}_percentile120'] = None
            if len(history) == 120 and all(r['data_quality'] == 'RELIABLE' for r in history):
                value = item[f'{field}_ratio']
                item[f'{field}_percentile120'] = sum(
                    1 if r[f'{field}_ratio'] < value else .5 if r[f'{field}_ratio'] == value else 0
                    for r in history)/120
        squeeze, trend = item['screen_percentile120'], item['strong_percentile120']
        label = '数据不足，暂不判断'
        if squeeze is not None and trend is not None:
            if trend < .30:
                label = '环境偏弱，谨慎参与'
            elif trend >= .70 and squeeze < .30:
                label = '趋势仍强，注意追涨'
            elif squeeze >= .70:
                label = '适合寻找收缩机会'
            else:
                label = '机会有限，精选个股'
        item['environment'] = label


def _rebuild(reader, calendar, names):
    counts = {day: dict(present=0, evaluated=0, strong=0, screen=0, invalid=0) for day in calendar}
    stocks = {day: [] for day in calendar}
    eligible_dates = []
    cursor = reader.execute('SELECT code,date,open,high,low,close FROM daily_ohlc WHERE date<=? ORDER BY code,date', (calendar[-1],))
    for code, group in groupby(cursor, key=lambda r: r[0]):
        if names and code not in names:
            continue
        bars = [dict(zip(('date', 'open', 'high', 'low', 'close'), r[1:])) for r in group]
        if len(bars) >= 250:
            eligible_dates.append(bars[249]['date'])
        history = evaluate_strong_trend_squeeze_history(bars)
        for i, (bar, signal) in enumerate(zip(bars, history)):
            day = bar['date']
            if day not in counts:
                continue
            item = counts[day]
            item['present'] += 1
            if i < 249:
                continue
            if not signal.calculable:
                item['invalid'] += 1
                continue
            item['evaluated'] += 1
            item['strong'] += not main_chain_trend_reasons(signal)
            if signal.passed:
                item['screen'] += 1
                stocks[day].append({'code': code, 'name': names.get(code, '')})
    eligible_dates.sort()
    rows = []
    for day, item in counts.items():
        eligible = bisect_right(eligible_dates, day)
        evaluated = item['evaluated']
        coverage = evaluated/eligible if eligible else 0
        rows.append(dict(date=day, screen_count=item['screen'] if evaluated else None,
                         strong_count=item['strong'] if evaluated else None,
                         screen_ratio=item['screen']/evaluated if evaluated else None,
                         strong_ratio=item['strong']/evaluated if evaluated else None,
                         evaluated_count=evaluated, eligible_count=eligible,
                         available_count=item['present'], invalid_count=item['invalid'],
                         unavailable_count=max(0, eligible-evaluated), coverage_rate=coverage,
                         data_quality='RELIABLE' if coverage >= .90 and evaluated >= 1000 else 'LOW_COVERAGE'))
    _enrich(rows)
    return {'rows': rows, 'stocks': stocks}


def _snapshot():
    global _MEMORY
    path = Path(db.DB_PATH).resolve()
    # Exclude the unfinished current day; the actual index bars define holidays.
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    today = now.date().isoformat()
    cutoff = today if (now.hour, now.minute) >= (15, 10) else today + ':before-close'
    with _LOCK:
        token = _file_token(path)
        key = (str(path), token, cutoff)
        if _MEMORY and _MEMORY[0] == key:
            return _MEMORY[1]
        cache_path = path.with_name(path.name+'.trend-breadth-cache.sqlite')
        with closing(sqlite3.connect(cache_path)) as cache, cache:
            cache.execute('''CREATE TABLE IF NOT EXISTS trend_squeeze_breadth_cache (
                             id INTEGER PRIMARY KEY CHECK(id=1), source_revision TEXT NOT NULL,
                             payload TEXT NOT NULL)''')
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as reader:
            version = reader.execute('PRAGMA data_version').fetchone()[0]
            reader.execute('BEGIN')
            operator = '<=' if (now.hour, now.minute) >= (15, 10) else '<'
            calendar = [r[0] for r in reader.execute(
                f"SELECT date FROM market_index_ohlc WHERE symbol='sh000001' AND date {operator} ? ORDER BY date", (today,))]
            if not calendar:
                return {'rows': [], 'stocks': {}, 'revision': '', 'calculated_at': now.isoformat()}
            names = dict(reader.execute('SELECT code,name FROM stock_pool ORDER BY code'))
            digest = hashlib.sha256((MODEL_VERSION+':stock-pool-scope:'+json.dumps([calendar, names], sort_keys=True)).encode())
            for row in reader.execute('SELECT code,date,open,high,low,close FROM daily_ohlc WHERE date<=? ORDER BY code,date', (calendar[-1],)):
                digest.update(repr(row).encode())
            revision = digest.hexdigest()
            with closing(sqlite3.connect(cache_path)) as cache:
                cached = cache.execute('SELECT source_revision,payload FROM trend_squeeze_breadth_cache WHERE id=1').fetchone()
            rebuilt = cached is None or cached[0] != revision
            payload = _rebuild(reader, calendar, names) if rebuilt else json.loads(cached[1])
            with_history = reader.execute('SELECT COUNT(DISTINCT code) FROM daily_ohlc WHERE date<=? AND (?=0 OR code IN (SELECT code FROM stock_pool))',
                                          (calendar[-1], len(names))).fetchone()[0]
            payload.update(pool_count=len(names), stocks_with_history_count=with_history)
            reader.commit()
            if reader.execute('PRAGMA data_version').fetchone()[0] != version:
                raise MarketBreadthDataChanging('行情正在更新，请稍后重试强势收缩历史宽度')
        if rebuilt:
            payload.update(revision=revision, calculated_at=now.isoformat())
            with closing(sqlite3.connect(cache_path)) as cache, cache:
                cache.execute('INSERT OR REPLACE INTO trend_squeeze_breadth_cache VALUES(1,?,?)',
                              (revision, json.dumps(payload, ensure_ascii=False, separators=(',', ':'))))
        # Cache writes live outside the source DB, so they cannot invalidate the
        # memory token or conceal a concurrent source update.
        _MEMORY = ((str(path), token, cutoff), payload)
        return payload


def build_trend_squeeze_breadth(*, start_date=None, end_date=None, limit=2000, stock_date=None):
    start_date = _validate_date(start_date, 'start_date')
    end_date = _validate_date(end_date, 'end_date')
    stock_date = _validate_date(stock_date, 'stock_date')
    if start_date and end_date and start_date > end_date:
        raise ValueError('start_date must not be after end_date')
    if not 1 <= int(limit) <= 2000:
        raise ValueError('limit must be between 1 and 2000')
    snapshot = _snapshot()
    rows = [r for r in snapshot['rows'] if (not start_date or r['date'] >= start_date)
            and (not end_date or r['date'] <= end_date)][-int(limit):]
    selection = None
    if stock_date:
        row = next((r for r in snapshot['rows'] if r['date'] == stock_date), None)
        selection = dict(date=stock_date, available=row is not None and row['evaluated_count'] > 0,
                         stocks=snapshot['stocks'].get(stock_date, []), summary=row)
    return dict(meta=dict(model_version=MODEL_VERSION, source='LOCAL_HISTORICAL_REBUILD',
                          source_revision=snapshot['revision'], calculated_at=snapshot['calculated_at'],
                          affects_strategy6=False, warning='当前股票池真实日线历史重建，存在幸存者偏差；提示阈值未做收益校准',
                          reliable_coverage_min=.90, reliable_sample_min=1000,
                          available_start=snapshot['rows'][0]['date'] if snapshot['rows'] else None,
                          available_end=snapshot['rows'][-1]['date'] if snapshot['rows'] else None,
                          pool_count=snapshot.get('pool_count', 0),
                          stocks_with_history_count=snapshot.get('stocks_with_history_count', 0)),
                rows=rows, selection=selection)
