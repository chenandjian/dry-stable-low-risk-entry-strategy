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
