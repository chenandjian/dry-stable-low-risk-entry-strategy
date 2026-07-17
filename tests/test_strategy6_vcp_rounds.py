from __future__ import annotations

import pytest

from strategy6.validation import resolve_strategy6_config


def _rows(samples):
    return [
        {
            "date": day,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": volume,
            "amount": 0.0,
        }
        for day, close, volume in samples
    ]


def _dates(round_):
    return round_.peak_date, round_.low_date, round_.recovery_peak_date


def test_deep_decline_and_weak_bounce_do_not_form_a_vcp_round():
    from strategy6.vcp_rounds import detect_vcp_rounds

    rows = _rows([
        ("2026-07-01", 22.17, 51_190_208),
        ("2026-07-02", 24.39, 107_107_441),
        ("2026-07-03", 22.14, 93_862_855),
        ("2026-07-06", 20.24, 61_908_140),
        ("2026-07-07", 19.34, 37_416_874),
        ("2026-07-08", 17.88, 43_403_482),
        ("2026-07-09", 17.12, 43_806_144),
        ("2026-07-10", 16.71, 43_447_914),
        ("2026-07-13", 15.82, 33_471_987),
        ("2026-07-14", 16.17, 22_011_457),
        ("2026-07-15", 15.98, 19_650_480),
        ("2026-07-16", 15.84, 14_853_605),
        ("2026-07-17", 16.08, 27_503_322),
    ])

    result = detect_vcp_rounds(rows, resolve_strategy6_config({}))

    assert result.completed_rounds == []
    assert result.confirmed is False


def test_weak_intermediate_bounce_is_merged_into_the_same_round():
    from strategy6.vcp_rounds import detect_vcp_rounds

    rows = _rows([
        ("2026-07-01", 14.64, 160_459_974),
        ("2026-07-02", 15.07, 129_360_709),
        ("2026-07-03", 14.56, 102_030_628),
        ("2026-07-06", 15.18, 111_614_486),
        ("2026-07-07", 14.10, 91_707_491),
        ("2026-07-08", 13.72, 73_785_910),
        ("2026-07-09", 13.59, 75_087_142),
        ("2026-07-10", 13.73, 71_555_830),
        ("2026-07-13", 13.22, 65_227_397),
        ("2026-07-14", 14.54, 88_208_787),
        ("2026-07-15", 14.48, 100_056_790),
        ("2026-07-16", 14.07, 66_882_348),
        ("2026-07-17", 14.65, 101_236_421),
    ])

    result = detect_vcp_rounds(rows, resolve_strategy6_config({}))

    assert len(result.completed_rounds) == 1
    assert _dates(result.completed_rounds[0]) == (
        "2026-07-06", "2026-07-13", "2026-07-14",
    )
    assert result.completed_rounds[0].rebound == pytest.approx(0.099849, abs=1e-6)
    assert result.forming_round is not None
    assert result.forming_round.peak_date == "2026-07-14"
    assert result.forming_round.low_date == "2026-07-16"


def test_two_complete_rounds_include_a_direct_breakout_round():
    from strategy6.vcp_rounds import detect_vcp_rounds

    rows = _rows([
        ("2026-06-25", 77.81, 210_277_817),
        ("2026-06-26", 71.60, 196_744_650),
        ("2026-06-29", 72.58, 169_901_506),
        ("2026-06-30", 75.87, 155_699_067),
        ("2026-07-01", 73.91, 158_048_728),
        ("2026-07-02", 67.37, 136_481_252),
        ("2026-07-03", 64.80, 104_183_554),
        ("2026-07-06", 66.18, 110_819_098),
        ("2026-07-07", 68.21, 126_055_323),
        ("2026-07-08", 65.61, 114_466_768),
        ("2026-07-09", 72.17, 163_246_591),
        ("2026-07-10", 70.95, 202_527_658),
    ])

    result = detect_vcp_rounds(rows, resolve_strategy6_config({}))

    assert [_dates(item) for item in result.completed_rounds] == [
        ("2026-06-30", "2026-07-03", "2026-07-07"),
        ("2026-07-07", "2026-07-08", "2026-07-09"),
    ]
    assert result.completed_rounds[-1].breakout_confirmed is True
    assert result.confirmed is True


def test_one_complete_round_and_unrecovered_second_decline_is_early_observation():
    from strategy6.vcp_rounds import detect_vcp_rounds

    rows = _rows([
        ("2026-07-06", 29.20, 70_000_000),
        ("2026-07-07", 30.95, 90_000_000),
        ("2026-07-08", 28.10, 85_000_000),
        ("2026-07-09", 26.30, 80_000_000),
        ("2026-07-10", 25.10, 75_000_000),
        ("2026-07-13", 24.08, 65_000_000),
        ("2026-07-14", 24.80, 55_000_000),
        ("2026-07-15", 25.74, 60_000_000),
        ("2026-07-16", 24.80, 50_000_000),
        ("2026-07-17", 24.04, 45_000_000),
    ])

    result = detect_vcp_rounds(rows, resolve_strategy6_config({}))

    assert len(result.completed_rounds) == 1
    assert _dates(result.completed_rounds[0]) == (
        "2026-07-07", "2026-07-13", "2026-07-15",
    )
    assert result.confirmed is False
    assert result.early_observation is True
    assert result.forming_round is not None
    assert result.forming_round.low_date == "2026-07-17"
