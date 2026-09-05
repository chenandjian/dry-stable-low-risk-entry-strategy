from __future__ import annotations

import math
import statistics
from typing import Iterable


class CleanKInputError(ValueError):
    """The analysis request is invalid."""


class CleanKDataError(ValueError):
    """The local OHLC history cannot support a trustworthy analysis."""


DEFAULT_CLEAN_K_CONFIG = {
    "min_period": 10,
    "max_period": 120,
    "micro_range_atr": 0.30,
    "full_significance_atr": 1.00,
    "two_side_wick_atr_limit": 0.80,
    "one_side_wick_atr_limit": 1.20,
    "dirty_extreme_range_atr": 1.50,
    "dirty_extreme_bar_score": 65.0,
    "clean_score": 75.0,
    "extremely_clean_score": 85.0,
    "min_sequence_score": 70.0,
    "min_structure_score": 60.0,
    "min_confidence": 0.70,
}


def resolve_clean_k_config(raw: dict | None = None) -> dict:
    cfg = {**DEFAULT_CLEAN_K_CONFIG, **(raw or {})}
    try:
        cfg["min_period"] = int(cfg["min_period"])
        cfg["max_period"] = int(cfg["max_period"])
        for key in DEFAULT_CLEAN_K_CONFIG:
            if key not in {"min_period", "max_period"}:
                cfg[key] = float(cfg[key])
    except (TypeError, ValueError) as exc:
        raise CleanKInputError(f"invalid clean-k configuration: {exc}") from exc

    if cfg["min_period"] < 2 or cfg["max_period"] < cfg["min_period"]:
        raise CleanKInputError("invalid clean-k period limits")
    if not 0 <= cfg["min_confidence"] <= 1:
        raise CleanKInputError("min_confidence must be between 0 and 1")
    positive_keys = (
        "micro_range_atr",
        "full_significance_atr",
        "two_side_wick_atr_limit",
        "one_side_wick_atr_limit",
        "dirty_extreme_range_atr",
    )
    if any(cfg[key] <= 0 for key in positive_keys):
        raise CleanKInputError("clean-k ATR thresholds must be positive")
    if cfg["full_significance_atr"] <= cfg["micro_range_atr"]:
        raise CleanKInputError("full_significance_atr must exceed micro_range_atr")
    return cfg


def resolve_clean_k_period(value, cfg: dict) -> int:
    if isinstance(value, bool):
        raise CleanKInputError("period must be an integer")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise CleanKInputError("period must be an integer") from exc
    if not math.isfinite(numeric) or not numeric.is_integer():
        raise CleanKInputError("period must be an integer")
    period = int(numeric)
    if not cfg["min_period"] <= period <= cfg["max_period"]:
        raise CleanKInputError(
            f"period must be between {cfg['min_period']} and {cfg['max_period']}"
        )
    return period


