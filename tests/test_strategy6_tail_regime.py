from __future__ import annotations

from datetime import date, timedelta

from strategy6.tail_regime import _close_range, evaluate_tail_regime


def _regime_rows(*, baseline_days: int = 12, tail_days: int = 7) -> list[dict]:
    rows: list[dict] = []
    previous_close = 100.0
    for index in range(baseline_days + tail_days):
        is_tail = index >= baseline_days
        if is_tail:
            offset = (index - baseline_days) % 3 - 1
            close = 100.0 + offset * 0.08
            open_price = close - 0.05
            high = max(open_price, close) + 0.25
            low = min(open_price, close) - 0.25
            volume = 430_000 + (index % 2) * 10_000
        else:
            direction = 1 if index % 2 == 0 else -1
            close = previous_close * (1 + direction * 0.012)
            open_price = previous_close * (1 - direction * 0.006)
            high = max(open_price, close) * 1.012
            low = min(open_price, close) * 0.988
            volume = 1_000_000 + (index % 3) * 80_000
        rows.append({
            "date": (date(2025, 1, 2) + timedelta(days=index)).isoformat(),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "amount": volume * close,
        })
        previous_close = close
    return rows


def test_detects_confirmed_tail_regime_near_known_change_point():
    rows = _regime_rows()

    result = evaluate_tail_regime(rows, consolidation_start_index=0)

    expected_start = rows[12]["date"]
    assert result.status == "CONFIRMED"
    assert abs((date.fromisoformat(result.start_date) - date.fromisoformat(expected_start)).days) <= 1
    assert result.days >= 6
    assert result.delta_bic >= 6
    assert result.volume_ratio <= 0.80
    assert sum(
        ratio <= 0.85
        for ratio in (result.range_ratio, result.body_ratio, result.abs_return_ratio)
    ) >= 2
    assert result.model_version == "TAIL_REGIME_CP_V1"


def test_volume_contraction_without_price_contraction_is_not_regime_change():
    rows = _regime_rows()
    for index, row in enumerate(rows[-7:]):
        direction = 1 if index % 2 == 0 else -1
        row["open"] = 100.0 * (1 - direction * 0.02)
        row["close"] = 100.0 * (1 + direction * 0.025)
        row["high"] = 104.0
        row["low"] = 96.0

    result = evaluate_tail_regime(rows, consolidation_start_index=0)

    assert result.status == "NO_REGIME_CHANGE"


def test_zero_body_and_zero_return_tail_are_valid_contraction_evidence():
    rows = _regime_rows()
    for row in rows[-7:]:
        row.update({
            "open": 100.0,
            "high": 102.0,
            "low": 98.0,
            "close": 100.0,
        })

    result = evaluate_tail_regime(rows, consolidation_start_index=0)

    assert result.status == "CONFIRMED"
    assert result.body_ratio == 0.0
    assert result.range_ratio > 0.85


def test_dynamic_close_range_reuses_current_close_denominator():
    rows = [
        {"close": 100.0},
        {"close": 107.5},
        {"close": 99.5},
    ]

    assert _close_range(rows) == (107.5 - 99.5) / 99.5


def test_stationary_series_has_no_regime_change():
    rows = _regime_rows(baseline_days=19, tail_days=0)
    for index, row in enumerate(rows):
        offset = index % 3 - 1
        row.update({
            "open": 100.0 + offset * 0.1,
            "high": 100.8 + offset * 0.1,
            "low": 99.2 + offset * 0.1,
            "close": 100.1 + offset * 0.1,
            "volume": 900_000 + (index % 2) * 20_000,
        })

    result = evaluate_tail_regime(rows, consolidation_start_index=0)

    assert result.status == "NO_REGIME_CHANGE"


def test_current_support_break_marks_detected_regime_broken():
    rows = _regime_rows()
    rows[-2]["close"] = 96.8
    rows[-2]["low"] = 96.5
    rows[-1]["close"] = 96.6
    rows[-1]["low"] = 96.3

    result = evaluate_tail_regime(
        rows,
        consolidation_start_index=0,
        key_support_price=98.0,
    )

    assert result.status == "BROKEN"
    assert "SUPPORT_TWO_CLOSE_BREAK" in result.risks


