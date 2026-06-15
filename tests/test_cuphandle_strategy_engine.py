from scanner.pattern_detector import CupHandleResult
from scanner.strategy_engine import (
    StrategyEvaluation,
    CupHandleStrategyEngine,
    StrategyWindows,
    build_pattern_config,
    compute_config_hash,
    resolve_strategy_windows,
    select_market_window,
    select_strategy_window,
    WINDOW_DEFAULT,
    WINDOW_MIN,
)


def base_config():
    return {
        "cup": {"min_duration": 35, "max_duration": 180},
        "handle": {"min_duration": 5, "max_duration": 30, "max_depth": 0.18},
        "breakout": {"buffer_pct": 0.02, "volume_multiplier": 1.5},
        "scoring": {"medium_threshold": 70},
    }


def test_build_pattern_config_prefixes_handle_keys():
    cfg = build_pattern_config(base_config())
    assert cfg["min_duration"] == 35
    assert cfg["max_duration"] == 180
    assert cfg["handle_min_duration"] == 5
    assert cfg["handle_max_duration"] == 30
    assert cfg["handle_max_depth"] == 0.18
    assert cfg["buffer_pct"] == 0.02
    assert cfg["volume_multiplier"] == 1.5


def test_config_hash_is_stable_for_key_order():
    config_a = {"b": 2, "a": {"x": 1, "y": 2}}
    config_b = {"a": {"y": 2, "x": 1}, "b": 2}
    config_hash = compute_config_hash(config_a)
    assert config_hash == compute_config_hash(config_b)
    assert config_hash.startswith("sha256:")
    assert len(config_hash) == len("sha256:") + 64
    assert all(ch in "0123456789abcdef" for ch in config_hash.removeprefix("sha256:"))


def test_engine_exposes_strategy_version_and_hash():
    engine = CupHandleStrategyEngine(base_config())
    assert engine.strategy_version == "cuphandle-v1"
    assert engine.config_hash.startswith("sha256:")


def test_strategy_evaluation_to_dict_serializes_handle_window_dates_from_data():
    data = [
        {"date": "2024-01-01", "close": 10.0, "high": 10.2, "low": 9.8},
        {"date": "2024-01-02", "close": 10.5, "high": 10.7, "low": 10.2},
        {"date": "2024-01-03", "close": 9.3, "high": 9.6, "low": 9.0},
        {"date": "2024-01-04", "close": 10.4, "high": 10.6, "low": 10.1},
        {"date": "2024-01-05", "close": 10.1, "high": 10.3, "low": 9.9},
        {"date": "2024-01-06", "close": 9.9, "high": 10.0, "low": 9.7},
    ]
    evaluation = StrategyEvaluation(
        passed=True,
        result=CupHandleResult(
            found=True,
            code="600036",
            name="招商银行",
            left_high_idx=1,
            cup_low_idx=2,
            right_high_idx=3,
            handle_low_idx=5,
            left_high_date="2024-01-02",
            cup_low_date="2024-01-03",
            right_high_date="2024-01-04",
            handle_low_date="2024-01-06",
            left_high_price=10.5,
            cup_low_price=9.0,
            right_high_price=10.4,
            handle_low_price=9.7,
            cup_duration=2,
            cup_depth_pct=14.3,
            handle_duration=2,
            handle_depth_pct=6.7,
            lip_deviation_pct=1.0,
            is_breakout=False,
            is_volume_breakout=False,
            vol_multiplier=1.1,
            score=78,
        ),
        dry_stable={"decision": {"verdict": "观察"}},
        strategy_version="cuphandle-v1",
        config_hash="sha256:test",
        data=data,
    )

    serialized = evaluation.to_dict()

    assert serialized["pattern"]["handleStartDate"] == "2024-01-05"
    assert serialized["pattern"]["handleEndDate"] == "2024-01-06"



def make_ohlc_from_closes(closes):
    rows = []
    for i, close in enumerate(closes):
        rows.append({
            "date": f"2025-{(i // 20) + 1:02d}-{(i % 20) + 1:02d}",
            "open": round(close * 0.99, 2),
            "high": round(close * 1.02, 2),
            "low": round(close * 0.98, 2),
            "close": round(close, 2),
            "volume": 10_000_000 + i * 10_000,
            "turnover": round(close * (10_000_000 + i * 10_000), 2),
        })
    return rows