def analyze_clean_k(
    source_rows: list[dict],
    *,
    period: int = 20,
    config: dict | None = None,
    stock_code: str = "",
    target_trade_date: str | None = None,
) -> dict:
    cfg = resolve_clean_k_config(config)
    period = resolve_clean_k_period(period, cfg)

    fetch_count = max(period + 40, 60)
    rows = _select_recent_source_rows(source_rows, fetch_count, target_trade_date)
    if not rows:
        raise CleanKDataError("no local OHLC data available")
    _validate_rows(rows)

    observed_latest_date = rows[-1]["date"]
    valid_rows = [row for row in rows if not _is_suspended_row(row)]
    if len(valid_rows) < period + 15:
        raise CleanKDataError(
            f"insufficient ATR history: need at least {period + 15} effective bars, "
            f"got {len(valid_rows)}"
        )

    atr_values = _calculate_wilder_atr14(valid_rows)
    target_start = len(valid_rows) - period
    target_rows = valid_rows[target_start:]
    metrics = []
    for index in range(target_start, len(valid_rows)):
        atr_prev = atr_values[index - 1] if index > 0 else None
        if atr_prev is None or atr_prev <= 0:
            raise CleanKDataError("insufficient ATR14_PREV for target bars")
        metrics.append(
            _calculate_bar_metrics(
                valid_rows[index], valid_rows[index - 1], atr_prev, cfg
            )
        )

    scored = [item["barCleanScore"] for item in metrics if item["barCleanScore"] is not None]
    if not scored:
        raise CleanKDataError("all target bars are one-price events")

    avg_bar_score = statistics.fmean(scored)
    median_bar_score = statistics.median(scored)
    trend_score = _trend_clean_score(target_rows)
    base_score = _base_clean_score(target_rows, metrics)
    contraction_score = _contraction_clean_score(target_rows, metrics)
    structure_score, structure_mode = _structure_result(
        trend_score, base_score, contraction_score
    )
    range_consistency_score = _range_consistency_score(metrics)
    range_rhythm_score = max(range_consistency_score, contraction_score)
    dirty_extreme_count = sum(bool(item["dirtyExtremeBar"]) for item in metrics)
    extreme_control_score = _extreme_control_score(dirty_extreme_count, len(scored))
    sequence_score = (
        structure_score * 0.55
        + range_rhythm_score * 0.20
        + extreme_control_score * 0.15
        + median_bar_score * 0.10
    )
    clean_score = sequence_score * 0.80 + avg_bar_score * 0.20

    event_count = sum(bool(item["eventBar"]) for item in metrics)
    warmup_count = target_start
    confidence = _clamp(warmup_count / 40.0) * _clamp(
        (period - event_count) / period
    )
    dirty_limit = max(1, math.floor(period * 0.10))
    is_clean = (
        clean_score >= cfg["clean_score"]
        and sequence_score >= cfg["min_sequence_score"]
        and structure_score >= cfg["min_structure_score"]
        and dirty_extreme_count <= dirty_limit
        and confidence >= cfg["min_confidence"]
    )

    start_date = target_rows[0]["date"]
    end_date = target_rows[-1]["date"]
    suspended_count = sum(
        _is_suspended_row(row) and row["date"] >= start_date for row in rows
    )
    trend_direction = _trend_direction(target_rows)
    data_is_fresh = not target_trade_date or observed_latest_date >= target_trade_date
    risk_flags = _build_risk_flags(
        is_clean=is_clean,
        structure_mode=structure_mode,
        trend_direction=trend_direction,
        dirty_extreme_count=dirty_extreme_count,
        event_count=event_count,
        suspended_count=suspended_count,
        confidence=confidence,
        data_is_fresh=data_is_fresh,
        cfg=cfg,
    )
    reasons = _build_reasons(
        period=period,
        structure_mode=structure_mode,
        structure_score=structure_score,
        contraction_score=contraction_score,
        dirty_extreme_count=dirty_extreme_count,
        metrics=metrics,
    )

    return {
        "stockCode": stock_code,
        "period": period,
        "startDate": start_date,
        "endDate": end_date,
        "targetTradeDate": target_trade_date,
        "latestDataDate": observed_latest_date,
        "dataIsFresh": data_is_fresh,
        "isClean": is_clean,
        "cleanKScore": _round(clean_score),
        "cleanLevel": _clean_level(clean_score, cfg),
        "structureMode": structure_mode,
        "trendDirection": trend_direction,
        "structureScore": _round(structure_score),
        "avgBarCleanScore": _round(avg_bar_score),
        "sequenceCleanScore": _round(sequence_score),
        "trendCleanScore": _round(trend_score),
        "baseCleanScore": _round(base_score),
        "contractionCleanScore": _round(contraction_score),
        "rangeRhythmScore": _round(range_rhythm_score),
        "extremeControlScore": _round(extreme_control_score),
        "dirtyExtremeCount": dirty_extreme_count,
        "eventBarCount": event_count,
        "suspendedCount": suspended_count,
        "evaluatedBarCount": len(target_rows),
        "warmupBarCount": warmup_count,
        "confidence": _round(confidence, 4),
        "reasons": reasons,
        "riskFlags": risk_flags,
        "barMetrics": metrics,
    }


