from fastapi.testclient import TestClient
import pytest

import main
import server
from scanner.config_io import ConfigFileError
from strategy6.backtest.runner import _load_yaml


def _valid_config() -> dict:
    return {
        "market": {},
        "data": {
            "scan_window_days": 250,
            "backtest_window_days": 250,
            "daily_sources": ["sina"],
        },
        "liquidity": {"min_listing_days": 500},
        "scheduler": {
            "enabled": False,
            "serial_dual_scan": {
                "enabled": True,
                "cron": "15 15 * * 1-5",
                "strategy1_failed_retry_rounds": 3,
            },
        },
        "strategy2": {"enabled": False},
        "strategy4": {"enabled": False},
    }


@pytest.mark.parametrize("loader", [main.load_config, server.load_config])
def test_entrypoint_loaders_reject_empty_config_with_clear_error(loader, tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ConfigFileError, match="configuration file is empty"):
        loader(path)


def test_strategy6_backtest_loader_rejects_empty_config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ConfigFileError, match="configuration file is empty"):
        _load_yaml(str(path))


def test_config_api_atomic_write_failure_keeps_scheduler_unchanged(monkeypatch):
    config = _valid_config()
    reloads = []
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": config)
    monkeypatch.setattr(
        server,
        "write_yaml_config_atomic",
        lambda *args, **kwargs: (_ for _ in ()).throw(ConfigFileError("disk failure")),
        raising=False,
    )
    monkeypatch.setattr(server, "_reload_scheduler_from_config", reloads.append)

    response = TestClient(server.app).put(
        "/api/config",
        json={"data": {"acquisition_mode": "tickflow"}},
    )

    assert response.status_code == 500
    assert response.json()["error"] == "CONFIG_WRITE_FAILED"
    assert reloads == []


def test_config_api_places_backup_under_ignored_data_directory(monkeypatch):
    writes = []
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": _valid_config())
    monkeypatch.setattr(
        server,
        "write_yaml_config_atomic",
        lambda *args, **kwargs: writes.append((args, kwargs)),
    )

    response = TestClient(server.app).put(
        "/api/config",
        json={"data": {"scan_window_days": 300}},
    )

    assert response.status_code == 200
    assert writes[0][1]["backup_path"] == "data/config-backups/config.yaml.bak"
