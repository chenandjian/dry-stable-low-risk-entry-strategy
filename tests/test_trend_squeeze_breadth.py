from datetime import date, datetime, timedelta
import sqlite3
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from scanner import db
import server
from scanner.trend_squeeze_breadth import build_trend_squeeze_breadth
from strategy6.strong_trend_squeeze import evaluate_strong_trend_squeeze, main_chain_trend_reasons


def seed(tmp_path):
    path = str(tmp_path / 'breadth.db')
    db.init_db(path)
    conn = db.get_conn()
    conn.execute("INSERT INTO stock_pool(code,name) VALUES('000001','真实样本')")
    rows = []
    for i in range(285):
        day = str(date(2024, 1, 1)+timedelta(days=i))
        close = 12+i*.03 if i < 260 else 19.8+(i % 2)*.002
        rows.append(dict(date=day, open=close, high=close+.15, low=close-.15, close=close, volume=1000))
        conn.execute("INSERT INTO market_index_ohlc(symbol,date,open,high,low,close) VALUES(?,?,?,?,?,?)",
                     ('sh000001', day, 3000, 3000, 3000, 3000))
    conn.commit()
    db.save_ohlc('000001', rows)
    return path, rows


def test_history_is_exact_and_unavailable_dates_are_not_zero(tmp_path):
    _, rows = seed(tmp_path)
    result = build_trend_squeeze_breadth()
    assert result['rows'][0]['screen_count'] is None
    for item in result['rows'][249:]:
        prefix = [r for r in rows if r['date'] <= item['date']]
        expected = evaluate_strong_trend_squeeze(prefix)
        assert item['screen_count'] == int(expected.passed)
        assert item['strong_count'] == int(expected.calculable and not main_chain_trend_reasons(expected))
        assert item['evaluated_count'] == 1
        assert item['environment'] == '数据不足，暂不判断'
        assert item['screen_ma5'] is None  # Too small a universe for reliable analysis.
    detail = build_trend_squeeze_breadth(stock_date=rows[-1]['date'])['selection']
    assert len(detail['stocks']) == result['rows'][-1]['screen_count']
    assert detail['date'] == rows[-1]['date']


def test_full_ohlc_cache_invalidates_on_high_only_correction(tmp_path):
    _, rows = seed(tmp_path)
    old = build_trend_squeeze_breadth()
    assert old['rows'][-1]['screen_count'] == 1
    conn = db.get_conn()
    conn.execute("UPDATE daily_ohlc SET high=40 WHERE code='000001' AND date=?", (rows[-1]['date'],))
    conn.commit()
    new = build_trend_squeeze_breadth()
    assert old['meta']['source_revision'] != new['meta']['source_revision']
    assert new['rows'][-1]['screen_count'] == 0


def test_missing_today_bar_does_not_repeat_previous_signal(tmp_path):
    _, rows = seed(tmp_path)
    conn = db.get_conn()
    conn.execute("DELETE FROM daily_ohlc WHERE date=?", (rows[-1]['date'],))
    conn.commit()
    item = build_trend_squeeze_breadth()['rows'][-1]
    assert item['screen_count'] is None
    assert item['eligible_count'] == 1
    assert item['evaluated_count'] == 0
    assert item['coverage_rate'] == 0


def test_api_and_date_validation(tmp_path, monkeypatch):
    path, rows = seed(tmp_path)
    monkeypatch.setattr(server, 'load_config', lambda: {'data': {'database_path': path}})
    response = TestClient(server.app).get('/api/market-breadth/trend-squeeze-history', params={'stock_date': rows[-1]['date'], 'limit': 5})
    assert response.status_code == 200
    assert len(response.json()['rows']) == 5
    assert response.json()['selection']['date'] == rows[-1]['date']
    assert TestClient(server.app).get('/api/market-breadth/trend-squeeze-history?start_date=bad').status_code == 400


def test_range_never_changes_historical_calculation(tmp_path):
    _, rows = seed(tmp_path)
    whole = build_trend_squeeze_breadth()
    clipped = build_trend_squeeze_breadth(start_date=rows[-5]['date'], end_date=rows[-1]['date'])
    assert clipped['rows'] == whole['rows'][-5:]
    with pytest.raises(ValueError):
        build_trend_squeeze_breadth(stock_date='bad')


