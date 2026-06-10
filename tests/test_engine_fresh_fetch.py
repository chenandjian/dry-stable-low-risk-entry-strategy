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

    def try_acquire_any(self):
        for name, ok in self.acquire_results.items():
            if ok:
                self.acquire_calls.append(name)
                return name
        return None


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
    monkeypatch.setattr(engine, 'fetch_market_index_daily', lambda symbol=None: [])
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
    monkeypatch.setattr(engine, 'fetch_market_index_daily', lambda symbol=None: [])

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
    assert failed_rows[0]['primary_source'] == 'baidu'
    assert failed_rows[0]['fallback_source'] == 'tencent'
    assert failed_rows[0]['primary_attempts'] == 2
    assert failed_rows[0]['fallback_attempts'] == 0
    assert failed_rows[0]['primary_error'] == 'data source busy'
    assert failed_rows[0]['fallback_error'] == 'data source busy'
    assert db.get_scan_tasks()[0]['failed'] == 1
    assert sleep_calls == [0.1]


def test_scan_all_records_failed_stock_when_fetch_fails(monkeypatch, tmp_path):
    db_path = tmp_path / 'cuphandle.db'
    config = {'data': {'database_path': str(db_path)}, 'liquidity': {'enabled': False}}
    stocks = [{'code': '600000', 'name': 'PF Bank', 'market': 'SSE'}]

    db.init_db(str(db_path))
    db.create_scan_task('task-1', '2026-06-04 09:30:00', total_stocks=1)
    db.save_task_stocks('task-1', stocks)

    monkeypatch.setattr(engine, 'DataSourceManager', FakeScanManager)
    monkeypatch.setattr(engine.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(engine, 'fetch_market_index_daily', lambda symbol=None: [])
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
    monkeypatch.setattr(engine, 'fetch_market_index_daily', lambda symbol=None: [])
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
    monkeypatch.setattr(engine, 'fetch_market_index_daily', lambda symbol=None: [])
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
        'decision': {'verdict': '可低吸', 'verdict_key': 'BUY_LOW', 'summary': '测试'},
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
            return type('Eval', (), {'result': result, 'dry_stable': dry_stable, 'passed': True})()

    monkeypatch.setattr(engine, 'CupHandleStrategyEngine', FakeStrategyEngine)

    result = engine.scan_all(config, task_id='task-1', stocks=stocks, worker_count=1)
    candidate_rows = db.get_task_stocks('task-1', status='candidate')

    assert result['stats']['candidates_found'] == 1
    assert len(result['candidates']) == 1
    assert result['candidates'][0][0]['code'] == '600000'
    assert len(candidate_rows) == 1
    assert candidate_rows[0]['code'] == '600000'


# ---- try_acquire_any fetch tests ----


def test_fetch_uses_free_source_via_try_acquire_any(monkeypatch, tmp_path):
    """Mgr offers sina first → sina wins, lock released."""
    db.init_db(str(tmp_path / "cuphandle.db"))
    mgr = FakeManager({"sina": True})

    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code, days=250: [_row("2026-06-04", close=10.0)])
    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code, days=250: [_row("2026-06-04", close=12.0)], raising=False)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: None)

    result = engine._fetch_with_retry(
        "600000", "sina",
        retry_attempts=1, fallback_attempts=1,
        sleep_fn=lambda _: None, mgr=mgr,
        source_chain=["sina", "tencent"],
    )

    assert result.data is not None
    assert result.data[-1]["close"] == 10.0
    assert mgr.acquire_calls == ["sina"]
    assert mgr.release_calls == ["sina"]


