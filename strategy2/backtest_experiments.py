"""Strategy2 Phase 2 backtest experiment helpers.

This module is intentionally pure and does not call the Strategy2 engine.
Experiment logic is applied only after the formal Strategy2 engine has already
produced a baseline-passed signal.
"""

from __future__ import annotations

from collections.abc import Mapping


ENTRY_CONFIRMATION_TYPES = {
    "NONE",
    "BREAK_RECENT_5D_HIGH",
    "CLOSE_ABOVE_MA20",
    "BREAK_HIGH_WITH_MODERATE_VOLUME",
}


def _get(raw: Mapping | None, snake: str, camel: str, default=None):
    if not raw:
        return default
    if snake in raw:
        return raw.get(snake)
    return raw.get(camel, default)


def _nullable_score(value, name: str) -> int | None:
    if value is None or value == "":
        return None
    if not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number or null")
    ivalue = int(value)
    if ivalue < 0 or ivalue > 100:
        raise ValueError(f"{name} must be between 0 and 100")
    return ivalue


def normalize_experiment_config(raw: Mapping | None) -> dict:
    """Normalize frontend/API experiment payload into stable snake_case keys."""
    enabled = bool(_get(raw, "enabled", "enabled", False))
    entry_raw = _get(raw, "entry_confirmation", "entryConfirmation", {}) or {}
    entry_type = str(_get(entry_raw, "type", "type", "NONE") or "NONE").upper()
    if entry_type not in ENTRY_CONFIRMATION_TYPES:
        raise ValueError(f"entry_confirmation.type must be one of {sorted(ENTRY_CONFIRMATION_TYPES)}")

    max_wait = _get(entry_raw, "max_wait_days", "maxWaitDays", 5)
    if not isinstance(max_wait, (int, float)) or int(max_wait) < 1 or int(max_wait) > 10:
        raise ValueError("entry_confirmation.max_wait_days must be between 1 and 10")

    moderate_volume_ratio = _get(entry_raw, "moderate_volume_max_ratio", "moderateVolumeMaxRatio", 1.8)
    if not isinstance(moderate_volume_ratio, (int, float)) or float(moderate_volume_ratio) <= 1.0:
        raise ValueError("entry_confirmation.moderate_volume_max_ratio must be greater than 1.0")

    time_exit_days = _get(raw, "time_exit_days", "timeExitDays", None)
    if time_exit_days in ("", None):
        time_exit_days = None
    elif int(time_exit_days) not in {5, 10}:
        raise ValueError("time_exit_days must be null, 5, or 10")
    else:
        time_exit_days = int(time_exit_days)

    market_raw = _get(raw, "market_context", "marketContext", {}) or {}
    return {
        "enabled": enabled,
        "minimum_total_score": _nullable_score(
            _get(raw, "minimum_total_score", "minimumTotalScore", None),
            "minimum_total_score",
        ),
        "minimum_volume_dry_score": _nullable_score(
            _get(raw, "minimum_volume_dry_score", "minimumVolumeDryScore", None),
            "minimum_volume_dry_score",
        ),
        "minimum_price_stable_score": _nullable_score(
            _get(raw, "minimum_price_stable_score", "minimumPriceStableScore", None),
            "minimum_price_stable_score",
        ),
        "time_exit_days": time_exit_days,
        "entry_confirmation": {
            "type": entry_type,
            "max_wait_days": int(max_wait),
            "moderate_volume_max_ratio": float(moderate_volume_ratio),
        },
        "market_context": {
            "enabled": bool(_get(market_raw, "enabled", "enabled", False)),
        },
    }


def is_experiment_enabled(experiment: Mapping | None) -> bool:
    return bool(experiment and experiment.get("enabled"))


def classify_opportunity_type(signal) -> str:
    """Classify opportunities for grouping only; never used as a hard filter."""
    trend_type = str(getattr(signal, "trend_type", "") or "").upper()
    if "DOWN" in trend_type or "REPAIR" in trend_type or "REVERSAL" in trend_type:
        return "REVERSAL"
    if "UP" in trend_type or "SIDEWAYS" in trend_type or "CONTINUATION" in trend_type:
        return "CONTINUATION"
    return "NEUTRAL"


def apply_signal_experiment_filter(signal, experiment: Mapping | None) -> tuple[bool, str]:
    """Apply Phase 2 post-signal thresholds and update traceability fields."""
    signal.baseline_passed = True
    signal.opportunity_type = classify_opportunity_type(signal)

    if not is_experiment_enabled(experiment):
        signal.experiment_passed = True
        signal.experiment_filter_reason = ""
        return True, ""

    checks = (
        ("minimum_total_score", getattr(signal, "score", 0), "MIN_TOTAL_SCORE"),
        ("minimum_volume_dry_score", getattr(signal, "volume_dry_score", 0), "MIN_VOLUME_DRY_SCORE"),
        ("minimum_price_stable_score", getattr(signal, "price_stable_score", 0), "MIN_PRICE_STABLE_SCORE"),
    )
    for key, actual, reason in checks:
        minimum = experiment.get(key)
        if minimum is not None and actual < minimum:
            signal.experiment_passed = False
            signal.experiment_filter_reason = reason
            return False, reason

    signal.experiment_passed = True
    signal.experiment_filter_reason = ""
    return True, ""


