from strategy4.first_wave import evaluate_first_wave
from strategy4.leader import score_leader_candidate
from strategy4.pullback import evaluate_pullback
from strategy4.risk_reward import evaluate_risk_reward
from strategy4.second_wave import evaluate_second_wave
from strategy4.topic_scoring import score_hot_topic


def test_hot_topic_scoring_confirms_multi_signal_topic():
    topic = score_hot_topic({
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "topic_type": "concept",
        "return_1d": 0.045,
        "return_3d": 0.10,
        "return_5d": 0.16,
        "amount_ratio": 1.8,
        "net_inflow": 500_000_000,
        "breadth_ratio": 0.78,
        "leader_limit_count": 2,
        "breakout": True,
        "leading_stock_code": "300750",
        "leading_stock_name": "宁德时代",
        "source": "akshare_ths",
    }, {"min_hot_topic_score": 85, "min_hot_topic_signal_count": 2})

    assert topic.status == "CONFIRMED_HOT"
    assert topic.hot_topic_score >= 85
    assert topic.signal_count >= 2
    assert "price_strength" in topic.strong_signals


def test_hot_topic_scoring_keeps_locked_attention_topic_despite_low_amount():
    topic = score_hot_topic({
        "topic_id": "concept-robot",
        "topic_name": "机器人",
        "topic_type": "concept",
        "return_1d": 0.04,
        "return_3d": 0.09,
        "return_5d": 0.12,
        "amount_ratio": 0.7,
        "net_inflow": 20_000_000,
        "breadth_ratio": 0.75,
        "leader_limit_count": 3,
        "locked_attention": True,
        "breakout": False,
        "source": "akshare_ths",
    }, {"min_hot_topic_score": 85, "min_hot_topic_signal_count": 2})

    assert topic.status == "LOCKED_HOT_TOPIC"
    assert "locked_attention" in topic.strong_signals
    assert not topic.noise_reason


def test_leader_scoring_marks_locked_leader_watch_not_low_attention():
    leader = score_leader_candidate({
        "code": "300750",
        "name": "宁德时代",
        "topic_id": "concept-ev",
        "topic_name": "新能源车",
        "rank_in_topic": 1,
        "amount_rank": 2,
        "started_early": True,
        "limit_shape": "ONE_WORD_LIMIT_UP",
        "consecutive_limit_count": 2,
        "relative_strength_vs_topic": 0.08,
        "recognition_sources": ["topic_leader", "market_limit"],
        "turnover_rate": 0.03,
        "is_climax": False,
        "has_pullback_buy_point": False,
        "executable_volatility": True,
    })

    assert leader.leader_strength_score >= 88
    assert leader.status == "LOCKED_LEADER_WATCH"
    assert "LOCKED_ATTENTION" in leader.reasons


def test_first_wave_pullback_second_wave_and_risk_reward_form_buyable_chain():
    bars = _bars_for_second_wave()

    first_wave = evaluate_first_wave(bars, {
        "first_wave_lookback_short": 10,
        "first_wave_lookback_long": 20,
        "min_first_wave_return_10d": 0.25,
        "min_first_wave_return_20d": 0.35,
        "min_strong_day_count_10d": 2,
    })
    assert first_wave.passed is True
    assert first_wave.first_wave_return >= 0.25

    pullback = evaluate_pullback(bars, {
        "pullback_min_pct": 0.08,
        "pullback_max_pct": 0.25,
        "pullback_min_days": 2,
        "pullback_max_days": 8,
    })
    assert pullback.passed is True
    assert 0.08 <= pullback.pullback_pct <= 0.25

    second_wave = evaluate_second_wave(bars)
    assert second_wave.passed is True
    assert "close_above_ma5" in second_wave.signals

    rr = evaluate_risk_reward(
        current_close=16.4,
        support_price=15.2,
        target_price=20.0,
        config={
            "max_risk_ratio": 0.15,
            "aggressive_max_risk_ratio": 0.20,
            "min_reward_risk_ratio": 2.0,
            "core_leader_min_reward_risk_ratio": 1.8,
        },
        is_core_leader=False,
    )
    assert rr.passed is True
    assert rr.reward_risk_ratio >= 2.0


def test_pullback_rejects_consecutive_heavy_bear_days():
    bars = _bars_for_second_wave()
    bars[-4]["close"] = 15.0
    bars[-4]["open"] = 16.5
    bars[-4]["volume"] = 8_000_000
    bars[-3]["close"] = 14.2
    bars[-3]["open"] = 15.5
    bars[-3]["volume"] = 9_000_000

    pullback = evaluate_pullback(bars, {
        "pullback_min_pct": 0.08,
        "pullback_max_pct": 0.25,
        "pullback_min_days": 2,
        "pullback_max_days": 8,
    })

    assert pullback.passed is False
    assert "CONSECUTIVE_HEAVY_BEAR_DAYS" in pullback.reject_reasons


def _bars_for_second_wave():
    closes = [
        10.0, 10.2, 10.4, 10.6, 10.8,
        11.2, 12.4, 13.8, 15.2, 17.0,
        16.5, 15.8, 15.3, 15.2, 15.6,
        15.9, 16.1, 16.0, 16.2, 16.4,
    ]
    rows = []
    for idx, close in enumerate(closes):
        previous = closes[idx - 1] if idx else close
        open_ = previous * 0.995
        rows.append({
            "date": f"2026-06-{idx + 1:02d}",
            "open": round(open_, 2),
            "high": round(max(open_, close) * 1.02, 2),
            "low": round(min(open_, close) * 0.98, 2),
            "close": round(close, 2),
            "volume": 6_000_000 if idx < 10 else 3_000_000,
            "amount": close * (6_000_000 if idx < 10 else 3_000_000),
        })
    rows[-1]["volume"] = 4_000_000
    rows[-1]["open"] = 15.9
    rows[-1]["low"] = 15.6
    rows[-1]["high"] = 16.6
    return rows
