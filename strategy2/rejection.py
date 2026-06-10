# strategy2/rejection.py
"""策略2一票否决规则 — 返回稳定错误码列表，空列表表示未触发任何否决。"""
import logging
from strategy2.models import Strategy2Indicators

logger = logging.getLogger(__name__)


def check_rejection_rules(
    ind: Strategy2Indicators,
    data: list[dict],
    key_support: float,
    current_close: float,
    v20: float,
) -> list[str]:
    """执行5条一票否决规则。

    Args:
        ind: 指标计算结果。
        data: 策略窗口日线数据（按日期升序，用于检查单日跌幅）。
        key_support: 关键支撑价。
        current_close: 评估日收盘价。
        v20: V20 平均成交量（用于放量判断）。

    Returns:
        命中的否决规则稳定错误码列表。空列表 = 未触发任何否决。
    """
    rejects = []

    # 1. 量干但 return_5 < -5%
    if ind.return_5 < -0.05:
        rejects.append("REJECT_VOLUME_DRY_PRICE_DROP")
        logger.debug("Reject: return_5=%.4f < -5%%", ind.return_5)

    # 2. 最近5日任一单日跌幅 <= -4% 且该日成交量 > V20
    if len(data) >= 5 and v20 > 0:
        recent_5 = data[-5:]
        for i in range(1, len(recent_5)):
            prev_close = recent_5[i - 1]["close"]
            curr_close = recent_5[i]["close"]
            curr_vol = recent_5[i]["volume"]
            if prev_close > 0:
                daily_change = curr_close / prev_close - 1
                if daily_change <= -0.04 and curr_vol > v20:
                    rejects.append("REJECT_HEAVY_VOLUME_DROP")
                    logger.debug(
                        "Reject: day %s drop=%.4f vol=%.0f > V20=%.0f",
                        recent_5[i].get("date", "?"), daily_change, curr_vol, v20,
                    )
                    break

    # 3. range_5 > 8%
    if ind.range_5 > 0.08:
        rejects.append("REJECT_RANGE_TOO_WIDE")
        logger.debug("Reject: range_5=%.4f > 8%%", ind.range_5)

    # 4. 当前收盘价低于 key_support
    if current_close < key_support:
        rejects.append("REJECT_SUPPORT_BROKEN")
        logger.debug(
            "Reject: current_close=%.2f < key_support=%.2f",
            current_close, key_support,
        )

    # 5. return_3 >= 8%
    if ind.return_3 >= 0.08:
        rejects.append("REJECT_RECENT_SURGE")
        logger.debug("Reject: return_3=%.4f >= 8%%", ind.return_3)

    return rejects
