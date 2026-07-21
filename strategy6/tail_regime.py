"""Shadow-only robust change-point detection for Strategy6 tail contraction."""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median

from strategy6.models import Strategy6TailRegime


MODEL_VERSION = "TAIL_REGIME_CP_V1"
MIN_BASELINE_DAYS = 5
MAX_BASELINE_DAYS = 20
MIN_TAIL_DAYS = 3
MIN_DELTA_BIC = 6.0
INDISTINGUISHABLE_DELTA = 2.0
MAX_VOLUME_RATIO = 0.80
MAX_PRICE_FEATURE_RATIO = 0.85
MAX_CLOSE_RANGE = 0.08
MIN_LOW_SLOPE_ATR = -0.10
EPSILON = 1e-9


@dataclass(frozen=True)
class _Detection:
    split_index: int
    delta_bic: float
    volume_ratio: float
    range_ratio: float
    body_ratio: float
    abs_return_ratio: float
    close_dispersion: float
    low_slope_atr: float
    reasons: tuple[str, ...]
    risks: tuple[str, ...]


def evaluate_tail_regime(
    rows: list[dict],
    *,
    consolidation_start_index: int,
    enabled: bool = True,
    big_down_return: float = -0.04,
    big_down_volume_ratio: float = 1.5,
    key_support_price: float | None = None,
) -> Strategy6TailRegime:
    """Evaluate a diagnostic tail regime without changing formal decisions."""
    if not enabled:
        return Strategy6TailRegime(enabled=False, status="DISABLED")

    normalized, invalid_reason = _normalize_rows(rows)
    if invalid_reason:
        return Strategy6TailRegime(
            status="INSUFFICIENT_BASELINE",
            risks=[invalid_reason],
        )
    if (
        consolidation_start_index < 0
        or consolidation_start_index + MIN_BASELINE_DAYS + MIN_TAIL_DAYS > len(normalized)
    ):
        return Strategy6TailRegime(
            status="INSUFFICIENT_BASELINE",
            risks=["TAIL_REGIME_SAMPLE_INSUFFICIENT"],
        )

    support_risks = _support_risks(normalized, key_support_price)
    current = _detect_visible_regime(
        normalized,
        consolidation_start_index=consolidation_start_index,
        big_down_return=big_down_return,
        big_down_volume_ratio=big_down_volume_ratio,
    )
    if current is None:
        if support_risks:
            return Strategy6TailRegime(status="BROKEN", risks=support_risks)
        return Strategy6TailRegime(status="NO_REGIME_CHANGE")

    current_risks = list(current.risks) + support_risks
    if current_risks:
        status = "BROKEN"
    else:
        previous = _detect_visible_regime(
            normalized[:-1],
            consolidation_start_index=consolidation_start_index,
            big_down_return=big_down_return,
            big_down_volume_ratio=big_down_volume_ratio,
        )
        status = (
            "CONFIRMED"
            if previous is not None
            and not previous.risks
            and abs(previous.split_index - current.split_index) <= 1
            else "FORMING"
        )

    return Strategy6TailRegime(
        status=status,
        start_date=str(normalized[current.split_index]["date"]),
        days=len(normalized) - current.split_index,
        delta_bic=round(current.delta_bic, 6),
        volume_ratio=round(current.volume_ratio, 6),
        range_ratio=round(current.range_ratio, 6),
        body_ratio=round(current.body_ratio, 6),
        abs_return_ratio=round(current.abs_return_ratio, 6),
        close_dispersion=round(current.close_dispersion, 6),
        low_slope_atr=round(current.low_slope_atr, 6),
        model_version=MODEL_VERSION,
        reasons=list(current.reasons),
        risks=current_risks,
    )


