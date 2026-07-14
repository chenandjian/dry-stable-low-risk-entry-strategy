from dataclasses import replace

import pytest

from strategy6.box_tail import combine_tail_paths
from strategy6.brooks.models import BrooksTailResult
from strategy6.filters import classify_candidate, hard_filter_reasons
from strategy6.models import (
    Strategy6BoxTail,
    Strategy6DryTail,
    Strategy6Indicators,
    Strategy6Pattern,
    Strategy6Phase,
    Strategy6Score,
    Strategy6Start,
    Strategy6Support,
    Strategy6TradePlan,
)
from strategy6.scorer import score_strategy6
from strategy6.validation import resolve_strategy6_config


@pytest.mark.parametrize(
    ("original_pass", "box_pass", "expected_path", "expected_pass", "expected_score"),
    [
        (True, False, "ORIGINAL", True, 16),
        (False, True, "BOX", True, 18),
        (True, True, "BOTH", True, 18),
        (False, False, "NONE", False, 16),
    ],
)
def test_tail_paths_use_or_logic(original_pass, box_pass, expected_path, expected_pass, expected_score):
    original = Strategy6DryTail(dry_tail_pass=original_pass, dry_stable_score=16)
    box = Strategy6BoxTail(passed=box_pass, score=18)

    combined = combine_tail_paths(original, box)

    assert combined.passed is expected_pass
    assert combined.path == expected_path
    assert combined.score == expected_score


def test_tail_score_uses_max_and_never_adds_compact_quality_score():
    original = Strategy6DryTail(dry_tail_pass=True, dry_stable_score=16)
    box = Strategy6BoxTail(passed=True, score=18, quality_score=27)

    combined = combine_tail_paths(original, box)

    assert combined.score == 18
    assert combined.score != 34
    assert combined.score != 27


def test_three_path_summary_preserves_legacy_tail_path_and_uses_max_score():
    original = Strategy6DryTail(dry_tail_pass=True, dry_stable_score=16)
    box = Strategy6BoxTail(enabled=True, passed=True, score=18)
    brooks = BrooksTailResult(enabled=True, passed=True, score=18)

    combined = combine_tail_paths(original, box, brooks)

    assert combined.path == "BOTH"
    assert combined.paths == ["ORIGINAL", "BOX", "BROOKS"]
    assert combined.summary == "MULTI"
    assert combined.primary == "BROOKS"
    assert combined.multi_path_confirmed is True
    assert combined.passed_path_count == 3
    assert combined.score == 18


def test_brooks_only_uses_new_authoritative_fields_without_changing_legacy_path():
    combined = combine_tail_paths(
        Strategy6DryTail(dry_tail_pass=False, dry_stable_score=7),
        Strategy6BoxTail(enabled=True, passed=False, score=12),
        BrooksTailResult(enabled=True, passed=True, score=17),
    )

    assert combined.path == "NONE"
    assert combined.paths == ["BROOKS"]
    assert combined.summary == "BROOKS"
    assert combined.primary == "BROOKS"
    assert combined.passed is True
    assert combined.score == 17


def test_strategy6_config_deep_merges_box_and_compact_defaults():
    cfg = resolve_strategy6_config({
        "strategy6": {
            "box_tail": {"compact_kline": {"enabled": False}},
        }
    })

    assert cfg["box_tail"]["enabled"] is True
    assert cfg["box_tail"]["min_box_days"] == 5
    assert cfg["box_tail"]["compact_kline"]["enabled"] is False
    assert cfg["box_tail"]["compact_kline"]["window_days"] == 5


def test_strategy6_config_rejects_invalid_box_threshold_order():
    with pytest.raises(ValueError, match="max_box_days"):
        resolve_strategy6_config({
            "strategy6": {"box_tail": {"min_box_days": 20, "max_box_days": 10}}
        })

    with pytest.raises(ValueError, match="premium_box_width_max"):
        resolve_strategy6_config({
            "strategy6": {
                "box_tail": {
                    "premium_box_width_max": 0.20,
                    "normal_box_width_max": 0.18,
                }
            }
        })


def _passing_context():
    ind = Strategy6Indicators(
        current_price=10.0,
        trading_days=500,
        ma5=10,
        ma10=10,
        ma20=10,
        ma50=10,
        ma120=11,
        ma250=9,
        amount_avg_10=10,
        amount_avg_30=10,
        amount_avg_60=10,
    )
    start = Strategy6Start(
        start_type="NORMAL_STRONG_BREAKOUT",
        start_grade="A",
        high_trigger="new_120d_high",
    )
    phase = Strategy6Phase(status="PHASE_VALID", valid=True)
    pattern = Strategy6Pattern(pattern_type="VCP", pattern_score=18)
    support = Strategy6Support(
        support_status="KEY_SUPPORT_VALID",
        key_support_price=9.5,
        support_zone_low=9.5,
        support_zone_high=10.5,
        support_test_count=2,
        support_cluster_score=18,
    )
    original = Strategy6DryTail(
        dry_tail_pass=False,
        dry_stable_score=8,
        tail_volume_ratio=0.55,
        rejects=["TAIL_NEW_LOW"],
    )
    box = Strategy6BoxTail(passed=True, score=18, status="BOX_STABLE")
    trade = Strategy6TradePlan(objective_rr_2=3.0, suggested_buy_price=10.0)
    return ind, start, phase, pattern, support, original, box, trade


def test_box_path_removes_only_original_tail_rejects_from_hard_filter():
    ind, start, phase, pattern, support, original, box, trade = _passing_context()
    cfg = resolve_strategy6_config({})
    reasons = hard_filter_reasons(
        [{"close": 10.0}, {"close": 10.0}],
        ind,
        start,
        phase,
        pattern,
        support,
        original,
        trade,
        cfg,
        box_tail=box,
    )

    assert "TAIL_NEW_LOW" not in reasons
    failed_reasons = hard_filter_reasons(
        [{"close": 10.0}, {"close": 10.0}],
        ind,
        start,
        phase,
        pattern,
        support,
        original,
        trade,
        cfg,
        box_tail=replace(box, passed=False),
    )
    assert "TAIL_NEW_LOW" in failed_reasons


def test_box_only_path_can_reach_existing_candidate_classification_without_threshold_changes():
    ind, start, phase, pattern, support, original, box, trade = _passing_context()
    cfg = resolve_strategy6_config({})
    score = score_strategy6(
        ind, start, phase, pattern, support, original, trade, cfg,
        box_tail=box,
    )

    assert score.tail_score == 18
    assert score.dry_stable_score == original.dry_stable_score
    candidate_type, _, lifecycle, _ = classify_candidate(
        ind,
        start,
        phase,
        pattern,
        support,
        original,
        trade,
        Strategy6Score(total_score=95, tail_score=18),
        [],
        cfg,
        box_tail=box,
    )
    assert candidate_type == "READY_CANDIDATE"
    assert lifecycle in {"READY", "BUY_ZONE"}