def _select_recent_source_rows(
    source_rows: list[dict], fetch_count: int, target_trade_date: str | None
) -> list[dict]:
    eligible = [
        dict(row) for row in source_rows
        if row.get("date") and (not target_trade_date or row["date"] <= target_trade_date)
    ]
    eligible.sort(key=lambda row: row["date"])
    selected = []
    effective_count = 0
    for row in reversed(eligible):
        selected.append(row)
        if not _is_suspended_row(row):
            effective_count += 1
        if effective_count >= fetch_count:
            break
    return list(reversed(selected))


def _validate_rows(rows: Iterable[dict]) -> None:
    for row in rows:
        try:
            values = [float(row[key]) for key in ("open", "high", "low", "close")]
            volume = float(row["volume"])
            turnover = float(row.get("turnover", 0) or 0)
        except (KeyError, TypeError, ValueError) as exc:
            raise CleanKDataError(f"invalid OHLC structure on {row.get('date', '--')}") from exc
        open_, high, low, close = values
        if not all(math.isfinite(value) for value in (*values, volume, turnover)):
            raise CleanKDataError(f"invalid OHLC value on {row['date']}")
        if min(values) <= 0 or volume < 0 or turnover < 0:
            raise CleanKDataError(f"invalid OHLC value on {row['date']}")
        if high < max(open_, close, low) or low > min(open_, close, high):
            raise CleanKDataError(f"invalid OHLC relationship on {row['date']}")
        if volume == 0 and turnover == 0 and not (open_ == high == low == close):
            raise CleanKDataError(f"invalid zero-volume nonflat OHLC on {row['date']}")


def _is_suspended_row(row: dict) -> bool:
    try:
        open_, high, low, close = (
            float(row[key]) for key in ("open", "high", "low", "close")
        )
        return (
            float(row.get("volume", 0)) == 0
            and float(row.get("turnover", 0) or 0) == 0
            and open_ == high == low == close
        )
    except (KeyError, TypeError, ValueError):
        return False


def _calculate_wilder_atr14(rows: list[dict]) -> list[float | None]:
    true_ranges: list[float | None] = [None]
    for index in range(1, len(rows)):
        current = rows[index]
        previous_close = float(rows[index - 1]["close"])
        true_ranges.append(
            max(
                float(current["high"]) - float(current["low"]),
                abs(float(current["high"]) - previous_close),
                abs(float(current["low"]) - previous_close),
            )
        )
    atr: list[float | None] = [None] * len(rows)
    if len(rows) <= 14:
        return atr
    atr[14] = statistics.fmean(true_ranges[1:15])
    for index in range(15, len(rows)):
        atr[index] = (atr[index - 1] * 13 + true_ranges[index]) / 14
    return atr


