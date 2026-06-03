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


# ---- Phase 2 Enhanced Scoring ----


def _score_volume_structure(data: list[dict], result: CupHandleResult) -> int:
    """4-stage volume analysis:
    - Cup bottom drying (6 pts): cup bottom avg vol < left descent avg vol
    - Right recovery pickup (5 pts): right rally avg vol > cup bottom avg vol
    - Handle contraction (4 pts): handle avg vol < right lip area avg vol
    - Breakout surge (5 pts): latest vol >= 1.5x 20-day avg vol
    """
    if not data or len(data) < 60:
        return 10  # fallback

    volumes = [d["volume"] for d in data]
    score = 0
    bottom_vols: list[float] = []

    # Stage 1: Cup bottom drying (6 pts)
    lh = result.left_high_idx
    cl = result.cup_low_idx
    if lh >= 0 and cl > lh:
        # Left descent = from left high to cup low
        mid = (lh + cl) // 2
        descent_vols = volumes[lh:mid] if mid > lh else []
        bottom_vols = volumes[mid:cl] if cl > mid else []
        if descent_vols and bottom_vols:
            avg_descent = sum(descent_vols) / len(descent_vols)
            avg_bottom = sum(bottom_vols) / len(bottom_vols)
            if avg_descent > 0 and avg_bottom < avg_descent * 0.85:
                score += 6
            elif avg_descent > 0 and avg_bottom < avg_descent:
                score += 3

    # Stage 2: Right recovery pickup (5 pts)
    rh = result.right_high_idx
    if cl >= 0 and rh > cl:
        recovery_vols = volumes[cl:rh]
        if recovery_vols and bottom_vols:
            avg_recovery = sum(recovery_vols) / len(recovery_vols)
            if avg_recovery > avg_bottom * 1.1:
                score += 5
            elif avg_recovery > avg_bottom:
                score += 2

    # Stage 3: Handle contraction (4 pts)
    hl = result.handle_low_idx
    if rh >= 0 and hl > rh:
        # Right lip area: around right high
        lip_start = max(0, rh - 5)
        lip_vols = volumes[lip_start:rh]
        handle_vols = volumes[rh:hl]
        if lip_vols and handle_vols:
            avg_lip = sum(lip_vols) / len(lip_vols)
            avg_handle = sum(handle_vols) / len(handle_vols)
            if avg_lip > 0 and avg_handle < avg_lip * 0.7:
                score += 4
            elif avg_lip > 0 and avg_handle < avg_lip * 0.9:
                score += 2

    # Stage 4: Breakout surge (5 pts)
    if result.is_volume_breakout:
        score += 5
    elif result.is_breakout:
        if result.vol_multiplier >= 1.2:
            score += 3
        else:
            score += 1

    return min(score, 20)


def _score_pre_trend(data: list[dict], result: CupHandleResult) -> int:
    """Analyze 60-day trend before left cup high.
    - >= 25% gain from low to left high: 10 pts
    - 15-25%: 7 pts
    - 10-15%: 4 pts
    - < 10%: 0 pts
    """
    if not data or result.left_high_idx < 60:
        return 6  # fallback

    lh = result.left_high_idx
    pre_start = max(0, lh - 60)
    pre_data = data[pre_start:lh]
    pre_lows = [d["low"] for d in pre_data]

    if not pre_lows:
        return 6

    pre_low = min(pre_lows)
    left_high = result.left_high_price

    if pre_low <= 0:
        return 6

    gain = (left_high - pre_low) / pre_low

    if gain >= 0.25:
        return 10
    elif gain >= 0.15:
        return 7
    elif gain >= 0.10:
        return 4
    return 0


def score_cup_handle_advanced(result: CupHandleResult, data: list[dict]) -> int:
    """Enhanced scoring with volume structure and pre-trend analysis.

    Args:
        result: CupHandleResult from pattern detector
        data: full OHLC data (list of dicts with date/open/high/low/close/volume)

    Returns:
        score 0-100
    """
    if not result.found:
        return 0

    score = 0

    # 1. Cup body structure (35 pts) - same as basic
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

    # Cup bottom roundness - keep flat for now
    score += 6

    # 2. Handle structure (25 pts) - same as basic
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

    # 3. Volume structure (20 pts) - ENHANCED
    score += _score_volume_structure(data, result)

    # 4. Pre-trend (10 pts) - ENHANCED
    score += _score_pre_trend(data, result)

    # 5. Breakout (10 pts) - same as basic
    if result.is_breakout and result.is_volume_breakout:
        score += 10
    elif result.is_breakout:
        score += 7
    else:
        score += 3

    return min(score, 100)
