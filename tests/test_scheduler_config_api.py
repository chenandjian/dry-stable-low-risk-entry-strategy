import server
import builtins
import yaml
from fastapi.testclient import TestClient
from pathlib import Path


def _valid_config() -> dict:
    return {
        "market": {},
        "data": {
            "database_path": "data/cuphandle.db",
            "scan_window_days": 250,
            "backtest_window_days": 250,
            "daily_sources": ["sina"],
        },
        "liquidity": {"min_listing_days": 500},
        "cup": {},
        "handle": {},
        "breakout": {},
        "decision": {},
        "strategy2": {"enabled": False},
        "scheduler": {
            "enabled": False,
            "serial_dual_scan": {
                "enabled": True,
                "cron": "15 15 * * 1-5",
                "strategy1_failed_retry_rounds": 3,
            },
        },
    }


def test_update_config_rejects_invalid_scheduler_cron(monkeypatch, tmp_path):
    cfg = _valid_config()
    writes = []
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": cfg.copy())
    monkeypatch.setattr(server.yaml, "dump", lambda *args, **kwargs: writes.append(args))

    res = TestClient(server.app).put(
        "/api/config",
        json={"scheduler": {"enabled": True, "serial_dual_scan": {"enabled": True, "cron": "bad cron"}}},
    )

    assert res.status_code == 400
    body = res.json()
    assert body["status"] == "error"
    assert "scheduler" in body["message"]
    assert writes == []


def test_update_config_rejects_invalid_scheduler_shape(monkeypatch):
    cfg = _valid_config()
    writes = []
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": cfg.copy())
    monkeypatch.setattr(server.yaml, "dump", lambda *args, **kwargs: writes.append(args))

    res = TestClient(server.app).put("/api/config", json={"scheduler": {"serial_dual_scan": False}})

    assert res.status_code == 400
    assert res.json()["status"] == "error"
    assert "serial_dual_scan" in res.json()["message"]
    assert writes == []


def test_update_config_accepts_weekday_serial_scan_time(monkeypatch, tmp_path):
    cfg = _valid_config()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(cfg, allow_unicode=True), encoding="utf-8")
    written = {}
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": cfg.copy())
    original_open = builtins.open

    def fake_open(file, *args, **kwargs):
        if file == "config.yaml":
            return original_open(config_path, *args, **kwargs)
        return original_open(file, *args, **kwargs)

    def fake_dump(config, file_obj, **kwargs):
        written.update(config)
        return yaml.safe_dump(config, file_obj, allow_unicode=True)

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(server.yaml, "dump", fake_dump)

    res = TestClient(server.app).put(
        "/api/config",
        json={"scheduler": {"enabled": True, "serial_dual_scan": {"enabled": True, "cron": "30 14 * * 1-5"}}},
    )

    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert written["scheduler"]["enabled"] is True
    assert written["scheduler"]["serial_dual_scan"]["cron"] == "30 14 * * 1-5"
    assert yaml.safe_load(config_path.read_text(encoding="utf-8"))["scheduler"]["serial_dual_scan"]["cron"] == "30 14 * * 1-5"


def test_update_config_reloads_scheduler_when_scheduler_changes(monkeypatch, tmp_path):
    cfg = _valid_config()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(cfg, allow_unicode=True), encoding="utf-8")
    reloaded = []
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": cfg.copy())
    monkeypatch.setattr(server, "_reload_scheduler_from_config", lambda config: reloaded.append(config.copy()))
    original_open = builtins.open

    def fake_open(file, *args, **kwargs):
        if file == "config.yaml":
            return original_open(config_path, *args, **kwargs)
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    res = TestClient(server.app).put(
        "/api/config",
        json={"scheduler": {"enabled": True, "serial_dual_scan": {"enabled": True, "cron": "50 15 * * 1-5"}}},
    )

    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert len(reloaded) == 1
    assert reloaded[0]["scheduler"]["enabled"] is True
    assert reloaded[0]["scheduler"]["serial_dual_scan"]["cron"] == "50 15 * * 1-5"


def test_update_config_reloads_scheduler_when_acquisition_mode_changes(monkeypatch, tmp_path):
    cfg = _valid_config()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(cfg, allow_unicode=True), encoding="utf-8")
    reloaded = []
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": cfg.copy())
    monkeypatch.setattr(server, "_reload_scheduler_from_config", lambda config: reloaded.append(config.copy()))
    original_open = builtins.open

    def fake_open(file, *args, **kwargs):
        if file == "config.yaml":
            return original_open(config_path, *args, **kwargs)
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    res = TestClient(server.app).put(
        "/api/config",
        json={"data": {"acquisition_mode": "tickflow"}},
    )

    assert res.status_code == 200
    assert res.json()["schedulerReloaded"] is True
    assert len(reloaded) == 1
    assert reloaded[0]["data"]["acquisition_mode"] == "tickflow"