def _find_signal_index(opp, date_to_index: Mapping[str, int]) -> int | None:
    return date_to_index.get(getattr(opp, "first_detected_date", ""))


def _close_above_ma20(ohlc_data: list[dict], idx: int) -> bool:
    if idx < 19:
        return False
    ma20 = sum(float(row["close"]) for row in ohlc_data[idx - 19:idx + 1]) / 20.0
    return float(ohlc_data[idx]["close"]) > ma20


def _moderate_volume_breakout(ohlc_data: list[dict], idx: int, max_ratio: float) -> bool:
    if idx < 5:
        return False
    recent_high = max(float(row["high"]) for row in ohlc_data[idx - 5:idx])
    avg_volume = sum(float(row.get("volume") or 0) for row in ohlc_data[idx - 5:idx]) / 5.0
    current_volume = float(ohlc_data[idx].get("volume") or 0)
    if avg_volume <= 0:
        return False
    return (
        float(ohlc_data[idx]["close"]) > recent_high
        and current_volume > avg_volume
        and current_volume <= avg_volume * max_ratio
    )


def _break_recent_5d_high(ohlc_data: list[dict], idx: int) -> bool:
    if idx < 5:
        return False
    recent_high = max(float(row["high"]) for row in ohlc_data[idx - 5:idx])
    return float(ohlc_data[idx]["close"]) > recent_high


def apply_entry_confirmation(opp, ohlc_data: list[dict], date_to_index: Mapping[str, int], experiment: Mapping | None) -> bool:
    """Mark whether an opportunity passes configured entry confirmation."""
    entry_cfg = (experiment or {}).get("entry_confirmation") or {}
    confirm_type = str(entry_cfg.get("type") or "NONE").upper()
    max_wait = int(entry_cfg.get("max_wait_days") or 5)
    max_volume_ratio = float(entry_cfg.get("moderate_volume_max_ratio") or 1.8)

    opp.entry_confirmation_type = confirm_type
    signal_idx = _find_signal_index(opp, date_to_index)
    if signal_idx is None:
        opp.entry_confirmation_status = "UNOBSERVED_ENTRY"
        return False

    if confirm_type == "NONE":
        opp.entry_confirmation_status = "ENTRY_CONFIRMED"
        opp.entry_confirmation_date = opp.first_detected_date
        opp.entry_confirmation_price = float(getattr(opp, "entry_close", 0.0) or 0.0)
        return True

    last_idx = min(len(ohlc_data) - 1, signal_idx + max_wait)
    for idx in range(signal_idx + 1, last_idx + 1):
        if confirm_type == "BREAK_RECENT_5D_HIGH":
            confirmed = _break_recent_5d_high(ohlc_data, idx)
        elif confirm_type == "CLOSE_ABOVE_MA20":
            confirmed = _close_above_ma20(ohlc_data, idx)
        elif confirm_type == "BREAK_HIGH_WITH_MODERATE_VOLUME":
            confirmed = _moderate_volume_breakout(ohlc_data, idx, max_volume_ratio)
        else:
            confirmed = False
        if confirmed:
            opp.entry_confirmation_status = "ENTRY_CONFIRMED"
            opp.entry_confirmation_date = ohlc_data[idx]["date"]
            opp.entry_confirmation_price = float(ohlc_data[idx]["close"])
            return True

    opp.entry_confirmation_status = "NO_ENTRY_CONFIRMATION"
    return False


def apply_time_exit(opp, ohlc_data: list[dict], date_to_index: Mapping[str, int], experiment: Mapping | None) -> bool:
    """Apply configured time exit only when target/stop did not already decide."""
    days = (experiment or {}).get("time_exit_days")
    if days is None:
        return False
    opp.time_exit_days = int(days)
    if (
        getattr(opp, "exit_reason", "") in {"TARGET", "STOP"}
        and getattr(opp, "holding_days", 0)
        and getattr(opp, "holding_days", 0) <= opp.time_exit_days
    ):
        return False
    if not getattr(opp, "entry_date", "") or not getattr(opp, "entry_price", 0):
        return False

    entry_idx = date_to_index.get(opp.entry_date)
    if entry_idx is None:
        return False
    exit_idx = entry_idx + int(days) - 1
    if exit_idx >= len(ohlc_data):
        return False

    exit_bar = ohlc_data[exit_idx]
    opp.exit_reason = "TIME_EXIT"
    opp.exit_date = exit_bar["date"]
    opp.exit_price = float(exit_bar["close"])
    opp.holding_days = int(days)
    opp.realized_return = opp.exit_price / opp.entry_price - 1.0
    return True
