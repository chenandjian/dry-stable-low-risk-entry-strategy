from scanner import db
from scanner import engine


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


def _row(day, close=10.0):
    return {"date": day, "open": close, "high": close, "low": close, "close": close, "volume": 10_000_000, "turnover": close * 10_000_000}


def test_fetch_with_retry_ignores_fresh_cache_when_source_succeeds(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("600000", [_row("2026-06-03", close=9.0)])
    calls = []

    def fake_sina(code):
        calls.append(code)
        return [_row("2026-06-04", close=10.0)]

    monkeypatch.setattr(engine, "fetch_sina_daily", fake_sina)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: None)
    result = engine._fetch_with_retry("600000", "sina", retry_attempts=2, fallback_attempts=2, sleep_fn=lambda _: None)

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
    result = engine._fetch_with_retry("600000", "sina", retry_attempts=2, fallback_attempts=2, sleep_fn=lambda _: None)

    assert result.data[-1]["date"] == "2026-06-04"
    assert result.primary_attempts == 2
    assert result.fallback_attempts == 1
    assert result.primary_error == "empty response"
    assert result.fallback_error is None


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
    )

    assert result.data[-1]["date"] == "2026-06-04"
    assert result.primary_attempts == 2
    assert result.fallback_attempts == 1
    assert result.fallback_error is None
    assert fallback_calls == ["600000"]
    assert mgr.acquire_calls == ["tencent"]
    assert mgr.release_calls == ["tencent"]


def test_fetch_with_retry_does_not_return_cache_when_sources_fail(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("600000", [_row("2026-06-03", close=9.0)])

    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: None)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: None)
    result = engine._fetch_with_retry("600000", "sina", retry_attempts=2, fallback_attempts=2, sleep_fn=lambda _: None)

    assert result.data is None
    assert result.primary_attempts == 2
    assert result.fallback_attempts == 2
    assert result.primary_error == "empty response"
    assert result.fallback_error == "empty response"
    assert result.from_cache is False
