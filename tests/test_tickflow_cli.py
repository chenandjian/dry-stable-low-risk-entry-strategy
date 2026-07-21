import json

import pandas as pd

from scanner import db
from tickflow_data.cli import parse_args, run_command
from tickflow_data.models import BatchFetchResult


def _frame(code, days=3):
    base = int(code[-2:]) / 100
    return pd.DataFrame(
        [
            {
                "trade_date": f"2026-07-{day:02d}",
                "open": 10 + base + day / 10,
                "high": 10.3 + base + day / 10,
                "low": 9.9 + base + day / 10,
                "close": 10.2 + base + day / 10,
                "volume": 1000 + day,
                "amount": 1_000_000 + day,
            }
            for day in range(1, days + 1)
        ]
    )


class _Client:
    def __init__(self, responses, calls):
        self.responses = responses
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def fetch(self, symbols, *, count):
        self.calls.append((list(symbols), count))
        return self.responses.pop(0)


def _factory(responses, calls):
    return lambda **kwargs: _Client(responses, calls)


def _seed_database(path):
    db.init_db(str(path))
    db.save_stock_pool(
        [
            {"code": "600519", "name": "贵州茅台", "market": "SH"},
            {"code": "000001", "name": "平安银行", "market": "SZ"},
        ]
    )


def test_cli_defaults_to_dry_run():
    args = parse_args(["update", "--codes", "600519"])

    assert args.execute is False
    assert args.dry_run is True
    assert args.history_days == 1100
    assert args.overlap_days == 10


def test_execute_creates_backup_progress_and_report(tmp_path):
    database = tmp_path / "cuphandle.db"
    progress = tmp_path / "progress.json"
    report = tmp_path / "report.md"
    _seed_database(database)
    calls = []
    responses = [
        BatchFetchResult(
            frames={
                "600519.SH": _frame("600519"),
                "000001.SZ": _frame("000001"),
            }
        )
    ]
    args = parse_args(
        [
            "backfill",
            "--execute",
            "--database",
            str(database),
            "--progress-file",
            str(progress),
            "--report",
            str(report),
        ]
    )

    result = run_command(args, client_factory=_factory(responses, calls))

    assert result.dry_run is False
    assert calls == [(["600519.SH", "000001.SZ"], 1100)]
    assert list(tmp_path.glob("cuphandle.pre-tickflow-*.db"))
    payload = json.loads(progress.read_text(encoding="utf-8"))
    assert payload["completed_codes"] == ["000001", "600519"]
    assert payload["adjustment"] == "forward_additive"
    assert payload["runs"][-1]["summary"] == {
        "requested": 2,
        "succeeded": 2,
        "failed": 0,
        "full_refresh": 2,
    }
    assert payload["runs"][-1]["elapsed_seconds"] >= 0
    assert "TickFlow批量日线运行报告" in report.read_text(encoding="utf-8")
    assert db.get_ohlc_metadata("600519")["source"] == "tickflow"


def test_resume_skips_successes_and_retries_failures(tmp_path):
    database = tmp_path / "cuphandle.db"
    progress = tmp_path / "progress.json"
    report = tmp_path / "report.md"
    _seed_database(database)
    first_calls = []
    first_responses = [
        BatchFetchResult(
            frames={"600519.SH": _frame("600519")},
            missing_symbols=["000001.SZ"],
        )
    ]
    common_args = [
        "backfill",
        "--execute",
        "--database",
        str(database),
        "--progress-file",
        str(progress),
        "--report",
        str(report),
    ]
    run_command(
        parse_args(common_args),
        client_factory=_factory(first_responses, first_calls),
    )

    second_calls = []
    second_responses = [
        BatchFetchResult(frames={"000001.SZ": _frame("000001")})
    ]
    result = run_command(
        parse_args(common_args),
        client_factory=_factory(second_responses, second_calls),
    )

    assert second_calls == [(["000001.SZ"], 1100)]
    assert [item.code for item in result.results] == ["000001"]
    payload = json.loads(progress.read_text(encoding="utf-8"))
    assert payload["completed_codes"] == ["000001", "600519"]


def test_cli_rejects_progress_file_from_incompatible_run(tmp_path):
    database = tmp_path / "cuphandle.db"
    progress = tmp_path / "progress.json"
    _seed_database(database)
    progress.write_text(
        json.dumps(
            {
                "mode": "update",
                "database": str(database.resolve()),
                "history_days": 800,
                "overlap_days": 10,
                "adjustment": "forward_additive",
                "completed_codes": ["600519"],
            }
        ),
        encoding="utf-8",
    )
    args = parse_args(
        [
            "backfill",
            "--execute",
            "--database",
            str(database),
            "--progress-file",
            str(progress),
        ]
    )

    try:
        run_command(args, client_factory=_factory([], []))
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("incompatible progress file should be rejected")


def test_default_progress_file_starts_a_new_daily_run_each_time(tmp_path):
    database = tmp_path / "cuphandle.db"
    _seed_database(database)
    argv = [
        "backfill",
        "--execute",
        "--database",
        str(database),
        "--codes",
        "600519",
    ]

    first_calls = []
    run_command(
        parse_args(argv),
        client_factory=_factory(
            [BatchFetchResult(frames={"600519.SH": _frame("600519")})],
            first_calls,
        ),
    )
    second_calls = []
    run_command(
        parse_args(argv),
        client_factory=_factory(
            [BatchFetchResult(frames={"600519.SH": _frame("600519")})],
            second_calls,
        ),
    )

    assert first_calls == [(["600519.SH"], 1100)]
    assert second_calls == [(["600519.SH"], 1100)]
    assert len(list((tmp_path / "tickflow").glob("progress-backfill-*.json"))) == 2
