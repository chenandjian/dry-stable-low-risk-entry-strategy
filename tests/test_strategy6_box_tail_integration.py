from dataclasses import replace

import pytest

from strategy6.box_tail import combine_tail_paths
from strategy6.brooks.models import BrooksTailResult, BrooksTradeTriggerResult
from strategy6.filters import classify_candidate, hard_filter_reasons
from strategy6.models import (
    Strategy6BoxTail,
    Strategy6DryTail,
    Strategy6Indicators,
    Strategy6Pattern,
    Strategy6Phase,
    Strategy6Score,
    Strategy6SetupQuality,
    Strategy6Start,
    Strategy6Support,
    Strategy6TradePlan,
)
from strategy6.scorer import score_strategy6
from strategy6.validation import resolve_strategy6_config


@pytest.mark.parametrize(
    ("original_pass", "box_pass", "expected_path", "expected_pass", "expected_score"),
    [
        (True, False, "ORIGINAL", True, 10),
        (False, True, "BOX", True, 3),
        (True, True, "BOTH", True, 15),
        (False, False, "NONE", False, 0),
    ],
)
def test_tail_paths_use_or_logic(original_pass, box_pass, expected_path, expected_pass, expected_score):
    original = Strategy6DryTail(dry_tail_pass=original_pass, dry_stable_score=16)
    box = Strategy6BoxTail(passed=box_pass, score=18)

    combined = combine_tail_paths(original, box)

    assert combined.passed is expected_pass
    assert combined.path == expected_path
    assert combined.score == expected_score


def test_tail_score_uses_calibrated_path_evidence_and_not_raw_path_max():
    original = Strategy6DryTail(dry_tail_pass=True, dry_stable_score=16)
    box = Strategy6BoxTail(passed=True, score=18, quality_score=27)

    combined = combine_tail_paths(original, box)

    assert combined.score == 15
    assert combined.score != 18
    assert combined.score != 27


def test_three_path_summary_preserves_legacy_tail_path_and_caps_path_evidence():
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
    assert combined.score == 15


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
    assert combined.score == 0


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


def _research_config():
    return resolve_strategy6_config({
        "strategy6": {"decision_profile": "research_quality_v2"},
    })


def test_formal_scoring_uses_original_tail_without_box_dependency():
    ind, start, phase, pattern, support, original, box, trade = _passing_context()
    original = replace(original, dry_tail_pass=True, dry_stable_score=16, rejects=[])
    cfg = resolve_strategy6_config({})

    without_box = score_strategy6(
        ind, start, phase, pattern, support, original, trade, cfg,
        box_tail=replace(box, passed=False, score=0),
    )
    with_box = score_strategy6(
        ind, start, phase, pattern, support, original, trade, cfg,
        box_tail=box,
    )

    assert without_box.score_model_version == "S6_FORMAL_ORIGINAL_V1"
    assert without_box.tail_score == 16
    assert with_box.tail_score == without_box.tail_score
    assert with_box.total_score == without_box.total_score


def test_formal_scoring_does_not_award_pattern_points_when_filter_is_disabled():
    ind, start, phase, pattern, support, original, box, trade = _passing_context()
    cfg = resolve_strategy6_config({
        "strategy6": {"pattern_filter_enabled": False},
    })

    score = score_strategy6(
        ind, start, phase, pattern, support, original, trade, cfg,
        box_tail=box,
    )

    assert score.pattern_score_component == 0


def test_formal_key_candidate_uses_original_tail_score_and_ignores_quality_gate():
    ind, start, phase, pattern, support, original, box, trade = _passing_context()
    original = replace(original, dry_tail_pass=True, dry_stable_score=16, rejects=[])
    cfg = resolve_strategy6_config({})
    score = Strategy6Score(
        total_score=80,
        tail_score=16,
        setup_quality_score=0,
        support_reaction_score=0,
        score_model_version="S6_FORMAL_ORIGINAL_V1",
    )

    candidate_type, *_ = classify_candidate(
        ind,
        start,
        phase,
        pattern,
        support,
        original,
        trade,
        score,
        [],
        cfg,
        box_tail=replace(box, passed=False, score=0),
    )

    assert candidate_type == "KEY_CANDIDATE"


def test_research_scoring_retains_quality_v2_model_and_combined_path_evidence():
    ind, start, phase, pattern, support, original, box, trade = _passing_context()
    cfg = _research_config()

    score = score_strategy6(
        ind,
        start,
        phase,
        pattern,
        support,
        original,
        trade,
        cfg,
        box_tail=box,
        setup_quality=Strategy6SetupQuality(score=20),
    )

    assert score.score_model_version == "S6_QUALITY_V2"
    assert score.tail_score == combine_tail_paths(original, box).score


