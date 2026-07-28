from strategy6.engine import StrongVcpTailEngine
from strategy6.validation import resolve_strategy6_config, strategy6_config_hash
from tests.test_strategy6_core_rules import build_strategy6_candidate_data


def test_strategy6_config_hash_is_stable_for_equivalent_config_order():
    first = resolve_strategy6_config({"strategy6": {"rr2_min_watch": 1.6, "tail_window_days": 5}})
    second = resolve_strategy6_config({"strategy6": {"tail_window_days": 5, "rr2_min_watch": 1.6}})

    assert strategy6_config_hash(first) == strategy6_config_hash(second)


def test_candidate_output_contains_strategy_version_and_config_hash():
    result = StrongVcpTailEngine({}).evaluate_at(
        build_strategy6_candidate_data(),
        code="000001",
        name="平安银行",
    )

    candidate = result.to_candidate_dict()
    assert candidate["strategy_version"] == "4.9.0"
    assert len(candidate["config_hash"]) == 64