def test_fetch_skips_busy_source_uses_next_free(monkeypatch, tmp_path):
    """sina busy → tencent free → tencent wins."""
    db.init_db(str(tmp_path / "cuphandle.db"))
    mgr = FakeManager({"sina": False, "tencent": True})

    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code, days=250: [_row("2026-06-04", close=10.0)])
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: [_row("2026-06-04", close=14.0)])

    result = engine._fetch_with_retry(
        "600000", "sina",
        retry_attempts=1, fallback_attempts=1,
        sleep_fn=lambda _: None, mgr=mgr,
        source_chain=["sina", "tencent"],
    )

    assert result.data is not None
    assert result.data[-1]["close"] == 14.0
    # tries sina first (config order), busy → skip → tencent wins
    assert mgr.acquire_calls == ["sina", "tencent"]


def test_fetch_all_busy_returns_none_after_retries(monkeypatch, tmp_path):
    """All sources busy → retry → exhausted → return None with busy error."""
    db.init_db(str(tmp_path / "cuphandle.db"))
    mgr = FakeManager({"baidu": False, "sina": False, "tencent": False})  # all busy

    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code, days=250: [_row("2026-06-04", close=12.0)], raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code, days=250: [_row("2026-06-04", close=13.0)])
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: [_row("2026-06-04", close=14.0)])

    result = engine._fetch_with_retry(
        "600000", "baidu",
        retry_attempts=1, fallback_attempts=1,
        sleep_fn=lambda _: None, mgr=mgr,
        source_chain=["baidu", "sina", "tencent"],
    )

    assert result.data is None
    assert engine._is_transient_source_busy(result) is True


def test_fetch_merges_and_saves(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("600000", [_row("2026-06-03", close=9.0)])

    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code, days=250: [_row("2026-06-04", close=10.0)])
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: None)
    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code, days=250: None, raising=False)

    result = engine._fetch_with_retry("600000", "sina", retry_attempts=1, fallback_attempts=1,
                                       sleep_fn=lambda _: None, source_chain=["sina", "tencent"])

    assert result.data[-1]["date"] == "2026-06-04"
    assert db.get_ohlc("600000")[-1]["date"] == "2026-06-04"


def test_fetch_all_sources_fail_returns_none(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))

    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code, days=250: None)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: None)
    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code, days=250: None, raising=False)

    result = engine._fetch_with_retry("600000", "sina", retry_attempts=1, fallback_attempts=1,
                                       sleep_fn=lambda _: None, source_chain=["sina", "tencent"])

    assert result.data is None


def test_fetch_rate_limit_preserved_as_transient_busy(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))

    def rate_limited(code, days=250):
        raise RuntimeError("456 Client Error")

    monkeypatch.setattr(engine, "fetch_sina_daily", rate_limited)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: None)
    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code, days=250: None, raising=False)

    result = engine._fetch_with_retry("000868", "sina", retry_attempts=1, fallback_attempts=1,
                                       sleep_fn=lambda _: None, source_chain=["sina", "tencent"])

    assert result.data is None
    assert engine._is_transient_source_busy(result) is True


def test_fetch_kline_days_passed_through(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    seen = []

    def fake_sina(code, days=250):
        seen.append(days)
        return [_row("2026-06-04", close=10.0)]

    monkeypatch.setattr(engine, "fetch_sina_daily", fake_sina)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: None)

    result = engine._fetch_with_retry(
        "600000", "sina",
        retry_attempts=1, fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["sina", "tencent"],
        kline_days=320,
    )

    assert result.data is not None
    assert 320 in seen


def test_fetch_no_mgr_falls_back_to_serial_order(monkeypatch, tmp_path):
    """Without DataSourceManager, sources are tried in chain order."""
    db.init_db(str(tmp_path / "cuphandle.db"))

    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code, days=250: None, raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code, days=250: [_row("2026-06-04", close=13.0)])

    result = engine._fetch_with_retry(
        "600000", "baidu",
        retry_attempts=1, fallback_attempts=1,
        sleep_fn=lambda _: None, mgr=None,
        source_chain=["baidu", "sina"],
    )

    assert result.data is not None
    assert result.data[-1]["close"] == 13.0


def test_normalize_source_chain_deduplicates_primary_and_preserves_order():
    assert engine._normalize_source_chain(["sina", "baidu", "sina", "tencent", "baidu"], "sina") == ["sina", "baidu", "tencent"]


