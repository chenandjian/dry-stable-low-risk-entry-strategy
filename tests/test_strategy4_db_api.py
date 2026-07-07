import scanner.db as db
import server as server_mod
from fastapi.testclient import TestClient


STRATEGY4_TYPE = "STRATEGY_4_HOT_LEADER_SECOND_WAVE"


def test_strategy4_tables_roundtrip_and_do_not_leak_into_other_candidate_tables(tmp_path):
    db.init_db(str(tmp_path / "test.db"))
    db.create_scan_task("s4-task", "2026-07-01 15:30:00", strategy_type=STRATEGY4_TYPE)

    db.replace_strategy4_hot_topics("s4-task", [{
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "topic_type": "concept",
        "source": "akshare_ths",
        "snapshot_time": "2026-07-01 15:30:00",
        "status": "CONFIRMED_HOT",
        "hot_topic_score": 92,
        "price_strength_score": 30,
        "amount_strength_score": 18,
        "fund_flow_score": 14,
        "breadth_score": 13,
        "leader_limit_score": 9,
        "breakout_score": 8,
        "signal_count": 5,
        "noise_reason": "",
        "leading_stock_code": "300750",
        "leading_stock_name": "宁德时代",
        "raw_snapshot": {"source_rank": 1},
    }])
    db.replace_strategy4_leaders("s4-task", [{
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "code": "300750",
        "name": "宁德时代",
        "leader_type": "SPACE_LEADER",
        "leader_strength_score": 95,
        "tradability_score": 65,
        "price_limit_rule": "PRICE_LIMIT_20CM",
        "limit_shape": "ONE_WORD_LIMIT_UP",
        "limit_pct": 0.20,
        "return_1d": 0.20,
        "return_5d": 0.42,
        "return_10d": 0.55,
        "return_20d": 0.80,
        "amount_1d": 500_000_000,
        "avg_amount_5d": 800_000_000,
        "avg_amount_10d": 700_000_000,
        "first_wave_max_amount": 1_500_000_000,
        "last_non_limit_amount": 1_200_000_000,
        "consecutive_limit_count": 2,
        "relative_strength_vs_topic": 0.08,
        "membership_source": "akshare_partial",
        "status": "LOCKED_LEADER_WATCH",
        "raw_snapshot": {"rank": 1},
    }])
    db.upsert_strategy4_candidate("s4-task", {
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "code": "300750",
        "name": "宁德时代",
        "evaluation_date": "2026-07-01",
        "status": "BUYABLE_SECOND_WAVE",
        "strategy4_score": 91,
        "hot_topic_score": 92,
        "leader_strength_score": 95,
        "tradability_score": 72,
        "first_wave_score": 20,
        "pullback_score": 20,
        "second_wave_score": 20,
        "reward_risk_score": 15,
        "leader_type": "SPACE_LEADER",
        "price_limit_rule": "PRICE_LIMIT_20CM",
        "limit_shape": "LIMIT_UP_CLOSE",
        "first_wave_return": 0.55,
        "pullback_pct": 0.12,
        "pullback_days": 4,
        "current_close": 16.4,
        "support_price": 15.2,
        "stop_loss": 14.9,
        "target_price": 20.0,
        "risk_ratio": 0.09,
        "reward_risk_ratio": 2.4,
        "entry_note": "二波启动",
        "reject_reason": "",
        "evaluation_snapshot": {"signals": ["close_above_ma5"]},
    })

    topics = db.get_strategy4_hot_topics("s4-task")
    leaders = db.get_strategy4_leaders("s4-task")
    candidates = db.get_strategy4_candidates("s4-task")
    detail = db.get_strategy4_candidate("300750", task_id="s4-task")

    assert topics[0]["topic_name"] == "AI算力"
    assert topics[0]["raw_snapshot"] == {"source_rank": 1}
    assert leaders[0]["status"] == "LOCKED_LEADER_WATCH"
    assert leaders[0]["raw_snapshot"] == {"rank": 1}
    assert candidates[0]["code"] == "300750"
    assert candidates[0]["evaluation_snapshot"] == {"signals": ["close_above_ma5"]}
    assert detail["reward_risk_ratio"] == 2.4
    assert db.get_candidates(task_id="s4-task") == []
    assert db.get_strategy2_candidates(task_id="s4-task") == []
    assert db.get_strategy3_candidates(task_id="s4-task") == []


