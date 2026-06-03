# analyzer/pattern_score.py
"""Pattern Score (形态评分) — 对杯柄或VCP形态评分, 0-20分。

取 cup_handle_score 和 vcp_score 中较高者。
"""
from dataclasses import dataclass
from scanner.pattern_detector import CupHandleResult


@dataclass
class PatternScoreResult:
    total_score: int = 0
    pattern_type: str = "无有效形态"
    cup_handle_score: int = 0
    vcp_score: int = 0
    details: list = None

    def __post_init__(self):
        if self.details is None:
            self.details = []


def score_pattern(result: CupHandleResult, data: list[dict]) -> PatternScoreResult:
    """Calculate pattern score (0-20).

    Currently supports cup handle scoring. VCP scoring is Phase 3.
    """
    r = PatternScoreResult()

    if not result.found:
        return r

    # Cup Handle Score (0-20)
    ch_score = _score_cup_handle_pattern(result, data)
    r.cup_handle_score = ch_score

    # VCP Score (0-20) — Phase 3
    r.vcp_score = 0

    r.total_score = max(ch_score, r.vcp_score)

    if r.total_score >= 17:
        r.pattern_type = "高质量杯柄" if ch_score >= r.vcp_score else "高质量VCP"
    elif r.total_score >= 13:
        r.pattern_type = "较成熟杯柄" if ch_score >= r.vcp_score else "较成熟VCP"
    elif r.total_score >= 8:
        r.pattern_type = "杯柄雏形" if ch_score >= r.vcp_score else "VCP雏形"
    else:
        r.pattern_type = "无有效形态"

    return r


def _score_cup_handle_pattern(result: CupHandleResult, data: list[dict]) -> int:
    """Cup Handle pattern score (0-20).

    Dimensions per strategy doc section 9:
      A. Prior uptrend (max 3 pts)
      B. Cup depth appropriate (max 3 pts)
      C. U-shaped bottom (max 3 pts)
      D. Right lip near left lip (max 2 pts)
      E. Handle position correct (max 3 pts)
      F. Handle pullback reasonable (max 2 pts)
      G. Handle volume contraction (max 2 pts)
      H. Handle end price stability (max 2 pts)
    """
    score = 0

    # A. Prior uptrend (max 3 pts)
    left_high = result.left_high_price
    if result.left_high_idx >= 60:
        pre_data = data[result.left_high_idx - 60:result.left_high_idx]
        pre_lows = [d["low"] for d in pre_data]
        if pre_lows:
            pre_low = min(pre_lows)
            if pre_low > 0:
                gain = (left_high - pre_low) / pre_low
                if gain >= 0.30:
                    score += 3
                elif gain >= 0.20:
                    score += 2
                elif gain >= 0.10:
                    score += 1

    # B. Cup depth appropriate (max 3 pts)
    depth = result.cup_depth_pct
    if 12 <= depth <= 33:
        score += 3
    elif 33 < depth <= 50:
        score += 1

    # C. U-shaped bottom (max 3 pts)
    cup_dur = result.cup_duration
    if cup_dur > 0 and result.left_high_idx >= 0 and result.right_high_idx >= 0:
        bottom_zone = [i for i in range(result.left_high_idx, result.right_high_idx)
                       if data[i]["close"] <= result.cup_low_price * 1.08]
        bottom_time_pct = len(bottom_zone) / cup_dur
        if bottom_time_pct >= 0.20:
            score += 3
        elif bottom_time_pct >= 0.10:
            score += 1

    # D. Right lip near left lip (max 2 pts)
    dev = result.lip_deviation_pct
    if dev <= 5:
        score += 2
    elif dev <= 10:
        score += 1

    # E. Handle position correct (upper half of cup) (max 3 pts)
    if result.left_high_price > result.cup_low_price:
        mid_point = result.cup_low_price + 0.5 * (result.left_high_price - result.cup_low_price)
        if result.handle_low_price >= mid_point:
            score += 3

    # F. Handle pullback reasonable (max 2 pts)
    h_depth = result.handle_depth_pct
    if h_depth <= 10:
        score += 2
    elif h_depth <= 15:
        score += 1

    # G. Handle volume contraction (max 2 pts)
    if result.right_high_idx >= 0 and result.handle_low_idx > result.right_high_idx:
        rh = result.right_high_idx
        hl = result.handle_low_idx
        recovery_vols = [data[i]["volume"] for i in range(result.cup_low_idx, rh)]
        handle_vols = [data[i]["volume"] for i in range(rh, hl)]
        if recovery_vols and handle_vols:
            avg_rec = sum(recovery_vols) / len(recovery_vols)
            avg_han = sum(handle_vols) / len(handle_vols)
            if avg_rec > 0 and avg_han <= avg_rec * 0.60:
                score += 2
            elif avg_rec > 0 and avg_han <= avg_rec * 0.80:
                score += 1

    # H. Handle end price stability (max 2 pts)
    if result.handle_low_idx >= 5:
        handle_ranges = []
        for i in range(result.handle_low_idx - 5, result.handle_low_idx):
            rng = (data[i]["high"] - data[i]["low"]) / data[i]["close"]
            handle_ranges.append(rng)
        if result.right_high_idx > result.cup_low_idx:
            recovery_ranges = []
            for i in range(result.cup_low_idx, result.right_high_idx):
                rng = (data[i]["high"] - data[i]["low"]) / data[i]["close"]
                recovery_ranges.append(rng)
            if handle_ranges and recovery_ranges:
                avg_h_rng = sum(handle_ranges) / len(handle_ranges)
                avg_r_rng = sum(recovery_ranges) / len(recovery_ranges)
                if avg_r_rng > 0 and avg_h_rng <= avg_r_rng * 0.70:
                    score += 2
                elif avg_r_rng > 0 and avg_h_rng <= avg_r_rng * 0.90:
                    score += 1

    return min(score, 20)
