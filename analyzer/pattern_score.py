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
    vcp_contractions: int = 0
    details: list = None

    def __post_init__(self):
        if self.details is None:
            self.details = []


def score_pattern(result: CupHandleResult, data: list[dict]) -> PatternScoreResult:
    """Calculate pattern score (0-20)."""
    r = PatternScoreResult()

    if not data:
        return r

    # Cup Handle Score (0-20)
    ch_score = _score_cup_handle_pattern(result, data) if result.found else 0
    r.cup_handle_score = ch_score

    # VCP Score (0-20)
    vcp_result = _score_vcp_pattern(data)
    r.vcp_score = vcp_result[0]
    r.vcp_contractions = vcp_result[1]

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


def _score_vcp_pattern(data: list[dict]) -> tuple[int, int]:
    """VCP score (0-20) per dry-stable strategy section 10.

    Returns (score, contraction_count).
    """
    if not data or len(data) < 60:
        return 0, 0

    closes = [d["close"] for d in data]
    lows = [d["low"] for d in data]
    volumes = [d["volume"] for d in data]
    contractions = _find_vcp_contractions(data)
    if not contractions:
        return 0, 0

    score = 0
    first_high_idx = contractions[0]["high_idx"]
    first_high = contractions[0]["high"]

    # A. Prior uptrend (max 3 pts)
    if first_high_idx >= 20:
        start = max(0, first_high_idx - 60)
        pre_low = min(lows[start:first_high_idx])
        if pre_low > 0:
            gain = (first_high - pre_low) / pre_low
            if gain >= 0.30:
                score += 3
            elif gain >= 0.20:
                score += 2
            elif gain >= 0.10:
                score += 1

    # B. Number of contractions (max 4 pts)
    if len(contractions) >= 3:
        score += 4
    elif len(contractions) >= 2:
        score += 3
    elif len(contractions) == 1:
        score += 1

    # C. Pullback amplitude decreasing (max 4 pts)
    depths = [c["depth"] for c in contractions[-4:]]
    decreasing_pairs = sum(1 for a, b in zip(depths, depths[1:]) if b < a)
    if len(depths) >= 2 and decreasing_pairs == len(depths) - 1:
        score += 4
    elif len(depths) >= 2 and decreasing_pairs >= max(1, len(depths) - 2):
        score += 2

    # D. Volume decreases across contractions (max 4 pts)
    avg_vols = [c["avg_volume"] for c in contractions[-4:]]
    vol_decreasing_pairs = sum(1 for a, b in zip(avg_vols, avg_vols[1:]) if b < a)
    if len(avg_vols) >= 2 and vol_decreasing_pairs == len(avg_vols) - 1:
        score += 4
    elif len(avg_vols) >= 2 and avg_vols[-1] < avg_vols[-2]:
        score += 2

    # E. Pivot clarity and distance (max 3 pts)
    pivot = _vcp_pivot(data, contractions)
    current = closes[-1]
    if pivot > 0:
        dist = abs(pivot - current) / pivot
        if dist <= 0.05:
            score += 3
        elif dist <= 0.10:
            score += 1

    # F. Small stop distance (max 2 pts)
    last_low = contractions[-1]["low"]
    if current > 0 and last_low > 0:
        risk = (current - last_low) / current
        if 0 <= risk <= 0.06:
            score += 2
        elif 0 <= risk <= 0.08:
            score += 1

    return min(score, 20), len(contractions)


def _find_vcp_contractions(data: list[dict]) -> list[dict]:
    """Find recent high-to-low contractions using local extrema."""
    closes = [d["close"] for d in data]
    lows = [d["low"] for d in data]
    volumes = [d["volume"] for d in data]
    start_idx = max(0, len(data) - 120)
    highs = _local_extrema(closes, start_idx, is_high=True)
    lows_idx = _local_extrema(lows, start_idx, is_high=False)

    contractions = []
    for hi in highs:
        next_lows = [lo for lo in lows_idx if hi < lo <= hi + 35]
        if not next_lows:
            continue
        lo = next_lows[0]
        high = closes[hi]
        low = lows[lo]
        if high <= 0 or low <= 0 or low >= high:
            continue
        depth = (high - low) / high
        if depth < 0.03 or depth > 0.40:
            continue
        avg_volume = sum(volumes[hi:lo + 1]) / (lo - hi + 1)
        contractions.append({
            "high_idx": hi,
            "low_idx": lo,
            "high": high,
            "low": low,
            "depth": depth,
            "avg_volume": avg_volume,
        })

    # Remove overlapping contractions and keep the most recent 4.
    filtered = []
    last_low_idx = -1
    for c in contractions:
        if c["high_idx"] > last_low_idx:
            filtered.append(c)
            last_low_idx = c["low_idx"]
    return filtered[-4:]


def _local_extrema(values: list[float], start_idx: int, is_high: bool, window: int = 2) -> list[int]:
    result = []
    end = len(values) - window
    for i in range(max(window, start_idx), end):
        left = values[i - window:i]
        right = values[i + 1:i + window + 1]
        if is_high and values[i] >= max(left) and values[i] >= max(right):
            result.append(i)
        elif not is_high and values[i] <= min(left) and values[i] <= min(right):
            result.append(i)
    return result


def _vcp_pivot(data: list[dict], contractions: list[dict]) -> float:
    if contractions:
        last_low_idx = contractions[-1]["low_idx"]
        prior_highs = [c["high"] for c in contractions if c["high_idx"] < last_low_idx]
        if prior_highs:
            recent_platform = max(d["close"] for d in data[-20:])
            return min(max(prior_highs[-1], recent_platform), max(prior_highs))
    return max(d["close"] for d in data[-20:]) if len(data) >= 20 else 0.0


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
