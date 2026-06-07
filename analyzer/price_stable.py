# analyzer/price_stable.py
"""Price Stability Score (价稳评分) — 判断价格是否停止下跌并进入窄幅稳定区间。

Scoring dimensions (0-10):
  A. Range contraction (max 2 pts)
  B. No new lows (max 2 pts)
  C. Higher lows (max 2 pts)
  D. Close above key MA/support (max 2 pts)
  E. ATR declining (max 2 pts)

Hard rule: score < 6 → can NOT be "可低吸"
New low cap: if any close in last 5 days is a new 20-day low → cap at 5
Increasing amplitude cap: consecutive declining with increasing amplitude → cap at 5
Support break cap: close below handle_low / MA50 → cap at 5
"""

from dataclasses import dataclass, field

DEFAULT_PS_CFG = {
    "close_tightness_strong_pct": 3,
    "close_tightness_normal_pct": 5,
    "support_break_max_score": 5,
}


@dataclass
class PriceStableResult:
    total_score: int = 0
    raw_score: int = 0
    sub_scores: dict = field(default_factory=dict)
    verdict: str = "不建议买入"
    details: list = field(default_factory=list)
    caps: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    positive_factors: list = field(default_factory=list)
    reject_reasons: list = field(default_factory=list)
    # Auxiliary fields
    close_tightness_5d: float = 0.0
    close_position_5d_avg: float = 0.0


def _avg(seq):
    if not seq:
        return 0.0
    return sum(seq) / len(seq)


def _ma(values, n):
    if len(values) < n:
        return [0] * len(values)
    result = []
    for i in range(len(values)):
        if i < n - 1:
            result.append(_avg(values[:i + 1]))
        else:
            result.append(_avg(values[i - n + 1:i + 1]))
    return result


def _atr(data, n=14):
    """Calculate Average True Range."""
    if len(data) < 2:
        return [0] * len(data)
    tr = []
    for i in range(1, len(data)):
        high = data[i]["high"]
        low = data[i]["low"]
        prev_close = data[i - 1]["close"]
        tr.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    tr.insert(0, tr[0] if tr else 0)
    return _ma(tr, n)


