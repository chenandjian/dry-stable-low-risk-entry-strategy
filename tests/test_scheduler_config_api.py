import server
import builtins
import yaml
from fastapi.testclient import TestClient


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
