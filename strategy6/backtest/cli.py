"""Command-line entry points for Strategy6 research."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from scanner import db
from scanner.config_io import load_yaml_config
from strategy6.backtest.index_history import (
    INDEX_STORAGE_ALIASES,
    ensure_index_history,
    load_index_history,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Strategy6 dual-path historical research")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in (
        "audit-data", "fetch-index", "baseline", "experiments", "optimize",
        "brooks-optimize", "brooks-validate",
        "tail-regime-full",
        "comprehensive-plan", "comprehensive-run", "comprehensive-status",
        "comprehensive-report",
    ):
        child = sub.add_parser(command)
        child.add_argument("--db", default="data/cuphandle.db")
        child.add_argument("--start", default="2023-01-01")
        child.add_argument("--end", default="2025-12-31")
        child.add_argument("--oos-start", default="2026-01-01")
        child.add_argument("--output", default="docs/reviews/strategy6-backtest")
        child.add_argument("--config", default="config.yaml")
        child.add_argument("--max-trials", type=int, default=2000)
        child.add_argument("--campaign-id", default="s6opt-20260712")
        child.add_argument("--stage-id", default="")
        child.add_argument("--max-joint-trials", type=int, default=24)
        child.add_argument(
            "--evaluation-step",
            type=int,
            default=(
                1 if command == "tail-regime-full"
                else 20 if command == "brooks-optimize"
                else 10 if command == "brooks-validate"
                else 5
            ),
        )
        child.add_argument("--trial-index", type=int, default=1)
        child.add_argument(
            "--workers",
            type=int,
            default=max(1, min(8, (os.cpu_count() or 2) - 1)),
            help="parallel stock evaluation processes; SQLite writes remain in the parent process",
        )
    return parser


def audit_database(path: str) -> dict:
    db.init_db(path)
    conn = db.get_conn()
    stock = conn.execute("SELECT COUNT(*) FROM stock_pool").fetchone()[0]
    row = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT code), MIN(date), MAX(date) FROM daily_ohlc"
    ).fetchone()
    index = {}
    for logical_symbol, aliases in INDEX_STORAGE_ALIASES.items():
        stored_symbol, coverage = max(
            ((alias, db.get_market_index_coverage(alias)) for alias in aliases),
            key=lambda item: item[1]["rows"],
        )
        index[logical_symbol] = {**coverage, "stored_symbol": stored_symbol}
    return {
        "database": str(Path(path).resolve()),
        "stocks": stock,
        "ohlc_rows": row[0],
        "ohlc_stocks": row[1],
        "min_date": row[2],
        "max_date": row[3],
        "index_coverage": index,
        "survivorship_bias": True,
        "historical_security_status_complete": False,
        "confidence_label": "RESEARCH_ONLY_CURRENT_UNIVERSE",
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "audit-data":
        print(json.dumps(audit_database(args.db), ensure_ascii=False, indent=2, default=str))
        return 0
    db.init_db(args.db)
    if args.command == "comprehensive-status":
        from strategy6.backtest.comprehensive_runner import campaign_status
        print(json.dumps(campaign_status(args.campaign_id), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "comprehensive-report":
        from strategy6.backtest.comprehensive_report import write_comprehensive_report
        from strategy6.validation import resolve_strategy6_config
        root_config = load_yaml_config(args.config)
        production_config = resolve_strategy6_config({"strategy6": root_config.get("strategy6") or {}})
        result = write_comprehensive_report(args.campaign_id, args.output, production_config)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "fetch-index":
        result = ensure_index_history(args.start, args.end, days=1500)
        print(json.dumps({
            "status": result.status,
            "missing_symbols": result.missing_symbols,
            "coverage": result.coverage,
        }, ensure_ascii=False, indent=2, default=str))
        return 0 if result.status == "READY" else 2
    coverage = load_index_history(args.start, args.end)
    if coverage.status != "READY":
        print(json.dumps({
            "status": coverage.status,
            "missing_symbols": coverage.missing_symbols,
            "message": "Run fetch-index before historical research.",
        }, ensure_ascii=False, indent=2))
        return 2
    if args.command in {"comprehensive-plan", "comprehensive-run"}:
        from strategy6.backtest.comprehensive_runner import run_comprehensive_cli
        return run_comprehensive_cli(args, coverage)
    if args.command == "tail-regime-full":
        from strategy6.backtest.tail_regime_runner import run_tail_regime_full_cli
        return run_tail_regime_full_cli(args, coverage)
    from strategy6.backtest.runner import run_cli_research
    return run_cli_research(args, coverage)


if __name__ == "__main__":
    raise SystemExit(main())
