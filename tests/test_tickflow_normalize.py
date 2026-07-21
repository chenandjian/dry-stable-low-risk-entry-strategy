import math

import pandas as pd
import pytest

from tickflow_data.normalize import TickFlowDataError, normalize_frame


def _frame(**overrides):
    row = {
        "trade_date": "2026-07-20",
        "open": 10.0,
        "high": 10.5,
        "low": 9.8,
        "close": 10.2,
        "volume": 1234,
        "amount": 1_258_680,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_normalize_frame_maps_tickflow_units_and_fields():
    rows = normalize_frame(_frame())

    assert rows == [
        {
            "date": "2026-07-20",
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.2,
            "volume": 123_400.0,
            "turnover": 1_258_680.0,
        }
    ]


def test_normalize_frame_sorts_dates_ascending():
    frame = pd.concat(
        [
            _frame(trade_date="2026-07-21"),
            _frame(trade_date="2026-07-18"),
        ],
        ignore_index=True,
    )

    assert [row["date"] for row in normalize_frame(frame)] == [
        "2026-07-18",
        "2026-07-21",
    ]


def test_normalize_frame_rejects_duplicate_dates():
    frame = pd.concat([_frame(), _frame(close=10.3)], ignore_index=True)

    with pytest.raises(TickFlowDataError, match="duplicate trade date"):
        normalize_frame(frame)


@pytest.mark.parametrize(
    "overrides",
    [
        {"high": 9.9},
        {"low": 10.1},
        {"close": 0},
        {"volume": -1},
        {"amount": -1},
        {"open": math.nan},
    ],
)
def test_normalize_frame_rejects_invalid_rows(overrides):
    with pytest.raises(TickFlowDataError):
        normalize_frame(_frame(**overrides))


def test_normalize_frame_rejects_missing_required_column():
    with pytest.raises(TickFlowDataError, match="missing columns"):
        normalize_frame(_frame().drop(columns=["amount"]))


def test_normalize_frame_rejects_empty_frame():
    with pytest.raises(TickFlowDataError, match="empty"):
        normalize_frame(pd.DataFrame())
