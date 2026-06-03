# scanner/scorer.py
from scanner.pattern_detector import CupHandleResult


def score_cup_handle(result: CupHandleResult) -> int:
    """计算杯柄形态综合评分 (0-100)。

    评分维度:
      - 杯体结构: 35 分
      - 柄部结构: 25 分
      - 成交量结构: 20 分 (Phase 2 完善)
      - 前置上涨趋势: 10 分 (Phase 2 完善)
      - 突破确认: 10 分
    """
    if not result.found:
        return 0

    score = 0

    # 1. 杯体结构 (35 分)
    depth = result.cup_depth_pct
    if 12 <= depth <= 33:
        score += 10
    elif 33 < depth <= 45:
        score += 5
    elif depth < 12:
        score += 3

    dur = result.cup_duration
    if 50 <= dur <= 120:
        score += 8
    elif 35 <= dur <= 180:
        score += 4

    dev = result.lip_deviation_pct
    if dev <= 5:
        score += 7
    elif dev <= 8:
        score += 5
    elif dev <= 12:
        score += 3

    score += 6  # 杯底圆滑（Phase 1 默认中等分）

    # 2. 柄部结构 (25 分)
    h_dur = result.handle_duration
    if 5 <= h_dur <= 20:
        score += 8
    elif 20 < h_dur <= 30:
        score += 5

    h_depth = result.handle_depth_pct
    if h_depth <= 8:
        score += 10
    elif h_depth <= 12:
        score += 7
    elif h_depth <= 18:
        score += 3

    if h_depth <= 10:
        score += 7
    elif h_depth <= 15:
        score += 4

    # 3. 成交量结构 (20 分) - Phase 1 基础分
    score += 10

    # 4. 前置上涨趋势 (10 分) - Phase 1 基础分
    score += 6

    # 5. 突破确认 (10 分)
    if result.is_breakout and result.is_volume_breakout:
        score += 10
    elif result.is_breakout:
        score += 7
    else:
        score += 3

    return min(score, 100)
