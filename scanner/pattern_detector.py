# scanner/pattern_detector.py
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class CupHandleResult:
    """杯柄检测结果"""
    found: bool = False
    code: str = ""
    name: str = ""

    # 关键点索引
    left_high_idx: int = -1
    cup_low_idx: int = -1
    right_high_idx: int = -1
    handle_low_idx: int = -1

    # 关键点日期
    left_high_date: str = ""
    cup_low_date: str = ""
    right_high_date: str = ""
    handle_low_date: str = ""

    # 关键点价格
    left_high_price: float = 0.0
    cup_low_price: float = 0.0
    right_high_price: float = 0.0
    handle_low_price: float = 0.0

    # 结构参数
    cup_duration: int = 0
    cup_depth_pct: float = 0.0
    handle_duration: int = 0
    handle_depth_pct: float = 0.0
    lip_deviation_pct: float = 0.0

    # 突破判断
    is_breakout: bool = False
    is_volume_breakout: bool = False
    breakout_price: float = 0.0
    vol_multiplier: float = 0.0

    # 元数据
    score: int = 0
    rating: str = ""


def find_swing_highs(closes: list[float], window: int = 5) -> list[int]:
    """找出局部高点索引。

    一个点被认为是 Swing High 当它在左右各 window 天内都是最高价。
    """
    if len(closes) < 2 * window + 1:
        return []

    highs = []
    n = len(closes)
    for i in range(window, n - window):
        left_max = max(closes[i - window:i])
        right_max = max(closes[i + 1:i + window + 1])
        if closes[i] > left_max and closes[i] > right_max:
            highs.append(i)
    return highs


def find_swing_lows(lows: list[float], window: int = 5) -> list[int]:
    """找出局部低点索引。"""
    if len(lows) < 2 * window + 1:
        return []

    result = []
    n = len(lows)
    for i in range(window, n - window):
        left_min = min(lows[i - window:i])
        right_min = min(lows[i + 1:i + window + 1])
        if lows[i] < left_min and lows[i] < right_min:
            result.append(i)
    return result


def detect_cup_handle(data: list[dict], config: dict) -> CupHandleResult:
    """检测单只股票是否存在杯柄结构。

    Args:
        data: 日线数据，按日期升序，长度 >= 250
        config: cup + handle + breakout 配置合并字典

    Returns:
        CupHandleResult
    """
    result = CupHandleResult()

    if len(data) < 120:
        return result

    closes = [d["close"] for d in data]
    highs_px = [d["high"] for d in data]
    lows_px = [d["low"] for d in data]

    # Step 1: 找 Swing 点
    sw_highs = find_swing_highs(closes, window=5)
    sw_lows = find_swing_lows(lows_px, window=5)

    if len(sw_highs) < 2 or len(sw_lows) < 1:
        return result

    # Step 2: 遍历可能的杯体组合
    cup_min_dur = config.get("min_duration", 35)
    cup_max_dur = config.get("max_duration", 180)
    min_depth = config.get("min_depth", 0.12)
    max_depth = config.get("max_depth", 0.45)
    max_lip_dev = config.get("max_lip_deviation", 0.12)

    best = None
    best_score = 0.0

    for lh_idx in sw_highs:
        left_high = closes[lh_idx]
        for cl_idx in sw_lows:
            cup_low = lows_px[cl_idx]
            if cl_idx <= lh_idx:
                continue
            cup_dur = cl_idx - lh_idx
            if cup_dur < cup_min_dur or cup_dur > cup_max_dur:
                continue
            depth = (left_high - cup_low) / left_high
            if depth < min_depth or depth > max_depth:
                continue

            for rh_idx in sw_highs:
                if rh_idx <= cl_idx:
                    continue
                right_high = closes[rh_idx]
                lip_dev = abs(right_high - left_high) / left_high
                if lip_dev > max_lip_dev:
                    continue
                right_dur = rh_idx - cl_idx
                if right_dur < cup_dur * 0.25:
                    continue

                # 杯底圆滑度
                bottom_zone = [i for i in range(lh_idx, rh_idx) if closes[i] <= cup_low * 1.08]
                roundness = len(bottom_zone) / cup_dur if cup_dur > 0 else 0
                min_round = config.get("min_bottom_roundness", 0.15)
                if roundness < min_round:
                    continue

                # 找柄部
                handle_info = _find_handle(
                    data, config,
                    right_high_idx=rh_idx,
                    cup_low_idx=cl_idx,
                    right_high=right_high,
                    cup_low=cup_low,
                )
                if handle_info is None:
                    continue

                # 综合评分
                cup_quality = _score_cup(depth, cup_dur, lip_dev, roundness)
                handle_quality = handle_info["quality"]
                total = cup_quality * 0.5 + handle_quality * 0.3

                if total > best_score:
                    best_score = total
                    best = {
                        "left_high_idx": lh_idx,
                        "cup_low_idx": cl_idx,
                        "right_high_idx": rh_idx,
                        "handle_low_idx": handle_info["low_idx"],
                        "left_high_price": left_high,
                        "cup_low_price": cup_low,
                        "right_high_price": right_high,
                        "handle_low_price": handle_info["low_price"],
                        "cup_duration": cup_dur,
                        "cup_depth_pct": round(depth * 100, 1),
                        "handle_duration": handle_info["duration"],
                        "handle_depth_pct": round(handle_info["depth_pct"] * 100, 1),
                        "lip_deviation_pct": round(lip_dev * 100, 1),
                        "is_breakout": handle_info.get("is_breakout", False),
                        "is_volume_breakout": handle_info.get("is_volume_breakout", False),
                        "vol_multiplier": round(handle_info.get("vol_multiplier", 0), 1),
                        "breakout_price": max(left_high, right_high),
                    }

    if best is None:
        return result

    result.found = True
    for k, v in best.items():
        setattr(result, k, v)
    result.left_high_date = data[best["left_high_idx"]]["date"]
    result.cup_low_date = data[best["cup_low_idx"]]["date"]
    result.right_high_date = data[best["right_high_idx"]]["date"]
    result.handle_low_date = data[best["handle_low_idx"]]["date"]

    return result