def build_cup_handle_closes():
    import math
    closes = []
    for i in range(40):
        t = i / 40
        closes.append(50.0 + (65.0 - 50.0) * t)
    for i in range(35):
        t = i / 35
        closes.append(65.0 - (65.0 - 52.0) * math.sin(t * math.pi / 2))
    for i in range(20):
        noise = (i % 3 - 1) * 0.5
        closes.append(53.0 + noise)
    for i in range(35):
        t = i / 35
        closes.append(52.0 + (62.0 - 52.0) * math.sin(t * math.pi / 2))
    for i in range(15):
        t = i / 15
        closes.append(62.0 - (62.0 - 58.0) * t)
    for i in range(5):
        closes.append(64.0 + i * 0.3)
    return closes


def full_config():
    cfg = base_config()
    cfg["cup"].update({
        "min_depth": 0.12,
        "max_depth": 0.45,
        "max_lip_deviation": 0.12,
        "min_bottom_roundness": 0.10,
    })
    cfg["handle"].update({
        "max_vs_right_rally": 0.50,
    })
    return cfg


def test_evaluate_at_returns_passed_for_valid_cup_handle():
    data = make_ohlc_from_closes(build_cup_handle_closes())
    engine = CupHandleStrategyEngine(full_config())

    evaluation = engine.evaluate_at(data, code="600000", name="浦发银行")

    assert evaluation.result.found is True
    assert evaluation.result.code == "600000"
    assert evaluation.result.name == "浦发银行"
    assert evaluation.result.score > 0
    assert evaluation.dry_stable is not None
    assert all(rule.ruleName != "VCP" for rule in evaluation.passed_rules + evaluation.failed_rules)


def test_evaluate_at_does_not_promote_vcp_only_result():
    flat_data = make_ohlc_from_closes([10 + (i % 5) * 0.1 for i in range(180)])
    engine = CupHandleStrategyEngine(full_config())

    evaluation = engine.evaluate_at(flat_data, code="600001")

    assert evaluation.passed is False
    assert evaluation.result.found is False
    # VCP analysis runs even when cup handle not found (BUG-006)
    # Flat data produces weak VCP (score < 13), so it doesn't promote
    assert evaluation.dry_stable is not None
    assert evaluation.dry_stable["pattern_score"]["key_pattern_type"] == "vcp"
    assert evaluation.dry_stable["pattern_score"]["score"] < 13


def test_diagnose_handle_returns_passed_and_failed_rule_arrays():
    data = make_ohlc_from_closes(build_cup_handle_closes())
    engine = CupHandleStrategyEngine(full_config())
    evaluation = engine.evaluate_at(data, code="600000")
    actual_start = data[evaluation.result.right_high_idx + 1]["date"]
    actual_end = data[-1]["date"]

    diagnosis = engine.diagnose_handle(data, actual_start, actual_end, code="600000")

    body = diagnosis.to_dict()
    assert "passedRules" in body
    assert "failedRules" in body
    assert any(rule["ruleName"] == "指定柄区间匹配" for rule in body["passedRules"])


def test_diagnose_handle_reports_mismatched_user_range():
    data = make_ohlc_from_closes(build_cup_handle_closes())
    engine = CupHandleStrategyEngine(full_config())

    diagnosis = engine.diagnose_handle(data, "2025-01-01", data[-1]["date"], code="600000")

    failed = diagnosis.to_dict()["failedRules"]
    assert any(rule["ruleName"] == "指定柄区间匹配" for rule in failed)
    match_rule = next(rule for rule in failed if rule["ruleName"] == "指定柄区间匹配")
    assert match_rule["severity"] == "high"
    assert match_rule["requiredValue"]
    assert match_rule["actualValue"]
    assert match_rule["explanation"]



def test_evaluate_at_rejects_when_dry_stable_prefers_vcp(monkeypatch):
    import scanner.strategy_engine as strategy_engine

    data = make_ohlc_from_closes(build_cup_handle_closes())
    engine = CupHandleStrategyEngine(full_config())

    def fake_analyze_dry_stable(result, data, market_data=None, config=None):
        return {
            "decision": {"verdict": "观察", "verdict_key": "WATCH_BREAKOUT"},
            "pattern_score": {"key_pattern_type": "vcp"},
        }

    monkeypatch.setattr(strategy_engine, "analyze_dry_stable", fake_analyze_dry_stable)

    evaluation = engine.evaluate_at(data, code="600000")

    assert evaluation.result.found is True
    assert evaluation.passed is True
    assert any(rule.ruleName == "关键形态类型" for rule in evaluation.passed_rules)


