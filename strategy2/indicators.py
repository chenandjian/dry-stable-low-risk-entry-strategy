# strategy2/indicators.py
"""策略2指标计算 — 只负责从策略窗口计算指标，不负责判断是否入选。

所有计算仅使用评估日 T 及之前的数据（data 末尾即为评估日）。
"""
import logging
from strategy2.models import IndicatorValidation, Strategy2Indicators

logger = logging.getLogger(__name__)


def validate_strategy_data(
    data: list[dict],
    strategy_window_days: int,
    min_required: int,
) -> IndicatorValidation:
    """校验日线数据是否满足策略2最低要求。

    Args:
        data: 日线数据列表（按日期升序）。
        strategy_window_days: 策略计算窗口天数。
        min_required: 最低有效数据天数。

    Returns:
        IndicatorValidation 结果。
    """
    if not data:
        return IndicatorValidation(
            valid=False, reason="INVALID_MARKET_DATA",
        )

    actual_days = len(data)

    # Check for missing or invalid values
    for d in data:
        close = d.get("close")
        volume = d.get("volume", 0)
        if close is None or volume is None:
            return IndicatorValidation(
                valid=False, data_days=actual_days,
                window_days=strategy_window_days,
                reason="INVALID_MARKET_DATA",
            )
        if not isinstance(close, (int, float)) or close <= 0:
            return IndicatorValidation(
                valid=False, data_days=actual_days,
                window_days=strategy_window_days,
                reason="INVALID_MARKET_DATA",
            )
        if not isinstance(volume, (int, float)) or volume < 0:
            return IndicatorValidation(
                valid=False, data_days=actual_days,
                window_days=strategy_window_days,
                reason="INVALID_MARKET_DATA",
            )

    if actual_days < min_required:
        return IndicatorValidation(
            valid=False, data_days=actual_days,
            window_days=strategy_window_days,
            reason="INSUFFICIENT_STRATEGY_DATA",
        )

    return IndicatorValidation(
        valid=True, data_days=actual_days, window_days=strategy_window_days,
    )


def compute_indicators(data: list[dict]) -> Strategy2Indicators:
    """在策略窗口数据上计算所有策略2指标。

    Args:
        data: 策略窗口内的日线数据（按日期升序），末尾为评估日 T。

    Returns:
        Strategy2Indicators 包含所有指标值。
    """
    n = len(data)

    def _avg_volume(window_size: int) -> float:
        """计算最近 window_size 日平均成交量。"""
        if window_size <= 0:
            return 0.0
        w = data[-window_size:] if n >= window_size else data
        if not w:
            return 0.0
        vols = [d["volume"] for d in w]
        return sum(vols) / len(vols)

    v3 = _avg_volume(3)
    v5 = _avg_volume(5)
    v10 = _avg_volume(10)
    v20 = _avg_volume(20)

    # volume_ratio_5_20
    volume_ratio_5_20 = v5 / v20 if v20 > 0 else 0.0

    # range_5: (5日最高 - 5日最低) / 5日最低
    recent_5 = data[-5:] if n >= 5 else data
    high_5 = max(d["high"] for d in recent_5)
    low_5 = min(d["low"] for d in recent_5)
    range_5 = (high_5 - low_5) / low_5 if low_5 > 0 else 0.0

    # close_range_5: (5日最高收盘 - 5日最低收盘) / 5日最低收盘
    close_high_5 = max(d["close"] for d in recent_5)
    close_low_5 = min(d["close"] for d in recent_5)
    close_range_5 = (close_high_5 - close_low_5) / close_low_5 if close_low_5 > 0 else 0.0

    # return_5: current_close / close_5_days_ago - 1
    current_close = data[-1]["close"]
    prev_idx_5 = n - 6  # 0-indexed, 5 trading days before
    if prev_idx_5 >= 0:
        return_5 = current_close / data[prev_idx_5]["close"] - 1
    elif n >= 2:
        return_5 = current_close / data[0]["close"] - 1
    else:
        return_5 = 0.0

    # return_3: current_close / close_3_days_ago - 1
    prev_idx_3 = n - 4  # 0-indexed, 3 trading days before
    if prev_idx_3 >= 0:
        return_3 = current_close / data[prev_idx_3]["close"] - 1
    elif n >= 2:
        return_3 = current_close / data[0]["close"] - 1
    else:
        return_3 = 0.0

    # daily_return: current / previous day
    if n >= 2:
        daily_return = current_close / data[-2]["close"] - 1
    else:
        daily_return = 0.0

    # 60日成交量分位
    lookback = min(60, n)
    vol_window = [d["volume"] for d in data[-lookback:]]
    recent_vols = [d["volume"] for d in recent_5]
    vol_pct = compute_volume_percentile(vol_window, recent_vols)

    return Strategy2Indicators(
        v3=v3,
        v5=v5,
        v10=v10,
        v20=v20,
        volume_ratio_5_20=volume_ratio_5_20,
        volume_percentile=vol_pct,
        volume_percentile_days=lookback,
        range_5=range_5,
        close_range_5=close_range_5,
        return_3=return_3,
        return_5=return_5,
        daily_return=daily_return,
    )


def compute_volume_percentile(
    volume_window: list[float],
    target_volumes: list[float],
) -> float:
    """计算目标成交量在参考窗口中的最低百分位。

    Args:
        volume_window: 参考窗口成交量列表（如近60日）。
        target_volumes: 待查询的成交量列表（取最小值判断分位）。

    Returns:
        百分位值 (0-100)，越小表示成交量越低。
    """
    if not volume_window or not target_volumes:
        return 50.0
    min_target = min(target_volumes)
    sorted_vols = sorted(volume_window)
    n = len(sorted_vols)
    count_le = sum(1 for v in sorted_vols if v <= min_target)
    return (count_le / n) * 100.0