def _calculate_bar_metrics(row: dict, previous: dict, atr_prev: float, cfg: dict) -> dict:
    open_ = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])
    previous_close = float(previous["close"])
    price_range = high - low
    epsilon = max(1e-10, abs(close) * 1e-10)
    true_range = max(price_range, abs(high - previous_close), abs(low - previous_close))
    gap_atr = abs(open_ - previous_close) / atr_prev

    if price_range <= epsilon:
        return {
            "tradeDate": row["date"],
            "atr14Prev": _round(atr_prev, 6),
            "intradayRangeAtr": 0.0,
            "trueRangeAtr": _round(true_range / atr_prev, 6),
            "bodyRatio": 0.0,
            "upperWickRatio": 0.0,
            "lowerWickRatio": 0.0,
            "wickAtr": 0.0,
            "wickAsymmetry": 0.0,
            "gapAtr": _round(gap_atr, 6),
            "significance": 0.0,
            "twoSideNoise": 0.0,
            "oneSideNoise": 0.0,
            "barCleanScore": None,
            "barStructureType": "ONE_PRICE_EVENT",
            "eventBar": True,
            "dirtyExtremeBar": False,
        }

    body = abs(close - open_)
    upper_wick = max(0.0, high - max(open_, close))
    lower_wick = max(0.0, min(open_, close) - low)
    body_ratio = body / price_range
    upper_ratio = upper_wick / price_range
    lower_ratio = lower_wick / price_range
    wick_total = upper_wick + lower_wick
    intraday_range_atr = price_range / atr_prev
    significance = _linear_score(
        intraday_range_atr,
        cfg["micro_range_atr"],
        cfg["full_significance_atr"],
        low_score=0.0,
        high_score=1.0,
    )
    two_side_wick_atr = 2 * min(upper_wick, lower_wick) / atr_prev
    one_side_wick_atr = max(upper_wick, lower_wick) / atr_prev
    two_side_noise = _clamp(two_side_wick_atr / cfg["two_side_wick_atr_limit"])
    one_side_noise = _clamp(one_side_wick_atr / cfg["one_side_wick_atr_limit"]) * (
        1 - body_ratio
    )
    gap_direction = _sign(open_ - previous_close)
    intraday_direction = _sign(close - open_)
    gap_reversal_noise = 0.0
    if gap_atr >= 0.50 and gap_direction and intraday_direction == -gap_direction:
        gap_reversal_noise = _clamp(gap_atr / 1.50)
    bar_noise = significance * (two_side_noise * 0.60 + one_side_noise * 0.25)
    bar_noise += gap_reversal_noise * 0.15
    bar_clean_score = 100 * (1 - _clamp(bar_noise))
    dirty = (
        intraday_range_atr > cfg["dirty_extreme_range_atr"]
        and bar_clean_score < cfg["dirty_extreme_bar_score"]
    )
    asymmetry = abs(upper_wick - lower_wick) / (wick_total + epsilon)

    return {
        "tradeDate": row["date"],
        "atr14Prev": _round(atr_prev, 6),
        "intradayRangeAtr": _round(intraday_range_atr, 6),
        "trueRangeAtr": _round(true_range / atr_prev, 6),
        "bodyRatio": _round(body_ratio, 6),
        "upperWickRatio": _round(upper_ratio, 6),
        "lowerWickRatio": _round(lower_ratio, 6),
        "wickAtr": _round(wick_total / atr_prev, 6),
        "wickAsymmetry": _round(asymmetry, 6),
        "gapAtr": _round(gap_atr, 6),
        "significance": _round(significance, 6),
        "twoSideNoise": _round(two_side_noise, 6),
        "oneSideNoise": _round(one_side_noise, 6),
        "barCleanScore": _round(bar_clean_score),
        "barStructureType": _bar_structure_type(
            intraday_range_atr, body_ratio, upper_wick, lower_wick, asymmetry, cfg
        ),
        "eventBar": False,
        "dirtyExtremeBar": dirty,
    }


def _bar_structure_type(
    range_atr: float,
    body_ratio: float,
    upper_wick: float,
    lower_wick: float,
    asymmetry: float,
    cfg: dict,
) -> str:
    if range_atr <= cfg["micro_range_atr"]:
        return "MICRO_RANGE"
    if body_ratio >= 0.70:
        return "BODY_DIRECTIONAL"
    if upper_wick > 0 and lower_wick > 0 and asymmetry <= 0.35 and body_ratio <= 0.35:
        return "TWO_SIDE_CONFLICT"
    if asymmetry >= 0.55 and upper_wick > lower_wick:
        return "ONE_SIDE_UPPER_REJECTION"
    if asymmetry >= 0.55 and lower_wick > upper_wick:
        return "ONE_SIDE_LOWER_REJECTION"
    return "BALANCED"


def _trend_clean_score(rows: list[dict]) -> float:
    closes = [float(row["close"]) for row in rows]
    path = sum(abs(closes[index] - closes[index - 1]) for index in range(1, len(closes)))
    er = abs(closes[-1] - closes[0]) / path if path > 0 else 0.0
    er_score = _linear_score(er, 0.20, 0.65)
    r2 = _linear_regression_r2([math.log(value) for value in closes])
    r2_score = _linear_score(r2, 0.35, 0.80)
    return er_score * 0.60 + r2_score * 0.40


