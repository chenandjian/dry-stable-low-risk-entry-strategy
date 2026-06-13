# strategy2/risk.py
"""策略2风险计算 — key_support、买入区间、止损、风险比。"""
import logging
from strategy2.models import Strategy2Risk

logger = logging.getLogger(__name__)


def compute_key_support(
    data: list[dict],
    lookback_days: int = 10,
) -> float | None:
    """计算关键支撑价：不含评估日的前 N 个交易日最低收盘价。

    Args:
        data: 策略窗口日线数据（按日期升序），末尾为评估日 T。
        lookback_days: 回看天数（不含评估日）。

    Returns:
        最低收盘价，数据不足时返回 None。
    """
    # 排除评估日（最后一行）
    before_eval = data[:-1]
    if not before_eval:
        return None

    # 取最近 lookback_days 个交易日
    window = before_eval[-lookback_days:] if len(before_eval) >= lookback_days else before_eval

    closes = [d["close"] for d in window if d.get("close") is not None and d["close"] > 0]
    if not closes:
        return None

    return min(closes)


def compute_buy_zone(
    key_support: float,
    buy_zone_max_premium: float = 0.03,
) -> tuple[float, float]:
    """计算买入区间。

    Returns:
        (buy_zone_low, buy_zone_high)
    """
    buy_zone_low = key_support
    buy_zone_high = key_support * (1 + buy_zone_max_premium)
    return buy_zone_low, buy_zone_high


def compute_risk(
    current_close: float,
    key_support: float,
    buy_zone_max_premium: float = 0.03,
    stop_loss_buffer: float = 0.03,
) -> Strategy2Risk:
    """计算关键支撑、买入区间、止损和风险比。

    Args:
        current_close: 评估日收盘价。
        key_support: 关键支撑价。
        buy_zone_max_premium: 买入区间最大溢价（默认 3%）。
        stop_loss_buffer: 止损缓冲比例（默认 3%）。

    Returns:
        Strategy2Risk 包含所有风险信息。
    """
    buy_low, buy_high = compute_buy_zone(key_support, buy_zone_max_premium)
    stop_loss = key_support * (1 - stop_loss_buffer)

    if current_close > 0:
        risk_ratio = (current_close - stop_loss) / current_close
    else:
        risk_ratio = 1.0  # handle zero/negative close safely

    # 风险等级
    if risk_ratio <= 0.03:
        risk_level = "低风险"
    elif risk_ratio <= 0.05:
        risk_level = "风险可接受"
    else:
        risk_level = "高风险"

    return Strategy2Risk(
        key_support=key_support,
        buy_zone_low=buy_low,
        buy_zone_high=buy_high,
        stop_loss=stop_loss,
        risk_ratio=risk_ratio,
        risk_level=risk_level,
    )
