import copy
from datetime import date, timedelta

import pytest

from strategy6.models import Strategy6VcpObservation


def _rows(count: int = 30) -> list[dict]:
    return [
        {
            "date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1_000_000,
        }
        for index in range(count)
    ]


def _contraction(
    rows: list[dict],
    peak_index: int,
    low_index: int,
    *,
    amplitude: float,
    volume: float,
    peak_close: float,
    low_close: float,
) -> dict:
    return {
        "peak_date": rows[peak_index]["date"],
        "low_date": rows[low_index]["date"],
        "peak_close": peak_close,
        "low_close": low_close,
        "amplitude": amplitude,
        "avg_volume": volume,
    }


def _observation(rows: list[dict], contractions: list[dict]) -> Strategy6VcpObservation:
    return Strategy6VcpObservation(
        eligible=True,
        lifecycle_status="VCP_NEAR_PIVOT",
        pattern_start_date=contractions[0]["peak_date"] if contractions else "",
        pattern_end_date=contractions[-1]["low_date"] if contractions else "",
        contraction_count=len(contractions),
        contractions=contractions,
    )


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, 0), (1, 0), (2, 12), (3, 17), (4, 20), (6, 20)],
)
def test_vcp_quality_contraction_count_boundaries(count, expected):
    from strategy6.vcp_quality import _score_contraction_count

    assert _score_contraction_count(count) == expected


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(0.35, 12), (0.50, 10), (0.65, 8), (0.80, 5), (0.90, 2), (0.9001, 0)],
)
def test_vcp_quality_range_ratio_boundaries(ratio, expected):
    from strategy6.vcp_quality import _score_range_ratio

    assert _score_range_ratio(ratio) == expected


@pytest.mark.parametrize(
    ("amplitude", "expected"),
    [(0.03, 8), (0.05, 6), (0.08, 4), (0.10, 2), (0.1001, 0)],
)
def test_vcp_quality_last_amplitude_boundaries(amplitude, expected):
    from strategy6.vcp_quality import _score_last_amplitude

    assert _score_last_amplitude(amplitude) == expected


@pytest.mark.parametrize(
    ("amplitude", "expected"),
    [(0.0799, 0), (0.08, 5), (0.25, 5), (0.2501, 3), (0.35, 3), (0.3501, 1), (0.45, 1), (0.4501, 0)],
)
def test_vcp_quality_first_amplitude_boundaries(amplitude, expected):
    from strategy6.vcp_quality import _score_first_amplitude

    assert _score_first_amplitude(amplitude) == expected


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(0.50, 15), (0.65, 12), (0.75, 9), (0.85, 6), (0.90, 3), (0.9001, 0)],
)
def test_vcp_quality_volume_ratio_boundaries(ratio, expected):
    from strategy6.vcp_quality import _score_volume_ratio

    assert _score_volume_ratio(ratio) == expected


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(0.35, 10), (0.50, 8), (0.65, 6), (0.80, 3), (0.90, 1), (0.9001, 0)],
)
def test_vcp_quality_total_volume_ratio_boundaries(ratio, expected):
    from strategy6.vcp_quality import _score_total_volume_ratio

    assert _score_total_volume_ratio(ratio) == expected


@pytest.mark.parametrize(
    ("change", "expected"),
    [(0.02, 15), (0.0, 13), (-0.01, 10), (-0.02, 6), (-0.03, 2), (-0.0301, 0)],
)
def test_vcp_quality_low_change_boundaries(change, expected):
    from strategy6.vcp_quality import _score_low_change

    assert _score_low_change(change) == expected


@pytest.mark.parametrize(
    ("days", "expected"),
    [(7, 1), (8, 3), (11, 3), (12, 5), (45, 5), (46, 3), (55, 3), (56, 1)],
)
def test_vcp_quality_total_days_boundaries(days, expected):
    from strategy6.vcp_quality import _score_total_days

    assert _score_total_days(days) == expected


@pytest.mark.parametrize(
    ("gap", "expected"),
    [(0.03, 5), (0.05, 3), (0.08, 1), (0.0801, 0)],
)
def test_vcp_quality_pivot_gap_boundaries(gap, expected):
    from strategy6.vcp_quality import _score_pivot_gap

    assert _score_pivot_gap(gap) == expected


@pytest.mark.parametrize(
    ("score", "grade"),
    [(100, "TOP"), (90, "TOP"), (89, "HIGH"), (80, "HIGH"), (79, "GOOD"), (70, "GOOD"), (69, "NORMAL"), (60, "NORMAL"), (59, "WEAK"), (0, "WEAK")],
)
def test_vcp_quality_grade_boundaries(score, grade):
    from strategy6.vcp_quality import _grade_for_score

    assert _grade_for_score(score) == grade