def _base_clean_score(rows: list[dict], metrics: list[dict]) -> float:
    atr_median = statistics.median(item["atr14Prev"] for item in metrics)
    width_atr = (
        max(float(row["high"]) for row in rows)
        - min(float(row["low"]) for row in rows)
    ) / atr_median
    drift_atr = abs(float(rows[-1]["close"]) - float(rows[0]["close"])) / atr_median
    width_score = _inverse_linear_score(width_atr, 2.0, 4.5)
    drift_score = _inverse_linear_score(drift_atr, 0.7, 2.2)
    return width_score * 0.70 + drift_score * 0.30


def _contraction_clean_score(rows: list[dict], metrics: list[dict]) -> float:
    range_values = [float(item["intradayRangeAtr"]) for item in metrics]
    first, _, last = _thirds(range_values)
    first_median = statistics.median(first)
    daily_ratio = statistics.median(last) / first_median if first_median > 0 else 1.0
    daily_score = _inverse_linear_score(daily_ratio, 0.60, 1.05)

    rolling = []
    for index in range(4, len(rows)):
        window_rows = rows[index - 4:index + 1]
        window_metrics = metrics[index - 4:index + 1]
        atr_median = statistics.median(item["atr14Prev"] for item in window_metrics)
        rolling.append(
            (
                max(float(row["high"]) for row in window_rows)
                - min(float(row["low"]) for row in window_rows)
            ) / atr_median
        )
    rolling_first, _, rolling_last = _thirds(rolling)
    rolling_first_median = statistics.median(rolling_first)
    rolling_ratio = (
        statistics.median(rolling_last) / rolling_first_median
        if rolling_first_median > 0 else 1.0
    )
    rolling_score = _inverse_linear_score(rolling_ratio, 0.65, 1.05)
    correlation = _spearman(range(len(range_values)), range_values)
    range_trend_score = _inverse_linear_score(correlation, -0.60, 0.0)
    return daily_score * 0.45 + rolling_score * 0.35 + range_trend_score * 0.20


def _range_consistency_score(metrics: list[dict]) -> float:
    values = [float(item["intradayRangeAtr"]) for item in metrics]
    median_value = statistics.median(values)
    if median_value <= 0:
        return 100.0
    mad = statistics.median(abs(value - median_value) for value in values)
    return _inverse_linear_score(mad / median_value, 0.15, 0.60)


def _extreme_control_score(dirty_count: int, valid_count: int) -> float:
    if valid_count <= 0:
        return 0.0
    dirty_rate = dirty_count / valid_count
    return 100 * (1 - min(dirty_rate / 0.30, 1))


def _structure_result(trend: float, base: float, contraction: float) -> tuple[float, str]:
    scores = {"TREND": trend, "BASE": base, "CONTRACTION": contraction}
    mode, score = max(scores.items(), key=lambda item: item[1])
    return score, mode if score >= 45 else "MIXED"


def _trend_direction(rows: list[dict]) -> str:
    change = float(rows[-1]["close"]) / float(rows[0]["close"]) - 1
    if change > 0.005:
        return "UP"
    if change < -0.005:
        return "DOWN"
    return "FLAT"


def _build_risk_flags(
    *, is_clean: bool, structure_mode: str, trend_direction: str, dirty_extreme_count: int,
    event_count: int, suspended_count: int, confidence: float,
    data_is_fresh: bool, cfg: dict,
) -> list[str]:
    flags = []
    if not data_is_fresh:
        flags.append("STALE_LOCAL_DATA")
    if confidence < cfg["min_confidence"]:
        flags.append("LOW_CONFIDENCE")
    if structure_mode == "MIXED":
        flags.append("MIXED_STRUCTURE")
    if dirty_extreme_count:
        flags.append("DIRTY_EXTREME_BARS")
    if event_count:
        flags.append("ONE_PRICE_EVENTS")
    if suspended_count:
        flags.append("SUSPENDED_BARS_EXCLUDED")
    if is_clean and structure_mode == "TREND" and trend_direction == "DOWN":
        flags.append("CLEAN_DOWNTREND")
    return flags