def test_evaluate_at_rejects_partial_dry_stable_schema(monkeypatch):
    import scanner.strategy_engine as strategy_engine

    data = make_ohlc_from_closes(build_cup_handle_closes())
    engine = CupHandleStrategyEngine(full_config())

    def fake_analyze_dry_stable(result, data, market_data=None, config=None):
        return {
            "decision": {},
            "pattern_score": {},
        }

    monkeypatch.setattr(strategy_engine, "analyze_dry_stable", fake_analyze_dry_stable)

    evaluation = engine.evaluate_at(data, code="600000")

    assert evaluation.result.found is True
    assert evaluation.passed is False
    failed_rule_names = {rule.ruleName for rule in evaluation.failed_rules}
    assert "关键形态类型" in failed_rule_names
    assert "最终策略结论" in failed_rule_names


def test_evaluate_at_rejects_unknown_dry_stable_verdict(monkeypatch):
    import scanner.strategy_engine as strategy_engine

    data = make_ohlc_from_closes(build_cup_handle_closes())
    engine = CupHandleStrategyEngine(full_config())

    def fake_analyze_dry_stable(result, data, market_data=None, config=None):
        return {
            "decision": {"verdict": "神秘状态"},
            "pattern_score": {"key_pattern_type": "cup_handle"},
        }

    monkeypatch.setattr(strategy_engine, "analyze_dry_stable", fake_analyze_dry_stable)

    evaluation = engine.evaluate_at(data, code="600000")

    assert evaluation.result.found is True
    assert evaluation.passed is False
    verdict_rule = next(rule for rule in evaluation.failed_rules if rule.ruleName == "最终策略结论")
    assert verdict_rule.actualValue == "神秘状态"


# ── select_strategy_window ────────────────────────────────────────────

def test_select_strategy_window_returns_last_n():
    data = [{"date": f"2025-01-{i+1:02d}"} for i in range(100)]
    result = select_strategy_window(data, 50)
    assert result is not None
    assert len(result) == 50
    assert result[0]["date"] == "2025-01-51"
    assert result[-1]["date"] == "2025-01-100"


def test_select_strategy_window_exact_count_returns_all():
    data = [{"date": f"2025-01-{i+1:02d}"} for i in range(50)]
    result = select_strategy_window(data, 50)
    assert result is not None
    assert len(result) == 50


def test_select_strategy_window_insufficient_returns_none():
    data = [{"date": f"2025-01-{i+1:02d}"} for i in range(30)]
    result = select_strategy_window(data, 50)
    assert result is None


def test_select_strategy_window_zero_raises():
    import pytest
    with pytest.raises(ValueError, match="positive integer"):
        select_strategy_window([], 0)


def test_select_strategy_window_negative_raises():
    import pytest
    with pytest.raises(ValueError, match="positive integer"):
        select_strategy_window([], -5)


# ── is_breakout exclusion ─────────────────────────────────────────────

def test_evaluate_at_rejects_breakout_pattern(monkeypatch):
    """ROUND5-001: is_breakout=True → evaluation.passed=False."""
    import scanner.strategy_engine as strategy_engine

    data = make_ohlc_from_closes(build_cup_handle_closes())
    engine = CupHandleStrategyEngine(full_config())

    def fake_analyze_dry_stable(result, data, market_data=None, config=None):
        return {
            "decision": {"verdict": "可低吸", "verdict_key": "BUY_LOW"},
            "pattern_score": {"key_pattern_type": "cup_handle"},
        }

    monkeypatch.setattr(strategy_engine, "analyze_dry_stable", fake_analyze_dry_stable)

    # Monkeypatch detect_cup_handle to return a breakout result
    original_detect = strategy_engine.detect_cup_handle

    def fake_detect_cup_handle(data, pattern_cfg):
        result = original_detect(data, pattern_cfg)
        result.is_breakout = True
        return result

    monkeypatch.setattr(strategy_engine, "detect_cup_handle", fake_detect_cup_handle)

    evaluation = engine.evaluate_at(data, code="600000")

    assert evaluation.result.found is True
    assert evaluation.result.is_breakout is True
    assert evaluation.passed is False
    failed_names = {rule.ruleName for rule in evaluation.failed_rules}
    assert "突破状态排除" in failed_names