def test_vcp_quality_uses_half_up_rounding():
    from strategy6.vcp_quality import _round_half_up

    assert _round_half_up(6.5) == 7
    assert _round_half_up(7.5) == 8


def test_vcp_quality_returns_unscored_without_two_complete_contractions():
    from strategy6.vcp_quality import evaluate_vcp_quality

    observation = Strategy6VcpObservation(eligible=True, contractions=[])
    original = copy.deepcopy(observation)

    result = evaluate_vcp_quality([], observation)

    assert result.scored is False
    assert result.score is None
    assert result.grade == ""
    assert observation == original


def test_vcp_quality_calculates_all_components_without_mutating_inputs():
    from strategy6.vcp_quality import evaluate_vcp_quality

    rows = _rows()
    contractions = [
        _contraction(rows, 2, 7, amplitude=0.20, volume=2_000_000, peak_close=100, low_close=80),
        _contraction(rows, 10, 14, amplitude=0.08, volume=1_200_000, peak_close=98, low_close=82),
        _contraction(rows, 17, 20, amplitude=0.03, volume=600_000, peak_close=97, low_close=84),
    ]
    observation = _observation(rows, contractions)
    original_rows = copy.deepcopy(rows)
    original_observation = copy.deepcopy(observation)

    result = evaluate_vcp_quality(rows, observation)

    assert result.scored is True
    assert result.contraction_score == 17
    assert result.range_score == 23
    assert result.volume_score == 24
    assert result.low_score == 15
    assert result.time_score == 10
    assert result.pivot_score == 5
    assert result.score == 94
    assert result.grade == "TOP"
    assert result.model_version == "VCP_QUALITY_V1"
    assert rows == original_rows
    assert observation == original_observation


def test_vcp_quality_caps_one_day_micro_contraction_at_79():
    from strategy6.vcp_quality import evaluate_vcp_quality

    rows = _rows()
    observation = _observation(rows, [
        _contraction(rows, 2, 6, amplitude=0.20, volume=2_000_000, peak_close=100, low_close=80),
        _contraction(rows, 10, 11, amplitude=0.005, volume=500_000, peak_close=99, low_close=82),
    ])

    result = evaluate_vcp_quality(rows, observation)

    assert result.score == 79
    assert result.grade == "GOOD"
    assert "VCP_MICRO_CONTRACTION_NOISE" in result.warnings


def test_vcp_quality_scores_missing_volume_as_zero_with_warning():
    from strategy6.vcp_quality import evaluate_vcp_quality

    rows = _rows()
    observation = _observation(rows, [
        _contraction(rows, 2, 6, amplitude=0.20, volume=0, peak_close=100, low_close=80),
        _contraction(rows, 10, 14, amplitude=0.05, volume=500_000, peak_close=98, low_close=82),
    ])

    result = evaluate_vcp_quality(rows, observation)

    assert result.scored is True
    assert result.volume_score == 0
    assert "VCP_QUALITY_VOLUME_MISSING" in result.warnings


def test_vcp_quality_returns_unscored_when_evidence_dates_are_not_visible():
    from strategy6.vcp_quality import evaluate_vcp_quality

    rows = _rows()
    observation = _observation(rows, [
        _contraction(rows, 2, 6, amplitude=0.20, volume=2_000_000, peak_close=100, low_close=80),
        _contraction(rows, 10, 14, amplitude=0.05, volume=1_000_000, peak_close=98, low_close=82),
    ])
    observation.contractions[-1]["low_date"] = "2027-01-01"

    result = evaluate_vcp_quality(rows, observation)

    assert result.scored is False
    assert result.score is None
    assert result.warnings == ["VCP_QUALITY_DATE_MAPPING_FAILED"]


def test_vcp_quality_ignores_rows_after_the_contraction_evidence():
    from strategy6.vcp_quality import evaluate_vcp_quality

    rows = _rows()
    observation = _observation(rows, [
        _contraction(rows, 2, 7, amplitude=0.20, volume=2_000_000, peak_close=100, low_close=80),
        _contraction(rows, 10, 14, amplitude=0.05, volume=1_000_000, peak_close=98, low_close=82),
    ])
    baseline = evaluate_vcp_quality(rows[:15], observation)
    future = rows[15:] + [{
        "date": "2027-01-01", "open": 1, "high": 999, "low": 1,
        "close": 999, "volume": 999_999_999,
    }]

    assert evaluate_vcp_quality(rows[:15] + future, observation) == baseline