def _find_handle(data, config, right_high_idx, cup_low_idx, right_high, cup_low):
    """在右杯口之后寻找柄部结构。"""
    n = len(data)
    min_dur = config.get("handle_min_duration", 5)
    max_dur = config.get("handle_max_duration", 30)
    max_depth = config.get("handle_max_depth", 0.18)
    max_vs_right = config.get("handle_max_vs_right_rally", 0.50)

    if right_high_idx >= n - min_dur:
        return None

    right_rally = right_high - cup_low
    search_end = min(right_high_idx + max_dur + 10, n)
    low_idx = right_high_idx + 1
    low_price = float("inf")

    for i in range(right_high_idx + 1, search_end):
        if data[i]["low"] < low_price:
            low_price = data[i]["low"]
            low_idx = i

    duration = low_idx - right_high_idx
    if duration < min_dur or duration > max_dur:
        return None

    depth = (right_high - low_price) / right_high
    if depth > max_depth:
        return None

    if right_rally > 0 and (right_high - low_price) / right_rally > max_vs_right:
        return None

    quality = max(0, (max_depth - depth) / max_depth)

    # 检查突破（从配置读取阈值）
    buffer = 1 + config.get("buffer_pct", 0.02)
    vol_threshold = config.get("volume_multiplier", 1.5)
    latest = data[-1]
    is_breakout = latest["close"] > right_high * buffer
    is_vol_breakout = False
    vol_mult = 0.0

    if is_breakout:
        recent_vols = [d["volume"] for d in data[-20:]]
        avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 0
        if avg_vol > 0:
            vol_mult = latest["volume"] / avg_vol
            is_vol_breakout = vol_mult >= vol_threshold

    return {
        "low_idx": low_idx,
        "low_price": low_price,
        "duration": duration,
        "depth_pct": depth,
        "quality": quality,
        "is_breakout": is_breakout,
        "is_volume_breakout": is_vol_breakout,
        "vol_multiplier": vol_mult,
    }


def _score_cup(depth: float, duration: int, lip_dev: float, roundness: float) -> float:
    """杯体质量评分（0-1 归一化）。"""
    s = 0.0
    if 0.12 <= depth <= 0.33:
        s += 0.4
    elif 0.33 < depth <= 0.45:
        s += 0.2
    if 50 <= duration <= 120:
        s += 0.2
    elif 35 <= duration <= 180:
        s += 0.1
    if lip_dev <= 0.05:
        s += 0.2
    elif lip_dev <= 0.12:
        s += 0.1
    if roundness >= 0.20:
        s += 0.2
    elif roundness >= 0.15:
        s += 0.1
    return min(s, 1.0)