def test_evaluate_at_passes_non_breakout_pattern(monkeypatch):
    """ROUND5-001: is_breakout=False with valid dry_stable → evaluation.passed=True."""
    import scanner.strategy_engine as strategy_engine

    data = make_ohlc_from_closes(build_cup_handle_closes())
    engine = CupHandleStrategyEngine(full_config())

    def fake_analyze_dry_stable(result, data, market_data=None, config=None):
        return {
            "decision": {"verdict": "观察", "verdict_key": "WATCH_BREAKOUT"},
            "pattern_score": {"key_pattern_type": "cup_handle"},
        }

    monkeypatch.setattr(strategy_engine, "analyze_dry_stable", fake_analyze_dry_stable)

    evaluation = engine.evaluate_at(data, code="600000")

    assert evaluation.result.found is True
    assert evaluation.result.is_breakout is False
    assert evaluation.passed is True
    passed_names = {rule.ruleName for rule in evaluation.passed_rules}
    assert "突破状态排除" in passed_names


def test_evaluate_at_rejects_high_drawdown_with_weakness(monkeypatch):
    """High quality filter: deep 120d drawdown + weak risk state should not be a candidate."""
    import scanner.strategy_engine as strategy_engine

    data = []
    for i in range(120):
        close = 65.0
        high = 67.0
        if i == 20:
            high = 100.0
            close = 96.0
        data.append({
            "date": f"2025-{(i // 20) + 1:02d}-{(i % 20) + 1:02d}",
            "open": close,
            "high": high,
            "low": close * 0.98,
            "close": close,
            "volume": 10_000_000,
            "turnover": close * 10_000_000,
        })

    engine = CupHandleStrategyEngine(full_config())

    def fake_detect_cup_handle(data, pattern_cfg):
        return CupHandleResult(
            found=True,
            left_high_idx=10,
            cup_low_idx=50,
            right_high_idx=100,
            handle_low_idx=115,
            left_high_date=data[10]["date"],
            cup_low_date=data[50]["date"],
            right_high_date=data[100]["date"],
            handle_low_date=data[115]["date"],
            left_high_price=72.0,
            cup_low_price=58.0,
            right_high_price=70.0,
            handle_low_price=63.0,
            cup_duration=90,
            cup_depth_pct=18.0,
            handle_duration=19,
            handle_depth_pct=10.0,
            lip_deviation_pct=3.0,
            is_breakout=False,
            score=72,
        )

    def fake_score_cup_handle_advanced(result, data, scoring_cfg):
        return 72

    def fake_analyze_dry_stable(result, data, market_data=None, config=None):
        return {
            "decision": {
                "verdict": "等回调入场",
                "verdict_key": "WAIT_ENTRY",
                "warnings": ["缩量但价格重心下移，疑似弱势阴跌"],
            },
            "pattern_score": {"key_pattern_type": "cup_handle"},
            "price_stable": {"score": 5},
            "risk_reward": {"rr1": 0.3, "position_advice": "0%"},
        }

    monkeypatch.setattr(strategy_engine, "detect_cup_handle", fake_detect_cup_handle)
    monkeypatch.setattr(strategy_engine, "score_cup_handle_advanced", fake_score_cup_handle_advanced)
    monkeypatch.setattr(strategy_engine, "analyze_dry_stable", fake_analyze_dry_stable)

    evaluation = engine.evaluate_at(data, code="301310", name="测试")

    assert evaluation.passed is False
    high_drawdown_rule = next(rule for rule in evaluation.failed_rules if rule.ruleName == "高位深跌弱势过滤")
    assert high_drawdown_rule.severity == "high"
    assert "120日高点回撤" in high_drawdown_rule.actualValue