def _detect_visible_regime(
    rows: list[dict],
    *,
    consolidation_start_index: int,
    big_down_return: float,
    big_down_volume_ratio: float,
) -> _Detection | None:
    last_split = len(rows) - MIN_TAIL_DAYS
    first_split = consolidation_start_index + MIN_BASELINE_DAYS
    if first_split > last_split:
        return None

    candidates: list[_Detection] = []
    features = _daily_features(rows)
    for split_index in range(first_split, last_split + 1):
        baseline_start = max(consolidation_start_index, split_index - MAX_BASELINE_DAYS)
        baseline_rows = rows[baseline_start:split_index]
        tail_rows = rows[split_index:]
        if len(baseline_rows) < MIN_BASELINE_DAYS or len(tail_rows) < MIN_TAIL_DAYS:
            continue
        baseline_features = features[baseline_start:split_index]
        tail_features = features[split_index:]
        if any(value is None for feature in baseline_features + tail_features for value in feature):
            continue

        delta_bic = sum(
            _delta_bic(
                [float(feature[column]) for feature in baseline_features],
                [float(feature[column]) for feature in tail_features],
            )
            for column in range(4)
        )
        if delta_bic < MIN_DELTA_BIC:
            continue

        volume_ratio = _median_ratio(tail_rows, baseline_rows, "volume")
        range_ratio = _feature_ratio(tail_features, baseline_features, 1)
        body_ratio = _feature_ratio(tail_features, baseline_features, 2)
        abs_return_ratio = _feature_ratio(tail_features, baseline_features, 3)
        contraction_count = sum(
            0 < ratio <= MAX_PRICE_FEATURE_RATIO
            for ratio in (range_ratio, body_ratio, abs_return_ratio)
        )
        close_dispersion = _close_dispersion(tail_rows)
        close_range = _close_range(tail_rows)
        low_slope_atr = _low_slope_atr(tail_rows)
        if not (
            0 < volume_ratio <= MAX_VOLUME_RATIO
            and contraction_count >= 2
            and 0 <= close_range <= MAX_CLOSE_RANGE
            and low_slope_atr >= MIN_LOW_SLOPE_ATR
        ):
            continue

        risks = _structure_risks(
            tail_rows,
            baseline_rows,
            big_down_return=big_down_return,
            big_down_volume_ratio=big_down_volume_ratio,
        )
        reasons = (
            "ROBUST_BIC_CHANGE_POINT",
            "TAIL_VOLUME_CONTRACTED",
            "TAIL_PRICE_ACTION_CONTRACTED",
            "TAIL_LOW_STRUCTURE_STABLE",
        )
        candidates.append(_Detection(
            split_index=split_index,
            delta_bic=delta_bic,
            volume_ratio=volume_ratio,
            range_ratio=range_ratio,
            body_ratio=body_ratio,
            abs_return_ratio=abs_return_ratio,
            close_dispersion=close_dispersion,
            low_slope_atr=low_slope_atr,
            reasons=reasons,
            risks=tuple(risks),
        ))

    if not candidates:
        return None
    best_delta = max(item.delta_bic for item in candidates)
    indistinguishable = [
        item for item in candidates
        if best_delta - item.delta_bic <= INDISTINGUISHABLE_DELTA
    ]
    return min(indistinguishable, key=lambda item: item.split_index)


def _normalize_rows(rows: list[dict]) -> tuple[list[dict], str]:
    required = ("date", "open", "high", "low", "close", "volume")
    normalized: list[dict] = []
    for row in rows:
        if any(row.get(key) in (None, "") for key in required):
            return [], "TAIL_REGIME_INVALID_KLINE"
        try:
            item = dict(row)
            for key in ("open", "high", "low", "close", "volume"):
                item[key] = float(item[key])
        except (TypeError, ValueError):
            return [], "TAIL_REGIME_INVALID_KLINE"
        if (
            item["open"] <= 0
            or item["high"] <= 0
            or item["low"] <= 0
            or item["close"] <= 0
            or item["volume"] < 0
            or item["high"] < max(item["open"], item["close"])
            or item["low"] > min(item["open"], item["close"])
        ):
            return [], "TAIL_REGIME_INVALID_KLINE"
        normalized.append(item)
    return normalized, ""