def test_all_sources_fail_backfills_compatibility_fields(monkeypatch, tmp_path):
    """ROUND4-002: When all sources fail, primary_attempts/error are backfilled from source_errors."""
    db.init_db(str(tmp_path / "cuphandle.db"))

    def fake_fetch_fails(code, days=250):
        raise RuntimeError("timeout")

    monkeypatch.setattr(engine, "fetch_baidu_daily", fake_fetch_fails, raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", fake_fetch_fails)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: None)

    result = engine._fetch_with_retry(
        "600000", "baidu",
        retry_attempts=2, fallback_attempts=3,
        sleep_fn=lambda _: None,
        source_chain=["baidu", "sina", "tencent"],
    )

    assert result.data is None
    # Compatibility fields should be backfilled
    assert result.primary_attempts > 0, f"primary_attempts should >0, got {result.primary_attempts}"
    assert result.primary_error is not None
    assert "timeout" in result.primary_error
    assert result.fallback_attempts > 0
    assert result.fallback_error is not None
    # source_errors should still have all three entries
    assert len(result.source_errors) == 3


def test_all_sources_busy_backfills_primary_error(monkeypatch, tmp_path):
    """ROUND4-002: When all sources are busy, primary_error indicates 'data source busy'."""
    db.init_db(str(tmp_path / "cuphandle.db"))
    mgr = FakeManager({"baidu": False, "sina": False, "tencent": False})

    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code, days=250: [_row("2026-06-04", close=12.0)], raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code, days=250: [_row("2026-06-04", close=13.0)])
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: [_row("2026-06-04", close=14.0)])

    result = engine._fetch_with_retry(
        "600000", "baidu",
        retry_attempts=1, fallback_attempts=1,
        sleep_fn=lambda _: None, mgr=mgr,
        source_chain=["baidu", "sina", "tencent"],
    )

    assert result.data is None
    assert result.primary_error == "data source busy"
    assert result.fallback_error == "data source busy"
    assert engine._is_transient_source_busy(result) is True


def test_source_errors_includes_busy_sources(monkeypatch, tmp_path):
    """ROUND3-005: Source busy recorded as 'busy' in source_errors dict."""
    import json
    db.init_db(str(tmp_path / "cuphandle.db"))
    mgr = FakeManager({"baidu": False, "sina": False, "tencent": False})  # all busy

    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code, days=250: [_row("2026-06-04", close=12.0)], raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code, days=250: [_row("2026-06-04", close=13.0)])
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: [_row("2026-06-04", close=14.0)])

    result = engine._fetch_with_retry(
        "600000", "baidu",
        retry_attempts=1, fallback_attempts=1,
        sleep_fn=lambda _: None, mgr=mgr,
        source_chain=["baidu", "sina", "tencent"],
    )

    assert result.data is None
    assert result.source_errors == {"baidu": "busy", "sina": "busy", "tencent": "busy"}
    # Verify JSON encoding
    encoded = engine._encode_source_errors(result.source_errors)
    parsed = json.loads(encoded)
    assert parsed == {"baidu": "busy", "sina": "busy", "tencent": "busy"}


# ---- ROUND5-002/003: source compatibility field test matrix ----


def _fr(**kw):
    """Shorthand: FetchResult with defaults for testing."""
    defaults = dict(data=None, primary_source="", fallback_source="", source_errors={})
    defaults.update(kw)
    return engine.FetchResult(**defaults)


def test_compat_primary_first_try_succeeds(monkeypatch, tmp_path):
    """ROUND5-002: primary source succeeds on first try — correct compat fields."""
    db.init_db(str(tmp_path / "cuphandle.db"))
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code, days=250: [_row("2026-06-04", close=10.0)])
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: None)

    result = engine._fetch_with_retry(
        "600000", "sina", retry_attempts=2, fallback_attempts=3,
        sleep_fn=lambda _: None, source_chain=["sina", "tencent"],
    )

    assert result.data is not None
    assert result.primary_source == "sina"
    assert result.primary_attempts == 1
    assert result.primary_error is None
    assert result.fallback_source == "sina"
    assert result.fallback_attempts == 0
    assert result.fallback_error is None
    assert result.source_errors == {}


