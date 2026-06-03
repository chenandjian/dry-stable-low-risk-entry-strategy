# analyzer/key_prices.py
"""Key Price Calculator — 计算低吸区间、Pivot枢纽点、止损价、止盈价。"""

from dataclasses import dataclass


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

    if not data or not result.found:
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

        # Pivot = handle high (right cup lip)
        r.pivot = round(result.right_high_price, 2)

        # Stop loss
        atr14 = _calc_atr(data, 14)
        r.stop_loss = round(min(handle_low * 0.98, handle_low - 0.5 * atr14), 2)

    # Target 1 = 2R
    risk = r.current_price - r.stop_loss
    if risk > 0:
        r.target_1 = round(r.current_price + 2 * risk, 2)
        r.target_2 = round(r.current_price + 3 * risk, 2)
    else:
        r.target_1 = round(r.current_price * 1.10, 2)
        r.target_2 = round(r.current_price * 1.20, 2)

    return r


def _calc_atr(data, n=14):
    if len(data) < n:
        return 0.0
    tr = []
    for i in range(1, len(data)):
        h, l, pc = data[i]["high"], data[i]["low"], data[i - 1]["close"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(tr[-n:]) / n if tr else 0.0
