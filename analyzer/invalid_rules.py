"""Centralized invalidation rules for dry-stable entries."""

from analyzer.pattern_score import _find_vcp_contractions


def find_invalid_conditions(data: list[dict], key_prices, result=None) -> list[str]:
    """Return hard invalidation conditions visible from OHLC data."""
    if not data:
        return []

    invalid = []
    closes = [d["close"] for d in data]
    volumes = [d.get("volume", 0) for d in data]
    current = key_prices.current_price or closes[-1]

    if key_prices.entry_zone_low > 0 and current < key_prices.entry_zone_low * 0.99:
        invalid.append("当前价跌破关键支撑")

    if _has_volume_breakdown(data):
        invalid.append("最近出现放量大阴线")

    if len(closes) >= 25 and closes[-1] <= min(closes[-21:-1]):
        invalid.append("价格连续创新低")

    if _ma_slope_down(closes, 50):
        invalid.append("50日线明显向下")

    if len(closes) >= 200:
        ma200 = sum(closes[-200:]) / 200
        ma50 = sum(closes[-50:]) / 50
        if closes[-1] < ma200 and ma50 < ma200:
            invalid.append("股价低于200日线且无修复迹象")

    if key_prices.pivot > 0 and _failed_breakout(closes, key_prices.pivot):
        invalid.append("突破失败后重新跌回枢纽点下方")

    if result is not None and getattr(result, "found", False):
        if getattr(result, "handle_depth_pct", 0) > 15:
            invalid.append("杯柄柄部回调超过15%")

    contractions = _find_vcp_contractions(data)
    if contractions:
        last_low = contractions[-1]["low"]
        ma20 = _avg(volumes[-20:])
        if current < last_low and ma20 > 0 and volumes[-1] >= ma20 * 1.2:
            invalid.append("VCP最后一轮收缩失败并放量破位")

    return list(dict.fromkeys(invalid))


def _has_volume_breakdown(data: list[dict]) -> bool:
    if len(data) < 21:
        return False
    volumes = [d.get("volume", 0) for d in data]
    closes = [d["close"] for d in data]
    ma20 = _avg(volumes[-21:-1])
    if ma20 <= 0:
        return False
    for i in range(max(1, len(data) - 3), len(data)):
        if closes[i] <= closes[i - 1] * 0.97 and volumes[i] >= ma20 * 1.5:
            return True
    return False


def _failed_breakout(closes: list[float], pivot: float) -> bool:
    if len(closes) < 5:
        return False
    recent = closes[-10:]
    had_breakout = any(c > pivot * 1.02 for c in recent[:-1])
    return had_breakout and closes[-1] < pivot


def _ma_slope_down(closes: list[float], n: int) -> bool:
    if len(closes) < n + 10:
        return False
    ma_now = _avg(closes[-n:])
    ma_prev = _avg(closes[-n - 10:-10])
    return ma_now < ma_prev * 0.98


def _avg(seq):
    return sum(seq) / len(seq) if seq else 0.0
