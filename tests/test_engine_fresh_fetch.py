from scanner import db
from scanner import engine
from scanner import stock_pool


class FakeManager:
    def __init__(self, acquire_results=None):
        self.acquire_results = acquire_results or {}
        self.acquire_calls = []
        self.release_calls = []

    def acquire(self, ds_name):
        self.acquire_calls.append(ds_name)
        return self.acquire_results.get(ds_name, False)

    def release(self, ds_name):
        self.release_calls.append(ds_name)


class FakeScanManager:
    events = []

    def try_acquire_any(self):
        self.events.append('acquire')
        return 'tencent'

    def release(self, ds_name):
        self.events.append(f'release:{ds_name}')


class ImmediateThread:
    def __init__(self, target=None, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        if self.target:
            self.target(*self.args)

    def join(self):
        return None


def _row(day, close=10.0):
    return {"date": day, "open": close, "high": close, "low": close, "close": close, "volume": 10_000_000, "turnover": close * 10_000_000}


def _rows(count, close=10.0):
    rows = []
    for day in range(1, count + 1):
        month = ((day - 1) // 28) + 1
        dom = ((day - 1) % 28) + 1
        rows.append(_row(f'2026-{month:02d}-{dom:02d}', close=close))
    return rows


def test_fetch_result_reports_transient_source_busy_only_for_busy_failures():
    busy_primary = engine.FetchResult(data=None, primary_source='tencent', fallback_source='sina', primary_error='data source busy')
    busy_fallback = engine.FetchResult(data=None, primary_source='sina', fallback_source='tencent', fallback_error='data source busy')
    not_busy = engine.FetchResult(data=None, primary_source='sina', fallback_source='tencent', primary_error='empty response', fallback_error='empty response')
    with_data = engine.FetchResult(data=[_row('2026-06-04')], primary_source='sina', fallback_source='tencent', fallback_error='data source busy')

    assert engine._is_transient_source_busy(busy_primary) is True
    assert engine._is_transient_source_busy(busy_fallback) is True
    assert engine._is_transient_source_busy(not_busy) is False
    assert engine._is_transient_source_busy(with_data) is False


def test_scan_all_requeues_stock_after_transient_source_busy(monkeypatch, tmp_path):
    config = {
        'data': {'database_path': str(tmp_path / 'cuphandle.db')},
        'liquidity': {'min_listing_days': 250},
        'scoring': {'medium_threshold': 70},
    }
    stock = {'code': '600000', 'name': 'PF Bank'}
    attempts = {'count': 0}
    sleep_calls = []
    FakeScanManager.events = []

    def fake_fetch_with_retry(code, ds, *args, mgr=None, **kwargs):
        attempts['count'] += 1
        FakeScanManager.events.append(f"fetch:{attempts['count']}")
        if attempts['count'] == 1:
            return engine.FetchResult(
                data=None,
                primary_source=ds,
                fallback_source='sina' if ds == 'tencent' else 'tencent',
                primary_error='data source busy',
                fallback_error='data source busy',
            )
        return engine.FetchResult(
            data=_rows(260),
            primary_source=ds,
            fallback_source='sina' if ds == 'tencent' else 'tencent',
            primary_attempts=1,
        )

    monkeypatch.setattr(engine, 'DataSourceManager', FakeScanManager)
    monkeypatch.setattr(engine, '_fetch_with_retry', fake_fetch_with_retry)
    monkeypatch.setattr(engine.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(engine.time, 'sleep', lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(stock_pool, 'get_a_stock_pool', lambda config: [stock.copy()])
    monkeypatch.setattr(engine, 'fetch_market_index_daily', lambda: [])
    monkeypatch.setattr(engine, 'passes_liquidity_filter', lambda data, cfg: True)
    class FakeStrategyEngine:
        def __init__(self, config):
            pass

        def evaluate_at(self, data, code='', name='', market_data=None):
            result = engine.CupHandleResult(found=False, code=code, name=name)
            return type('Eval', (), {'result': result, 'dry_stable': None})()

    monkeypatch.setattr(engine, 'CupHandleStrategyEngine', FakeStrategyEngine)
    monkeypatch.setattr(
        engine,
        'analyze_dry_stable',
        lambda result, data, market_data=None: {
            'pattern_score': {'score': 0, 'key_pattern_type': 'other', 'type': 'other'},
            'decision': {'verdict': '不建议买入', 'summary': ''},
        },
    )

    result = engine.scan_all(config)

    assert attempts['count'] == 2
    assert result['stats']['scanned'] == 1
    assert result['stats']['skipped'] == 0
    assert result['stats']['candidates_found'] == 0
    assert sleep_calls == [0.1]
    assert FakeScanManager.events == [
        'acquire',
        'fetch:1',
        'release:tencent',
        'acquire',
        'fetch:2',
        'release:tencent',
    ]


def test_scan_all_stops_requeue_after_busy_retry_budget(monkeypatch, tmp_path):
    db_path = tmp_path / 'cuphandle.db'
    config = {
        'data': {'database_path': str(db_path), 'source_busy_max_retries': 1},
        'liquidity': {'enabled': False, 'min_listing_days': 250},
        'scoring': {'medium_threshold': 70},
    }
    stock = {'code': '600000', 'name': 'PF Bank'}
    attempts = {'count': 0}
    sleep_calls = []
    FakeScanManager.events = []

    db.init_db(str(db_path))
    db.create_scan_task('task-1', '2026-06-04 09:30:00', total_stocks=0)

    def fake_fetch_with_retry(code, ds, *args, mgr=None, **kwargs):
        attempts['count'] += 1
        FakeScanManager.events.append(f"fetch:{attempts['count']}")
        return engine.FetchResult(
            data=None,
            primary_source=ds,
            fallback_source='sina' if ds == 'tencent' else 'tencent',
            primary_attempts=2,
            fallback_attempts=0,
            primary_error='data source busy',
            fallback_error='data source busy',
        )

    monkeypatch.setattr(engine, 'DataSourceManager', FakeScanManager)
    monkeypatch.setattr(engine, '_fetch_with_retry', fake_fetch_with_retry)
    monkeypatch.setattr(engine.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(engine.time, 'sleep', lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(stock_pool, 'get_a_stock_pool', lambda config: [stock.copy()])
    monkeypatch.setattr(engine, 'fetch_market_index_daily', lambda: [])

    result = engine.scan_all(config, task_id='task-1')

    failed_rows = db.get_task_stocks('task-1', status='failed', limit=10, offset=0)

    assert attempts['count'] == 2
    assert result['task_id'] == 'task-1'
    assert result['stats']['total'] == 1
    assert result['stats']['scanned'] == 1
    assert result['stats']['skipped'] == 0
    assert result['stats']['failed'] == 1
    assert result['stats']['candidates_found'] == 0
    assert len(failed_rows) == 1
    assert failed_rows[0]['code'] == '600000'
    assert failed_rows[0]['status_reason'] == '数据源忙，超过重试次数'
    assert failed_rows[0]['primary_source'] == 'tencent'
    assert failed_rows[0]['fallback_source'] == 'sina'
    assert failed_rows[0]['primary_attempts'] == 2
    assert failed_rows[0]['fallback_attempts'] == 0
    assert failed_rows[0]['primary_error'] == 'data source busy'
    assert failed_rows[0]['fallback_error'] == 'data source busy'
    assert db.get_scan_tasks()[0]['failed'] == 1
    assert sleep_calls == [0.1]
    assert FakeScanManager.events == [
        'acquire',
        'fetch:1',
        'release:tencent',
        'acquire',
        'fetch:2',
        'release:tencent',
    ]


def test_scan_all_records_failed_stock_when_fetch_fails(monkeypatch, tmp_path):
    db_path = tmp_path / 'cuphandle.db'
    config = {'data': {'database_path': str(db_path)}, 'liquidity': {'enabled': False}}
    stocks = [{'code': '600000', 'name': 'PF Bank', 'market': 'SSE'}]

    db.init_db(str(db_path))
    db.create_scan_task('task-1', '2026-06-04 09:30:00', total_stocks=1)
    db.save_task_stocks('task-1', stocks)

    monkeypatch.setattr(engine, 'DataSourceManager', FakeScanManager)
    monkeypatch.setattr(engine.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(engine, 'fetch_market_index_daily', lambda: [])
    monkeypatch.setattr(
        engine,
        '_fetch_with_retry',
        lambda *args, **kwargs: engine.FetchResult(
            data=None,
            primary_source='tencent',
            fallback_source='sina',
            primary_attempts=2,
            fallback_attempts=2,
            primary_error='timeout',
            fallback_error='empty response',
        ),
    )

    result = engine.scan_all(config, task_id='task-1', stocks=stocks, worker_count=1)
    rows = db.get_task_stocks('task-1', status='failed')

    assert result['stats']['skipped'] == 0
    assert result['stats']['failed'] == 1
    assert len(rows) == 1
    assert rows[0]['code'] == '600000'
    assert rows[0]['status_reason'] == '数据源全部失败，未使用旧缓存扫描'
    assert rows[0]['primary_error'] == 'timeout'
    assert rows[0]['fallback_error'] == 'empty response'
    assert rows[0]['finished_at']


def test_scan_all_marks_skipped_for_insufficient_listing_days(monkeypatch, tmp_path):
    db_path = tmp_path / 'cuphandle.db'
    config = {
        'data': {'database_path': str(db_path)},
        'liquidity': {'enabled': False, 'min_listing_days': 250},
    }
    stocks = [{'code': '600000', 'name': 'PF Bank', 'market': 'SSE'}]

    db.init_db(str(db_path))
    db.create_scan_task('task-1', '2026-06-04 09:30:00', total_stocks=1)
    db.save_task_stocks('task-1', stocks)

    monkeypatch.setattr(engine, 'DataSourceManager', FakeScanManager)
    monkeypatch.setattr(engine.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(engine, 'fetch_market_index_daily', lambda: [])
    monkeypatch.setattr(
        engine,
        '_fetch_with_retry',
        lambda *args, **kwargs: engine.FetchResult(
            data=[_row('2026-06-04')],
            primary_source='tencent',
            fallback_source='sina',
            primary_attempts=1,
        ),
    )

    result = engine.scan_all(config, task_id='task-1', stocks=stocks, worker_count=1)
    rows = db.get_task_stocks('task-1', status='skipped')

    assert result['stats']['skipped'] == 1
    assert len(rows) == 1
    assert rows[0]['status_reason'] == '上市天数不足'
    assert rows[0]['kline_latest_date'] == '2026-06-04'
    assert rows[0]['finished_at']


def test_scan_all_deduplicates_candidates(monkeypatch, tmp_path):
    db_path = tmp_path / 'cuphandle.db'
    config = {
        'data': {'database_path': str(db_path)},
        'liquidity': {'enabled': False, 'min_listing_days': 250},
        'scoring': {'medium_threshold': 70},
    }
    unique_stock = {'code': '600000', 'name': 'PF Bank', 'market': 'SSE'}
    stocks = [unique_stock.copy(), unique_stock.copy()]

    db.init_db(str(db_path))
    db.create_scan_task('task-1', '2026-06-04 09:30:00', total_stocks=1)
    db.save_task_stocks('task-1', [unique_stock])

    monkeypatch.setattr(engine, 'DataSourceManager', FakeScanManager)
    monkeypatch.setattr(engine.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(engine, 'fetch_market_index_daily', lambda: [])
    monkeypatch.setattr(
        engine,
        '_fetch_with_retry',
        lambda *args, **kwargs: engine.FetchResult(
            data=_rows(260, close=20.0),
            primary_source='tencent',
            fallback_source='sina',
            primary_attempts=1,
        ),
    )
    monkeypatch.setattr(engine, 'passes_liquidity_filter', lambda data, cfg: True)

    dry_stable = {
        'decision': {'verdict': '可低吸', 'summary': '测试'},
        'volume_dry': {'score': 8},
        'price_stable': {'score': 8},
        'pattern_score': {'score': 16, 'type': '杯柄', 'key_pattern_type': 'cup_handle'},
        'risk_reward': {'risk_percent': 4.0, 'rr1': 2.0, 'position_advice': '30%'},
        'key_prices': {
            'entry_zone_low': 19,
            'entry_zone_high': 20,
            'pivot': 21,
            'stop_loss': 18,
            'target_1': 24,
            'target_2': 26,
        },
        'market_environment': {'status': '一般', 'position_advice': '轻仓'},
    }

    class FakeStrategyEngine:
        def __init__(self, config):
            pass

        def evaluate_at(self, data, code='', name='', market_data=None):
            result = engine.CupHandleResult(found=True, code=code, name=name, score=80)
            return type('Eval', (), {'result': result, 'dry_stable': dry_stable})()

    monkeypatch.setattr(engine, 'CupHandleStrategyEngine', FakeStrategyEngine)

    result = engine.scan_all(config, task_id='task-1', stocks=stocks, worker_count=1)
    candidate_rows = db.get_task_stocks('task-1', status='candidate')

    assert result['stats']['candidates_found'] == 1
    assert len(result['candidates']) == 1
    assert result['candidates'][0][0]['code'] == '600000'
    assert len(candidate_rows) == 1
    assert candidate_rows[0]['code'] == '600000'


def test_fetch_with_retry_ignores_fresh_cache_when_source_succeeds(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("600000", [_row("2026-06-03", close=9.0)])
    calls = []

    def fake_sina(code):
        calls.append(code)
        return [_row("2026-06-04", close=10.0)]

    monkeypatch.setattr(engine, "fetch_sina_daily", fake_sina)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: None)
    result = engine._fetch_with_retry("600000", "sina", retry_attempts=2, fallback_attempts=2, sleep_fn=lambda _: None, source_chain=["sina", "tencent"])

    assert calls == ["600000"]
    assert result.data[-1]["date"] == "2026-06-04"
    assert result.from_cache is False
    assert result.primary_attempts == 1
    assert result.fallback_attempts == 0
    assert db.get_ohlc("600000")[-1]["date"] == "2026-06-04"


def test_fetch_with_retry_uses_fallback_after_primary_failures(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    primary_calls = []
    fallback_calls = []

    def fake_sina(code):
        primary_calls.append(code)
        return None

    def fake_tencent(code):
        fallback_calls.append(code)
        return [_row("2026-06-04", close=10.0)]

    monkeypatch.setattr(engine, "fetch_sina_daily", fake_sina)
    monkeypatch.setattr(engine, "fetch_tencent_daily", fake_tencent)
    result = engine._fetch_with_retry("600000", "sina", retry_attempts=2, fallback_attempts=2, sleep_fn=lambda _: None, source_chain=["sina", "tencent"])

    assert result.data[-1]["date"] == "2026-06-04"
    assert result.primary_attempts == 2
    assert result.fallback_attempts == 1
    assert result.primary_error == "empty response"
    assert result.fallback_error is None


def test_fetch_with_retry_tencent_primary_fetches_independently(monkeypatch, tmp_path):
    """Tencent primary fetch no longer needs extra sina lock — fetches directly."""
    db.init_db(str(tmp_path / "cuphandle.db"))
    tencent_calls = []
    mgr = FakeManager({"sina": False})

    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: tencent_calls.append(code) or [_row("2026-06-04", close=10.0)])
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: [_row("2026-06-04", close=10.0)])

    result = engine._fetch_with_retry(
        "600000",
        "tencent",
        retry_attempts=2,
        fallback_attempts=2,
        sleep_fn=lambda _: None,
        mgr=mgr,
        source_chain=["sina", "tencent"],
    )

    assert result.data is not None
    assert result.data[-1]["date"] == "2026-06-04"
    assert result.primary_attempts == 1
    assert result.primary_error is None
    assert tencent_calls == ["600000"]
    assert mgr.acquire_calls == []


def test_fetch_with_retry_fallback_acquires_releases_via_manager(monkeypatch, tmp_path):
    """Fallback source acquisition and release is handled by _fetch_with_retry via mgr."""
    db.init_db(str(tmp_path / "cuphandle.db"))
    sina_calls = []
    tencent_calls = []
    mgr = FakeManager({"tencent": True})

    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: sina_calls.append(code) or None)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: tencent_calls.append(code) or [_row("2026-06-04", close=10.0)])

    result = engine._fetch_with_retry(
        "600000",
        "sina",
        retry_attempts=2,
        fallback_attempts=2,
        sleep_fn=lambda _: None,
        mgr=mgr,
        source_chain=["sina", "tencent"],
    )

    assert result.data[-1]["date"] == "2026-06-04"
    assert result.primary_attempts == 2
    assert result.fallback_attempts == 1
    assert result.fallback_error is None
    assert sina_calls == ["600000", "600000"]
    assert tencent_calls == ["600000"]
    assert mgr.acquire_calls == ["tencent"]
    assert mgr.release_calls == ["tencent"]


def test_fetch_with_retry_skips_fallback_when_manager_reports_source_busy(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    fallback_calls = []
    mgr = FakeManager({"tencent": False})

    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: None)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: fallback_calls.append(code) or [_row("2026-06-04", close=10.0)])

    result = engine._fetch_with_retry(
        "600000",
        "sina",
        retry_attempts=2,
        fallback_attempts=2,
        sleep_fn=lambda _: None,
        mgr=mgr,
        source_chain=["sina", "tencent"],
    )

    assert result.data is None
    assert result.primary_attempts == 2
    assert result.fallback_attempts == 0
    assert result.primary_error == "empty response"
    assert result.fallback_error == "data source busy"
    assert fallback_calls == []
    assert mgr.acquire_calls == ["tencent"]
    assert mgr.release_calls == []


def test_fetch_with_retry_acquires_and_releases_fallback_lock(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    fallback_calls = []
    mgr = FakeManager({"tencent": True})

    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: None)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: fallback_calls.append(code) or [_row("2026-06-04", close=10.0)])

    result = engine._fetch_with_retry(
        "600000",
        "sina",
        retry_attempts=2,
        fallback_attempts=2,
        sleep_fn=lambda _: None,
        mgr=mgr,
        source_chain=["sina", "tencent"],
    )

    assert result.data[-1]["date"] == "2026-06-04"
    assert result.primary_attempts == 2
    assert result.fallback_attempts == 1
    assert result.fallback_error is None
    assert fallback_calls == ["600000"]
    assert mgr.acquire_calls == ["tencent"]
    assert mgr.release_calls == ["tencent"]




def test_fetch_with_retry_treats_sina_456_as_transient_source_busy(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    calls = []

    def fake_sina(code):
        calls.append(code)
        raise RuntimeError("456 Client Error")

    monkeypatch.setattr(engine, "fetch_sina_daily", fake_sina)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: None)

    result = engine._fetch_with_retry("000868", "sina", retry_attempts=2, fallback_attempts=2, sleep_fn=lambda _: None, source_chain=["sina", "tencent"])

    assert result.data is None
    assert result.primary_error == "data source busy"
    assert engine._is_transient_source_busy(result) is True


def test_fetch_with_retry_does_not_return_cache_when_sources_fail(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("600000", [_row("2026-06-03", close=9.0)])

    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: None)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: None)
    result = engine._fetch_with_retry("600000", "sina", retry_attempts=2, fallback_attempts=2, sleep_fn=lambda _: None, source_chain=["sina", "tencent"])

    assert result.data is None
    assert result.primary_attempts == 2
    assert result.fallback_attempts == 2
    assert result.primary_error == "empty response"
    assert result.fallback_error == "empty response"
    assert result.from_cache is False


def test_fetch_with_retry_uses_configured_daily_source_chain_mootdx_first(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    calls = []

    monkeypatch.setattr(engine, "fetch_mootdx_daily", lambda code: calls.append("mootdx") or [_row("2026-06-05", close=11.0)], raising=False)
    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code: calls.append("baidu") or [_row("2026-06-05", close=12.0)], raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: calls.append("sina") or [_row("2026-06-05", close=13.0)])
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: calls.append("tencent") or [_row("2026-06-05", close=14.0)])

    result = engine._fetch_with_retry(
        "600000",
        "mootdx",
        retry_attempts=2,
        fallback_attempts=2,
        sleep_fn=lambda _: None,
        source_chain=["mootdx", "baidu", "sina", "tencent"],
    )

    assert calls == ["mootdx"]
    assert result.data[-1]["date"] == "2026-06-05"
    assert result.data[-1]["close"] == 11.0
    assert result.primary_source == "mootdx"
    assert result.fallback_source == "mootdx"
    assert result.primary_attempts == 1
    assert result.primary_error is None


def test_normalize_source_chain_deduplicates_primary_and_preserves_order():
    assert engine._normalize_source_chain(["sina", "baidu", "sina", "tencent", "baidu"], "sina") == ["sina", "baidu", "tencent"]


def test_fetch_with_retry_does_not_treat_unmanaged_sources_as_busy(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    calls = []
    mgr = FakeManager({"tencent": True})

    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: calls.append("sina") or None)
    monkeypatch.setattr(engine, "fetch_mootdx_daily", lambda code: calls.append("mootdx") or None, raising=False)
    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code: calls.append("baidu") or None, raising=False)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: calls.append("tencent") or [_row("2026-06-05", close=14.0)])

    result = engine._fetch_with_retry(
        "600000",
        "sina",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        mgr=mgr,
        source_chain=["sina", "mootdx", "baidu", "tencent"],
    )

    assert calls == ["sina", "mootdx", "baidu", "tencent"]
    assert result.data[-1]["close"] == 14.0
    assert result.fallback_source == "tencent"
    assert result.fallback_error is None
    assert mgr.acquire_calls == ["tencent"]
    assert mgr.release_calls == ["tencent"]


