from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml


class ConfigFileError(ValueError):
    """Raised when a YAML configuration cannot be read or saved safely."""


def _validate_config_root(value: Any, path: Path) -> dict:
    if value is None:
        raise ConfigFileError(f"configuration file is empty: {path}")
    if not isinstance(value, dict):
        raise ConfigFileError(f"configuration root must be a mapping: {path}")
    if not value:
        raise ConfigFileError(f"configuration must be a non-empty mapping: {path}")
    return value


def load_yaml_config(path: str | Path = "config.yaml") -> dict:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            value = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ConfigFileError(f"invalid YAML in configuration file {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigFileError(f"cannot read configuration file {config_path}: {exc}") from exc
    return _validate_config_root(value, config_path)


def _new_temporary_path(target: Path) -> tuple[int, Path]:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    return descriptor, Path(name)


def _safe_close(descriptor: int | None) -> None:
    if descriptor is None:
        return
    try:
        os.close(descriptor)
    except OSError:
        pass


def _safe_unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _copy_backup_atomically(target: Path, backup: Path) -> None:
    descriptor: int | None = None
    temporary: Path | None = None
    try:
        backup.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = _new_temporary_path(backup)
        destination = os.fdopen(descriptor, "wb")
        descriptor = None
        with target.open("rb") as source, destination:
            shutil.copyfileobj(source, destination)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, backup)
    except Exception:
        _safe_close(descriptor)
        _safe_unlink(temporary)
        raise


def write_yaml_config_atomic(
    config: dict,
    path: str | Path = "config.yaml",
    *,
    backup_path: str | Path | None = None,
) -> None:
    target = Path(path)
    _validate_config_root(config, target)
    descriptor: int | None = None
    temporary: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = _new_temporary_path(target)
        handle = os.fdopen(descriptor, "w", encoding="utf-8", newline="")
        descriptor = None
        with handle:
            yaml.safe_dump(
                config,
                handle,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )
            handle.flush()
            os.fsync(handle.fileno())

        load_yaml_config(temporary)
        if target.exists():
            backup = Path(backup_path) if backup_path is not None else Path(f"{target}.bak")
            _copy_backup_atomically(target, backup)
        os.replace(temporary, target)
    except Exception as exc:
        _safe_close(descriptor)
        _safe_unlink(temporary)
        if isinstance(exc, ConfigFileError):
            raise
        raise ConfigFileError(f"cannot write configuration file {target}: {exc}") from exc
    finally:
        _safe_unlink(temporary)


__all__ = ["ConfigFileError", "load_yaml_config", "write_yaml_config_atomic"]
