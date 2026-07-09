"""Strategy6 support price and zone calculation."""
from __future__ import annotations

from strategy6.models import Strategy6Indicators, Strategy6Start, Strategy6Support


def evaluate_support(rows: list[dict], ind: Strategy6Indicators, start: Strategy6Start) -> Strategy6Support:
    status, ma_label, ma_price = _support_status(ind)
    if status == "SUPPORT_FAILED":
        return Strategy6Support(support_status=status)

    key_support = _select_key_support(rows, ind, ma_price, start)
    zone_low, zone_high = _support_zone(key_support, status)
    support_tests = _support_test_count(rows, key_support)
    pivot = max((r["close"] for r in rows[-20:]), default=ind.current_price)
    box_height = max(0.0, pivot - key_support)
    score = _support_score(ind.current_price, status, key_support, support_tests)
    return Strategy6Support(
        support_status=status,
        main_support_ma=ma_label,
        key_support_price=round(key_support, 4),
        support_zone_low=round(zone_low, 4),
        support_zone_high=round(zone_high, 4),
        defense_support_price=round(ind.ma50 if ind.ma50 > 0 else key_support, 4),
        support_test_count=support_tests,
        pivot_price=round(pivot, 4),
        box_height=round(box_height, 4),
        support_score=score,
    )


def _support_status(ind: Strategy6Indicators) -> tuple[str, str, float]:
    close = ind.current_price
    candidates = (
        ("MA5_SUPPORT", "MA5", ind.ma5, 0.04, 1.0),
        ("MA10_SUPPORT", "MA10", ind.ma10, 0.05, 1.0),
        ("MA20_SUPPORT", "MA20", ind.ma20, 0.08, 0.94),
        ("MA50_TESTING", "MA50", ind.ma50, 0.10, 0.92),
    )
    for status, label, price, max_dist, min_ratio in candidates:
        if close <= 0 or price <= 0:
            continue
        dist = abs(close - price) / close
        if close >= price * min_ratio and dist <= max_dist:
            return status, label, price
    return "SUPPORT_FAILED", "", 0.0


def _select_key_support(rows: list[dict], ind: Strategy6Indicators, ma_price: float, start: Strategy6Start) -> float:
    values = [ma_price]
    if rows[-10:]:
        values.append(min(r["close"] for r in rows[-10:]))
        values.append(min(r["low"] for r in rows[-10:]))
    if rows[-20:]:
        values.append(min(r["close"] for r in rows[-20:]))
        values.append(min(r["low"] for r in rows[-20:]))
    for row in rows[-20:]:
        if row["date"] == start.start_date:
            values.append(row["low"])
            break
    valid = [value for value in values if value > 0 and value <= ind.current_price * 1.03]
    if not valid:
        return ma_price if ma_price > 0 else ind.current_price
    return max(valid, key=lambda value: _support_candidate_score(rows, ind.current_price, value, ma_price))


def _support_candidate_score(rows: list[dict], close: float, value: float, ma_price: float) -> float:
    distance = abs(close - value) / close if close > 0 else 1
    score = max(0.0, 20 - distance * 400)
    score += min(20, _support_test_count(rows, value) * 10)
    if abs(value - ma_price) / close <= 0.02 if close > 0 else False:
        score += 15
    recent_idx_bonus = 10
    return score + recent_idx_bonus


def _support_zone(key_support: float, status: str) -> tuple[float, float]:
    if status in {"MA5_SUPPORT", "MA10_SUPPORT"}:
        return key_support * 0.99, key_support * 1.03
    if status == "MA20_SUPPORT":
        return key_support * 0.97, key_support * 1.04
    if status == "MA50_TESTING":
        return key_support * 0.92, key_support * 1.05
    return key_support * 0.98, key_support * 1.03


def _support_test_count(rows: list[dict], key_support: float) -> int:
    if key_support <= 0:
        return 0
    return sum(1 for row in rows[-10:] if row["low"] <= key_support * 1.02 and row["close"] >= key_support * 0.98)


def _support_score(close: float, status: str, key_support: float, support_tests: int) -> int:
    base = {"MA5_SUPPORT": 18, "MA10_SUPPORT": 17, "MA20_SUPPORT": 15, "MA50_TESTING": 9}.get(status, 0)
    if close > 0 and key_support > 0 and key_support * 0.98 <= close <= key_support * 1.04:
        base += 4
    if support_tests >= 2:
        base += 3
    elif support_tests >= 1:
        base += 2
    return min(25, base)

