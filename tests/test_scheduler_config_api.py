import builtins
import copy

import pytest
import server
import yaml
from fastapi.testclient import TestClient
from pathlib import Path

from scanner.config_io import write_yaml_config_atomic


@pytest.fixture(autouse=True)
def _isolate_atomic_config_writes(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(
        server,
        "write_yaml_config_atomic",
        lambda config, path="config.yaml", **kwargs: write_yaml_config_atomic(config, config_path),
    )


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
    monkeypatch.setattr(
        server,
        "write_yaml_config_atomic",
        lambda *args, **kwargs: writes.append(args),
    )

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
    monkeypatch.setattr(server, "write_yaml_config_atomic", lambda *args, **kwargs: writes.append(args))

    res = TestClient(server.app).put("/api/config", json={"scheduler": {"serial_dual_scan": False}})

    assert res.status_code == 400
    assert res.json()["status"] == "error"
    assert "serial_dual_scan" in res.json()["message"]
    assert writes == []


def test_update_config_accepts_weekday_serial_scan_time(monkeypatch, tmp_path):
    cfg = _valid_config()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(cfg, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": cfg.copy())
    original_open = builtins.open

    def fake_open(file, *args, **kwargs):
        if file == "config.yaml":
            return original_open(config_path, *args, **kwargs)
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)

    res = TestClient(server.app).put(
        "/api/config",
        json={"scheduler": {"enabled": True, "serial_dual_scan": {"enabled": True, "cron": "30 14 * * 1-5"}}},
    )

    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
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
    written = yaml.safe_load(temporary_config.read_text(encoding="utf-8"))
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


def test_get_config_masks_tickflow_api_key_without_mutating_loaded_config(monkeypatch):
    cfg = _valid_config()
    cfg["data"]["tickflow_api_key"] = "secret-value"
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": cfg)

    response = TestClient(server.app).get("/api/config")

    assert response.status_code == 200
    returned = response.json()["config"]["data"]
    assert returned["tickflow_access_mode"] == "free"
    assert returned["tickflow_api_key"] == ""
    assert returned["tickflow_api_key_configured"] is True
    assert cfg["data"]["tickflow_api_key"] == "secret-value"


def test_update_config_switches_tickflow_mode_without_deleting_key_and_reloads_scheduler(
    monkeypatch, tmp_path
):
    cfg = _valid_config()
    cfg["data"]["tickflow_api_key"] = "existing-secret"
    config_path = tmp_path / "config.yaml"
    reloaded = []
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": copy.deepcopy(cfg))
    monkeypatch.setattr(server, "_reload_scheduler_from_config", lambda config: reloaded.append(config))
    original_open = builtins.open
    monkeypatch.setattr(
        builtins,
        "open",
        lambda file, *args, **kwargs: original_open(config_path, *args, **kwargs)
        if file == "config.yaml" else original_open(file, *args, **kwargs),
    )

    response = TestClient(server.app).put(
        "/api/config", json={"data": {"tickflow_access_mode": "free"}}
    )

    assert response.status_code == 200
    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["data"]["tickflow_access_mode"] == "free"
    assert written["data"]["tickflow_api_key"] == "existing-secret"
    assert len(reloaded) == 1


@pytest.mark.parametrize("invalid_mode", ["automatic", 123, None])
def test_update_config_rejects_invalid_tickflow_access_mode_without_writing(
    monkeypatch, invalid_mode
):
    cfg = _valid_config()
    writes = []
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": copy.deepcopy(cfg))
    monkeypatch.setattr(server, "write_yaml_config_atomic", lambda *args, **kwargs: writes.append(args))

    response = TestClient(server.app).put(
        "/api/config", json={"data": {"tickflow_access_mode": invalid_mode}}
    )

    assert response.status_code == 400
    assert "tickflow_access_mode" in response.json()["message"]
    assert writes == []


@pytest.mark.parametrize("incoming", [None, "", "   "])
def test_update_config_blank_or_missing_tickflow_key_preserves_existing(
    monkeypatch, tmp_path, incoming
):
    cfg = _valid_config()
    cfg["data"]["tickflow_api_key"] = "existing-secret"
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": copy.deepcopy(cfg))
    monkeypatch.setattr(server, "_reload_scheduler_from_config", lambda config: None)
    original_open = builtins.open
    monkeypatch.setattr(
        builtins,
        "open",
        lambda file, *args, **kwargs: original_open(config_path, *args, **kwargs)
        if file == "config.yaml" else original_open(file, *args, **kwargs),
    )
    payload = {"data": {"scan_window_days": 300}}
    if incoming is not None:
        payload["data"]["tickflow_api_key"] = incoming

    response = TestClient(server.app).put("/api/config", json=payload)

    assert response.status_code == 200
    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["data"]["tickflow_api_key"] == "existing-secret"


def test_update_config_replaces_trimmed_tickflow_key_and_reloads_scheduler(monkeypatch, tmp_path):
    cfg = _valid_config()
    cfg["data"]["tickflow_api_key"] = "old-secret"
    config_path = tmp_path / "config.yaml"
    reloaded = []
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": copy.deepcopy(cfg))
    monkeypatch.setattr(server, "_reload_scheduler_from_config", lambda config: reloaded.append(config))
    original_open = builtins.open
    monkeypatch.setattr(
        builtins,
        "open",
        lambda file, *args, **kwargs: original_open(config_path, *args, **kwargs)
        if file == "config.yaml" else original_open(file, *args, **kwargs),
    )

    response = TestClient(server.app).put(
        "/api/config", json={"data": {"tickflow_api_key": " new-format-key "}}
    )

    assert response.status_code == 200
    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert written["data"]["tickflow_api_key"] == "new-format-key"
    assert len(reloaded) == 1


def test_update_config_rejects_non_string_tickflow_key_without_writing(monkeypatch):
    cfg = _valid_config()
    writes = []
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": copy.deepcopy(cfg))
    monkeypatch.setattr(server, "write_yaml_config_atomic", lambda *args, **kwargs: writes.append(args))

    response = TestClient(server.app).put(
        "/api/config", json={"data": {"tickflow_api_key": 12345}}
    )

    assert response.status_code == 400
    assert "tickflow_api_key" in response.json()["message"]
    assert writes == []


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
    monkeypatch.setattr(server, "write_yaml_config_atomic", lambda *args, **kwargs: writes.append(args))

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
    monkeypatch.setattr(server, "write_yaml_config_atomic", lambda *args, **kwargs: writes.append(args))

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
                    "id": "strategy6_scan",
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
    assert body["runtime"]["jobs"][0]["id"] == "strategy6_scan"
