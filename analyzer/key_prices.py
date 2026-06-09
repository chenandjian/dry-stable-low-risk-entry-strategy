# analyzer/key_prices.py
"""Key Price Calculator — 计算低吸区间、Pivot枢纽点、止损价、止盈价。"""

from dataclasses import dataclass

from analyzer.pattern_score import _find_vcp_contractions, _vcp_pivot


@dataclass
class KeyPricesResult:
    current_price: float = 0.0
    entry_zone_low: float = 0.0
    entry_zone_high: float = 0.0
    pivot: float = 0.0
    stop_loss: float = 0.0
    target_1: float = 0.0
    target_2: float = 0.0


def calculate_key_prices(result, data: list[dict], pattern_type: str = "cup_handle") -> KeyPricesResult:
    """Calculate key price levels based on detected pattern."""
    r = KeyPricesResult()

    if not data or (pattern_type == "cup_handle" and not result.found):
        return r

    latest = data[-1]
    r.current_price = latest["close"]

    if pattern_type == "cup_handle":
        # Entry zone: near handle low, bounded by MA10 and MA20
        handle_low = result.handle_low_price
        r.entry_zone_low = round(handle_low * 1.01, 2)

        # MA10 and MA20 for upper bound
        closes = [d["close"] for d in data]
        ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else r.current_price
        ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else r.current_price
        r.entry_zone_high = round(min(handle_low * 1.05, ma10 * 1.02, ma20 * 1.03), 2)

        # Pivot = handle high; stricter variant uses the highest close in handle.
        handle_start = result.right_high_idx + 1
        handle_end = max(handle_start + 1, len(data) - 1)
        handle_closes = [d["close"] for d in data[handle_start:handle_end]]
        handle_high = max(handle_closes) if handle_closes else result.right_high_price
        r.pivot = round(handle_high, 2)

        # Stop loss
        atr14 = _calc_atr(data, 14)
        r.stop_loss = round(min(handle_low * 0.98, handle_low - 0.5 * atr14), 2)
    elif pattern_type == "vcp":
        contractions = _find_vcp_contractions(data)
        if not contractions:
            return r
        last_low = contractions[-1]["low"]
        r.entry_zone_low = round(last_low * 1.01, 2)

        closes = [d["close"] for d in data]
        ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else r.current_price
        ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else r.current_price
        r.entry_zone_high = round(min(last_low * 1.05, ma10 * 1.02, ma20 * 1.03), 2)
        r.pivot = round(_vcp_pivot(data, contractions), 2)

        atr14 = _calc_atr(data, 14)
        recent_swing_low = min(d["low"] for d in data[-10:])
        r.stop_loss = round(min(last_low * 0.98, recent_swing_low - 0.5 * atr14), 2)

    # Target 1: use real resistance above current price, NOT a fake 2R.
    # Target 2: theoretical target (2R/3R or measured move for display).
    risk = r.current_price - r.stop_loss
    if risk > 0:
        real_target = _find_real_target(data, r.current_price, r.pivot)
        if real_target is not None and real_target > r.current_price:
            r.target_1 = round(real_target, 2)
        else:
            r.target_1 = 0.0  # No real target above → RR1 = 0

        r.target_2 = round(r.current_price + 3 * risk, 2)
        if pattern_type == "cup_handle":
            measured_target = r.pivot + (result.left_high_price - result.cup_low_price)
            if measured_target > r.current_price:
                r.target_2 = min(r.target_2, measured_target)
        elif pattern_type == "vcp":
            contractions = _find_vcp_contractions(data)
            if contractions:
                largest = max(c["high"] - c["low"] for c in contractions)
                measured_target = r.pivot + largest
                if measured_target > r.current_price:
                    r.target_2 = min(r.target_2, measured_target)
    else:
        r.target_1 = round(r.current_price * 1.10, 2)
        r.target_2 = round(r.current_price * 1.20, 2)

    return r


def _find_real_target(data: list[dict], current_price: float, pivot: float) -> float | None:
    """Find the nearest real resistance above current_price.

    Priority:
    1. pivot if it's above current price (杯口突破位, not yet broken)
    2. Highest high in recent 60 days if above current price
    3. Nearby platform top
    Returns None if no resistance found above current price.
    """
    # 1. Pivot above current → it's the nearest real target
    if pivot > current_price:
        return pivot

    # 2. Highest high in recent 60 days
    if len(data) >= 60:
        recent_high = max(d["high"] for d in data[-60:])
        if recent_high > current_price:
            return recent_high

    # 3. Local highs above current
    highs = [d["high"] for d in data[-120:]]
    for h in sorted(set(highs)):
        if h > current_price:
            return h

    return None  # No resistance found


def _calc_atr(data, n=14):
    if len(data) < n:
        return 0.0
    tr = []
    for i in range(1, len(data)):
        h, l, pc = data[i]["high"], data[i]["low"], data[i - 1]["close"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(tr[-n:]) / n if tr else 0.0