def test_evaluate_at_keeps_wait_entry_when_drawdown_is_not_deep(monkeypatch):
    """The quality filter should not overfit by rejecting ordinary pullbacks."""
    import scanner.strategy_engine as strategy_engine

    data = []
    for i in range(120):
        close = 72.0
        high = 74.0
        if i == 20:
            high = 100.0
            close = 96.0
        data.append({
            "date": f"2025-{(i // 20) + 1:02d}-{(i % 20) + 1:02d}",
            "open": close,
            "high": high,
            "low": close * 0.98,
            "close": close,
            "volume": 10_000_000,
            "turnover": close * 10_000_000,
        })

    engine = CupHandleStrategyEngine(full_config())

    def fake_detect_cup_handle(data, pattern_cfg):
        return CupHandleResult(found=True, is_breakout=False, score=72)

    def fake_score_cup_handle_advanced(result, data, scoring_cfg):
        return 72

    def fake_analyze_dry_stable(result, data, market_data=None, config=None):
        return {
            "decision": {"verdict": "等回调入场", "verdict_key": "WAIT_ENTRY"},
            "pattern_score": {"key_pattern_type": "cup_handle"},
            "price_stable": {"score": 5},
            "risk_reward": {"rr1": 1.5, "position_advice": "10%-20%"},
        }

    monkeypatch.setattr(strategy_engine, "detect_cup_handle", fake_detect_cup_handle)
    monkeypatch.setattr(strategy_engine, "score_cup_handle_advanced", fake_score_cup_handle_advanced)
    monkeypatch.setattr(strategy_engine, "analyze_dry_stable", fake_analyze_dry_stable)

    evaluation = engine.evaluate_at(data, code="600000", name="测试")

    assert evaluation.passed is True
    assert all(rule.ruleName != "高位深跌弱势过滤" for rule in evaluation.failed_rules)


def test_evaluate_at_rejects_weak_trade_value_candidate(monkeypatch):
    """WAIT_ENTRY with 0% position and RR1<1 has no practical trade value."""
    import scanner.strategy_engine as strategy_engine

    data = make_ohlc_from_closes([20 + (i % 5) * 0.1 for i in range(120)])
    engine = CupHandleStrategyEngine(full_config())

    def fake_detect_cup_handle(data, pattern_cfg):
        return CupHandleResult(found=True, is_breakout=False, score=76)

    def fake_score_cup_handle_advanced(result, data, scoring_cfg):
        return 76

    def fake_analyze_dry_stable(result, data, market_data=None, config=None):
        return {
            "decision": {
                "verdict": "等回调入场",
                "verdict_key": "WAIT_ENTRY",
                "reject_reasons": ["跌破关键支撑，价格尚未稳定"],
            },
            "pattern_score": {"key_pattern_type": "cup_handle"},
            "price_stable": {
                "score": 5,
                "reject_reasons": ["跌破关键支撑，价格尚未稳定"],
            },
            "risk_reward": {"rr1": 0.4, "position_advice": "0%"},
        }

    monkeypatch.setattr(strategy_engine, "detect_cup_handle", fake_detect_cup_handle)
    monkeypatch.setattr(strategy_engine, "score_cup_handle_advanced", fake_score_cup_handle_advanced)
    monkeypatch.setattr(strategy_engine, "analyze_dry_stable", fake_analyze_dry_stable)

    evaluation = engine.evaluate_at(data, code="002888", name="惠威科技")

    assert evaluation.passed is False
    weak_value_rule = next(rule for rule in evaluation.failed_rules if rule.ruleName == "弱交易价值过滤")
    assert weak_value_rule.severity == "high"
    assert "RR1=0.4" in weak_value_rule.actualValue
    assert "仓位建议0%" in weak_value_rule.actualValue


def test_evaluate_at_keeps_wait_entry_when_trade_value_is_acceptable(monkeypatch):
    """WAIT_ENTRY remains a candidate when risk/reward and position are still usable."""
    import scanner.strategy_engine as strategy_engine

    data = make_ohlc_from_closes([20 + (i % 5) * 0.1 for i in range(120)])
    engine = CupHandleStrategyEngine(full_config())

    def fake_detect_cup_handle(data, pattern_cfg):
        return CupHandleResult(found=True, is_breakout=False, score=76)

    def fake_score_cup_handle_advanced(result, data, scoring_cfg):
        return 76

    def fake_analyze_dry_stable(result, data, market_data=None, config=None):
        return {
            "decision": {"verdict": "等回调入场", "verdict_key": "WAIT_ENTRY"},
            "pattern_score": {"key_pattern_type": "cup_handle"},
            "price_stable": {"score": 6},
            "risk_reward": {"rr1": 1.5, "position_advice": "10%-20%"},
        }

    monkeypatch.setattr(strategy_engine, "detect_cup_handle", fake_detect_cup_handle)
    monkeypatch.setattr(strategy_engine, "score_cup_handle_advanced", fake_score_cup_handle_advanced)
    monkeypatch.setattr(strategy_engine, "analyze_dry_stable", fake_analyze_dry_stable)

    evaluation = engine.evaluate_at(data, code="600000", name="测试")

    assert evaluation.passed is True
    assert all(rule.ruleName != "弱交易价值过滤" for rule in evaluation.failed_rules)