def test_compat_primary_fails_fallback_succeeds(monkeypatch, tmp_path):
    """ROUND5-002: primary fails, fallback succeeds — primary errors backfilled."""
    db.init_db(str(tmp_path / "cuphandle.db"))

    def fail_then_succeed(code, days=250):
        raise RuntimeError("timeout")

    monkeypatch.setattr(engine, "fetch_baidu_daily", fail_then_succeed, raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code, days=250: [_row("2026-06-04", close=13.0)])
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: None)

    result = engine._fetch_with_retry(
        "600000", "baidu", retry_attempts=2, fallback_attempts=3,
        sleep_fn=lambda _: None, source_chain=["baidu", "sina", "tencent"],
    )

    assert result.data is not None
    assert result.primary_source == "baidu"
    assert result.primary_attempts == 2
    assert result.primary_error == "timeout"
    assert result.fallback_source == "sina"
    assert result.fallback_attempts == 1
    assert result.fallback_error is None  # success
    assert "baidu" in result.source_errors
    assert "timeout" in result.source_errors["baidu"]


def test_compat_primary_busy_fallback_succeeds(monkeypatch, tmp_path):
    """ROUND5-002: primary busy, fallback succeeds — primary_error='data source busy'."""
    db.init_db(str(tmp_path / "cuphandle.db"))
    mgr = FakeManager({"baidu": False, "sina": True})

    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code, days=250: [_row("2026-06-04", close=12.0)], raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code, days=250: [_row("2026-06-04", close=13.0)])
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: None)

    result = engine._fetch_with_retry(
        "600000", "baidu", retry_attempts=1, fallback_attempts=1,
        sleep_fn=lambda _: None, mgr=mgr,
        source_chain=["baidu", "sina", "tencent"],
    )

    assert result.data is not None
    assert result.primary_source == "baidu"
    assert result.primary_attempts == 0  # busy — no network attempt
    assert result.primary_error == "data source busy"
    assert result.fallback_source == "sina"
    assert result.fallback_error is None
    assert result.source_errors == {"baidu": "busy"}


def test_compat_two_fail_third_succeeds(monkeypatch, tmp_path):
    """ROUND5-003: two fail, third succeeds — fallback points to third (success)."""
    db.init_db(str(tmp_path / "cuphandle.db"))

    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code, days=250: None, raising=False)
    def fail_sina(code, days=250):
        raise RuntimeError("sina timeout")
    monkeypatch.setattr(engine, "fetch_sina_daily", fail_sina)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: [_row("2026-06-04", close=14.0)])

    result = engine._fetch_with_retry(
        "600000", "baidu", retry_attempts=2, fallback_attempts=2,
        sleep_fn=lambda _: None, source_chain=["baidu", "sina", "tencent"],
    )

    assert result.data is not None
    assert result.primary_source == "baidu"
    assert result.primary_error is not None
    assert result.fallback_source == "tencent"
    assert result.fallback_attempts == 1
    assert result.fallback_error is None
    assert "baidu" in result.source_errors
    assert "sina" in result.source_errors


def test_compat_two_fail_third_busy_fallback_points_to_second(monkeypatch, tmp_path):
    """ROUND5-003: two fail, third busy — fallback points to last actual failure (second)."""
    db.init_db(str(tmp_path / "cuphandle.db"))
    mgr = FakeManager({"baidu": True, "sina": True, "tencent": False})

    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code, days=250: None, raising=False)
    def fail_sina(code, days=250):
        raise RuntimeError("sina error")
    monkeypatch.setattr(engine, "fetch_sina_daily", fail_sina)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: [_row("2026-06-04", close=14.0)])

    result = engine._fetch_with_retry(
        "600000", "baidu", retry_attempts=2, fallback_attempts=2,
        sleep_fn=lambda _: None, mgr=mgr,
        source_chain=["baidu", "sina", "tencent"],
    )

    assert result.data is None
    assert result.fallback_source == "sina"  # last actual failure, NOT tencent (busy)
    assert result.fallback_error == "sina error"
    assert result.source_errors["tencent"] == "busy"


