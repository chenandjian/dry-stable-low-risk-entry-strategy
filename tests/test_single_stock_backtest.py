from datetime import datetime, timedelta

import pytest
import scanner.single_stock_backtest as single_stock_backtest
from scanner import db
from scanner.single_stock_backtest import ensure_backtest_data, DataCoverageError


def rows_for_dates(code_dates):
    rows = []
    for i, date in enumerate(code_dates):
        close = 10 + i * 0.1
        rows.append({
            "date": date,
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": 1_000_000 + i,
            "turnover": close * (1_000_000 + i),
        })
    return rows


def date_range(start_date: str, end_date: str) -> list[str]:
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def test_ensure_backtest_data_uses_cache_when_coverage_is_complete(tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    dates = [f"2025-01-{day:02d}" for day in range(1, 21)]
    db.save_ohlc("600000", rows_for_dates(dates))
    calls = []

    def fake_fetch(*args, **kwargs):
        calls.append(args)
        raise AssertionError("fresh fetch should not be called")

    data, coverage = ensure_backtest_data(
        "600000",
        required_start_date="2025-01-01",
        required_end_date="2025-01-20",
        fetch_fn=fake_fetch,
    )

    assert calls == []
    assert len(data) == 20
    assert coverage["source"] == "cache"
    assert coverage["availableRange"] == {"startDate": "2025-01-01", "endDate": "2025-01-20"}


def test_ensure_backtest_data_fetches_when_cache_is_short(tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    db.save_ohlc("600000", rows_for_dates(["2025-01-10", "2025-01-11"]))

    def fake_fetch(code):
        assert code == "600000"
        return rows_for_dates([f"2025-01-{day:02d}" for day in range(1, 21)])

    data, coverage = ensure_backtest_data(
        "600000",
        required_start_date="2025-01-01",
        required_end_date="2025-01-20",
        fetch_fn=fake_fetch,
    )

    assert len(data) == 20
    assert coverage["source"] == "fresh_merged"
    assert db.get_ohlc("600000")[0]["date"] == "2025-01-01"


def test_ensure_backtest_data_default_fetch_requests_span_aware_days(tmp_path, monkeypatch):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    required_start_date = "2024-01-01"
    required_end_date = "2025-02-28"
    full_range_rows = rows_for_dates(date_range(required_start_date, required_end_date))
    fetch_calls = []

    def fake_sina_fetch(code, days=250):
        fetch_calls.append((code, days))
        assert code == "600000"
        if days <= 250:
            return full_range_rows[-250:]
        return full_range_rows

    def fake_tencent_fetch(code, days=250):
        raise AssertionError("tencent fallback should not be used when sina returns data")

    monkeypatch.setattr("scanner.single_stock_backtest.fetch_sina_daily", fake_sina_fetch)
    monkeypatch.setattr("scanner.single_stock_backtest.fetch_tencent_daily", fake_tencent_fetch)

    data, coverage = ensure_backtest_data(
        "600000",
        required_start_date=required_start_date,
        required_end_date=required_end_date,
    )

    assert len(fetch_calls) == 1
    assert fetch_calls[0][0] == "600000"
    assert fetch_calls[0][1] > 250
    assert coverage["source"] == "fresh_merged"
    assert coverage["availableRange"] == {
        "startDate": required_start_date,
        "endDate": required_end_date,
    }
    assert data[0]["date"] == required_start_date
    assert data[-1]["date"] == required_end_date


def test_ensure_backtest_data_injected_fetch_with_days_gets_span_aware_days(tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    required_start_date = "2024-01-01"
    required_end_date = "2025-02-28"
    full_range_rows = rows_for_dates(date_range(required_start_date, required_end_date))
    fetch_calls = []

    def fake_fetch(code, days=250):
        fetch_calls.append((code, days))
        assert code == "600000"
        if days <= 250:
            return full_range_rows[-250:]
        return full_range_rows

    data, coverage = ensure_backtest_data(
        "600000",
        required_start_date=required_start_date,
        required_end_date=required_end_date,
        fetch_fn=fake_fetch,
    )

    assert len(fetch_calls) == 1
    assert fetch_calls[0][0] == "600000"
    assert fetch_calls[0][1] > 250
    assert coverage["source"] == "fresh_merged"
    assert coverage["availableRange"] == {
        "startDate": required_start_date,
        "endDate": required_end_date,
    }
    assert data[0]["date"] == required_start_date
    assert data[-1]["date"] == required_end_date


def test_ensure_backtest_data_raises_when_fresh_data_still_incomplete(tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))

    def fake_fetch(code):
        return rows_for_dates(["2025-01-10", "2025-01-11"])

    try:
        ensure_backtest_data(
            "600000",
            required_start_date="2025-01-01",
            required_end_date="2025-01-20",
            fetch_fn=fake_fetch,
        )
    except DataCoverageError as exc:
        payload = exc.to_dict()
    else:
        raise AssertionError("DataCoverageError was not raised")

    assert payload["error"] == "Insufficient data coverage"
    assert payload["requiredRange"] == {"startDate": "2025-01-01", "endDate": "2025-01-20"}
    assert payload["availableRange"] == {"startDate": "2025-01-10", "endDate": "2025-01-11"}
    assert payload["missingRanges"]


def test_run_single_stock_cuphandle_backtest_exists():
    assert hasattr(single_stock_backtest, "run_single_stock_cuphandle_backtest")


def test_run_backtest_uses_only_data_up_to_detection_day(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    config = {
        "data": {"database_path": str(db_path)},
        "cup": {"max_duration": 60},
        "handle": {"max_duration": 20},
        "breakout": {},
        "scoring": {"medium_threshold": 70},
        "output": {"output_dir": str(tmp_path / "output_data")},
    }
    older_dates = [f"2024-12-{day:02d}" for day in range(27, 32)]
    dates = [f"2025-01-{day:02d}" for day in range(1, 21)]
    data = rows_for_dates(older_dates + dates)
    db.save_ohlc("600000", data)
    seen_windows = []

    class FakeEvaluation:
        def __init__(self, date):
            self.passed = date in {"2025-01-10", "2025-01-11"}
            self.result = type("R", (), {
                "found": self.passed,
                "score": 80,
                "handle_low_date": "2025-01-09",
                "right_high_idx": 7,
                "handle_low_idx": 8,
                "left_high_date": "2025-01-03",
                "cup_low_date": "2025-01-05",
                "right_high_date": "2025-01-08",
                "cup_depth_pct": 20,
                "cup_duration": 5,
                "handle_depth_pct": 7,
                "handle_duration": 2,
                "lip_deviation_pct": 2,
                "is_breakout": False,
                "is_volume_breakout": False,
                "vol_multiplier": 1.0,
            })()
            self.dry_stable = {
                "key_prices": {"entry_zone_low": 10, "entry_zone_high": 11, "pivot": 12, "stop_loss": 9, "target_1": 14, "target_2": 16},
                "risk_reward": {"rr1": 2.0},
                "volume_dry": {"score": 8, "level": "良好"},
                "price_stable": {"score": 7, "level": "良好"},
                "pattern_score": {"score": 16, "type": "cup_handle", "key_pattern_type": "cup_handle"},
                "decision": {"verdict": "可低吸", "summary": "测试通过"},
            }
            self.passed_rules = []
            self.failed_rules = []

    class FakeEngine:
        strategy_version = "cuphandle-v1"
        config_hash = "sha256:" + "1" * 64

        def __init__(self, config):
            self.config = config

        def evaluate_at(self, window, **kwargs):
            seen_windows.append((window[-1]["date"], len(window)))
            return FakeEvaluation(window[-1]["date"])

        def diagnose_handle(self, *args, **kwargs):
            return None

    monkeypatch.setattr(single_stock_backtest, "CupHandleStrategyEngine", FakeEngine, raising=False)

    result = single_stock_backtest.run_single_stock_cuphandle_backtest(
        "600000",
        "2025-01-01",
        "2025-01-20",
        config,
        context_days=0,
    )

    expected_windows = [(date, index) for index, date in enumerate(dates, start=1)]

    assert seen_windows == expected_windows
    assert [date for date, _ in seen_windows] == dates
    assert [length for _, length in seen_windows] == list(range(1, len(dates) + 1))
    assert [row["date"] for row in result["ohlc"]] == dates
    assert result["summary"]["tradingDays"] == len(dates)
    assert result["summary"]["totalPatterns"] == 1
    assert result["patterns"][0]["firstDetectedDate"] == "2025-01-10"
    assert result["patterns"][0]["detectedDate"] in {"2025-01-10", "2025-01-11"}
    assert result["outputFile"].endswith(".json")



def test_run_backtest_writes_json_file(tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    data = rows_for_dates([f"2025-01-{day:02d}" for day in range(1, 21)])
    db.save_ohlc("600000", data)
    config = {
        "data": {"database_path": str(db_path)},
        "output": {"output_dir": str(tmp_path / "output_data")},
        "cup": {},
        "handle": {},
        "breakout": {},
        "scoring": {},
    }

    result = single_stock_backtest.run_single_stock_cuphandle_backtest(
        "600000",
        "2025-01-01",
        "2025-01-20",
        config,
        context_days=0,
    )

    import json
    from pathlib import Path
    path = Path(result["outputFile"])
    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["code"] == "600000"
    assert saved["strategyVersion"] == result["strategyVersion"]



def test_run_backtest_validates_dates(tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    config = {
        "data": {"database_path": str(db_path)},
        "output": {"output_dir": str(tmp_path / "output_data")},
        "cup": {},
        "handle": {},
        "breakout": {},
        "scoring": {},
    }

    with pytest.raises(ValueError, match="start_date must be on or before end_date"):
        single_stock_backtest.run_single_stock_cuphandle_backtest(
            "600000", "2025-01-20", "2025-01-01", config
        )

    with pytest.raises(ValueError, match="handle_start_date and handle_end_date must both be provided"):
        single_stock_backtest.run_single_stock_cuphandle_backtest(
            "600000", "2025-01-01", "2025-01-20", config, handle_start_date="2025-01-05"
        )

    with pytest.raises(ValueError, match="specified handle range must be within backtest range"):
        single_stock_backtest.run_single_stock_cuphandle_backtest(
            "600000",
            "2025-01-10",
            "2025-01-20",
            config,
            handle_start_date="2025-01-05",
            handle_end_date="2025-01-12",
        )



def test_run_backtest_includes_specified_handle_diagnosis(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    config = {
        "data": {"database_path": str(db_path)},
        "output": {"output_dir": str(tmp_path / "output_data")},
        "cup": {},
        "handle": {},
        "breakout": {},
        "scoring": {},
    }
    dates = [f"2025-01-{day:02d}" for day in range(1, 16)]
    db.save_ohlc("600000", rows_for_dates(dates))
    diagnosis_windows = []

    class FakeEvaluation:
        passed = False
        dry_stable = None
        passed_rules = []
        failed_rules = []
        result = type("R", (), {"found": False, "score": 0})()

    class FakeDiagnosis:
        def to_dict(self):
            return {"passed": True, "matchedPatternId": "p1"}

    class FakeEngine:
        strategy_version = "cuphandle-v1"
        config_hash = "sha256:" + "2" * 64

        def __init__(self, config):
            self.config = config

        def evaluate_at(self, window, **kwargs):
            return FakeEvaluation()

        def diagnose_handle(self, data_until_handle_end, handle_start_date, handle_end_date, **kwargs):
            diagnosis_windows.append((len(data_until_handle_end), handle_start_date, handle_end_date))
            return FakeDiagnosis()

    monkeypatch.setattr(single_stock_backtest, "CupHandleStrategyEngine", FakeEngine, raising=False)

    result = single_stock_backtest.run_single_stock_cuphandle_backtest(
        "600000",
        "2025-01-01",
        "2025-01-15",
        config,
        handle_start_date="2025-01-10",
        handle_end_date="2025-01-12",
        context_days=0,
    )

    assert diagnosis_windows == [(12, "2025-01-10", "2025-01-12")]
    assert result["specifiedDiagnosis"] == {"passed": True, "matchedPatternId": "p1"}

