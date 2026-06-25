"""策略3配置和 OHLC 输入校验。"""
from __future__ import annotations

from datetime import datetime
from numbers import Real


DEFAULT_STRATEGY3_CONFIG = {
    "enabled": True,
    "strategy_window_days": 250,
    "minimum_required_days": 180,
    "pullback_lookback_days": 60,
    "support_lookback_days": 20,
    "candidate_min_score": 75,
    "core_min_score": 85,
    "max_risk_ratio": 0.08,
    "max_pullback_from_high": 0.30,
    "min_pullback_from_high": 0.08,
    "max_recent_range_5": 0.12,
    "max_recent_surge_3": 0.10,
    "min_relative_strength_60": 0.05,
    "volume_shrink_ratio": 0.85,
}

REQUIRED_OHLC_FIELDS = {"date", "open", "high", "low", "close", "volume"}


def resolve_strategy3_config(config: dict | None) -> dict:
    """Resolve and validate strategy3 config.

    Accepts either the full project config with a ``strategy3`` section or a
    strategy3-only dict. Validation is strict so all entry points behave the
    same way.
    """
    config = config or {}
    if "strategy3" in config:
        raw = dict(DEFAULT_STRATEGY3_CONFIG)
        raw.update(config.get("strategy3") or {})
    else:
        raw = dict(DEFAULT_STRATEGY3_CONFIG)
        raw.update(config)

    liquidity = config.get("liquidity") or {}
    min_listing_days = _coerce_int(liquidity.get("min_listing_days", 350), "liquidity.min_listing_days")

    raw["enabled"] = bool(raw.get("enabled", True))
    _validate_int_range(raw, "minimum_required_days", 120, 1000)
    _validate_int_range(raw, "strategy_window_days", raw["minimum_required_days"], min_listing_days)
    _validate_int_range(raw, "pullback_lookback_days", 40, 120)
    _validate_int_range(raw, "support_lookback_days", 10, 40)
    _validate_number_range(raw, "candidate_min_score", 0, 100)
    _validate_number_range(raw, "core_min_score", 0, 100)
    if raw["core_min_score"] < raw["candidate_min_score"]:
        raise ValueError("core_min_score must be >= candidate_min_score")
    _validate_number_range(raw, "max_risk_ratio", 0.01, 0.5)
    _validate_number_range(raw, "min_pullback_from_high", 0.0, 0.5)
    _validate_number_range(raw, "max_pullback_from_high", raw["min_pullback_from_high"], 0.8)
    _validate_number_range(raw, "max_recent_range_5", 0.01, 0.5)
    _validate_number_range(raw, "max_recent_surge_3", 0.01, 0.5)
    _validate_number_range(raw, "min_relative_strength_60", -0.5, 0.5)
    _validate_number_range(raw, "volume_shrink_ratio", 0.1, 2.0)
    return raw


def validate_ohlc_structure(data: list[dict] | None) -> str | None:
    """Return stable error code when OHLC structure is invalid."""
    if not data or not isinstance(data, list):
        return "INVALID_MARKET_DATA"

    prev_date = None
    for row in data:
        if not isinstance(row, dict) or not REQUIRED_OHLC_FIELDS.issubset(row):
            return "INVALID_MARKET_DATA"
        date_value = row.get("date")
        if not isinstance(date_value, str):
            return "INVALID_MARKET_DATA"
        try:
            parsed = datetime.strptime(date_value, "%Y-%m-%d")
        except ValueError:
            return "INVALID_MARKET_DATA"
        if prev_date is not None and parsed <= prev_date:
            return "INVALID_MARKET_DATA"
        prev_date = parsed
    return None


def validate_ohlc_values(data: list[dict] | None) -> str | None:
    """Return stable error code when OHLC values are invalid."""
    if not data:
        return "INVALID_MARKET_DATA"
    for row in data:
        try:
            open_ = float(row["open"])
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            volume = float(row["volume"])
        except (TypeError, ValueError, KeyError):
            return "INVALID_MARKET_DATA"
        if min(open_, high, low, close) <= 0 or volume < 0:
            return "INVALID_MARKET_DATA"
        if high < max(open_, close, low) or low > min(open_, close, high):
            return "INVALID_MARKET_DATA"
    return None


def _validate_int_range(config: dict, key: str, min_value: int, max_value: int) -> None:
    value = _coerce_int(config.get(key), key)
    if value < min_value or value > max_value:
        raise ValueError(f"{key} must be between {min_value} and {max_value}")
    config[key] = value


def _validate_number_range(config: dict, key: str, min_value: float, max_value: float) -> None:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{key} must be a number")
    value = float(value)
    if value < min_value or value > max_value:
        raise ValueError(f"{key} must be between {min_value} and {max_value}")
    config[key] = value


def _coerce_int(value, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value
