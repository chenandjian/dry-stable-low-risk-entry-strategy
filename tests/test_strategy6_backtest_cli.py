import json

from scanner import db
from strategy6.backtest.cli import audit_database, build_parser


def test_cli_exposes_audit_fetch_baseline_experiments_and_optimize_commands():
    parser = build_parser()
    for command in (
        "audit-data", "fetch-index", "baseline", "experiments", "optimize",
        "selection-optimize",
        "entry-quality-optimize",
    ):
        args = parser.parse_args([command])
        assert args.command == command

    selection = parser.parse_args(["selection-optimize", "--trial-index", "7"])
    assert selection.trial_index == 7
    entry_quality = parser.parse_args(["entry-quality-optimize", "--trial-index", "4"])
    assert entry_quality.trial_index == 4


def test_cli_accepts_bounded_parallel_worker_count():
    parser = build_parser()
    assert parser.parse_args(["baseline", "--workers", "3"]).workers == 3
    assert parser.parse_args(["baseline"]).workers >= 1


def test_database_audit_reports_stock_and_index_coverage(tmp_path):
    path = tmp_path / "audit.db"
    db.init_db(str(path))
    db.save_stock_pool([{"code": "000001", "name": "样本", "market": "sz"}])
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO daily_ohlc(code,date,open,high,low,close,volume,turnover) VALUES(?,?,?,?,?,?,?,?)",
        ("000001", "2025-01-02", 10, 11, 9, 10, 100, 1000),
    )
    conn.commit()
    audit = audit_database(str(path))
    assert audit["stocks"] == 1
    assert audit["ohlc_rows"] == 1
    assert audit["survivorship_bias"] is True
    assert audit["confidence_label"] == "RESEARCH_ONLY_CURRENT_UNIVERSE"
