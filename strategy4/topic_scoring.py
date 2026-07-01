"""Strategy4 hot topic scoring."""
from __future__ import annotations

from strategy4.models import HotTopicScore


def score_hot_topic(snapshot: dict, config: dict) -> HotTopicScore:
    price = _score_price(snapshot)
    amount = _score_amount(snapshot)
    fund = _score_fund(snapshot)
    breadth = _score_breadth(snapshot)
    leader_limit = min(10.0, float(snapshot.get("leader_limit_count") or 0) * 4.0)
    breakout = 10.0 if snapshot.get("breakout") else 0.0
    total = price + amount + fund + breadth + leader_limit + breakout

    signals: list[str] = []
    if price >= 20:
        signals.append("price_strength")
    if amount >= 14:
        signals.append("amount_strength")
    if fund >= 10:
        signals.append("fund_flow")
    if breadth >= 10:
        signals.append("breadth")
    if leader_limit >= 8:
        signals.append("leader_limit")
    if breakout:
        signals.append("breakout")
    if snapshot.get("locked_attention"):
        signals.append("locked_attention")

    min_score = float(config.get("min_hot_topic_score", 85))
    min_signal_count = int(config.get("min_hot_topic_signal_count", 2))
    signal_count = len(signals)
    noise_reason = ""
    status = "WATCH_HOT"

    if snapshot.get("locked_attention") and price >= 18 and breadth >= 10 and leader_limit >= 8:
        status = "LOCKED_HOT_TOPIC"
    elif total >= min_score and signal_count >= min_signal_count:
        status = "CONFIRMED_HOT"
    elif signal_count < min_signal_count:
        status = "NOISE_TOPIC"
        noise_reason = "INSUFFICIENT_HOT_SIGNALS"

    return HotTopicScore(
        topic_id=str(snapshot.get("topic_id") or snapshot.get("topic_name") or ""),
        topic_name=str(snapshot.get("topic_name") or ""),
        topic_type=str(snapshot.get("topic_type") or ""),
        source=str(snapshot.get("source") or ""),
        status=status,
        hot_topic_score=round(total, 2),
        price_strength_score=round(price, 2),
        amount_strength_score=round(amount, 2),
        fund_flow_score=round(fund, 2),
        breadth_score=round(breadth, 2),
        leader_limit_score=round(leader_limit, 2),
        breakout_score=round(breakout, 2),
        signal_count=signal_count,
        strong_signals=signals,
        noise_reason=noise_reason,
        leading_stock_code=str(snapshot.get("leading_stock_code") or ""),
        leading_stock_name=str(snapshot.get("leading_stock_name") or ""),
        raw_snapshot=dict(snapshot),
    )


def _score_price(snapshot: dict) -> float:
    r1 = float(snapshot.get("return_1d") or 0)
    r3 = float(snapshot.get("return_3d") or 0)
    r5 = float(snapshot.get("return_5d") or 0)
    return min(30.0, max(0.0, r1 / 0.05 * 10 + r3 / 0.10 * 10 + r5 / 0.15 * 10))


def _score_amount(snapshot: dict) -> float:
    ratio = float(snapshot.get("amount_ratio") or 0)
    return min(20.0, max(0.0, (ratio - 0.8) / 1.0 * 20))


def _score_fund(snapshot: dict) -> float:
    inflow = float(snapshot.get("net_inflow") or 0)
    return min(15.0, max(0.0, inflow / 500_000_000 * 15))


def _score_breadth(snapshot: dict) -> float:
    breadth = float(snapshot.get("breadth_ratio") or 0)
    return min(15.0, max(0.0, breadth / 0.75 * 15))