def test_big_down_volume_on_first_tail_bar_marks_regime_broken():
    rows = _regime_rows()
    for index, row in enumerate(rows[-7:]):
        close = 94.0 + (index % 3 - 1) * 0.06
        row.update({
            "open": close + 0.03,
            "high": close + 0.25,
            "low": close - 0.25,
            "close": close,
            "volume": 1_800_000 if index == 0 else 430_000,
        })

    result = evaluate_tail_regime(rows, consolidation_start_index=0)

    assert result.status == "BROKEN"
    assert "TAIL_REGIME_BIG_DOWN_VOLUME" in result.risks


def test_first_detected_day_is_forming_then_stable_start_is_confirmed():
    forming_rows = _regime_rows(tail_days=3)
    middle = forming_rows[-2]
    middle.update({
        "open": 100.0,
        "high": 102.5,
        "low": 99.7,
        "close": 102.4,
    })

    forming = evaluate_tail_regime(forming_rows, consolidation_start_index=0)
    confirmed = evaluate_tail_regime(_regime_rows(tail_days=7), consolidation_start_index=0)

    assert forming.status == "FORMING"
    assert confirmed.status == "CONFIRMED"
    assert forming.start_date == confirmed.start_date


def test_t_minus_one_confirmation_uses_its_own_consolidation_start():
    result = evaluate_tail_regime(
        _regime_rows(tail_days=7),
        consolidation_start_index=0,
        previous_consolidation_start_index=10,
    )

    assert result.status == "FORMING"


def test_t_minus_one_support_break_prevents_false_confirmation():
    result = evaluate_tail_regime(
        _regime_rows(tail_days=7),
        consolidation_start_index=0,
        previous_consolidation_start_index=0,
        key_support_price=98.0,
        previous_key_support_price=101.0,
    )

    assert result.status == "FORMING"
    assert "PREVIOUS_SUPPORT_TWO_CLOSE_BREAK" in result.risks


def test_invalid_t_minus_one_phase_cannot_confirm_current_regime():
    result = evaluate_tail_regime(
        _regime_rows(tail_days=7),
        consolidation_start_index=0,
        previous_consolidation_start_index=0,
        previous_phase_valid=False,
    )

    assert result.status == "FORMING"
    assert "PREVIOUS_PHASE_INVALID" in result.risks


def test_t_minus_one_structure_risks_are_preserved_for_audit(monkeypatch):
    import strategy6.tail_regime as module

    def detection(risks=()):
        return module._Detection(
            split_index=12,
            delta_bic=10.0,
            volume_ratio=0.5,
            range_ratio=0.5,
            body_ratio=0.5,
            abs_return_ratio=0.5,
            close_dispersion=0.01,
            low_slope_atr=0.0,
            reasons=("ROBUST_BIC_CHANGE_POINT",),
            risks=risks,
        )

    monkeypatch.setattr(
        module,
        "_detect_visible_regime",
        lambda rows, **kwargs: (
            detection() if len(rows) == 19
            else detection(("TAIL_REGIME_BIG_DOWN_VOLUME",))
        ),
    )

    result = evaluate_tail_regime(
        _regime_rows(),
        consolidation_start_index=0,
        previous_consolidation_start_index=0,
    )

    assert result.status == "FORMING"
    assert "PREVIOUS_TAIL_REGIME_BIG_DOWN_VOLUME" in result.risks


def test_invalid_or_insufficient_rows_are_reported_without_exception():
    rows = _regime_rows(baseline_days=4, tail_days=3)
    rows[-1]["volume"] = None

    result = evaluate_tail_regime(rows, consolidation_start_index=0)

    assert result.status == "INSUFFICIENT_BASELINE"
    assert result.risks


def test_disabled_detector_returns_explicit_disabled_status():
    result = evaluate_tail_regime(
        _regime_rows(),
        consolidation_start_index=0,
        enabled=False,
    )

    assert result.enabled is False
    assert result.status == "DISABLED"
