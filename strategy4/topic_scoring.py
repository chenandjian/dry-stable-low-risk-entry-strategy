"""Strategy4 hot topic scoring."""
from __future__ import annotations

from strategy4.models import HotTopicScore


def score_hot_topic(snapshot: dict, config: dict, topic_index_context: dict | None = None) -> HotTopicScore:
    price = _score_price(snapshot)
    amount = _score_amount(snapshot)
    fund = _score_fund(snapshot)
    breadth = _score_breadth(snapshot)
    leader_limit = min(10.0, float(snapshot.get("leader_limit_count") or 0) * 4.0)
    breakout = 10.0 if snapshot.get("breakout") else 0.0
    legacy_total = price + amount + fund + breadth + leader_limit + breakout
    total = legacy_total

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
    if topic_index_context and topic_index_context.get("observed"):
        trend = float(topic_index_context.get("topic_index_trend_score") or 0)
        index_breakout = float(topic_index_context.get("topic_index_breakout_score") or 0)
        index_volume = float(topic_index_context.get("topic_index_volume_score") or 0)
        risk_penalty = float(topic_index_context.get("topic_index_risk_penalty") or 0)
        total = min(100.0, max(0.0, total + trend * 0.35 + index_breakout * 0.35 + index_volume * 0.20 + risk_penalty))
        if trend >= 8:
            signals.append("topic_index_trend")
        if index_breakout > 0:
            signals.append("topic_index_breakout")
        if index_volume >= 4:
            signals.append("topic_index_volume")

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

    topic_index_context = topic_index_context or {}
    topic_index_observed = bool(topic_index_context.get("observed"))
    topic_index_phase = str(topic_index_context.get("phase") or "")
    topic_index_cfg = config.get("topic_index")
    require_topic_index = bool(topic_index_cfg and topic_index_cfg.get("require_for_buyable_candidate", True))
    if require_topic_index and not topic_index_observed and status in {"CONFIRMED_HOT", "LOCKED_HOT_TOPIC"}:
        status = "WATCH_HOT"
        noise_reason = "UNOBSERVED_TOPIC_INDEX"
    if topic_index_observed and topic_index_phase == "WEAK_NOISE":
        status = "NOISE_TOPIC"
        noise_reason = "TOPIC_INDEX_WEAK_NOISE"
    elif topic_index_observed and topic_index_phase == "HIGH_RISK_CLIMAX" and status == "CONFIRMED_HOT":
        status = "WATCH_HOT"
        noise_reason = "TOPIC_INDEX_HIGH_RISK_CLIMAX"

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
        topic_index_source=str(topic_index_context.get("source") or ""),
        topic_index_latest_date=str(topic_index_context.get("latest_date") or ""),
        topic_index_rows=int(topic_index_context.get("rows") or 0),
        topic_index_observed=topic_index_observed,
        topic_index_status=str(topic_index_context.get("status") or ""),
        topic_index_trend_score=round(float(topic_index_context.get("topic_index_trend_score") or 0), 2),
        topic_index_breakout_score=round(float(topic_index_context.get("topic_index_breakout_score") or 0), 2),
        topic_index_volume_score=round(float(topic_index_context.get("topic_index_volume_score") or 0), 2),
        topic_index_risk_penalty=round(float(topic_index_context.get("topic_index_risk_penalty") or 0), 2),
        topic_index_phase=topic_index_phase,
        signal_count=signal_count,
        strong_signals=signals,
        noise_reason=noise_reason,
        leading_stock_code=str(snapshot.get("leading_stock_code") or ""),
        leading_stock_name=str(snapshot.get("leading_stock_name") or ""),
        raw_snapshot={**dict(snapshot), "legacy_hot_topic_score": round(legacy_total, 2), "topic_index_context": dict(topic_index_context)},
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
