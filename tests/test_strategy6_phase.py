from strategy6.models import Strategy6Start
from strategy6.phase import segment_phases
from strategy6.validation import resolve_strategy6_config
from tests.test_strategy6_core_rules import build_strategy6_candidate_data


def test_phase_segmentation_enforces_strict_non_overlapping_order():
    rows = build_strategy6_candidate_data()[-30:]
    start = Strategy6Start(start_date=rows[-14]["date"], start_type="NORMAL_STRONG_BREAKOUT", start_grade="A")
    cfg = resolve_strategy6_config({})

    phase = segment_phases(rows, start, cfg)

    assert phase.valid is True
    assert phase.start_date < phase.consolidation_start_date < phase.tail_start_date <= phase.signal_date
    assert phase.start_index < phase.consolidation_start_index < phase.tail_start_index <= phase.signal_index
    assert phase.tail_days == 5
    assert 5 <= phase.start_age_days <= 60
    assert 5 <= phase.consolidation_days <= 40


def test_start_younger_than_five_days_is_start_confirmed_only():
    rows = build_strategy6_candidate_data()[-30:]
    start = Strategy6Start(start_date=rows[-3]["date"], start_type="VOLUME_LIMIT_UP", start_grade="S")

    phase = segment_phases(rows, start, resolve_strategy6_config({}))

    assert phase.valid is False
    assert phase.status == "START_TOO_RECENT"
    assert phase.lifecycle_status == "START_CONFIRMED"
    assert phase.start_age_days == 2


def test_consolidation_longer_than_configured_maximum_is_invalid():
    rows = build_strategy6_candidate_data()[-70:]
    start = Strategy6Start(start_date=rows[-60]["date"], start_type="VOLUME_LIMIT_UP", start_grade="S")

    phase = segment_phases(rows, start, resolve_strategy6_config({}))

    assert phase.valid is False
    assert phase.status == "CONSOLIDATION_TOO_LONG"
    assert phase.consolidation_days > 40


def test_dynamic_tail_uses_the_earliest_qualified_contraction_window():
    rows = build_strategy6_candidate_data()[-80:]
    start = Strategy6Start(start_date=rows[-30]["date"], start_type="VOLUME_LIMIT_UP", start_grade="S")
    anchor = rows[-11]["close"]
    for index, row in enumerate(rows[-10:-7]):
        row.update({
            "open": anchor * 0.96,
            "high": anchor * 1.08,
            "low": anchor * 0.92,
            "close": anchor * (1.04 if index % 2 == 0 else 0.96),
            "volume": 2_500_000,
        })
    for index, row in enumerate(rows[-7:]):
        close = anchor * (1 + (index % 2) * 0.002)
        row.update({
            "open": close * 0.999,
            "high": close * 1.006,
            "low": close * 0.994,
            "close": close,
            "volume": 350_000,
        })
    cfg = resolve_strategy6_config({"strategy6": {
        "decision_profile": "research_quality_v2",
        "dynamic_tail_min_score": 4,
    }})

    phase = segment_phases(rows, start, cfg)

    assert phase.valid is True
    assert phase.tail_segmentation_status == "DYNAMIC_CONTRACTION"
    assert 6 <= phase.tail_days <= 8
    assert phase.tail_segmentation_score >= 4
    assert phase.tail_range_contraction_ratio < 1
    assert phase.tail_atr_contraction_ratio < 1
    assert phase.tail_body_contraction_ratio < 1


def test_dynamic_tail_falls_back_to_configured_window_without_contraction():
    rows = build_strategy6_candidate_data()[-80:]
    start = Strategy6Start(start_date=rows[-30]["date"], start_type="VOLUME_LIMIT_UP", start_grade="S")
    for index, row in enumerate(rows[-30:]):
        close = 10.0 * (1.05 if index % 2 else 0.95)
        row.update({
            "open": close * 0.97,
            "high": close * 1.08,
            "low": close * 0.92,
            "close": close,
            "volume": 1_000_000,
        })
    cfg = resolve_strategy6_config({"strategy6": {
        "decision_profile": "research_quality_v2",
        "tail_window_days": 5,
    }})

    phase = segment_phases(rows, start, cfg)

    assert phase.tail_days == 5
    assert phase.tail_segmentation_status == "FALLBACK_FIXED"
    assert phase.tail_segmentation_score < cfg["dynamic_tail_min_score"]
