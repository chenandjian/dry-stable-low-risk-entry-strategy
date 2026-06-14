"""Strategy1 backtest experiment helpers.

The functions here are intentionally pure. They are applied after
CupHandleStrategyEngine has produced a baseline-passed signal.
"""

from __future__ import annotations

from collections.abc import Mapping


BREAKOUT_MODES = {"NONE", "PRICE_ONLY", "PRICE_AND_VOLUME", "NEAR_PIVOT"}
EXECUTION_MODELS = {"NEXT_OPEN", "SIGNAL_CLOSE_DIAGNOSTIC"}
ALLOWED_VERDICT_KEYS = {"BUY_LOW", "WATCH_BREAKOUT", "WAIT_ENTRY"}


def _get(raw: Mapping | None, snake: str, camel: str | None = None, default=None):
    if not raw:
        return default
    if snake in raw:
        return raw.get(snake)
    if camel and camel in raw:
        return raw.get(camel)
    return default


def _nullable_number(value, name: str, *, min_value: float | None = None, max_value: float | None = None):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number or null")
    fvalue = float(value)
    if min_value is not None and fvalue < min_value:
        raise ValueError(f"{name} must be >= {min_value}")
    if max_value is not None and fvalue > max_value:
        raise ValueError(f"{name} must be <= {max_value}")
    return fvalue


def _nullable_score(value, name: str) -> int | None:
    parsed = _nullable_number(value, name, min_value=0, max_value=100)
    return int(parsed) if parsed is not None else None