def score_price_stable(data: list[dict], config: dict | None = None,
                       handle_low: float = 0) -> PriceStableResult:
    """Calculate Price Stability Score from daily OHLC data.

    Requires at least 30 trading days of data.

    Args:
        config: 来自 config.yaml 的 price_stable 段。
        handle_low: 柄部低点价格，用于支撑跌破封顶（0 表示不检查）。
    """
    cfg = {**DEFAULT_PS_CFG, **(config or {})}
    result = PriceStableResult()

    if not data or len(data) < 30:
        return result

    closes = [d["close"] for d in data]
    highs = [d["high"] for d in data]
    lows = [d["low"] for d in data]
    n = len(data)

    score = 0

    # A. Range contraction (max 2 pts)
    ranges = [(highs[i] - lows[i]) / closes[i] for i in range(n) if closes[i] > 0]
    range5 = _avg(ranges[-5:]) if len(ranges) >= 5 else 0
    range20 = _avg(ranges[-20:]) if len(ranges) >= 20 else 0
    score_a = 0
    if range20 > 0:
        ratio_a = range5 / range20
        if ratio_a <= 0.60:
            score_a = 2
            result.details.append(f"Range5/Range20={ratio_a:.2f} <= 0.60: +2")
        elif ratio_a <= 0.80:
            score_a = 1
            result.details.append(f"Range5/Range20={ratio_a:.2f} <= 0.80: +1")
        else:
            result.details.append(f"Range5/Range20={ratio_a:.2f} > 0.80: +0")
    result.sub_scores["A_range_contraction"] = score_a
    score += score_a

    # B. No new lows (max 2 pts)
    score_b = 0
    low10 = min(lows[-10:]) if len(lows) >= 10 else 0
    prev_low20 = min(lows[-30:-10]) if len(lows) >= 30 else low10 * 1.1
    if prev_low20 > 0:
        if low10 > prev_low20:
            score_b = 2
            result.details.append("Low10 > PrevLow20: +2")
        elif low10 >= prev_low20 * 0.98:
            score_b = 1
            result.details.append(f"Low10({low10:.2f}) >= PrevLow20({prev_low20:.2f})*0.98: +1")
        else:
            result.details.append(f"Low10({low10:.2f}) < PrevLow20({prev_low20:.2f})*0.98: +0")
    result.sub_scores["B_no_new_lows"] = score_b
    score += score_b

    # C. Higher lows (max 2 pts)
    score_c = 0
    local_lows = []
    for i in range(5, n - 5):
        left_min = min(lows[i - 5:i])
        right_min = min(lows[i + 1:i + 6])
        if lows[i] < left_min and lows[i] < right_min:
            local_lows.append((i, lows[i]))

    if len(local_lows) >= 2:
        ll1 = local_lows[-2][1]
        ll2 = local_lows[-1][1]
        if ll2 > ll1:
            score_c = 2
            result.details.append("LocalLow2 > LocalLow1: +2")
        elif ll2 >= ll1 * 0.98:
            score_c = 1
            result.details.append(f"LocalLow2 >= LocalLow1*0.98: +1")
        else:
            result.details.append("LocalLow2 < LocalLow1: +0")
    result.sub_scores["C_higher_lows"] = score_c
    score += score_c

    # D. Close above MA20 (max 2 pts) — optimized: count days
    score_d = 0
    ma20 = _ma(closes, 20)
    above_count = sum(1 for i in range(n - 5, n) if closes[i] >= ma20[i])
    if above_count >= 4:
        score_d = 2
        result.details.append(f"{above_count}/5 days above MA20: +2")
    elif above_count >= 3 and closes[-1] >= ma20[-1]:
        score_d = 1
        result.details.append(f"{above_count}/5 days above MA20, last above: +1")
    else:
        result.details.append(f"{above_count}/5 days above MA20: +0")
    result.sub_scores["D_above_support"] = score_d
    score += score_d

    # E. ATR declining (max 2 pts)
    score_e = 0
    atr_vals = _atr(data, 14)
    atr5 = _avg(atr_vals[-5:]) if len(atr_vals) >= 5 else 0
    atr20 = _avg(atr_vals[-20:]) if len(atr_vals) >= 20 else 0
    if atr20 > 0:
        ratio_e = atr5 / atr20
        if ratio_e <= 0.75:
            score_e = 2
            result.details.append(f"ATR5/ATR20={ratio_e:.2f} <= 0.75: +2")
        elif ratio_e <= 0.90:
            score_e = 1
            result.details.append(f"ATR5/ATR20={ratio_e:.2f} <= 0.90: +1")
        else:
            result.details.append(f"ATR5/ATR20={ratio_e:.2f} > 0.90: +0")
    result.sub_scores["E_atr_declining"] = score_e
    score += score_e

    result.raw_score = min(score, 10)
    result.total_score = result.raw_score

    # --- Auxiliary indicators ---

    # Close tightness
    if len(closes) >= 5:
        close5 = closes[-5:]
        max_c5, min_c5 = max(close5), min(close5)
        if min_c5 > 0:
            result.close_tightness_5d = round(max_c5 / min_c5 - 1, 4)
            tight_strong = float(cfg["close_tightness_strong_pct"]) / 100
            tight_normal = float(cfg["close_tightness_normal_pct"]) / 100
            if result.close_tightness_5d <= tight_strong:
                result.positive_factors.append(f"近5日收盘波动≤{cfg['close_tightness_strong_pct']}%，价格紧致")
            elif result.close_tightness_5d <= tight_normal:
                result.positive_factors.append(f"近5日收盘波动≤{cfg['close_tightness_normal_pct']}%，价格较紧致")

    # Close position
    close_positions = []
    for i in range(max(0, n - 5), n):
        if highs[i] > lows[i]:
            close_positions.append((closes[i] - lows[i]) / (highs[i] - lows[i]))
    if close_positions:
        result.close_position_5d_avg = round(_avg(close_positions), 2)
        if result.close_position_5d_avg >= 0.6:
            result.positive_factors.append("近5日收盘位置偏强，买盘承接明显")

    # --- Capping rules ---

    # 1. New 20-day low cap
    close_low20 = min(closes[-20:]) if len(closes) >= 20 else 0
    for i in range(n - 5, n):
        if closes[i] <= close_low20 * 0.99:
            result.total_score = min(result.total_score, 5)
            result.caps.append("近5日出现20日新低，价稳最高5分")
            result.reject_reasons.append("近5日出现20日新低，价格尚未稳定")
            break

    # 2. Consecutive declining with increasing amplitude
    for i in range(n - 3, n):
        if i > 0 and closes[i] < closes[i - 1]:
            if i > 1 and closes[i - 1] < closes[i - 2]:
                drop1 = abs(closes[i - 1] - closes[i - 2])
                drop2 = abs(closes[i] - closes[i - 1])
                if drop2 > drop1:
                    result.total_score = min(result.total_score, 5)
                    result.caps.append("连续下跌且跌幅放大，价稳最高5分")
                    break

    # 3. Support break cap
    support_broken = False
    if handle_low > 0 and closes[-1] < handle_low:
        support_broken = True
    if closes[-1] < ma20[-1] * 0.98 if len(ma20) > 0 else False:
        support_broken = True
    if support_broken:
        cap = int(cfg["support_break_max_score"])
        result.total_score = min(result.total_score, cap)
        result.caps.append(f"跌破关键支撑，价稳最高{cap}分")
        result.reject_reasons.append("跌破关键支撑，价格尚未稳定")

    # Verdict
    if result.total_score >= 7:
        result.verdict = "可低吸"
    elif result.total_score >= 6:
        result.verdict = "观察"
    else:
        result.verdict = "不建议买入"

    return result