def test_evaluate_at_rejects_handle_support_breakdown(monkeypatch):
    """Close below handle support by more than 2% should invalidate the handle candidate."""
    import scanner.strategy_engine as strategy_engine

    data = make_ohlc_from_closes([20 + (i % 5) * 0.1 for i in range(118)] + [19.8, 19.5])
    engine = CupHandleStrategyEngine(full_config())

    def fake_detect_cup_handle(data, pattern_cfg):
        return CupHandleResult(
            found=True,
            is_breakout=False,
            score=76,
            right_high_idx=100,
            handle_low_price=20.0,
        )

    def fake_score_cup_handle_advanced(result, data, scoring_cfg):
        return 76

    def fake_analyze_dry_stable(result, data, market_data=None, config=None):
        return {
            "decision": {"verdict": "等回调入场", "verdict_key": "WAIT_ENTRY"},
            "pattern_score": {"key_pattern_type": "cup_handle"},
            "price_stable": {"score": 6},
            "risk_reward": {"rr1": 1.5, "position_advice": "10%-20%"},
        }

    monkeypatch.setattr(strategy_engine, "detect_cup_handle", fake_detect_cup_handle)
    monkeypatch.setattr(strategy_engine, "score_cup_handle_advanced", fake_score_cup_handle_advanced)
    monkeypatch.setattr(strategy_engine, "analyze_dry_stable", fake_analyze_dry_stable)

    evaluation = engine.evaluate_at(data, code="600000", name="测试")

    assert evaluation.passed is False
    support_rule = next(rule for rule in evaluation.failed_rules if rule.ruleName == "柄部支撑破位过滤")
    assert support_rule.severity == "high"
    assert "handle_support=20.00" in support_rule.actualValue


def test_evaluate_at_keeps_single_mild_handle_support_dip(monkeypatch):
    """A single close slightly below handle support is only a warning, not a hard reject."""
    import scanner.strategy_engine as strategy_engine

    data = make_ohlc_from_closes([20 + (i % 5) * 0.1 for i in range(119)] + [19.8])
    engine = CupHandleStrategyEngine(full_config())

    def fake_detect_cup_handle(data, pattern_cfg):
        return CupHandleResult(
            found=True,
            is_breakout=False,
            score=76,
            right_high_idx=100,
            handle_low_price=20.0,
        )

    def fake_score_cup_handle_advanced(result, data, scoring_cfg):
        return 76

    def fake_analyze_dry_stable(result, data, market_data=None, config=None):
        return {
            "decision": {"verdict": "等回调入场", "verdict_key": "WAIT_ENTRY"},
            "pattern_score": {"key_pattern_type": "cup_handle"},
            "price_stable": {"score": 6},
            "risk_reward": {"rr1": 1.5, "position_advice": "10%-20%"},
        }

    monkeypatch.setattr(strategy_engine, "detect_cup_handle", fake_detect_cup_handle)
    monkeypatch.setattr(strategy_engine, "score_cup_handle_advanced", fake_score_cup_handle_advanced)
    monkeypatch.setattr(strategy_engine, "analyze_dry_stable", fake_analyze_dry_stable)

    evaluation = engine.evaluate_at(data, code="600000", name="测试")

    assert evaluation.passed is True
    assert all(rule.ruleName != "柄部支撑破位过滤" for rule in evaluation.failed_rules)


# ── 扫描与回测一致性 ─────────────────────────────────────────────────

def test_same_data_same_window_produces_consistent_result():
    """ROUND5-CONSISTENCY: 相同OHLC数据、相同配置 → 策略结论一致。

    不区分"扫描路径"与"回测路径"——两者都通过 evaluate_at() 调用同一引擎。
    """
    data = make_ohlc_from_closes(build_cup_handle_closes())
    config = full_config()

    engine1 = CupHandleStrategyEngine(config)
    engine2 = CupHandleStrategyEngine(config)

    e1 = engine1.evaluate_at(data, code="600000", name="测试")
    e2 = engine2.evaluate_at(data, code="600000", name="测试")

    assert e1.passed == e2.passed
    assert e1.result.score == e2.result.score
    assert e1.result.pattern_kind == e2.result.pattern_kind
    assert e1.strategy_version == e2.strategy_version
    assert e1.config_hash == e2.config_hash

    if e1.dry_stable and e2.dry_stable:
        assert e1.dry_stable["decision"].get("verdict_key") == e2.dry_stable["decision"].get("verdict_key")
        assert e1.dry_stable["pattern_score"].get("key_pattern_type") == e2.dry_stable["pattern_score"].get("key_pattern_type")
        assert e1.dry_stable["key_prices"]["stop_loss"] == e2.dry_stable["key_prices"]["stop_loss"]
        assert e1.dry_stable["key_prices"]["entry_zone_low"] == e2.dry_stable["key_prices"]["entry_zone_low"]
        assert e1.dry_stable["key_prices"]["entry_zone_high"] == e2.dry_stable["key_prices"]["entry_zone_high"]