def _section(raw: Mapping | None, name: str) -> Mapping:
    value = _get(raw, name, name, {}) or {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _ratio(raw: Mapping | None, snake: str, camel: str, name: str):
    return _nullable_number(_get(raw, snake, camel, None), name, min_value=0, max_value=1)


def normalize_experiment_config(raw: Mapping | None) -> dict:
    """Normalize frontend/API experiment payload into stable snake_case keys."""
    enabled = bool(_get(raw, "enabled", "enabled", False))

    breakout_raw = _section(raw, "breakout")
    breakout_mode = str(_get(breakout_raw, "mode", "mode", "NONE") or "NONE").upper()
    if breakout_mode not in BREAKOUT_MODES:
        raise ValueError(f"breakout.mode must be one of {sorted(BREAKOUT_MODES)}")

    decision_raw = _section(raw, "decision")
    allowed = _get(decision_raw, "allowed_verdict_keys", "allowedVerdictKeys", None)
    if allowed is None:
        allowed = ["BUY_LOW", "WATCH_BREAKOUT", "WAIT_ENTRY"]
    if not isinstance(allowed, list) or any(key not in ALLOWED_VERDICT_KEYS for key in allowed):
        raise ValueError(f"allowed_verdict_keys must contain only {sorted(ALLOWED_VERDICT_KEYS)}")

    risk_raw = _section(raw, "risk")
    time_exit_days = _get(raw, "time_exit_days", "timeExitDays", None)
    if time_exit_days in ("", None):
        time_exit_days = None
    elif int(time_exit_days) not in {3, 5, 10}:
        raise ValueError("time_exit_days must be null, 3, 5, or 10")
    else:
        time_exit_days = int(time_exit_days)

    execution_model = str(_get(raw, "execution_model", "executionModel", "NEXT_OPEN") or "NEXT_OPEN").upper()
    if execution_model not in EXECUTION_MODELS:
        raise ValueError(f"execution_model must be one of {sorted(EXECUTION_MODELS)}")

    return {
        "enabled": enabled,
        "minimum_total_score": _nullable_score(
            _get(raw, "minimum_total_score", "minimumTotalScore", None),
            "minimum_total_score",
        ),
        "cup": {
            "min_depth": _ratio(raw, "cup_min_depth", "cupMinDepth", "cup.min_depth"),
            "max_depth": _ratio(raw, "cup_max_depth", "cupMaxDepth", "cup.max_depth"),
            "min_duration": _nullable_score(_get(raw, "cup_min_duration", "cupMinDuration", None), "cup.min_duration"),
            "max_duration": _nullable_score(_get(raw, "cup_max_duration", "cupMaxDuration", None), "cup.max_duration"),
            "max_lip_deviation": _ratio(raw, "max_lip_deviation", "maxLipDeviation", "cup.max_lip_deviation"),
            "min_bottom_roundness": _ratio(raw, "min_bottom_roundness", "minBottomRoundness", "cup.min_bottom_roundness"),
        },
        "handle": {
            "min_duration": _nullable_score(_get(raw, "handle_min_duration", "handleMinDuration", None), "handle.min_duration"),
            "max_duration": _nullable_score(_get(raw, "handle_max_duration", "handleMaxDuration", None), "handle.max_duration"),
            "max_depth": _ratio(raw, "handle_max_depth", "handleMaxDepth", "handle.max_depth"),
            "max_vs_right_rally": _ratio(raw, "handle_max_vs_right_rally", "handleMaxVsRightRally", "handle.max_vs_right_rally"),
        },
        "breakout": {
            "mode": breakout_mode,
            "buffer_pct": _ratio(breakout_raw, "buffer_pct", "bufferPct", "breakout.buffer_pct"),
            "volume_multiplier": _nullable_number(
                _get(breakout_raw, "volume_multiplier", "volumeMultiplier", None),
                "breakout.volume_multiplier",
                min_value=0,
                max_value=10,
            ),
        },
        "decision": {
            "min_pattern_score": _nullable_score(_get(decision_raw, "min_pattern_score", "minPatternScore", None), "decision.min_pattern_score"),
            "min_volume_dry_score": _nullable_score(_get(decision_raw, "min_volume_dry_score", "minVolumeDryScore", None), "decision.min_volume_dry_score"),
            "min_price_stable_score": _nullable_score(_get(decision_raw, "min_price_stable_score", "minPriceStableScore", None), "decision.min_price_stable_score"),
            "allowed_verdict_keys": allowed,
        },
        "risk": {
            "max_risk_percent": _nullable_number(_get(risk_raw, "max_risk_percent", "maxRiskPercent", None), "risk.max_risk_percent", min_value=0, max_value=100),
            "low_buy_max_risk_percent": _nullable_number(_get(risk_raw, "low_buy_max_risk_percent", "lowBuyMaxRiskPercent", None), "risk.low_buy_max_risk_percent", min_value=0, max_value=100),
            "min_rr1": _nullable_number(_get(risk_raw, "min_rr1", "minRr1", None), "risk.min_rr1", min_value=0, max_value=20),
            "max_chase_pct": _nullable_number(_get(risk_raw, "max_chase_pct", "maxChasePct", None), "risk.max_chase_pct", min_value=0, max_value=100),
        },
        "execution_model": execution_model,
        "time_exit_days": time_exit_days,
    }


def is_experiment_enabled(experiment: Mapping | None) -> bool:
    return bool(experiment and experiment.get("enabled"))


def apply_signal_experiment_filter(signal, experiment: Mapping | None) -> tuple[bool, str]:
    """Apply post-signal Strategy1 experiment filters and keep traceability."""
    signal.baseline_passed = True
    if not is_experiment_enabled(experiment):
        signal.experiment_passed = True
        signal.experiment_filter_reason = ""
        return True, ""

    checks = [
        ("minimum_total_score", getattr(signal, "score", 0), "MIN_TOTAL_SCORE"),
        ("cup.min_depth", getattr(signal, "cup_depth_pct", 0), "CUP_MIN_DEPTH"),
        ("cup.max_depth", getattr(signal, "cup_depth_pct", 0), "CUP_MAX_DEPTH"),
        ("handle.min_duration", getattr(signal, "handle_duration", 0), "HANDLE_MIN_DURATION"),
        ("handle.max_duration", getattr(signal, "handle_duration", 0), "HANDLE_MAX_DURATION"),
        ("handle.max_depth", getattr(signal, "handle_depth_pct", 0), "HANDLE_MAX_DEPTH"),
        ("decision.min_volume_dry_score", getattr(signal, "volume_dry_score", 0), "MIN_VOLUME_DRY_SCORE"),
        ("decision.min_price_stable_score", getattr(signal, "price_stable_score", 0), "MIN_PRICE_STABLE_SCORE"),
        ("decision.min_pattern_score", getattr(signal, "pattern_score_20", 0), "MIN_PATTERN_SCORE"),
        ("risk.max_risk_percent", getattr(signal, "risk_percent", 0), "MAX_RISK_PERCENT"),
        ("risk.min_rr1", getattr(signal, "rr1", 0), "MIN_RR1"),
    ]

    for key, actual, reason in checks:
        expected = _nested_get(experiment, key)
        if expected is None:
            continue
        if key.endswith("max_depth") or key.endswith("max_duration") or key.endswith("max_risk_percent"):
            failed = actual > expected
        else:
            failed = actual < expected
        if failed:
            signal.experiment_passed = False
            signal.experiment_filter_reason = reason
            return False, reason

    allowed = (experiment.get("decision") or {}).get("allowed_verdict_keys")
    if allowed and getattr(signal, "verdict_key", "") not in allowed:
        signal.experiment_passed = False
        signal.experiment_filter_reason = "VERDICT_NOT_ALLOWED"
        return False, "VERDICT_NOT_ALLOWED"

    signal.experiment_passed = True
    signal.experiment_filter_reason = ""
    return True, ""


def _nested_get(mapping: Mapping, dotted: str):
    current = mapping
    for part in dotted.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current