def test_fetch_with_retry_continues_after_managed_source_busy(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    calls = []
    mgr = FakeManager({"tencent": False})

    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: calls.append("sina") or None)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: calls.append("tencent") or [_row("2026-06-05", close=13.0)])
    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code: calls.append("baidu") or [_row("2026-06-05", close=12.0)], raising=False)

    result = engine._fetch_with_retry(
        "600000",
        "sina",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        mgr=mgr,
        source_chain=["sina", "tencent", "baidu"],
    )

    assert calls == ["sina", "baidu"]
    assert result.data[-1]["close"] == 12.0
    assert result.fallback_source == "baidu"
    assert result.fallback_error is None
    assert mgr.acquire_calls == ["tencent"]
    assert mgr.release_calls == []


def test_fetch_with_retry_continues_after_unknown_source(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    calls = []

    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: calls.append("sina") or None)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: calls.append("tencent") or [_row("2026-06-05", close=14.0)])

    result = engine._fetch_with_retry(
        "600000",
        "sina",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["sina", "bad_source", "tencent"],
    )

    assert calls == ["sina", "tencent"]
    assert result.data[-1]["close"] == 14.0
    assert result.fallback_source == "tencent"
    assert result.fallback_error is None


def test_fetch_with_retry_preserves_fetch_busy_error_if_later_sources_fail(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    calls = []
    mgr = FakeManager({"tencent": True})

    def busy_tencent(code):
        calls.append("tencent")
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: calls.append("sina") or None)
    monkeypatch.setattr(engine, "fetch_tencent_daily", busy_tencent)
    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code: calls.append("baidu") or None, raising=False)

    result = engine._fetch_with_retry(
        "600000",
        "sina",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        mgr=mgr,
        source_chain=["sina", "tencent", "baidu"],
    )

    assert calls == ["sina", "tencent", "baidu"]
    assert result.data is None
    assert result.fallback_error == "data source busy"
    assert engine._is_transient_source_busy(result) is True