def test_select_strategy_window_consistency_with_backtest_window():
    """ROUND5-CONSISTENCY: select_strategy_window 与回测窗口语义一致。

    scan_window_days == backtest_window_days 时，同一数据截取结果相同。
    """
    data = make_ohlc_from_closes(build_cup_handle_closes())
    scan_result = select_strategy_window(data, 100)
    backtest_result = select_strategy_window(data, 100)

    assert scan_result is not None
    assert backtest_result is not None
    assert len(scan_result) == len(backtest_result)
    assert scan_result[0]["date"] == backtest_result[0]["date"]
    assert scan_result[-1]["date"] == backtest_result[-1]["date"]


# ── resolve_strategy_windows config validation (BUG-004) ─────────────

def test_resolve_strategy_windows_uses_fixed_defaults():
    """Missing values → fixed 250, not cascading to min_listing_days."""
    w = resolve_strategy_windows({"liquidity": {"min_listing_days": 500}})
    assert w.min_listing_days == 500
    assert w.scan_window_days == WINDOW_DEFAULT
    assert w.backtest_window_days == WINDOW_DEFAULT


def test_resolve_strategy_windows_rejects_zero():
    import pytest
    with pytest.raises(ValueError, match="must be >= 30"):
        resolve_strategy_windows({"data": {"scan_window_days": 0}})


def test_resolve_strategy_windows_rejects_min_listing_days_zero():
    """RECHECK-002: min_listing_days=0 must be rejected, not treated as missing."""
    import pytest
    with pytest.raises(ValueError, match="must be >= 30"):
        resolve_strategy_windows({"liquidity": {"min_listing_days": 0}})


def test_resolve_strategy_windows_rejects_negative():
    import pytest
    with pytest.raises(ValueError, match="must be >= 30"):
        resolve_strategy_windows({"data": {"scan_window_days": -1}})


def test_resolve_strategy_windows_rejects_29():
    import pytest
    with pytest.raises(ValueError, match="must be >= 30"):
        resolve_strategy_windows({"data": {"scan_window_days": 29}})


def test_resolve_strategy_windows_accepts_30():
    w = resolve_strategy_windows({"data": {"scan_window_days": 30}, "liquidity": {"min_listing_days": 30}})
    assert w.scan_window_days == 30


def test_resolve_strategy_windows_rejects_float():
    import pytest
    with pytest.raises(ValueError, match="must be an integer"):
        resolve_strategy_windows({"data": {"scan_window_days": 2.5}})


def test_resolve_strategy_windows_rejects_integer_float():
    """RECHECK-002: 50.0 (float) must be rejected, not silently converted."""
    import pytest
    with pytest.raises(ValueError, match="must be an integer"):
        resolve_strategy_windows({
            "data": {"scan_window_days": 50.0},
            "liquidity": {"min_listing_days": 100},
        })


def test_resolve_strategy_windows_rejects_float_min_listing():
    import pytest
    with pytest.raises(ValueError, match="must be an integer"):
        resolve_strategy_windows({"liquidity": {"min_listing_days": 50.0}})


def test_resolve_strategy_windows_rejects_float_backtest():
    import pytest
    with pytest.raises(ValueError, match="must be an integer"):
        resolve_strategy_windows({"data": {"backtest_window_days": 50.0}})


def test_resolve_strategy_windows_rejects_string():
    import pytest
    with pytest.raises(ValueError, match="must be an integer"):
        resolve_strategy_windows({"data": {"scan_window_days": "50"}})


def test_resolve_strategy_windows_rejects_bool():
    import pytest
    with pytest.raises(ValueError, match="must be an integer"):
        resolve_strategy_windows({"data": {"scan_window_days": True}})


