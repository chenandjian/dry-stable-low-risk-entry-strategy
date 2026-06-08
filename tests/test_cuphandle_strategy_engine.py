from scanner.pattern_detector import CupHandleResult
from scanner.strategy_engine import (
    StrategyEvaluation,
    CupHandleStrategyEngine,
    build_pattern_config,
    compute_config_hash,
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
    assert evaluation.dry_stable is None


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
            "decision": {"verdict": "观察"},
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