def _build_reasons(
    *, period: int, structure_mode: str, structure_score: float,
    contraction_score: float, dirty_extreme_count: int, metrics: list[dict],
) -> list[str]:
    mode_text = {
        "TREND": "趋势结构",
        "BASE": "稳定平台",
        "CONTRACTION": "有序收缩",
        "MIXED": "混合结构",
    }[structure_mode]
    reasons = [f"最近{period}日主要表现为{mode_text}（{structure_score:.1f}分）"]
    if contraction_score >= 75:
        reasons.append("后段日内振幅较前段明显收缩")
    significant_conflicts = sum(
        item["barStructureType"] == "TWO_SIDE_CONFLICT" and item["significance"] >= 0.5
        for item in metrics
    )
    if significant_conflicts <= max(1, math.floor(period * 0.10)):
        reasons.append("有效双向长影线较少")
    reasons.append(
        f"高噪音异常K线{dirty_extreme_count}根，"
        + ("处于可控范围" if dirty_extreme_count <= max(1, math.floor(period * 0.10)) else "超过允许范围")
    )
    return reasons


def _clean_level(score: float, cfg: dict) -> str:
    if score >= cfg["extremely_clean_score"]:
        return "EXTREMELY_CLEAN"
    if score >= cfg["clean_score"]:
        return "CLEAN"
    if score >= 65:
        return "ACCEPTABLE"
    if score >= 55:
        return "NOISY"
    return "VERY_NOISY"


def _thirds(values: list[float]) -> tuple[list[float], list[float], list[float]]:
    if len(values) < 3:
        raise CleanKDataError("not enough values for three-segment contraction analysis")
    first_end = len(values) // 3
    second_end = (len(values) * 2) // 3
    return values[:first_end], values[first_end:second_end], values[second_end:]


def _linear_regression_r2(values: list[float]) -> float:
    count = len(values)
    if count < 2:
        return 0.0
    x_mean = (count - 1) / 2
    y_mean = statistics.fmean(values)
    ss_x = sum((index - x_mean) ** 2 for index in range(count))
    ss_y = sum((value - y_mean) ** 2 for value in values)
    if ss_x <= 0 or ss_y <= 0:
        return 0.0
    covariance = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values))
    return _clamp((covariance * covariance) / (ss_x * ss_y))


def _spearman(left: Iterable[float], right: Iterable[float]) -> float:
    left_values = list(left)
    right_values = list(right)
    if len(left_values) != len(right_values) or len(left_values) < 2:
        return 0.0
    left_ranks = _average_ranks(left_values)
    right_ranks = _average_ranks(right_values)
    left_mean = statistics.fmean(left_ranks)
    right_mean = statistics.fmean(right_ranks)
    numerator = sum(
        (x - left_mean) * (y - right_mean) for x, y in zip(left_ranks, right_ranks)
    )
    left_scale = sum((x - left_mean) ** 2 for x in left_ranks)
    right_scale = sum((y - right_mean) ** 2 for y in right_ranks)
    denominator = math.sqrt(left_scale * right_scale)
    return numerator / denominator if denominator > 0 else 0.0


def _average_ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = (index + 1 + end) / 2
        for position in range(index, end):
            ranks[ordered[position][0]] = rank
        index = end
    return ranks


def _linear_score(
    value: float, low: float, high: float, *, low_score: float = 0.0,
    high_score: float = 100.0,
) -> float:
    if value <= low:
        return low_score
    if value >= high:
        return high_score
    ratio = (value - low) / (high - low)
    return low_score + ratio * (high_score - low_score)


def _inverse_linear_score(value: float, best: float, worst: float) -> float:
    return 100.0 - _linear_score(value, best, worst)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


__all__ = [
    "CleanKDataError",
    "CleanKInputError",
    "DEFAULT_CLEAN_K_CONFIG",
    "analyze_clean_k",
    "resolve_clean_k_config",
    "resolve_clean_k_period",
]