def test_formal_filters_do_not_allow_box_to_bypass_original_tail_rejects():
    ind, start, phase, pattern, support, original, box, trade = _passing_context()
    original = replace(original, rejects=["TAIL_VOLUME_NOT_DRY"])

    reasons = hard_filter_reasons(
        [{"close": 10.0}, {"close": 10.0}],
        ind,
        start,
        phase,
        pattern,
        support,
        original,
        trade,
        resolve_strategy6_config({}),
        box_tail=box,
    )

    assert "TAIL_VOLUME_NOT_DRY" in reasons


def test_formal_key_threshold_cannot_be_satisfied_by_auxiliary_tail_score():
    ind, start, phase, pattern, support, original, box, trade = _passing_context()
    ind = replace(ind, current_price=11.0)
    original = replace(original, dry_tail_pass=True, dry_stable_score=8, rejects=[])

    candidate_type, *_ = classify_candidate(
        ind,
        start,
        phase,
        pattern,
        support,
        original,
        trade,
        Strategy6Score(
            total_score=95,
            tail_score=18,
            score_model_version="S6_FORMAL_ORIGINAL_V1",
        ),
        [],
        resolve_strategy6_config({}),
        box_tail=box,
    )

    assert candidate_type == "WATCH_CANDIDATE"


def test_box_path_cannot_bypass_original_structural_tail_rejects():
    ind, start, phase, pattern, support, original, box, trade = _passing_context()
    cfg = _research_config()
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

    assert "TAIL_NEW_LOW" in reasons
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


def test_auxiliary_paths_cannot_bypass_severe_distribution_quality_risk():
    ind, start, phase, pattern, support, original, box, trade = _passing_context()
    reasons = hard_filter_reasons(
        [{"close": 10.0}, {"close": 10.0}],
        ind, start, phase, pattern, support, original, trade,
        _research_config(),
        box_tail=box,
        setup_quality=Strategy6SetupQuality(
            score=5,
            distribution_day_count=4,
            risk_tags=["DISTRIBUTION_PRESSURE_HIGH"],
        ),
    )

    assert "DISTRIBUTION_PRESSURE_HIGH" in reasons


def test_box_only_path_is_watch_only_even_with_high_score():
    ind, start, phase, pattern, support, original, box, trade = _passing_context()
    cfg = _research_config()
    score = score_strategy6(
        ind, start, phase, pattern, support, original, trade, cfg,
        box_tail=box,
    )

    assert score.tail_score <= 15
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
    assert candidate_type == "WATCH_CANDIDATE"
    assert lifecycle == "SETUP_FORMING"


def test_brooks_only_waiting_trigger_cannot_emit_ready_or_buy_zone_semantics():
    ind, start, phase, pattern, support, original, box, trade = _passing_context()
    cfg = _research_config()
    brooks = BrooksTailResult(
        enabled=True,
        passed=True,
        score=18,
        status="SECOND_ENTRY_LONG_READY",
        trade_trigger=BrooksTradeTriggerResult(ready=False),
    )

    candidate_type, classification, lifecycle, suggestion = classify_candidate(
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
        box_tail=replace(box, passed=False),
        brooks_tail=brooks,
    )

    assert candidate_type == "WATCH_CANDIDATE"
    assert classification == "observe"
    assert lifecycle == "SETUP_FORMING"
    assert "等待触发" in suggestion


def test_brooks_only_ready_trigger_remains_watch_without_core_confirmation():
    ind, start, phase, pattern, support, original, box, trade = _passing_context()
    brooks = BrooksTailResult(
        enabled=True,
        passed=True,
        score=18,
        trade_trigger=BrooksTradeTriggerResult(ready=True),
    )

    candidate_type, classification, lifecycle, _ = classify_candidate(
        ind,
        start,
        phase,
        pattern,
        support,
        original,
        trade,
        Strategy6Score(total_score=95, tail_score=18),
        [],
        _research_config(),
        box_tail=replace(box, passed=False),
        brooks_tail=brooks,
    )

    assert candidate_type == "WATCH_CANDIDATE"
    assert classification == "observe"
    assert lifecycle == "SETUP_FORMING"


def test_original_or_box_path_is_not_downgraded_by_unready_brooks_path():
    ind, start, phase, pattern, support, original, box, trade = _passing_context()
    brooks = BrooksTailResult(
        enabled=True,
        passed=True,
        score=18,
        trade_trigger=BrooksTradeTriggerResult(ready=False),
    )

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
        _research_config(),
        box_tail=box,
        brooks_tail=brooks,
    )

    assert candidate_type == "READY_CANDIDATE"
    assert lifecycle in {"READY", "BUY_ZONE"}