def test_update_config_validates_strategy6_and_strips_legacy_sector_fields(monkeypatch, tmp_path):
    cfg = _valid_config()
    cfg["strategy6"] = {
        "enabled": True,
        "enable_sector_filter": True,
        "sector_filter_mode": "strict",
    }
    written = {}
    repository_config = Path("config.yaml")
    repository_config_before = repository_config.read_bytes()
    temporary_config = tmp_path / "config.yaml"
    original_open = builtins.open

    def fake_open(file, *args, **kwargs):
        if file == "config.yaml":
            return original_open(temporary_config, *args, **kwargs)
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": cfg.copy())
    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(server.yaml, "dump", lambda config, *args, **kwargs: written.update(config))

    response = TestClient(server.app).put(
        "/api/config",
        json={"strategy6": {
            "rr2_min_watch": 1.5,
            "rr2_min_key": 2.0,
            "rr2_min_ready": 2.5,
            "box_tail": {"normal_box_width_max": 0.16, "compact_kline": {"enabled": False}},
        }},
    )

    assert response.status_code == 200
    assert "enable_sector_filter" not in written["strategy6"]
    assert "sector_filter_mode" not in written["strategy6"]
    assert written["strategy6"]["pattern_filter_mode"] == "score_only"
    assert written["strategy6"]["box_tail"]["normal_box_width_max"] == 0.16
    assert written["strategy6"]["box_tail"]["min_box_days"] == 5
    assert written["strategy6"]["box_tail"]["compact_kline"]["enabled"] is False
    assert written["strategy6"]["box_tail"]["compact_kline"]["window_days"] == 5
    assert repository_config.read_bytes() == repository_config_before


def test_get_config_completes_legacy_strategy6_brooks_defaults(monkeypatch):
    cfg = _valid_config()
    cfg["custom_section"] = {"keep": "original"}
    cfg["strategy6"] = {"enabled": True, "rr2_min_watch": 1.7}
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": cfg)

    response = TestClient(server.app).get("/api/config")

    assert response.status_code == 200
    returned = response.json()["config"]
    assert returned["custom_section"] == {"keep": "original"}
    assert returned["strategy6"]["rr2_min_watch"] == 1.7
    assert returned["strategy6"]["brooks_tail"]["enabled"] is True
    assert returned["strategy6"]["brooks_tail"]["trade_trigger"]["breakout_follow_through_days"] == 2
    assert returned["strategy6"]["brooks_tail"]["scoring"]["pass_score_min"] == 14


def test_update_config_rejects_invalid_strategy6_threshold_order(monkeypatch, tmp_path):
    cfg = _valid_config()
    cfg["strategy6"] = {"enabled": True}
    writes = []
    repository_config = Path("config.yaml")
    repository_config_before = repository_config.read_bytes()
    temporary_config = tmp_path / "config.yaml"
    original_open = builtins.open

    def fake_open(file, *args, **kwargs):
        if file == "config.yaml":
            return original_open(temporary_config, *args, **kwargs)
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": cfg.copy())
    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(server.yaml, "dump", lambda *args, **kwargs: writes.append(args))

    response = TestClient(server.app).put(
        "/api/config",
        json={"strategy6": {"rr2_min_watch": 3.0, "rr2_min_key": 2.0, "rr2_min_ready": 2.5}},
    )

    assert response.status_code == 400
    assert "Invalid strategy6 config" in response.json()["message"]
    assert writes == []
    assert repository_config.read_bytes() == repository_config_before


def test_update_config_rejects_invalid_data_acquisition_mode(monkeypatch):
    cfg = _valid_config()
    writes = []
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": cfg.copy())
    monkeypatch.setattr(server.yaml, "dump", lambda *args, **kwargs: writes.append(args))

    res = TestClient(server.app).put(
        "/api/config",
        json={"data": {"acquisition_mode": "automatic_fallback"}},
    )

    assert res.status_code == 400
    assert "data.acquisition_mode" in res.json()["message"]
    assert writes == []


def test_scheduler_logs_include_runtime_state(monkeypatch):
    cfg = _valid_config()
    cfg["scheduler"]["enabled"] = True
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": cfg.copy())

    from scheduler import scheduler as sched_mod

    monkeypatch.setattr(
        sched_mod,
        "get_scheduler_status",
        lambda: {
            "running": True,
            "jobs": [
                {
                    "id": "serial_dual_strategy_scan",
                    "next_run_time": "2026-06-17 15:50:00",
                }
            ],
        },
    )

    res = TestClient(server.app).get("/api/scheduler/logs?limit=5")

    assert res.status_code == 200
    body = res.json()
    assert body["scheduler"]["enabled"] is True
    assert body["runtime"]["running"] is True
    assert body["runtime"]["jobs"][0]["id"] == "serial_dual_strategy_scan"