def test_strategy4_apis_return_snapshots_and_reject_cross_strategy_tasks(tmp_path, monkeypatch):
    db.init_db(str(tmp_path / "test.db"))
    monkeypatch.setattr(server_mod, "load_config", lambda: {"data": {"database_path": str(tmp_path / "test.db")}, "strategy4": {}})
    server_mod._running.update({"running": False, "task_id": None, "strategy_type": None, "stats": {}})

    db.create_scan_task("s1-task", "2026-07-01 15:20:00", strategy_type="STRATEGY_1_CUP_HANDLE")
    db.create_scan_task("s4-existing", "2026-07-01 15:30:00", strategy_type=STRATEGY4_TYPE)
    db.replace_strategy4_hot_topics("s4-existing", [{
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "topic_type": "concept",
        "source": "akshare_ths",
        "snapshot_time": "2026-07-01 15:30:00",
        "status": "CONFIRMED_HOT",
        "hot_topic_score": 92,
    }])
    db.replace_strategy4_leaders("s4-existing", [{
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "code": "300750",
        "name": "宁德时代",
        "leader_type": "SPACE_LEADER",
        "leader_strength_score": 95,
        "tradability_score": 65,
        "status": "LOCKED_LEADER_WATCH",
    }])
    db.upsert_strategy4_candidate("s4-existing", {
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "code": "300750",
        "name": "宁德时代",
        "evaluation_date": "2026-07-01",
        "status": "BUYABLE_SECOND_WAVE",
        "strategy4_score": 91,
        "hot_topic_score": 92,
        "leader_strength_score": 95,
        "tradability_score": 72,
    })

    client = TestClient(server_mod.app)
    assert client.get("/api/strategy4/tasks/s4-existing/topics").json()["topics"][0]["topic_name"] == "AI算力"
    assert client.get("/api/strategy4/tasks/s4-existing/leaders").json()["leaders"][0]["code"] == "300750"
    assert client.get("/api/strategy4/tasks/s4-existing/candidates").json()["candidates"][0]["status"] == "BUYABLE_SECOND_WAVE"
    assert client.get("/api/strategy4/tasks/s4-existing/candidates/300750").json()["candidate"]["code"] == "300750"

    mismatch = client.get("/api/strategy4/tasks/s1-task/candidates")
    assert mismatch.status_code == 400
    assert mismatch.json()["error"] == "TASK_STRATEGY_MISMATCH"