def test_fetch_with_retry_falls_back_to_baidu_after_mootdx_failure(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    calls = []

    monkeypatch.setattr(engine, "fetch_mootdx_daily", lambda code: calls.append("mootdx") or None, raising=False)
    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code: calls.append("baidu") or [_row("2026-06-05", close=12.0)], raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: calls.append("sina") or [_row("2026-06-05", close=13.0)])
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: calls.append("tencent") or [_row("2026-06-05", close=14.0)])

    result = engine._fetch_with_retry(
        "600000",
        "mootdx",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["mootdx", "baidu", "sina", "tencent"],
    )

    assert calls == ["mootdx", "baidu"]
    assert result.data[-1]["close"] == 12.0
    assert result.primary_error == "empty response"
    assert result.fallback_source == "baidu"
    assert result.fallback_error is None


def test_fetch_with_retry_falls_back_through_sina_to_tencent(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    calls = []

    monkeypatch.setattr(engine, "fetch_mootdx_daily", lambda code: calls.append("mootdx") or None, raising=False)
    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code: calls.append("baidu") or None, raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: calls.append("sina") or None)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: calls.append("tencent") or [_row("2026-06-05", close=14.0)])

    result = engine._fetch_with_retry(
        "600000",
        "mootdx",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["mootdx", "baidu", "sina", "tencent"],
    )

    assert calls == ["mootdx", "baidu", "sina", "tencent"]
    assert result.data[-1]["close"] == 14.0
    assert result.fallback_source == "tencent"
    assert result.fallback_error is None