def test_compat_three_all_fail_consistency(monkeypatch, tmp_path):
    """ROUND5-002/003: three all fail — fallback points to last actual failure."""
    db.init_db(str(tmp_path / "cuphandle.db"))

    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code, days=250: None, raising=False)
    def fail_sina(code, days=250):
        raise RuntimeError("sina down")
    monkeypatch.setattr(engine, "fetch_sina_daily", fail_sina)
    def fail_tencent(code, days=250):
        raise RuntimeError("tencent timeout")
    monkeypatch.setattr(engine, "fetch_tencent_daily", fail_tencent)

    result = engine._fetch_with_retry(
        "600000", "baidu", retry_attempts=2, fallback_attempts=3,
        sleep_fn=lambda _: None, source_chain=["baidu", "sina", "tencent"],
    )

    assert result.data is None
    assert result.primary_source == "baidu"
    assert result.primary_attempts > 0
    assert result.primary_error == "empty response"
    assert result.fallback_source == "tencent"  # last actual failure
    assert result.fallback_attempts > 0
    assert result.fallback_error == "tencent timeout"
    assert len(result.source_errors) == 3


def test_compat_three_all_busy(monkeypatch, tmp_path):
    """ROUND5-002: three all busy — all errors = 'data source busy', attempts = 0."""
    db.init_db(str(tmp_path / "cuphandle.db"))
    mgr = FakeManager({"baidu": False, "sina": False, "tencent": False})

    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code, days=250: [_row("2026-06-04", close=12.0)], raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code, days=250: [_row("2026-06-04", close=13.0)])
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: [_row("2026-06-04", close=14.0)])

    result = engine._fetch_with_retry(
        "600000", "baidu", retry_attempts=1, fallback_attempts=1,
        sleep_fn=lambda _: None, mgr=mgr,
        source_chain=["baidu", "sina", "tencent"],
    )

    assert result.data is None
    assert result.primary_source == "baidu"
    assert result.primary_attempts == 0
    assert result.primary_error == "data source busy"
    assert result.fallback_source == "tencent"
    assert result.fallback_attempts == 0
    assert result.fallback_error == "data source busy"
    assert result.source_errors == {"baidu": "busy", "sina": "busy", "tencent": "busy"}
    assert engine._is_transient_source_busy(result) is True


def test_primary_failed_all_fallbacks_busy_has_consistent_compatibility_fields(monkeypatch, tmp_path):
    """FINAL-001: primary fails, all fallbacks busy → fallback points to last busy source."""
    db.init_db(str(tmp_path / "cuphandle.db"))
    mgr = FakeManager({"baidu": True, "sina": False, "tencent": False})

    def fail_baidu(code, days=250):
        raise RuntimeError("timeout")
    monkeypatch.setattr(engine, "fetch_baidu_daily", fail_baidu, raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code, days=250: [_row("2026-06-04", close=13.0)])
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code, days=250: [_row("2026-06-04", close=14.0)])

    result = engine._fetch_with_retry(
        "600000", "baidu", retry_attempts=2, fallback_attempts=1,
        sleep_fn=lambda _: None, mgr=mgr,
        source_chain=["baidu", "sina", "tencent"],
    )

    assert result.data is None
    assert result.primary_source == "baidu"
    assert result.primary_attempts == 2
    assert result.primary_error == "timeout"

    assert result.fallback_source == "tencent"
    assert result.fallback_attempts == 0
    assert result.fallback_error == "data source busy"

    assert result.source_errors == {
        "baidu": "attempts=2 error=timeout",
        "sina": "busy",
        "tencent": "busy",
    }