def _daily_features(rows: list[dict]) -> list[tuple[float, float, float, float]]:
    values: list[tuple[float, float, float, float]] = []
    for index, row in enumerate(rows):
        previous_close = rows[index - 1]["close"] if index > 0 else row["close"]
        true_range = max(
            row["high"] - row["low"],
            abs(row["high"] - previous_close),
            abs(row["low"] - previous_close),
        ) / previous_close
        body = abs(row["close"] - row["open"]) / previous_close
        absolute_return = abs(row["close"] - previous_close) / previous_close
        values.append((math.log1p(row["volume"]), true_range, body, absolute_return))
    return values


def _delta_bic(baseline: list[float], tail: list[float]) -> float:
    combined = baseline + tail
    n = len(combined)
    scale = max(_mad(combined), EPSILON)
    single_cost = sum(abs(value - median(combined)) for value in combined) / scale
    split_cost = (
        sum(abs(value - median(baseline)) for value in baseline)
        + sum(abs(value - median(tail)) for value in tail)
    ) / scale
    single_bic = n * math.log(max(single_cost / n, EPSILON)) + math.log(n)
    split_bic = n * math.log(max(split_cost / n, EPSILON)) + 2 * math.log(n)
    return single_bic - split_bic


def _mad(values: list[float]) -> float:
    center = median(values)
    return median(abs(value - center) for value in values)


def _median_ratio(tail: list[dict], baseline: list[dict], key: str) -> float:
    denominator = median(float(row[key]) for row in baseline)
    return median(float(row[key]) for row in tail) / denominator if denominator > EPSILON else 0.0


def _feature_ratio(
    tail: list[tuple[float, float, float, float]],
    baseline: list[tuple[float, float, float, float]],
    column: int,
) -> float:
    denominator = median(item[column] for item in baseline)
    return median(item[column] for item in tail) / denominator if denominator > EPSILON else 0.0


def _close_dispersion(rows: list[dict]) -> float:
    closes = [row["close"] for row in rows]
    center = median(closes)
    return _mad(closes) / center if center > EPSILON else 0.0


def _close_range(rows: list[dict]) -> float:
    closes = [row["close"] for row in rows]
    center = median(closes)
    return (max(closes) - min(closes)) / center if center > EPSILON else 0.0


def _low_slope_atr(rows: list[dict]) -> float:
    slopes = [
        (rows[right]["low"] - rows[left]["low"]) / (right - left)
        for left in range(len(rows) - 1)
        for right in range(left + 1, len(rows))
    ]
    atr_values: list[float] = []
    for index, row in enumerate(rows):
        previous_close = rows[index - 1]["close"] if index > 0 else row["close"]
        atr_values.append(max(
            row["high"] - row["low"],
            abs(row["high"] - previous_close),
            abs(row["low"] - previous_close),
        ))
    atr = median(atr_values) if atr_values else 0.0
    return median(slopes) / atr if slopes and atr > EPSILON else 0.0


def _structure_risks(
    tail: list[dict],
    baseline: list[dict],
    *,
    big_down_return: float,
    big_down_volume_ratio: float,
) -> list[str]:
    risks: list[str] = []
    baseline_volume = median(row["volume"] for row in baseline)
    for previous, current in zip(tail, tail[1:]):
        day_return = (current["close"] - previous["close"]) / previous["close"]
        if day_return <= big_down_return and current["volume"] >= baseline_volume * big_down_volume_ratio:
            risks.append("TAIL_REGIME_BIG_DOWN_VOLUME")
            break
    split = max(1, len(tail) // 2)
    if tail[split:]:
        early_low = min(row["low"] for row in tail[:split])
        late_low = min(row["low"] for row in tail[split:])
        if early_low > 0 and late_low < early_low * 0.99:
            risks.append("TAIL_REGIME_LOW_DETERIORATING")
    return risks


def _support_risks(rows: list[dict], key_support_price: float | None) -> list[str]:
    if not key_support_price or key_support_price <= 0 or len(rows) < 2:
        return []
    if rows[-2]["close"] < key_support_price and rows[-1]["close"] < key_support_price:
        return ["SUPPORT_TWO_CLOSE_BREAK"]
    return []