def test_fetch_with_retry_multi_source_failure_does_not_return_cache(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("600000", [_row("2026-06-03", close=9.0)])
    calls = []

    monkeypatch.setattr(engine, "fetch_mootdx_daily", lambda code: calls.append("mootdx") or None, raising=False)
    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code: calls.append("baidu") or None, raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: calls.append("sina") or None)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: calls.append("tencent") or None)

    result = engine._fetch_with_retry(
        "600000",
        "mootdx",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["mootdx", "baidu", "sina", "tencent"],
    )

    assert calls == ["mootdx", "baidu", "sina", "tencent"]
    assert result.data is None
    assert result.from_cache is False
    assert db.get_ohlc("600000")[-1]["date"] == "2026-06-03"


def test_scan_all_passes_configured_daily_sources_to_fetch(monkeypatch, tmp_path):
    config = {
        "data": {
            "database_path": str(tmp_path / "cuphandle.db"),
            "daily_sources": ["baidu", "sina"],
            "worker_count": 1,
        },
        "liquidity": {"min_listing_days": 250},
        "scoring": {"medium_threshold": 70},
    }
    seen = []

    def fake_fetch_with_retry(code, ds, *args, source_chain=None, **kwargs):
        seen.append({"ds": ds, "source_chain": source_chain})
        return engine.FetchResult(data=_rows(260), primary_source=ds, fallback_source=ds, primary_attempts=1)

    monkeypatch.setattr(engine, "_fetch_with_retry", fake_fetch_with_retry)
    monkeypatch.setattr(engine, "DataSourceManager", FakeScanManager)
    monkeypatch.setattr(engine.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(stock_pool, "get_a_stock_pool", lambda config: [{"code": "600000", "name": "PF Bank"}])
    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda: [])
    monkeypatch.setattr(engine, "passes_liquidity_filter", lambda data, cfg: True)
    monkeypatch.setattr(engine, "detect_cup_handle", lambda data, cfg: engine.CupHandleResult(found=False))
    monkeypatch.setattr(
        engine,
        "analyze_dry_stable",
        lambda result, data, market_data=None: {
            "pattern_score": {"score": 0, "key_pattern_type": "other", "type": "other"},
            "decision": {"verdict": "不建议买入", "summary": ""},
        },
    )

    engine.scan_all(config, worker_count=1)

    assert seen == [{"ds": "baidu", "source_chain": ["baidu", "sina"]}]


