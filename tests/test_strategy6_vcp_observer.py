from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from strategy6.validation import resolve_strategy6_config


def _rows(closes, volumes=None):
    volumes = volumes or [2_000_000 * (0.80 ** (i // 2)) for i in range(len(closes))]
    return [
        {
            "date": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volumes[i],
            "amount": 600_000_000,
        }
        for i, close in enumerate(closes)
    ]


def _contracted_rows():
    closes = [100, 110, 96, 106, 97, 105, 98, 104, 99, 103, 100]
    closes += [103, 100.5, 102.5, 100.8, 102, 101, 102, 101.2, 102, 101.5]
    volumes = [2_500_000] + [2_000_000 * (0.80 ** (i // 2)) for i in range(20)]
    return _rows(closes, volumes)


def _force_valid_anchor(monkeypatch):
    from strategy6 import vcp_observer

    monkeypatch.setattr(
        vcp_observer,
        "find_historical_start_anchor",
        lambda rows, *args, **kwargs: SimpleNamespace(
            start_date=rows[0]["date"],
            failure_reasons=[],
        ),
    )


def test_vcp_observer_defaults_are_explicit_and_validated():
    config = resolve_strategy6_config({})

    assert config["vcp_observer_enabled"] is True
    assert config["vcp_observer_lookback_days"] == 60
    assert config["vcp_observer_breakout_retention_days"] == 10
    assert config["vcp_observer_extension_pct"] == pytest.approx(0.08)


def test_vcp_observer_marks_one_complete_round_as_early_observation(monkeypatch):
    from strategy6 import vcp_observer

    rows = _rows(
        [29.20, 30.95, 28.10, 26.30, 25.10, 24.08, 24.80, 25.74, 24.80, 24.04],
        [70_000_000, 90_000_000, 85_000_000, 80_000_000, 75_000_000,
         65_000_000, 55_000_000, 60_000_000, 50_000_000, 45_000_000],
    )
    monkeypatch.setattr(
        vcp_observer,
        "find_historical_start_anchor",
        lambda *args, **kwargs: SimpleNamespace(start_date=rows[0]["date"], failure_reasons=[]),
    )

    result = vcp_observer.evaluate_vcp_observation(
        rows,
        resolve_strategy6_config({}),
        code="002056",
    )

    assert result.eligible is True
    assert result.lifecycle_status == "VCP_ROUND1_CONFIRMED"
    assert result.contraction_count == 1
    assert result.contractions[0]["recovery_peak_date"] == rows[7]["date"]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("vcp_observer_lookback_days", 19),
        ("vcp_observer_breakout_retention_days", 0),
        ("vcp_observer_extension_pct", 0),
    ],
)
def test_vcp_observer_rejects_invalid_config(key, value):
    with pytest.raises(ValueError, match=key):
        resolve_strategy6_config({"strategy6": {key: value}})


def test_vcp_observer_detects_contracting_structure_near_pivot(monkeypatch):
    from strategy6.vcp_observer import evaluate_vcp_observation

    _force_valid_anchor(monkeypatch)

    result = evaluate_vcp_observation(
        _contracted_rows(),
        resolve_strategy6_config({}),
    )

    assert result.eligible is True
    assert result.lifecycle_status == "VCP_NEAR_PIVOT"
    assert result.contraction_count >= 2
    assert result.pivot_price == pytest.approx(103.0)
    assert result.structure_low == pytest.approx(100.0)
    assert result.distance_to_pivot_pct == pytest.approx(101.5 / 103.0 - 1, abs=1e-6)
    assert result.pattern_start_date < result.pattern_end_date
    assert result.origin_start_date == "2026-01-01"
    assert result.reasons == [
        "VCP_ORIGIN_STRONG_START",
        "VCP_COMPLETE_ROUNDS",
        "VCP_RANGE_CONTRACTING",
        "VCP_VOLUME_CONTRACTING",
        "VCP_LOW_NOT_FALLING",
        "VCP_NEAR_PIVOT",
    ]


def test_vcp_observer_classifies_forming_when_price_is_not_near_pivot(monkeypatch):
    from strategy6.vcp_observer import evaluate_vcp_observation

    _force_valid_anchor(monkeypatch)

    rows = _contracted_rows()
    config = resolve_strategy6_config({
        "strategy6": {"pattern_pivot_proximity_pct": 0.001},
    })

    result = evaluate_vcp_observation(rows, config)

    assert result.eligible is True
    assert result.lifecycle_status == "VCP_CONFIRMED"


def test_vcp_observer_requires_a_historical_passing_strong_start():
    from strategy6.vcp_observer import evaluate_vcp_observation

    closes = [
        100, 102, 104, 106, 108, 110,
        108, 106, 104, 102, 100,
        102, 104, 106, 108,
        106.5, 105, 103.5, 107.5,
    ]
    volumes = [2_000_000] * 11 + [1_000_000] * 8
    rows = _rows(closes, volumes)

    result = evaluate_vcp_observation(
        rows,
        resolve_strategy6_config({}),
        code="000001",
    )

    assert result.contraction_count >= 1
    assert result.eligible is False
    assert result.lifecycle_status == "VCP_NONE"
    assert result.origin_start_date == ""
    assert "VCP_ORIGIN_START_MISSING" in result.risk_tags


def test_historical_start_anchor_ignores_failed_higher_score_event(monkeypatch):
    from strategy6 import strong_start

    failed = SimpleNamespace(
        start_type="VOLUME_LIMIT_UP",
        event_quality_score=20,
        start_date="2026-01-02",
        failure_reasons=["START_LOW_BROKEN"],
    )
    valid = SimpleNamespace(
        start_type="NORMAL_STRONG_BREAKOUT",
        event_quality_score=15,
        start_date="2026-01-03",
        failure_reasons=[],
    )
    candidates = iter([failed, valid])
    monkeypatch.setattr(strong_start, "_build_start_candidate", lambda *args: next(candidates))

    result = strong_start.find_historical_start_anchor(
        _rows([100, 110, 112]),
        resolve_strategy6_config({}),
        "000001",
        end_index=2,
    )

    assert result is valid


@pytest.mark.parametrize(
    "reason",
    [
        "SUPPORT_FAILED",
        "BIG_DOWN_VOLUME",
        "DISTRIBUTION_PRESSURE_HIGH",
        "SUPPORT_VOLUME_BREAK_UNRECOVERED",
    ],
)
def test_vcp_observer_rejects_structural_and_distribution_failures(reason):
    from strategy6.models import Strategy6VcpObservation
    from strategy6.vcp_observer import apply_vcp_base_filters

    observation = Strategy6VcpObservation(
        eligible=True,
        lifecycle_status="VCP_ROUND1_CONFIRMED",
    )

    apply_vcp_base_filters(observation, [reason])

    assert observation.eligible is False
    assert observation.lifecycle_status == "VCP_INVALID"
    assert reason in observation.risk_tags


def test_vcp_observer_tracks_breakout_post_breakout_and_extension(monkeypatch):
    from strategy6.vcp_observer import evaluate_vcp_observation

    _force_valid_anchor(monkeypatch)

    rows = _contracted_rows()
    breakout_volume = 1_200_000
    breakout = _rows([106.0], [breakout_volume])[0]
    breakout["date"] = (date.fromisoformat(rows[-1]["date"]) + timedelta(days=1)).isoformat()
    rows.append(breakout)

    breakout_result = evaluate_vcp_observation(rows, resolve_strategy6_config({}))
    assert breakout_result.lifecycle_status == "VCP_BREAKOUT_CONFIRMED"
    assert breakout_result.breakout_date == breakout["date"]
    assert breakout_result.days_since_breakout == 0

    for close in (105.0, 106.5):
        next_row = _rows([close], [700_000])[0]
        next_row["date"] = (date.fromisoformat(rows[-1]["date"]) + timedelta(days=1)).isoformat()
        rows.append(next_row)
    post_result = evaluate_vcp_observation(rows, resolve_strategy6_config({}))
    assert post_result.lifecycle_status == "VCP_POST_BREAKOUT"
    assert post_result.days_since_breakout == 2

    extended_row = _rows([112.0], [650_000])[0]
    extended_row["date"] = (date.fromisoformat(rows[-1]["date"]) + timedelta(days=1)).isoformat()
    rows.append(extended_row)
    extended_result = evaluate_vcp_observation(rows, resolve_strategy6_config({}))
    assert extended_result.lifecycle_status == "VCP_EXTENDED"
    assert "VCP_PRICE_EXTENDED" in extended_result.risk_tags


def test_vcp_observer_does_not_call_pivot_loss_post_breakout_and_invalidates_unrecovered_volume_break(monkeypatch):
    from strategy6.vcp_observer import evaluate_vcp_observation

    _force_valid_anchor(monkeypatch)

    rows = _contracted_rows()
    for close, volume in (
        (106.0, 1_200_000),
        (101.7, 2_000_000),
    ):
        row = _rows([close], [volume])[0]
        row["date"] = (date.fromisoformat(rows[-1]["date"]) + timedelta(days=1)).isoformat()
        rows.append(row)

    grace = evaluate_vcp_observation(rows, resolve_strategy6_config({}))
    assert grace.eligible is True
    assert grace.lifecycle_status in {"VCP_FORMING", "VCP_NEAR_PIVOT"}
    assert "VCP_PIVOT_LOST" in grace.risk_tags

    for close in (101.75, 101.8, 101.85):
        row = _rows([close], [500_000])[0]
        row["date"] = (date.fromisoformat(rows[-1]["date"]) + timedelta(days=1)).isoformat()
        rows.append(row)

    invalid = evaluate_vcp_observation(rows, resolve_strategy6_config({}))
    assert invalid.eligible is False
    assert invalid.lifecycle_status == "VCP_INVALID"
    assert invalid.invalidation_reason == "VCP_VOLUME_BREAKDOWN_UNRECOVERED"
    assert "VCP_VOLUME_BREAKDOWN_UNRECOVERED" in invalid.risk_tags


def test_vcp_observer_invalidates_structure_break_and_expires_old_breakout(monkeypatch):
    from strategy6.vcp_observer import evaluate_vcp_observation

    _force_valid_anchor(monkeypatch)

    base = _contracted_rows()
    breakout = _rows([106.0], [1_200_000])[0]
    breakout["date"] = (date.fromisoformat(base[-1]["date"]) + timedelta(days=1)).isoformat()

    broken = [*base, breakout]
    break_row = _rows([95.0], [2_000_000])[0]
    break_row["date"] = (date.fromisoformat(broken[-1]["date"]) + timedelta(days=1)).isoformat()
    broken.append(break_row)
    invalid = evaluate_vcp_observation(broken, resolve_strategy6_config({}))
    assert invalid.eligible is False
    assert invalid.lifecycle_status == "VCP_INVALID"
    assert invalid.invalidation_reason == "VCP_STRUCTURE_LOW_BROKEN"

    expired = [*base, breakout]
    for index in range(11):
        row = _rows([104.0], [600_000])[0]
        row["date"] = (date.fromisoformat(expired[-1]["date"]) + timedelta(days=1)).isoformat()
        row["close"] += index * 0.01
        expired.append(row)
    old = evaluate_vcp_observation(expired, resolve_strategy6_config({}))
    assert old.eligible is False
    assert old.lifecycle_status == "VCP_NONE"
    assert "VCP_OBSERVATION_EXPIRED" in old.risk_tags


def test_vcp_observer_does_not_revive_same_structure_after_low_was_broken(monkeypatch):
    from strategy6.vcp_observer import evaluate_vcp_observation

    _force_valid_anchor(monkeypatch)

    rows = _contracted_rows()
    for close, volume in ((106.0, 1_200_000), (95.0, 2_000_000), (105.0, 700_000)):
        row = _rows([close], [volume])[0]
        row["date"] = (date.fromisoformat(rows[-1]["date"]) + timedelta(days=1)).isoformat()
        rows.append(row)

    result = evaluate_vcp_observation(rows, resolve_strategy6_config({}))

    assert result.eligible is False
    assert result.lifecycle_status == "VCP_INVALID"
    assert result.invalidation_reason == "VCP_STRUCTURE_LOW_BROKEN"


def test_vcp_observer_is_as_of_and_does_not_mutate_historical_result(monkeypatch):
    from strategy6.vcp_observer import evaluate_vcp_observation

    _force_valid_anchor(monkeypatch)

    historical_rows = _contracted_rows()
    historical = evaluate_vcp_observation(historical_rows, resolve_strategy6_config({}))
    future_rows = [dict(row) for row in historical_rows]
    future = _rows([106.0], [1_200_000])[0]
    future["date"] = (date.fromisoformat(future_rows[-1]["date"]) + timedelta(days=1)).isoformat()
    future_rows.append(future)

    assert evaluate_vcp_observation(
        future_rows[: len(historical_rows)],
        resolve_strategy6_config({}),
    ) == historical


def test_vcp_observer_replays_real_002156_structure_without_future_leakage(monkeypatch):
    from strategy6.vcp_observer import evaluate_vcp_observation

    _force_valid_anchor(monkeypatch)

    samples = [
        ("2026-05-20", 62.28, 198689180.0), ("2026-05-21", 61.76, 239668006.0),
        ("2026-05-22", 63.44, 200825154.0), ("2026-05-25", 69.78, 227939691.0),
        ("2026-05-26", 75.39, 339104117.0), ("2026-05-27", 71.52, 283496432.0),
        ("2026-05-28", 69.30, 196069725.0), ("2026-05-29", 66.00, 193985192.0),
        ("2026-06-01", 61.39, 158786298.0), ("2026-06-02", 63.84, 162998142.0),
        ("2026-06-03", 70.22, 176502468.0), ("2026-06-04", 71.10, 202609151.0),
        ("2026-06-05", 66.84, 147987895.0), ("2026-06-08", 62.26, 121568182.0),
        ("2026-06-09", 64.43, 128026548.0), ("2026-06-10", 61.44, 111972871.0),
        ("2026-06-11", 60.09, 91814093.0), ("2026-06-12", 57.22, 145541639.0),
        ("2026-06-15", 61.54, 125544435.0), ("2026-06-16", 62.93, 124742380.0),
        ("2026-06-17", 67.22, 179471718.0), ("2026-06-18", 68.27, 163341799.0),
        ("2026-06-22", 71.25, 205216947.0), ("2026-06-23", 68.42, 142535597.0),
        ("2026-06-24", 74.64, 201596971.0), ("2026-06-25", 77.81, 210277817.0),
        ("2026-06-26", 71.60, 196744650.0), ("2026-06-29", 72.58, 169901506.0),
        ("2026-06-30", 75.87, 155699067.0), ("2026-07-01", 73.91, 158048728.0),
        ("2026-07-02", 67.37, 136481252.0), ("2026-07-03", 64.80, 104183554.0),
        ("2026-07-06", 66.18, 110819098.0), ("2026-07-07", 68.21, 126055323.0),
        ("2026-07-08", 65.61, 114466768.0), ("2026-07-09", 72.17, 163246591.0),
        ("2026-07-10", 70.95, 202527658.0), ("2026-07-13", 73.57, 213880418.0),
        ("2026-07-14", 77.87, 242989997.0), ("2026-07-15", 78.71, 293539875.0),
    ]
    rows = [
        {
            "date": day, "open": close, "high": close, "low": close,
            "close": close, "volume": volume, "amount": 0.0,
        }
        for day, close, volume in samples
    ]
    config = resolve_strategy6_config({})

    expected = {
        "2026-07-08": "VCP_ROUND1_CONFIRMED",
        "2026-07-09": "VCP_BREAKOUT_CONFIRMED",
        "2026-07-10": "VCP_POST_BREAKOUT",
        "2026-07-13": "VCP_POST_BREAKOUT",
        "2026-07-14": "VCP_EXTENDED",
    }
    observed = {}
    for day, expected_status in expected.items():
        visible = [row for row in rows if row["date"] <= day]
        result = evaluate_vcp_observation(visible, config)
        observed[day] = result.lifecycle_status
        assert result.lifecycle_status == expected_status
        assert result.eligible is True
        assert result.pivot_price == pytest.approx(68.21)
        expected_low = 64.80 if day == "2026-07-08" else 65.61
        assert result.structure_low == pytest.approx(expected_low)

    assert observed["2026-07-08"] == "VCP_ROUND1_CONFIRMED"
