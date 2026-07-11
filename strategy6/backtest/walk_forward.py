"""Calendar-aligned walk-forward windows and OOS lock metadata."""
from __future__ import annotations

import hashlib
import json

from strategy6.backtest.validation import TimeSplit


def build_walk_forward_windows(
    trading_dates: list[str],
    *,
    train_years: int = 3,
    validation_years: int = 1,
) -> dict:
    dates = sorted(set(date for date in trading_dates if len(date) >= 10))
    years = sorted(set(int(date[:4]) for date in dates))
    required = train_years + validation_years
    if len(years) < required:
        return {"status": "INSUFFICIENT_DATA", "windows": [], "available_years": years}
    windows = []
    for start in range(0, len(years) - required + 1):
        train = years[start:start + train_years]
        validation = years[start + train_years:start + required]
        train_dates = [date for date in dates if int(date[:4]) in train]
        validation_dates = [date for date in dates if int(date[:4]) in validation]
        if not train_dates or not validation_dates:
            continue
        windows.append({
            "window_id": f"wf-{train[0]}-{validation[-1]}",
            "train_start": min(train_dates),
            "train_end": max(train_dates),
            "validation_start": min(validation_dates),
            "validation_end": max(validation_dates),
        })
    return {"status": "READY" if windows else "INSUFFICIENT_DATA", "windows": windows, "available_years": years}


def lock_oos(split: TimeSplit, *, data_fingerprint: str, strategy_commit: str) -> dict:
    identity = {
        "start_date": split.oos_start,
        "end_date": split.oos_end,
        "data_fingerprint": data_fingerprint,
        "strategy_commit": strategy_commit,
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {"status": "OOS_LOCKED", **identity, "lock_hash": digest}

