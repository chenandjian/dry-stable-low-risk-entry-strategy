# strategy2/trend.py
"""策略2 V2 走势趋势过滤 — 价格路径 + 120日长期确认。

规则：
    必要条件：current_close < MA20 AND MA20 < MA60
    DOWNTREND = 必要条件
        AND short_mid_score >= 4 (8项)
        AND long_score >= 1 (3项)
        AND total_evidence_score >= 6

禁止使用 RETURN_60 / RETURN_120 端点收益作为下降证据。
"""
import logging
import statistics
from strategy2.models import Strategy2Trend

logger = logging.getLogger(__name__)


def _ols_slope(x: list[float], y: list[float]) -> float:
    """普通最小二乘斜率。"""
    n = len(x)
    if n < 2:
        return 0.0
    sx = sum(x)
    sy = sum(y)
    sxy = sum(xi * yi for xi, yi in zip(x, y))
    sxx = sum(xi * xi for xi in x)
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0
    return (n * sxy - sx * sy) / denom


def evaluate_trend(data: list[dict]) -> Strategy2Trend | None:
    """V2 价格路径 + 120日长期确认趋势评估。

    Args:
        data: 按日期升序的 OHLC 日线数据。

    Returns:
        Strategy2Trend（trend_type 可能为 INSUFFICIENT_TREND_DATA）。
    """
    if len(data) < 120:
        return Strategy2Trend(
            trend_type="INSUFFICIENT_TREND_DATA",
        )

    closes = [d["close"] for d in data]
    current_close = closes[-1]

    # ── 均线 ──
    ma20 = statistics.mean(closes[-20:])
    ma60 = statistics.mean(closes[-60:])
    ma120 = statistics.mean(closes[-120:])

    # ── 必要条件：close < MA20 AND MA20 < MA60 ──
    necessary_met = current_close < ma20 and ma20 < ma60

    # ── MA20斜率 ──
    ma20_minus_5 = statistics.mean(closes[-25:-5])
    if ma20_minus_5 <= 0:
        return Strategy2Trend(trend_type="INVALID_MARKET_DATA")
    ma20_slope = ma20 / ma20_minus_5 - 1.0

    # ── MA60斜率 ──
    ma60_minus_10 = statistics.mean(closes[-70:-10])
    ma60_slope = None
    if ma60_minus_10 > 0:
        ma60_slope = ma60 / ma60_minus_10 - 1.0

    # ── 60日高点回撤 ──
    closes_60 = closes[-60:]
    max_60 = max(closes_60)
    drawdown_60 = current_close / max_60 - 1.0 if max_60 > 0 else 0.0

    # ── 20日价格中枢变化 ──
    latest_20_center = statistics.mean(closes[-20:])
    previous_20_center = statistics.mean(closes[-40:-20])
    center_shift_20 = latest_20_center / previous_20_center - 1.0 if previous_20_center > 0 else 0.0

    # ── 60日价格区间位置 ──
    min_60 = min(closes_60)
    if max_60 == min_60:
        price_position_60 = 0.5
    else:
        price_position_60 = (current_close - min_60) / (max_60 - min_60)

    # ── 60日线性趋势 ──
    x = list(range(60))
    y_60 = closes[-60:]
    slope_60 = _ols_slope(x, y_60)
    linear_trend_60 = slope_60 * 59.0 / ma60 if ma60 > 0 else 0.0

    # ── 120日高点回撤 ──
    closes_120 = closes[-120:]
    max_120 = max(closes_120)
    drawdown_120 = current_close / max_120 - 1.0 if max_120 > 0 else 0.0

    # ── 40日价格中枢变化 ──
    latest_40_center = statistics.mean(closes[-40:])
    previous_40_center = statistics.mean(closes[-80:-40])
    center_shift_40 = latest_40_center / previous_40_center - 1.0 if previous_40_center > 0 else 0.0

    # ── 兼容旧字段 ──
    return_20 = current_close / closes[-21] - 1.0 if len(closes) >= 21 else 0.0
    return_60 = current_close / closes[-61] - 1.0

    # ── 短中期 8 项证据 ──
    conditions = []
    short_mid_score = 0

    if current_close < ma20:
        conditions.append("CLOSE_BELOW_MA20")
        short_mid_score += 1

    if ma20 < ma60:
        conditions.append("MA20_BELOW_MA60")
        short_mid_score += 1

    if ma20_slope < 0:
        conditions.append("MA20_SLOPE_NEGATIVE")
        short_mid_score += 1

    if ma60_slope is not None and ma60_slope < 0:
        conditions.append("MA60_SLOPE_NEGATIVE")
        short_mid_score += 1

    if drawdown_60 <= -0.12:
        conditions.append("DRAWDOWN_FROM_HIGH60_AT_LEAST_12_PERCENT")
        short_mid_score += 1

    if center_shift_20 <= -0.05:
        conditions.append("LATEST20_CENTER_BELOW_PREVIOUS20_BY_5_PERCENT")
        short_mid_score += 1

    if price_position_60 <= 0.3:
        conditions.append("PRICE_POSITION60_BOTTOM_30_PERCENT")
        short_mid_score += 1

    if linear_trend_60 <= -0.03:
        conditions.append("LINEAR_TREND60_BELOW_MINUS_3_PERCENT")
        short_mid_score += 1

    # ── 长期 3 项证据 ──
    long_score = 0

    if ma60 < ma120:
        conditions.append("MA60_BELOW_MA120")
        long_score += 1

    if drawdown_120 <= -0.18:
        conditions.append("DRAWDOWN_FROM_HIGH120_AT_LEAST_18_PERCENT")
        long_score += 1

    if center_shift_40 <= -0.06:
        conditions.append("LATEST40_CENTER_BELOW_PREVIOUS40_BY_6_PERCENT")
        long_score += 1

    total = short_mid_score + long_score

    # ── 判定 ──
    if necessary_met and short_mid_score >= 4 and long_score >= 1 and total >= 6:
        return Strategy2Trend(
            trend_type="DOWNTREND",
            short_mid_score=short_mid_score,
            long_score=long_score,
            total_evidence_score=total,
            necessary_conditions_met=True,
            ma20=ma20, ma60=ma60, ma120=ma120,
            ma20_slope=ma20_slope, ma60_slope=ma60_slope,
            drawdown_from_high_60=drawdown_60,
            center_shift_20=center_shift_20,
            price_position_60=price_position_60,
            linear_trend_60=linear_trend_60,
            drawdown_from_high_120=drawdown_120,
            center_shift_40=center_shift_40,
            return_20=return_20, return_60=return_60,
            downtrend_conditions=conditions,
        )

    return Strategy2Trend(
        trend_type="UPTREND_OR_SIDEWAYS",
        short_mid_score=short_mid_score,
        long_score=long_score,
        total_evidence_score=total,
        necessary_conditions_met=necessary_met,
        ma20=ma20, ma60=ma60, ma120=ma120,
        ma20_slope=ma20_slope, ma60_slope=ma60_slope,
        drawdown_from_high_60=drawdown_60,
        center_shift_20=center_shift_20,
        price_position_60=price_position_60,
        linear_trend_60=linear_trend_60,
        drawdown_from_high_120=drawdown_120,
        center_shift_40=center_shift_40,
        return_20=return_20, return_60=return_60,
        downtrend_conditions=conditions,
    )