def test_strategy4_tracking_apis_return_pool_and_task_tracking_candidates(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    monkeypatch.setattr(server_mod, "load_config", lambda: {"data": {"database_path": db_path}, "strategy4": {}})
    server_mod._running.update({"running": False, "task_id": None, "strategy_type": None, "stats": {}})

    db.create_scan_task("s4-track", "2026-07-01 15:30:00", strategy_type=STRATEGY4_TYPE)
    db.upsert_strategy4_tracked_topic({
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "topic_type": "concept",
        "first_detected_date": "2026-06-01",
        "last_confirmed_date": "2026-06-20",
        "last_evaluated_date": "2026-07-01",
        "age_calendar_days": 30,
        "tracking_status": "SECOND_WAVE_WATCH",
        "tracking_phase": "golden_second_wave",
        "latest_hot_score": 76,
    })
    db.upsert_strategy4_tracked_leader({
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "code": "300750",
        "name": "宁德时代",
        "first_detected_date": "2026-06-01",
        "last_confirmed_date": "2026-06-20",
        "last_evaluated_date": "2026-07-01",
        "tracking_status": "SECOND_WAVE_READY",
        "tracking_phase": "golden_second_wave",
        "latest_leader_score": 72,
        "candidate_origin": "tracking_pool",
    })
    db.insert_strategy4_tracking_event({
        "evaluation_date": "2026-07-01",
        "task_id": "s4-track",
        "entity_type": "leader",
        "topic_id": "concept-ai",
        "code": "300750",
        "event_type": "CANDIDATE",
        "new_status": "SECOND_WAVE_READY",
    })
    db.upsert_strategy4_candidate("s4-track", {
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "code": "300750",
        "name": "宁德时代",
        "evaluation_date": "2026-07-01",
        "status": "BUYABLE_SECOND_WAVE",
        "strategy4_score": 88,
        "hot_topic_score": 76,
        "leader_strength_score": 72,
        "tradability_score": 80,
        "candidate_origin": "tracking_pool",
    })

    client = TestClient(server_mod.app)
    topics = client.get("/api/strategy4/tracking/topics").json()["topics"]
    leaders = client.get("/api/strategy4/tracking/leaders?status=SECOND_WAVE_READY").json()["leaders"]
    events = client.get("/api/strategy4/tracking/events?topic_id=concept-ai").json()["events"]
    tracking_candidates = client.get("/api/strategy4/tasks/s4-track/tracking-candidates").json()["candidates"]

    assert topics[0]["topic_id"] == "concept-ai"
    assert leaders[0]["code"] == "300750"
    assert events[0]["event_type"] == "CANDIDATE"
    assert tracking_candidates[0]["candidate_origin"] == "tracking_pool"


def test_start_strategy4_scan_uses_strategy4_type_and_persists_result(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    monkeypatch.setattr(server_mod, "load_config", lambda: {"data": {"database_path": db_path}, "strategy4": {}})
    server_mod._running.update({"running": False, "task_id": None, "strategy_type": None, "stats": {}})

    def fake_scan(config, progress_callback=None, task_id=None, **kwargs):
        db.replace_strategy4_hot_topics(task_id, [{
            "topic_id": "concept-ai",
            "topic_name": "AI算力",
            "topic_type": "concept",
            "source": "mock",
            "snapshot_time": "2026-07-01 15:30:00",
            "status": "CONFIRMED_HOT",
            "hot_topic_score": 90,
        }])
        db.replace_strategy4_leaders(task_id, [])
        return {
            "topics": [{"topic_id": "concept-ai"}],
            "leaders": [],
            "candidates": [],
            "stats": {"total": 1, "total_stocks": 1, "processed": 1, "scanned": 1, "failed": 0, "skipped": 0, "candidates_found": 0, "elapsed_seconds": 0.1},
            "task_id": task_id,
        }

    monkeypatch.setattr(server_mod, "scan_strategy4_all", fake_scan)
    class ImmediateThread:
        def __init__(self, target, daemon=False):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    monkeypatch.setattr(server_mod.threading, "Thread", ImmediateThread)

    res = TestClient(server_mod.app).post("/api/strategy4/scans")
    body = res.json()

    assert res.status_code == 200
    assert body["strategyType"] == STRATEGY4_TYPE
    assert db.get_task_strategy_type(body["taskId"]) == STRATEGY4_TYPE
    assert db.get_strategy4_hot_topics(body["taskId"])[0]["topic_name"] == "AI算力"


def test_strategy4_scan_resolves_leading_stock_code_from_local_stock_pool(tmp_path, monkeypatch):
    import types
    from strategy4.scanner import scan_strategy4_all

    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.save_stock_pool([{"code": "300750", "name": "宁德时代", "market": "SZ"}])
    fake_ak = types.SimpleNamespace()
    fake_ak.stock_board_concept_name_ths = lambda: _fake_frame([{
        "板块": "新能源车",
        "涨跌幅": 4.5,
        "总成交额": 1800000000,
        "净流入": 500000000,
        "上涨家数": 78,
        "下跌家数": 12,
        "领涨股票": "宁德时代",
    }])
    fake_ak.stock_board_industry_name_ths = lambda: _fake_frame([])
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    result = scan_strategy4_all(
        {"data": {"database_path": db_path}, "strategy4": {}},
        task_id="s4-name-resolve",
    )

    assert result["leaders"][0]["code"] == "300750"
    assert db.get_strategy4_leaders("s4-name-resolve")[0]["code"] == "300750"


def test_strategy4_default_scan_recalls_multiple_leaders_from_topic_members(tmp_path, monkeypatch):
    import types
    from strategy4.scanner import scan_strategy4_all

    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    fake_ak = types.SimpleNamespace()
    fake_ak.stock_board_concept_name_ths = lambda: _fake_frame([{
        "板块": "AI算力",
        "涨跌幅": 5.0,
        "3日涨幅": 10.0,
        "5日涨幅": 16.0,
        "量比": 1.8,
        "净流入": 600000000,
        "上涨家数": 80,
        "下跌家数": 10,
        "涨停家数": 2,
    }])
    fake_ak.stock_board_industry_name_ths = lambda: _fake_frame([])
    fake_ak.stock_board_concept_cons_ths = lambda symbol: _fake_frame([
        {"代码": "300750", "名称": "宁德时代", "涨跌幅": 20.0, "成交额": 2000000000},
        {"代码": "688981", "名称": "中芯国际", "涨跌幅": 12.0, "成交额": 1500000000},
    ])
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    result = scan_strategy4_all(
        {"data": {"database_path": db_path}, "strategy4": {"max_total_leaders_per_topic": 2, "core_leaders_per_topic": 1, "backup_leaders_per_topic": 1}},
        task_id="s4-members",
    )
    cached_members = db.get_strategy4_topic_members("concept:AI算力", evaluation_date="2026-07-01")

    assert [l["code"] for l in result["leaders"]] == ["300750", "688981"]
    assert len(db.get_strategy4_leaders("s4-members")) == 2
    assert [m["code"] for m in cached_members] == ["300750", "688981"]
    assert cached_members[0]["membership_mode"] == "current_members_proxy"


def test_strategy4_scan_does_not_create_candidates_from_noise_topics(tmp_path, monkeypatch):
    import types
    from strategy4.scanner import scan_strategy4_all

    db_path = str(tmp_path / "test.db")
    task_id = "s4-noise-topic"
    db.init_db(db_path)
    db.create_scan_task(task_id, "2026-07-01 15:30:00", strategy_type=STRATEGY4_TYPE)
    db.save_ohlc("300750", _bars_for_buyable_second_wave())
    fake_ak = types.SimpleNamespace()
    fake_ak.stock_board_concept_name_ths = lambda: _fake_frame([{
        "板块": "伪热点",
        "涨跌幅": 0,
        "3日涨幅": 0,
        "5日涨幅": 0,
        "量比": 0.5,
        "净流入": 0,
        "上涨家数": 1,
        "下跌家数": 80,
    }])
    fake_ak.stock_board_industry_name_ths = lambda: _fake_frame([])
    fake_ak.stock_board_concept_cons_ths = lambda symbol: _fake_frame([
        {"代码": "300750", "名称": "宁德时代", "涨跌幅": 20.0, "成交额": 2000000000},
    ])
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    result = scan_strategy4_all(
        {"data": {"database_path": db_path}, "strategy4": {}},
        task_id=task_id,
    )

    assert result["topics"][0]["status"] == "NOISE_TOPIC"
    assert result["candidates"] == []
    assert db.get_strategy4_candidates(task_id) == []


def test_strategy4_scan_requires_confirmed_leader_before_candidate(tmp_path, monkeypatch):
    import types
    from strategy4.scanner import scan_strategy4_all

    db_path = str(tmp_path / "test.db")
    task_id = "s4-weak-leader"
    db.init_db(db_path)
    db.create_scan_task(task_id, "2026-07-01 15:30:00", strategy_type=STRATEGY4_TYPE)
    db.save_ohlc("300750", _bars_for_buyable_second_wave())
    fake_ak = types.SimpleNamespace()
    fake_ak.stock_board_concept_name_ths = lambda: _fake_frame([{
        "板块": "AI算力",
        "涨跌幅": 5.0,
        "3日涨幅": 10.0,
        "5日涨幅": 16.0,
        "量比": 1.8,
        "净流入": 600000000,
        "上涨家数": 80,
        "下跌家数": 10,
        "涨停家数": 2,
    }])
    fake_ak.stock_board_industry_name_ths = lambda: _fake_frame([])
    fake_ak.stock_board_concept_cons_ths = lambda symbol: _fake_frame([
        {"代码": "300750", "名称": "宁德时代", "涨跌幅": 20.0, "成交额": 2000000000},
    ])
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    result = scan_strategy4_all(
        {"data": {"database_path": db_path}, "strategy4": {"min_leader_strength_score": 88}},
        task_id=task_id,
    )

    assert result["leaders"][0]["leader_strength_score"] < 88
    assert result["candidates"] == []
    assert db.get_strategy4_candidates(task_id) == []


def test_strategy4_scan_tracks_failed_daily_fetch_in_task_stocks(tmp_path, monkeypatch):
    import types
    from scanner.daily_data_service import FetchResult
    from strategy4.scanner import scan_strategy4_all

    db_path = str(tmp_path / "test.db")
    task_id = "s4-daily-failed"
    db.init_db(db_path)
    db.create_scan_task(task_id, "2026-07-01 15:30:00", strategy_type=STRATEGY4_TYPE)
    fake_ak = types.SimpleNamespace()
    fake_ak.stock_board_concept_name_ths = lambda: _fake_frame([{
        "板块": "AI算力",
        "涨跌幅": 5.0,
        "3日涨幅": 10.0,
        "5日涨幅": 16.0,
        "量比": 1.8,
        "净流入": 600000000,
        "上涨家数": 80,
        "下跌家数": 10,
        "涨停家数": 2,
    }])
    fake_ak.stock_board_industry_name_ths = lambda: _fake_frame([])
    fake_ak.stock_board_concept_cons_ths = lambda symbol: _fake_frame([
        {"代码": "300750", "名称": "宁德时代", "涨跌幅": 20.0, "成交额": 2000000000},
    ])
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    result = scan_strategy4_all(
        {"data": {"database_path": db_path}, "strategy4": {}},
        task_id=task_id,
        fetch_daily_fn=lambda *args, **kwargs: FetchResult(
            data=None,
            primary_source="baidu",
            fallback_source="tencent",
            source_errors={"baidu": "empty response", "sina": "empty response", "tencent": "empty response"},
        ),
    )
    summary = db.refresh_scan_task_counts(task_id)
    failed = db.get_task_stocks(task_id, status="failed", limit=10)

    assert result["stats"]["failed"] == 1
    assert summary["failed"] == 1
    assert failed[0]["code"] == "300750"
    assert failed[0]["status_reason"] == "策略4龙头日线数据拉取失败"


def test_strategy4_scan_classifies_limit_shape_from_real_ohlc(tmp_path, monkeypatch):
    import types
    from strategy4.scanner import scan_strategy4_all

    db_path = str(tmp_path / "test.db")
    task_id = "s4-limit-shape"
    db.init_db(db_path)
    db.create_scan_task(task_id, "2026-07-01 15:30:00", strategy_type=STRATEGY4_TYPE)
    bars = _bars_for_buyable_second_wave()
    bars[-2]["close"] = 10.00
    bars[-1].update({"open": 10.80, "high": 12.00, "low": 10.60, "close": 12.00})
    db.save_ohlc("300750", bars)
    fake_ak = types.SimpleNamespace()
    fake_ak.stock_board_concept_name_ths = lambda: _fake_frame([{
        "板块": "AI算力",
        "涨跌幅": 5.0,
        "3日涨幅": 10.0,
        "5日涨幅": 16.0,
        "量比": 1.8,
        "净流入": 600000000,
        "上涨家数": 80,
        "下跌家数": 10,
        "涨停家数": 2,
    }])
    fake_ak.stock_board_industry_name_ths = lambda: _fake_frame([])
    fake_ak.stock_board_concept_cons_ths = lambda symbol: _fake_frame([
        {"代码": "300750", "名称": "宁德时代", "涨跌幅": 20.0, "成交额": 2000000000},
    ])
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    scan_strategy4_all(
        {"data": {"database_path": db_path}, "strategy4": {}},
        task_id=task_id,
    )

    assert db.get_strategy4_leaders(task_id)[0]["limit_shape"] == "LIMIT_UP_CLOSE"


def test_strategy4_scan_counts_survive_refresh_when_candidate_found(tmp_path, monkeypatch):
    import types
    from strategy4.scanner import scan_strategy4_all

    db_path = str(tmp_path / "test.db")
    task_id = "s4-counts"
    db.init_db(db_path)
    db.create_scan_task(task_id, "2026-07-01 15:30:00", strategy_type=STRATEGY4_TYPE)
    db.save_ohlc("300750", _bars_for_buyable_second_wave())
    fake_ak = types.SimpleNamespace()
    fake_ak.stock_board_concept_name_ths = lambda: _fake_frame([{
        "板块": "AI算力",
        "涨跌幅": 5.0,
        "3日涨幅": 10.0,
        "5日涨幅": 16.0,
        "量比": 1.8,
        "净流入": 600000000,
        "上涨家数": 80,
        "下跌家数": 10,
        "涨停家数": 2,
    }])
    fake_ak.stock_board_concept_index_ths = lambda symbol, start_date, end_date: _fake_frame(_topic_index_rows())
    fake_ak.stock_board_industry_name_ths = lambda: _fake_frame([])
    fake_ak.stock_board_concept_cons_ths = lambda symbol: _fake_frame([
        {"代码": "300750", "名称": "宁德时代", "涨跌幅": 20.0, "成交额": 2000000000},
    ])
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    result = scan_strategy4_all(
        {
            "data": {"database_path": db_path},
            "strategy4": {"min_leader_strength_score": 60, "topic_index": {"min_required_rows": 20}},
        },
        task_id=task_id,
    )
    summary = db.refresh_scan_task_counts(task_id)

    assert result["stats"]["candidates_found"] == 1
    assert summary["total_stocks"] == 1
    assert summary["candidate"] == 1
    assert summary["candidates_count"] == 1


def test_strategy4_scan_can_use_historical_kline_derived_source_without_live_external(tmp_path):
    from strategy4.scanner import scan_strategy4_all

    db_path = str(tmp_path / "test.db")
    task_id = "s4-derived-scan"
    db.init_db(db_path)
    db.create_scan_task(task_id, "2026-06-20 15:30:00", strategy_type=STRATEGY4_TYPE)
    db.save_strategy4_topic_index_ohlc(
        topic_id="concept:AI算力",
        topic_name="AI算力",
        topic_type="concept",
        source="fixture",
        rows=_derived_topic_rows(),
    )
    db.save_strategy4_topic_members(
        topic_id="concept:AI算力",
        topic_name="AI算力",
        topic_type="concept",
        source="fixture",
        membership_snapshot_date="2026-07-02",
        membership_mode="current_members_proxy",
        members=[{"code": "300750", "name": "宁德时代"}],
    )
    db.save_ohlc("300750", _bars_for_buyable_second_wave())

    result = scan_strategy4_all(
        {
            "data": {"database_path": db_path},
            "strategy4": {
                "source_modes": {"live_external_enabled": False},
                "min_hot_topic_score": 40,
                "min_hot_topic_signal_count": 1,
                "min_leader_strength_score": 40,
                "topic_index": {"min_required_rows": 20, "history_days": 60},
                "derived_source": {
                    "topic_top_n": 5,
                    "max_topics_per_day": 5,
                    "max_leaders_per_topic": 3,
                    "min_topic_index_rows": 20,
                    "min_member_count": 1,
                    "min_topic_hot_score": 40,
                    "min_confirmed_topic_hot_score": 40,
                    "min_breadth_ratio": 0.0,
                },
            },
        },
        task_id=task_id,
    )

    assert result["topics"][0]["snapshot_source"] == "historical_kline_derived"
    assert result["topics"][0]["source_modes"] == ["historical_kline_derived"]
    assert result["leaders"][0]["membership_mode"] == "current_members_proxy"
    assert result["leaders"][0]["source_modes"] == ["historical_kline_derived"]
    assert db.get_strategy4_hot_topics(task_id)[0]["source_modes"] == ["historical_kline_derived"]


def test_strategy4_scan_persists_topic_index_context_and_relative_strength(tmp_path, monkeypatch):
    import types
    from strategy4.scanner import scan_strategy4_all

    db_path = str(tmp_path / "test.db")
    task_id = "s4-topic-index-observed"
    db.init_db(db_path)
    db.create_scan_task(task_id, "2026-07-01 15:30:00", strategy_type=STRATEGY4_TYPE)
    db.save_ohlc("300750", _bars_for_buyable_second_wave())
    fake_ak = types.SimpleNamespace()
    fake_ak.stock_board_concept_name_ths = lambda: _fake_frame([{
        "板块": "AI算力",
        "涨跌幅": 5.0,
        "3日涨幅": 10.0,
        "5日涨幅": 16.0,
        "量比": 1.8,
        "净流入": 600000000,
        "上涨家数": 80,
        "下跌家数": 10,
        "涨停家数": 2,
    }])
    fake_ak.stock_board_industry_name_ths = lambda: _fake_frame([])
    fake_ak.stock_board_concept_index_ths = lambda symbol, start_date, end_date: _fake_frame(_topic_index_rows())
    fake_ak.stock_board_concept_cons_ths = lambda symbol: _fake_frame([
        {"代码": "300750", "名称": "宁德时代", "涨跌幅": 20.0, "成交额": 2000000000},
    ])
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    result = scan_strategy4_all(
        {
            "data": {"database_path": db_path},
            "strategy4": {"min_leader_strength_score": 60, "topic_index": {"min_required_rows": 20}},
        },
        task_id=task_id,
    )

    topic = result["topics"][0]
    leader = result["leaders"][0]
    saved_rows = db.get_strategy4_topic_index_ohlc("concept:AI算力")

    assert topic["topic_index_observed"] is True
    assert topic["topic_index_latest_date"] == "2099-01-20"
    assert topic["topic_index_phase"] in {"EARLY_ACCELERATION", "MAIN_TREND"}
    assert saved_rows[-1]["date"] == "2099-01-20"
    assert leader["raw_snapshot"]["topic_return_10d"] > 0
    assert "leader_rs_10d" in leader["raw_snapshot"]


def test_strategy4_scan_respects_topic_index_allowed_phases_for_candidates(tmp_path, monkeypatch):
    import types
    from strategy4.scanner import scan_strategy4_all

    db_path = str(tmp_path / "test.db")
    task_id = "s4-topic-index-phase-filter"
    db.init_db(db_path)
    db.create_scan_task(task_id, "2026-07-01 15:30:00", strategy_type=STRATEGY4_TYPE)
    db.save_ohlc("300750", _bars_for_buyable_second_wave())
    fake_ak = types.SimpleNamespace()
    fake_ak.stock_board_concept_name_ths = lambda: _fake_frame([{
        "板块": "AI算力",
        "涨跌幅": 5.0,
        "3日涨幅": 10.0,
        "5日涨幅": 16.0,
        "量比": 1.8,
        "净流入": 600000000,
        "上涨家数": 80,
        "下跌家数": 10,
        "涨停家数": 2,
    }])
    fake_ak.stock_board_industry_name_ths = lambda: _fake_frame([])
    fake_ak.stock_board_concept_index_ths = lambda symbol, start_date, end_date: _fake_frame(_topic_index_rows())
    fake_ak.stock_board_concept_cons_ths = lambda symbol: _fake_frame([
        {"代码": "300750", "名称": "宁德时代", "涨跌幅": 20.0, "成交额": 2000000000},
    ])
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    result = scan_strategy4_all(
        {
            "data": {"database_path": db_path},
            "strategy4": {
                "min_leader_strength_score": 60,
                "topic_index": {"min_required_rows": 20},
                "topic_index_filters": {"allowed_phases": ["PULLBACK_REPAIR"]},
            },
        },
        task_id=task_id,
    )

    assert result["topics"][0]["topic_index_phase"] in {"EARLY_ACCELERATION", "MAIN_TREND"}
    assert result["candidates"] == []
    assert db.get_strategy4_candidates(task_id) == []


def test_strategy4_scan_blocks_buyable_candidate_when_topic_index_unobserved(tmp_path, monkeypatch):
    import types
    from strategy4.scanner import scan_strategy4_all

    db_path = str(tmp_path / "test.db")
    task_id = "s4-topic-index-unobserved"
    db.init_db(db_path)
    db.create_scan_task(task_id, "2026-07-01 15:30:00", strategy_type=STRATEGY4_TYPE)
    db.save_ohlc("300750", _bars_for_buyable_second_wave())
    fake_ak = types.SimpleNamespace()
    fake_ak.stock_board_concept_name_ths = lambda: _fake_frame([{
        "板块": "AI算力",
        "涨跌幅": 5.0,
        "3日涨幅": 10.0,
        "5日涨幅": 16.0,
        "量比": 1.8,
        "净流入": 600000000,
        "上涨家数": 80,
        "下跌家数": 10,
        "涨停家数": 2,
    }])
    fake_ak.stock_board_industry_name_ths = lambda: _fake_frame([])
    fake_ak.stock_board_concept_index_ths = lambda symbol, start_date, end_date: (_ for _ in ()).throw(RuntimeError("source down"))
    fake_ak.stock_board_concept_cons_ths = lambda symbol: _fake_frame([
        {"代码": "300750", "名称": "宁德时代", "涨跌幅": 20.0, "成交额": 2000000000},
    ])
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    result = scan_strategy4_all(
        {
            "data": {"database_path": db_path},
            "strategy4": {"min_leader_strength_score": 60, "topic_index": {"min_required_rows": 20}},
        },
        task_id=task_id,
    )

    assert result["topics"][0]["topic_index_observed"] is False
    assert result["topics"][0]["topic_index_status"] != "observed"
    assert result["candidates"] == []
    assert db.get_strategy4_candidates(task_id) == []


def test_start_strategy4_scan_returns_started_without_running_scan_synchronously(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    monkeypatch.setattr(server_mod, "load_config", lambda: {"data": {"database_path": db_path}, "strategy4": {}})
    server_mod._running.update({"running": False, "task_id": None, "strategy_type": None, "stats": {}})
    called = {"scan": False, "thread_started": False}

    def fake_scan(*args, **kwargs):
        called["scan"] = True
        return {"topics": [], "leaders": [], "candidates": [], "stats": {}}

    class FakeThread:
        def __init__(self, target, daemon=False):
            self.target = target
            self.daemon = daemon

        def start(self):
            called["thread_started"] = True

    monkeypatch.setattr(server_mod, "scan_strategy4_all", fake_scan)
    monkeypatch.setattr(server_mod.threading, "Thread", FakeThread)

    res = TestClient(server_mod.app).post("/api/strategy4/scans")
    body = res.json()

    assert res.status_code == 200
    assert body["status"] == "started"
    assert body["strategyType"] == STRATEGY4_TYPE
    assert called["thread_started"] is True
    assert called["scan"] is False
    server_mod._clear_running()


class _fake_frame:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return list(self._rows)


def _bars_for_buyable_second_wave():
    closes = [
        10.0, 10.2, 10.4, 10.6, 10.8,
        11.2, 12.4, 13.8, 15.2, 17.0,
        16.5, 15.8, 15.3, 15.2, 15.6,
        15.9, 16.1, 16.0, 16.2, 16.4,
    ]
    rows = []
    for idx, close in enumerate(closes):
        previous = closes[idx - 1] if idx else close
        open_ = previous * 0.995
        rows.append({
            "date": f"2026-06-{idx + 1:02d}",
            "open": round(open_, 2),
            "high": round(max(open_, close) * 1.02, 2),
            "low": round(min(open_, close) * 0.98, 2),
            "close": round(close, 2),
            "volume": 6_000_000 if idx < 10 else 3_000_000,
            "turnover": close * (6_000_000 if idx < 10 else 3_000_000),
        })
    rows[-1]["volume"] = 4_000_000
    rows[-1]["open"] = 15.9
    rows[-1]["low"] = 15.6
    rows[-1]["high"] = 16.6
    rows[9]["high"] = 24.0
    for row in rows[10:]:
        row["low"] = max(row["low"], 15.1)
    return rows


def _topic_index_rows():
    rows = []
    for idx in range(20):
        close = 100 + idx * 0.5
        rows.append({
            "日期": f"2099-01-{idx + 1:02d}",
            "开盘价": round(close * 0.99, 2),
            "最高价": round(close * 1.02, 2),
            "最低价": round(close * 0.98, 2),
            "收盘价": round(close, 2),
            "成交额": 1_000_000_000 + idx * 50_000_000,
            "涨跌幅": 0.5,
        })
    return rows


def _derived_topic_rows():
    rows = []
    for idx in range(20):
        close = 100 + idx * 0.8
        rows.append({
            "date": f"2026-06-{idx + 1:02d}",
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "amount": 1_000_000_000 + idx * 30_000_000,
        })
    return rows
