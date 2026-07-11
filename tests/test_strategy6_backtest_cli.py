import json

from scanner import db
from strategy6.backtest.cli import audit_database, build_parser


def test_cli_exposes_audit_fetch_baseline_experiments_and_optimize_commands():
    parser = build_parser()
    for command in ("audit-data", "fetch-index", "baseline", "experiments", "optimize"):
        args = parser.parse_args([command])
        assert args.command == command


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