def test_single_source_chain_failure_truly_mirrors_primary(monkeypatch, tmp_path):
    """FINAL-001: single-source chain → fallback truly mirrors primary (same error, attempts)."""
    db.init_db(str(tmp_path / "cuphandle.db"))

    def fail_baidu(code, days=250):
        raise RuntimeError("timeout")
    monkeypatch.setattr(engine, "fetch_baidu_daily", fail_baidu, raising=False)

    result = engine._fetch_with_retry(
        "600000", "baidu", retry_attempts=2, fallback_attempts=1,
        sleep_fn=lambda _: None, source_chain=["baidu"],
    )

    assert result.data is None
    assert result.primary_source == "baidu"
    assert result.primary_error == "timeout"
    assert result.fallback_source == "baidu"
    assert result.fallback_attempts == 2  # truly mirrors primary
    assert result.fallback_error == "timeout"


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
    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda symbol=None: [])
    monkeypatch.setattr(engine, "passes_liquidity_filter", lambda data, cfg: True)
    class FakeStrategyEngine:
        def __init__(self, config):
            pass
        def evaluate_at(self, data, code='', name='', market_data=None):
            result = engine.CupHandleResult(found=False, code=code, name=name)
            return type('Eval', (), {'result': result, 'dry_stable': None})()
    monkeypatch.setattr(engine, "CupHandleStrategyEngine", FakeStrategyEngine)
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
    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda symbol=None: [])
    monkeypatch.setattr(engine, "passes_liquidity_filter", lambda data, cfg: True)
    class FakeStrategyEngine:
        def __init__(self, config):
            pass
        def evaluate_at(self, data, code='', name='', market_data=None):
            result = engine.CupHandleResult(found=False, code=code, name=name)
            return type('Eval', (), {'result': result, 'dry_stable': None})()
    monkeypatch.setattr(engine, "CupHandleStrategyEngine", FakeStrategyEngine)
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
    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda symbol=None: [])
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


# ---- re_evaluate_task ----

def test_re_evaluate_finds_candidates_on_existing_data(monkeypatch, tmp_path):
    """Should find cup-handle candidates from DB-stored OHLC without re-fetching."""
    db_path = tmp_path / "cuphandle.db"
    config = {
        "data": {"database_path": str(db_path), "scan_window_days": 50},
        "liquidity": {"enabled": False, "min_listing_days": 260},
        "scoring": {"medium_threshold": 70},
    }
    db.init_db(str(db_path))
    db.create_scan_task("task-1", "2026-01-01 09:00:00", total_stocks=2)
    db.save_task_stocks("task-1", [
        {"code": "600000", "name": "TestA", "market": "SSE"},
        {"code": "000001", "name": "TestB", "market": "SZ"},
    ])
    # Store OHLC with a cup-handle pattern
    db.save_ohlc("600000", _rows(260, close=20.0))
    db.save_ohlc("000001", _rows(50, close=5.0))

    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda symbol=None: [])

    class FakeEngine:
        def __init__(self, config): pass
        def evaluate_at(self, data, code="", name="", market_data=None):
            r = engine.CupHandleResult(found=True, code=code, name=name, score=75)
            dry = {
                "decision": {"verdict": "突破确认", "verdict_key": "WATCH_BREAKOUT", "summary": "ok"},
                "volume_dry": {"score": 7}, "price_stable": {"score": 7},
                "pattern_score": {"score": 15, "type": "杯柄", "key_pattern_type": "cup_handle"},
                "risk_reward": {"risk_percent": 5, "rr1": 2.0, "position_advice": "20%"},
                "key_prices": {"entry_zone_low": 19, "entry_zone_high": 21, "pivot": 22,
                               "stop_loss": 18, "target_1": 25, "target_2": 28},
                "market_environment": {"status": "一般", "position_advice": "轻仓"},
            }
            return type("Eval", (), {"result": r, "dry_stable": dry, "passed": True})()

    monkeypatch.setattr(engine, "CupHandleStrategyEngine", FakeEngine)
    # Make passes_liquidity_filter always return True
    monkeypatch.setattr(engine, "passes_liquidity_filter", lambda data, cfg: True)

    result = engine.re_evaluate_task(config, "task-1")

    assert result["status"] == "completed"
    assert result["candidates_found"] == 2
    assert result["total_stocks"] == 2
    # Verify candidates persisted
    cands = db.get_candidates(task_id="task-1")
    assert len(cands) == 2


