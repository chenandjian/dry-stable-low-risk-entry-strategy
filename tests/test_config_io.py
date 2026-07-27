from pathlib import Path

import pytest
import yaml

from scanner.config_io import (
    ConfigFileError,
    load_yaml_config,
    write_yaml_config_atomic,
)


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("", "empty"),
        ("- item\n", "mapping"),
        ("data: [\n", "invalid YAML"),
    ],
)
def test_load_yaml_config_rejects_invalid_root_with_path(tmp_path, contents, message):
    path = tmp_path / "config.yaml"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ConfigFileError) as exc_info:
        load_yaml_config(path)

    assert str(path) in str(exc_info.value)
    assert message in str(exc_info.value)


def test_write_yaml_config_atomically_replaces_target_and_keeps_backup(tmp_path):
    path = tmp_path / "config.yaml"
    old_config = {"server": {"port": 8080}, "data": {"daily_sources": ["sina"]}}
    new_config = {"server": {"port": 8090}, "data": {"daily_sources": ["tencent"]}}
    path.write_text(yaml.safe_dump(old_config), encoding="utf-8")

    write_yaml_config_atomic(new_config, path)

    assert load_yaml_config(path) == new_config
    assert load_yaml_config(Path(f"{path}.bak")) == old_config
    assert list(tmp_path.glob(".config.yaml.*.tmp")) == []


def test_write_yaml_config_serialization_failure_preserves_original(monkeypatch, tmp_path):
    path = tmp_path / "config.yaml"
    original = b"server:\n  port: 8080\n"
    path.write_bytes(original)

    from scanner import config_io

    monkeypatch.setattr(
        config_io.yaml,
        "safe_dump",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("dump failed")),
    )

    with pytest.raises(ConfigFileError, match="write"):
        write_yaml_config_atomic({"server": {"port": 8090}}, path)

    assert path.read_bytes() == original
    assert not Path(f"{path}.bak").exists()
    assert list(tmp_path.glob(".config.yaml.*.tmp")) == []


def test_write_yaml_config_replace_failure_preserves_original(monkeypatch, tmp_path):
    path = tmp_path / "config.yaml"
    original = b"server:\n  port: 8080\n"
    path.write_bytes(original)

    from scanner import config_io

    real_replace = config_io.os.replace

    def fail_final_replace(source, destination):
        if Path(destination) == path:
            raise OSError("replace blocked")
        return real_replace(source, destination)

    monkeypatch.setattr(config_io.os, "replace", fail_final_replace)

    with pytest.raises(ConfigFileError, match="replace blocked"):
        write_yaml_config_atomic({"server": {"port": 8090}}, path)

    assert path.read_bytes() == original
    assert load_yaml_config(Path(f"{path}.bak")) == {"server": {"port": 8080}}
    assert list(tmp_path.glob(".config.yaml.*.tmp")) == []


def test_write_yaml_config_temp_creation_failure_is_wrapped(monkeypatch, tmp_path):
    path = tmp_path / "config.yaml"
    original = b"server:\n  port: 8080\n"
    path.write_bytes(original)

    from scanner import config_io

    monkeypatch.setattr(
        config_io,
        "_new_temporary_path",
        lambda target: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(ConfigFileError, match="disk full"):
        write_yaml_config_atomic({"server": {"port": 8090}}, path)

    assert path.read_bytes() == original


def test_write_yaml_config_rejects_empty_mapping_before_touching_target(tmp_path):
    path = tmp_path / "config.yaml"
    original = b"server:\n  port: 8080\n"
    path.write_bytes(original)

    with pytest.raises(ConfigFileError, match="non-empty mapping"):
        write_yaml_config_atomic({}, path)

    assert path.read_bytes() == original