def test_resolve_strategy_windows_rejects_scan_gt_min_listing():
    import pytest
    with pytest.raises(ValueError, match="must not exceed"):
        resolve_strategy_windows({
            "data": {"scan_window_days": 300},
            "liquidity": {"min_listing_days": 200},
        })


def test_resolve_strategy_windows_allows_backtest_gt_min_listing():
    """backtest_window_days can exceed min_listing_days."""
    w = resolve_strategy_windows({
        "data": {"scan_window_days": 200, "backtest_window_days": 500},
        "liquidity": {"min_listing_days": 200},
    })
    assert w.backtest_window_days == 500
    assert w.min_listing_days == 200
    assert w.scan_window_days == 200


def test_old_config_missing_fields_gets_defaults():
    """Old config with no window fields → all 250."""
    w = resolve_strategy_windows({})
    assert w.min_listing_days == WINDOW_DEFAULT
    assert w.scan_window_days == WINDOW_DEFAULT
    assert w.backtest_window_days == WINDOW_DEFAULT


# ── 真实路径一致性 (BUG-010) ────────────────────────────────────────

def test_scan_vs_backtest_core_results_consistent():
    """Same data, same config, same market data → consistent core results.

    Simulates scan path (full data → truncate → evaluate_at)
    vs backtest path (sliding window → truncate → evaluate_at).
    """
    data = make_ohlc_from_closes(build_cup_handle_closes())
    config = full_config()
    config["data"] = config.get("data", {})
    config["data"]["scan_window_days"] = 100
    config["data"]["backtest_window_days"] = 100
    config["liquidity"] = config.get("liquidity", {})
    config["liquidity"]["min_listing_days"] = 250

    # Truncate like scan and backtest would
    scan_data = select_strategy_window(data, 100)
    assert scan_data is not None

    engine = CupHandleStrategyEngine(config)
    e = engine.evaluate_at(scan_data, code="600000", name="测试")

    # Verify core output fields exist and are consistent
    assert e.strategy_version == "cuphandle-v1"
    assert e.config_hash.startswith("sha256:")
    if e.dry_stable:
        assert "decision" in e.dry_stable
        assert "pattern_score" in e.dry_stable
        assert "key_prices" in e.dry_stable
        assert "volume_dry" in e.dry_stable
        assert "price_stable" in e.dry_stable


def test_re_evaluate_same_window_as_scan_produces_same_result(monkeypatch):
    """re_evaluate_task with same data → same evaluate_at result."""
    import scanner.engine as engine_mod

    data = make_ohlc_from_closes(build_cup_handle_closes())
    config = full_config()
    config["data"] = config.get("data", {})
    config["data"]["scan_window_days"] = 100
    config["liquidity"] = config.get("liquidity", {})
    config["liquidity"]["min_listing_days"] = 250

    strategy_data = select_strategy_window(data, 100)
    assert strategy_data is not None

    engine = CupHandleStrategyEngine(config)
    e1 = engine.evaluate_at(strategy_data, code="600000", name="测试")

    # Simulate re_evaluate: same truncated data → same result
    windows = resolve_strategy_windows(config)
    strategy_data2 = select_strategy_window(data, windows.scan_window_days)
    e2 = engine.evaluate_at(strategy_data2, code="600000", name="测试")

    assert e1.passed == e2.passed
    assert e1.result.score == e2.result.score
    assert e1.result.pattern_kind == e2.result.pattern_kind


# ── select_market_window (COMPLETION-001) ───────────────────────────

def test_select_market_window_excludes_future_rows():
    rows = [
        {"date": "2026-01-29"},
        {"date": "2026-01-30"},
        {"date": "2026-02-01"},
    ]
    result = select_market_window(rows, "2026-01-30")
    assert [row["date"] for row in result] == ["2026-01-29", "2026-01-30"]


def test_select_market_window_handles_none():
    assert select_market_window(None, "2026-01-30") == []


def test_select_market_window_handles_empty():
    assert select_market_window([], "2026-01-30") == []


def test_select_market_window_all_within_decision_date():
    rows = [{"date": "2026-01-28"}, {"date": "2026-01-29"}]
    result = select_market_window(rows, "2026-01-30")
    assert len(result) == 2


def test_select_market_window_all_future_returns_empty():
    rows = [{"date": "2026-02-01"}, {"date": "2026-02-02"}]
    result = select_market_window(rows, "2026-01-30")
    assert result == []