def test_re_evaluate_replaces_old_candidates(monkeypatch, tmp_path):
    """Old candidates should be removed, new ones take their place."""
    db_path = tmp_path / "cuphandle.db"
    config = {
        "data": {"database_path": str(db_path), "scan_window_days": 50},
        "liquidity": {"enabled": False, "min_listing_days": 260},
        "scoring": {"medium_threshold": 70},
    }
    db.init_db(str(db_path))
    db.create_scan_task("task-1", "2026-01-01 09:00:00", total_stocks=1)
    db.save_task_stocks("task-1", [{"code": "600000", "name": "TestA", "market": "SSE"}])
    db.save_ohlc("600000", _rows(260, close=20.0))

    # Pre-populate an old candidate (via upsert)
    db.upsert_candidate("task-1", {"code": "600000", "name": "TestA", "score": 60})
    assert len(db.get_candidates(task_id="task-1")) == 1

    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda symbol=None: [])
    monkeypatch.setattr(engine, "passes_liquidity_filter", lambda data, cfg: True)

    class FakeEngine:
        def __init__(self, config): pass
        def evaluate_at(self, data, code="", name="", market_data=None):
            r = engine.CupHandleResult(found=True, code=code, name=name, score=80)
            dry = {
                "decision": {"verdict": "可低吸", "verdict_key": "BUY_LOW", "summary": "good"},
                "volume_dry": {"score": 8}, "price_stable": {"score": 8},
                "pattern_score": {"score": 17, "type": "杯柄", "key_pattern_type": "cup_handle"},
                "risk_reward": {"risk_percent": 4, "rr1": 2.5, "position_advice": "30%"},
                "key_prices": {"entry_zone_low": 19, "entry_zone_high": 20, "pivot": 21,
                               "stop_loss": 18, "target_1": 25, "target_2": 30},
                "market_environment": {"status": "良好", "position_advice": "正常"},
            }
            return type("Eval", (), {"result": r, "dry_stable": dry, "passed": True})()

    monkeypatch.setattr(engine, "CupHandleStrategyEngine", FakeEngine)

    result = engine.re_evaluate_task(config, "task-1")
    assert result["candidates_found"] == 1
    # Old score-60 candidate replaced by new score-80
    cands = db.get_candidates(task_id="task-1")
    assert len(cands) == 1
    assert cands[0]["score"] == 80


def test_re_evaluate_handles_no_ohlc_gracefully(monkeypatch, tmp_path):
    """Tasks with stocks that have no OHLC data should not crash."""
    db_path = tmp_path / "cuphandle.db"
    config = {"data": {"database_path": str(db_path)}}
    db.init_db(str(db_path))
    db.create_scan_task("task-1", "2026-01-01 09:00:00", total_stocks=1)
    db.save_task_stocks("task-1", [{"code": "999999", "name": "Ghost", "market": "SSE"}])

    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda symbol=None: [])

    result = engine.re_evaluate_task(config, "task-1")
    assert result["status"] == "completed"
    assert result["candidates_found"] == 0


def test_re_evaluate_returns_no_stocks_for_unknown_task(monkeypatch, tmp_path):
    """Unknown task_id should return no_stocks status."""
    db_path = tmp_path / "cuphandle.db"
    config = {"data": {"database_path": str(db_path)}}
    db.init_db(str(db_path))

    result = engine.re_evaluate_task(config, "nonexistent")
    assert result["status"] == "no_stocks"
    assert result["candidates_found"] == 0