def test_fetch_with_retry_uses_configured_kline_days(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    seen_days = []

    def fake_sina(code, days=250):
        seen_days.append(days)
        return [_row("2026-06-04", close=10.0)]

    monkeypatch.setattr(engine, "fetch_sina_daily", fake_sina)

    result = engine._fetch_with_retry(
        "600000",
        "sina",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["sina", "tencent"],
        kline_days=320,
    )

    assert result.data[-1]["date"] == "2026-06-04"
    assert seen_days == [320]


def test_scan_all_uses_daily_kline_days_config(monkeypatch, tmp_path):
    config = {
        "data": {"database_path": str(tmp_path / "cuphandle.db"), "daily_kline_days": 320},
        "liquidity": {"enabled": False, "min_listing_days": 250},
        "scoring": {"medium_threshold": 70},
    }
    seen = []

    def fake_fetch_with_retry(code, ds, *args, kline_days=None, **kwargs):
        seen.append(kline_days)
        return engine.FetchResult(data=_rows(320), primary_source=ds, fallback_source="sina", primary_attempts=1)

    monkeypatch.setattr(engine, "DataSourceManager", FakeScanManager)
    monkeypatch.setattr(engine.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(engine, "_fetch_with_retry", fake_fetch_with_retry)
    monkeypatch.setattr(stock_pool, "get_a_stock_pool", lambda config: [{"code": "600000", "name": "PF Bank"}])
    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda: [])
    monkeypatch.setattr(engine, "passes_liquidity_filter", lambda data, cfg: True)
    monkeypatch.setattr(engine, "detect_cup_handle", lambda data, cfg: engine.CupHandleResult(found=False))
    monkeypatch.setattr(
        engine,
        "analyze_dry_stable",
        lambda result, data, market_data=None: {
            "pattern_score": {"score": 0, "key_pattern_type": "other", "type": "other"},
            "decision": {"verdict": "不建议买入", "summary": ""},
        },
    )

    engine.scan_all(config, worker_count=1)

    assert seen == [320]


def test_scan_all_reports_progress_when_stock_skipped_for_insufficient_listing_days(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    config = {
        "data": {"database_path": str(db_path)},
        "liquidity": {"enabled": False, "min_listing_days": 250},
    }
    stocks = [{"code": "600000", "name": "PF Bank", "market": "SSE"}]
    progress = []

    db.init_db(str(db_path))
    db.create_scan_task("task-1", "2026-06-04 09:30:00", total_stocks=1)
    db.save_task_stocks("task-1", stocks)

    monkeypatch.setattr(engine, "DataSourceManager", FakeScanManager)
    monkeypatch.setattr(engine.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda: [])
    monkeypatch.setattr(
        engine,
        "_fetch_with_retry",
        lambda *args, **kwargs: engine.FetchResult(
            data=[_row("2026-06-04")],
            primary_source="tencent",
            fallback_source="sina",
            primary_attempts=1,
        ),
    )

    engine.scan_all(
        config,
        task_id="task-1",
        stocks=stocks,
        worker_count=1,
        progress_callback=lambda stage, current, total, detail, discovery=None: progress.append((stage, current, total, detail)),
    )

    assert progress == [("scanning", 1, 1, "600000 PF Bank")]