def test_universe_scope_and_empty_successful_screen_are_explicit(tmp_path):
    _, rows = seed(tmp_path)
    conn = db.get_conn()
    conn.execute("INSERT INTO stock_pool(code,name) VALUES('000002','无历史')")
    conn.executemany('INSERT INTO daily_ohlc(code,date,open,high,low,close) VALUES(?,?,?,?,?,?)',
                     [('999999', r['date'], r['open'], r['high'], r['low'], r['close']) for r in rows])
    conn.execute("UPDATE daily_ohlc SET high=40 WHERE code='000001' AND date=?", (rows[-1]['date'],))
    conn.commit()
    result = build_trend_squeeze_breadth(stock_date=rows[-1]['date'])
    assert result['meta']['pool_count'] == 2
    assert result['meta']['stocks_with_history_count'] == 1
    assert result['rows'][-1]['evaluated_count'] == 1
    assert result['selection']['available']
    assert result['selection']['stocks'] == []


def test_statistics_require_contiguous_reliable_windows_and_handle_ties():
    from scanner.trend_squeeze_breadth import _enrich
    rows = [dict(screen_count=5, screen_ratio=.005, strong_ratio=.1, data_quality='RELIABLE') for _ in range(125)]
    _enrich(rows)
    assert rows[118]['screen_percentile120'] is None
    assert rows[119]['screen_percentile120'] == .5
    assert rows[119]['environment'] == '机会有限，精选个股'
    assert rows[-1]['screen_ma20'] == pytest.approx(.005)
    rows[-2]['data_quality'] = 'LOW_COVERAGE'
    _enrich(rows)
    assert rows[-1]['screen_ma5'] is None
    assert rows[-1]['screen_percentile120'] is None
    assert rows[-1]['screen_change'] is None


def test_concurrent_refresh_does_not_publish_a_mixed_cache(tmp_path, monkeypatch):
    from scanner import trend_squeeze_breadth as module
    from scanner.market_breadth import MarketBreadthDataChanging
    _, rows = seed(tmp_path)
    original = module._rebuild
    def changing(reader, calendar, names):
        payload = original(reader, calendar, names)
        conn = db.get_conn()
        conn.execute("UPDATE daily_ohlc SET high=40 WHERE date=?", (rows[-1]['date'],))
        conn.commit()
        return payload
    monkeypatch.setattr(module, '_rebuild', changing)
    with pytest.raises(MarketBreadthDataChanging):
        build_trend_squeeze_breadth()
    with sqlite3.connect(db.DB_PATH+'.trend-breadth-cache.sqlite') as cache:
        assert cache.execute('SELECT COUNT(*) FROM trend_squeeze_breadth_cache').fetchone()[0] == 0


def test_unfinished_today_is_excluded_until_close_confirmation(tmp_path, monkeypatch):
    from scanner import trend_squeeze_breadth as module
    _, rows = seed(tmp_path)
    day = date.fromisoformat(rows[-1]['date'])
    clock = datetime(day.year, day.month, day.day, 15, 9, tzinfo=ZoneInfo('Asia/Shanghai'))
    monkeypatch.setattr(module, 'datetime', SimpleNamespace(now=lambda zone: clock))
    assert build_trend_squeeze_breadth()['rows'][-1]['date'] == rows[-2]['date']
    clock = clock.replace(minute=10)
    assert build_trend_squeeze_breadth()['rows'][-1]['date'] == rows[-1]['date']


def test_trend_endpoint_initializes_database_off_event_loop(monkeypatch):
    import asyncio
    import threading
    event_thread = threading.get_ident()
    initialized = []
    monkeypatch.setattr(server, 'load_config', lambda: {'data': {'database_path': 'unused.db'}})
    monkeypatch.setattr(db, 'init_db', lambda path: initialized.append(threading.get_ident()))
    monkeypatch.setattr(server, 'build_trend_squeeze_breadth', lambda **kwargs: {'rows': []})
    asyncio.run(server.trend_squeeze_breadth_history())
    assert initialized and initialized[0] != event_thread
