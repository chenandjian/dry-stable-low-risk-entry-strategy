from __future__ import annotations

from datetime import date, timedelta

from strategy6.slow_rounded_base import evaluate_slow_rounded_base


REFERENCE_ROWS = [
    ("2026-08-07", 28.56, 29.27, 27.60, 28.53, 175217163),
    ("2026-08-10", 28.50, 29.12, 27.86, 28.09, 136925831),
    ("2026-08-11", 28.09, 28.44, 27.53, 27.73, 102629209),
    ("2026-08-12", 27.53, 28.48, 27.53, 28.17, 118779189),
    ("2026-08-13", 28.17, 28.38, 27.78, 28.00, 86236718),
    ("2026-08-14", 28.17, 28.20, 26.86, 27.17, 128540523),
    ("2026-08-17", 27.20, 27.99, 27.10, 27.90, 85602961),
    ("2026-08-18", 27.92, 28.45, 27.60, 28.33, 93975341),
    ("2026-08-19", 28.25, 28.25, 26.85, 26.85, 117830994),
    ("2026-08-20", 27.64, 27.64, 26.80, 27.07, 73774989),
    ("2026-08-21", 27.10, 27.90, 26.40, 27.77, 103525129),
    ("2026-08-24", 27.77, 28.59, 27.31, 27.76, 99104961),
    ("2026-08-25", 27.50, 28.45, 27.13, 28.18, 79417724),
    ("2026-08-26", 28.18, 28.40, 27.44, 27.93, 68079374),
]


def _rows_from_reference():
    return [
        {
            "date": row[0], "open": row[1], "high": row[2], "low": row[3],
            "close": row[4], "volume": row[5] / row[4], "turnover": row[5],
        }
        for row in REFERENCE_ROWS
    ]


def _rows_from_closes(closes: list[float], *, start: date = date(2026, 1, 5)) -> list[dict]:
    rows = []
    current = start
    previous = closes[0]
    for index, close in enumerate(closes):
        while current.weekday() >= 5:
            current += timedelta(days=1)
        open_price = previous if index else close * 1.003
        span = max(close * 0.008, abs(close - open_price) * 0.35)
        rows.append({
            "date": current.isoformat(),
            "open": round(open_price, 4),
            "high": round(max(open_price, close) + span, 4),
            "low": round(min(open_price, close) - span, 4),
            "close": close,
            "volume": 1_000_000 - index * 8_000,
            "turnover": close * (1_000_000 - index * 8_000),
        })
        previous = close
        current += timedelta(days=1)
    return rows


def test_reference_sample_matches_without_fixed_length_or_drawdown_template():
    result = evaluate_slow_rounded_base(_rows_from_reference())

    assert result["matched"] is True
    assert result["score"] >= 72
    assert result["end_date"] == "2026-08-26"
    # The detector may choose a shorter current sub-window, so the exact
    # reference drawdown must not become a hidden template requirement.
    assert 0.05 <= result["features"]["pullback_depth"] <= 0.15
    assert 10 <= result["window_days"] <= 30


def test_different_depth_and_duration_rounded_bases_also_match():
    six_pct = _rows_from_closes([
        30.0, 29.6, 29.2, 28.9, 28.6, 28.35, 28.2, 28.08,
        28.02, 28.00, 28.03, 28.05, 28.08, 28.10, 28.12, 28.15,
    ])
    thirteen_pct = _rows_from_closes([
        50.0, 48.8, 47.5, 46.4, 45.5, 44.8, 44.3, 43.9, 43.65,
        43.52, 43.48, 43.50, 43.53, 43.55, 43.58, 43.60, 43.62,
        43.65, 43.67, 43.70, 43.72,
    ])

    shallow = evaluate_slow_rounded_base(six_pct)
    deep = evaluate_slow_rounded_base(thirteen_pct)

    assert shallow["matched"] is True
    assert deep["matched"] is True
    assert shallow["window_days"] != 13
    assert deep["window_days"] != 13


def test_same_depth_and_length_v_reversal_does_not_match():
    rows = _rows_from_closes([
        30.0, 29.8, 28.2, 26.0, 27.5, 29.0, 30.1,
        30.5, 30.6, 30.7, 30.8, 30.9, 31.0, 31.1,
    ])

    result = evaluate_slow_rounded_base(rows)

    assert result["matched"] is False
    assert set(result["warnings"]) & {
        "DECLINE_NOT_DECELERATING", "V_REVERSAL_OR_ALREADY_EXTENDED",
    }


def test_flat_box_without_prior_pullback_does_not_match():
    rows = _rows_from_closes([
        20.00, 19.98, 20.03, 20.01, 19.99, 20.02, 20.00,
        20.01, 19.98, 20.00, 20.02, 20.01, 19.99, 20.00,
    ])

    result = evaluate_slow_rounded_base(rows)

    assert result["matched"] is False
    assert result["invariants"]["prior_pullback"] is False


def test_dynamic_search_never_returns_a_stale_historical_end_date():
    old_base = _rows_from_reference()
    extension = _rows_from_closes(
        [29.0, 30.0, 31.2, 32.5, 33.8, 34.5, 35.0, 35.4],
        start=date(2026, 8, 27),
    )
    rows = old_base + extension

    result = evaluate_slow_rounded_base(rows)

    assert result["end_date"] == extension[-1]["date"]
    assert result["matched"] is False


def test_invalid_or_short_history_returns_data_insufficient():
    result = evaluate_slow_rounded_base(_rows_from_closes([10.0] * 9))

    assert result["matched"] is False
    assert result["status"] == "DATA_INSUFFICIENT"
    assert result["grade"] == "UNQUALIFIED"


def test_invalid_latest_bar_does_not_fall_back_to_a_stale_pattern():
    rows = _rows_from_closes([
        30.0, 29.6, 29.2, 28.9, 28.6, 28.35, 28.2, 28.08,
        28.02, 28.00, 28.03, 28.05, 28.08, 28.10,
    ])
    rows.append({
        "date": "2026-01-30", "open": 28.1, "high": 27.0,
        "low": 28.0, "close": 28.1, "volume": 100,
    })

    result = evaluate_slow_rounded_base(rows)

    assert result["matched"] is False
    assert result["status"] == "DATA_INVALID"
    assert result["end_date"] == "2026-01-30"
    assert result["warnings"] == ["LATEST_BAR_INVALID"]


def test_collection_pattern_failure_isolated_from_batch_diagnostics(monkeypatch):
    from strategy6 import collection_patterns

    monkeypatch.setattr(
        collection_patterns,
        "evaluate_slow_rounded_base",
        lambda rows: (_ for _ in ()).throw(RuntimeError("detector failed")),
    )

    result = collection_patterns.evaluate_collection_patterns(_rows_from_reference())

    assert result[0]["matched"] is False
    assert result[0]["status"] == "EVALUATION_FAILED"
    assert result[0]["warnings"] == ["PATTERN_EVALUATION_FAILED"]
