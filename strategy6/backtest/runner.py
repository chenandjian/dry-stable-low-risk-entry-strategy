"""Resumable local-database runner for Strategy6 research commands."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import time

import yaml

from scanner import db
from strategy6.backtest.cli import audit_database
from strategy6.backtest.config import resolve_backtest_config
from strategy6.backtest.data import build_data_fingerprint, market_calendar_from_indexes
from strategy6.backtest.experiments import filter_experiment_signals
from strategy6.backtest.metrics import calculate_concentration, calculate_trade_metrics, group_trade_metrics
from strategy6.backtest.models import BacktestRunSpec, ParameterSet
from strategy6.backtest.optimization import (
    build_pareto_frontier,
    calculate_robust_score,
    check_constraints,
    sample_parameter_sets,
)
from strategy6.backtest.portfolio import simulate_portfolio
from strategy6.backtest.report import write_backtest_report
from strategy6.backtest.service import run_parameter_research
from strategy6.backtest.snapshot import signal_to_record
from strategy6.backtest.validation import TimeSplit
from strategy6.backtest.walk_forward import lock_oos
from strategy6.engine import StrongVcpTailEngine
from strategy6.version import STRATEGY6_VERSION


OPTIMIZATION_SPACE = {
    "box_tail.min_box_days": [5, 7, 10],
    "box_tail.max_box_days": [20, 25, 30],
    "box_tail.normal_box_width_max": [0.12, 0.15, 0.18, 0.20],
    "box_tail.min_box_low_test_count": [2, 3],
    "box_tail.min_center_shift": [-0.01, -0.02, -0.03],
    "box_tail.max_volume_contraction_ratio": [0.70, 0.80, 0.85, 0.90],
    "box_tail.tail_volume_ratio_max": [0.60, 0.70, 0.75, 0.80],
}


def run_cli_research(args, coverage) -> int:
    root_config = _load_yaml(args.config)
    backtest_config = resolve_backtest_config({})
    if args.command == "baseline":
        strategy_config = copy.deepcopy(root_config.get("strategy6") or {})
        strategy_config.setdefault("box_tail", {})["enabled"] = False
        result = run_local_parameter_set(
            experiment_id="E0_ORIGINAL_BASELINE",
            strategy_config=strategy_config,
            backtest_config=backtest_config,
            coverage=coverage,
            args=args,
        )
        write_backtest_report(result, args.output)
        return 0
    if args.command == "experiments":
        baseline_config = copy.deepcopy(root_config.get("strategy6") or {})
        baseline_config.setdefault("box_tail", {})["enabled"] = False
        baseline = run_local_parameter_set(
            experiment_id="E0_ORIGINAL_BASELINE", strategy_config=baseline_config,
            backtest_config=backtest_config, coverage=coverage, args=args,
        )
        dual = run_local_parameter_set(
            experiment_id="E1_DUAL_DEFAULT",
            strategy_config=copy.deepcopy(root_config.get("strategy6") or {}),
            backtest_config=backtest_config, coverage=coverage, args=args,
        )
        dual["experiments"] = _derive_experiment_metrics(dual["trades"])
        dual["experiments"]["E0_ORIGINAL_BASELINE"] = baseline["summary"]
        write_backtest_report(dual, args.output)
        return 0
    if args.command == "optimize":
        base = copy.deepcopy(root_config.get("strategy6") or {})
        configs = sample_parameter_sets(
            base, OPTIMIZATION_SPACE,
            max_trials=max(1, int(args.max_trials)), random_seed=20260711,
        )
        trials = []
        final_result = None
        for index, strategy_config in enumerate(configs, start=1):
            result = run_local_parameter_set(
                experiment_id=f"OPTIMIZATION_{index:04d}", strategy_config=strategy_config,
                backtest_config=backtest_config, coverage=coverage, args=args,
            )
            portfolio_metrics = result["summary"].get("fixed_risk_portfolio") or {}
            selector_metrics = {
                "trades": portfolio_metrics.get("trades", 0),
                "expectancy_r": portfolio_metrics.get("expectancy_r", 0),
                "profit_factor": portfolio_metrics.get("profit_factor", 0),
                "max_drawdown": portfolio_metrics.get("max_drawdown", 1),
                "net_return": portfolio_metrics.get("net_return", 0),
            }
            constraint = check_constraints(selector_metrics, {
                "min_total_trades": 100,
                "min_expectancy_r": 0.05,
                "min_profit_factor": 1.10,
                "max_drawdown_pct": 0.25,
            })
            robust = calculate_robust_score(selector_metrics)
            trials.append({
                "parameter_set_id": result["parameter_set_id"],
                **selector_metrics,
                **robust,
                "constraint_passed": constraint["passed"] and result["run"]["status"] == "COMPLETED",
                "constraint_checks": constraint["checks"],
                "parameters": strategy_config.get("box_tail", {}),
            })
            final_result = result
        if final_result is not None:
            eligible = [item for item in trials if item["constraint_passed"]]
            pareto = build_pareto_frontier(eligible)
            final_result["parameter_trials"] = trials
            final_result["optimization"] = {
                "eligible_trials": len(eligible),
                "pareto_parameter_set_ids": [item["parameter_set_id"] for item in pareto],
                "recommendation": "CONDITIONAL" if pareto else "INSUFFICIENT_DATA",
                "production_config_modified": False,
                "oos_used_for_selection": False,
            }
            write_backtest_report(final_result, args.output)
        return 0
    raise ValueError(f"unsupported command: {args.command}")


def run_local_parameter_set(
    *,
    experiment_id: str,
    strategy_config: dict,
    backtest_config: dict,
    coverage,
    args,
) -> dict:
    audit = audit_database(args.db)
    data_version = _database_version(audit, coverage.coverage)
    parameter = ParameterSet.create({"strategy6": strategy_config})
    run = BacktestRunSpec.create(
        experiment_id=experiment_id,
        strategy_version=STRATEGY6_VERSION,
        strategy_git_commit=_git_commit(),
        strategy_config=strategy_config,
        backtest_config=backtest_config,
        data_version=data_version,
    )
    split = TimeSplit(
        "2023-01-01", "2024-12-31", "2025-01-01", "2025-12-31",
        args.oos_start, "2099-12-31",
    )
    db.save_strategy6_backtest_run({
        **run.__dict__, "status": "RUNNING", "split_json": split.__dict__,
    })
    db.save_strategy6_backtest_parameter_set(run.run_id, {
        "parameter_set_id": parameter.parameter_set_id,
        "config_hash": parameter.config_hash,
        "parameters": parameter.parameters,
        "status": "RUNNING",
    })
    dates = [
        date for date in market_calendar_from_indexes(coverage.data_by_symbol)
        if args.start <= date <= args.end and date < args.oos_start
    ]
    conn = db.get_conn()
    stocks = conn.execute("SELECT code, name FROM stock_pool ORDER BY code").fetchall()
    completed = db.get_completed_strategy6_backtest_codes(run.run_id, parameter.parameter_set_id)
    started = time.time()
    for index, (code, name) in enumerate(stocks, start=1):
        if code in completed:
            continue
        rows = _load_stock_rows(conn, code, args.end)
        minimum_history = int(strategy_config.get("minimum_trading_days", 500))
        if len(rows) < minimum_history:
            db.save_strategy6_backtest_stock_progress(
                run.run_id, parameter.parameter_set_id, code, name=name,
                status="SKIPPED_INSUFFICIENT_HISTORY",
                error_message=f"available={len(rows)}, required={minimum_history}",
            )
            continue
        try:
            stock_result = run_parameter_research(
                parameter_set_id=parameter.parameter_set_id,
                data_by_code={code: {"name": name, "rows": rows}},
                evaluation_dates=dates,
                market_data_by_symbol=coverage.data_by_symbol,
                backtest_config=backtest_config,
                engine_factory=lambda cfg=copy.deepcopy(strategy_config): StrongVcpTailEngine({"strategy6": cfg}),
                minimum_history=minimum_history,
                oos_start=args.oos_start,
            )
            db.replace_strategy6_backtest_signals(
                run.run_id, parameter.parameter_set_id, code,
                [_signal_record(item) for item in stock_result["signals"]],
            )
            db.replace_strategy6_backtest_orders(
                run.run_id, parameter.parameter_set_id, code, stock_result["orders"],
            )
            db.replace_strategy6_backtest_trades(
                run.run_id, parameter.parameter_set_id, code, stock_result["trades"],
            )
            db.save_strategy6_backtest_stock_progress(
                run.run_id, parameter.parameter_set_id, code, name=name, status="COMPLETED",
                signals_count=len(stock_result["signals"]), orders_count=len(stock_result["orders"]),
                trades_count=len(stock_result["trades"]),
            )
        except Exception as exc:
            db.save_strategy6_backtest_stock_progress(
                run.run_id, parameter.parameter_set_id, code, name=name, status="FAILED",
                error_message=str(exc),
            )
        if index % 100 == 0:
            elapsed = max(0.001, time.time() - started)
            print(f"[{experiment_id}] {index}/{len(stocks)} stocks, {index / elapsed:.2f} stocks/s", flush=True)
    signals = db.get_strategy6_backtest_signals(run.run_id, parameter.parameter_set_id)
    orders = _load_json_details(conn, "strategy6_backtest_orders", run.run_id, parameter.parameter_set_id)
    trades = _load_json_details(conn, "strategy6_backtest_trades", run.run_id, parameter.parameter_set_id)
    progress_counts = dict(conn.execute(
        '''SELECT status, COUNT(*) FROM strategy6_backtest_stock_progress
           WHERE run_id=? AND parameter_set_id=? GROUP BY status''',
        (run.run_id, parameter.parameter_set_id),
    ).fetchall())
    final_status = resolve_run_completion_status(
        total=len(stocks),
        completed=int(progress_counts.get("COMPLETED", 0)),
        skipped=sum(int(count) for status, count in progress_counts.items() if str(status).startswith("SKIPPED_")),
        failed=int(progress_counts.get("FAILED", 0)),
    )
    summary = calculate_trade_metrics(trades)
    summary["unfilled_rate"] = sum(item.get("status") != "FILLED" for item in orders) / len(orders) if orders else 0.0
    position = backtest_config["position"]
    equal_portfolio = simulate_portfolio(
        trades,
        initial_equity=float(position["initial_equity"]),
        mode="EQUAL_WEIGHT",
        risk_per_trade=float(position["risk_per_trade"]),
        max_position_pct=float(position["max_position_pct"]),
        max_concurrent_positions=int(position["max_concurrent_positions"]),
    )
    risk_portfolio = simulate_portfolio(
        trades,
        initial_equity=float(position["initial_equity"]),
        mode="FIXED_RISK",
        risk_per_trade=float(position["risk_per_trade"]),
        max_position_pct=float(position["max_position_pct"]),
        max_concurrent_positions=int(position["max_concurrent_positions"]),
    )
    summary["equal_weight_portfolio"] = equal_portfolio["metrics"]
    summary["fixed_risk_portfolio"] = risk_portfolio["metrics"]
    db.save_strategy6_backtest_metric(run.run_id, parameter.parameter_set_id, "TRAIN_VALIDATION", "trade", summary)
    db.save_strategy6_backtest_run({
        **run.__dict__, "status": final_status, "split_json": split.__dict__,
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    db.save_strategy6_backtest_parameter_set(run.run_id, {
        "parameter_set_id": parameter.parameter_set_id,
        "config_hash": parameter.config_hash,
        "parameters": parameter.parameters,
        "status": final_status,
        "reject_reason": "" if final_status == "COMPLETED" else "STOCK_EVALUATION_INCOMPLETE",
    })
    oos = lock_oos(split, data_fingerprint=data_version, strategy_commit=run.strategy_git_commit)
    return {
        "run": {**run.__dict__, "status": final_status, "progress_counts": progress_counts},
        "parameter_set_id": parameter.parameter_set_id,
        "data_audit": audit,
        "oos_lock": oos,
        "signals": [item["snapshot"] | {"setup_id": item["setup_id"]} for item in signals],
        "orders": orders,
        "trades": trades,
        "summary": summary,
        "path_metrics": group_trade_metrics(trades, "tail_path"),
        "concentration": calculate_concentration(trades),
        "portfolios": {
            "EQUAL_WEIGHT": equal_portfolio,
            "FIXED_RISK": risk_portfolio,
        },
        "experiments": {},
        "parameter_trials": [],
    }


def _load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _load_stock_rows(conn, code: str, end_date: str) -> list[dict]:
    rows = conn.execute(
        '''SELECT date, open, high, low, close, volume, turnover
           FROM daily_ohlc WHERE code=? AND date<=? ORDER BY date''',
        (code, end_date),
    ).fetchall()
    return [
        {"date": row[0], "open": row[1], "high": row[2], "low": row[3],
         "close": row[4], "volume": row[5], "turnover": row[6]}
        for row in rows
    ]


def _signal_record(item: dict) -> dict:
    return {
        "code": item["code"], "name": item.get("name", ""),
        "evaluation_date": item["evaluation_date"], "setup_id": item["setup_id"],
        "tail_path": item["tail_path"], "candidate_type": item["candidate_type"],
        "snapshot": item,
    }


def _load_json_details(conn, table: str, run_id: str, parameter_set_id: str) -> list[dict]:
    rows = conn.execute(
        f"SELECT detail_json FROM {table} WHERE run_id=? AND parameter_set_id=? ORDER BY code, signal_date",
        (run_id, parameter_set_id),
    ).fetchall()
    return [json.loads(row[0] or "{}") for row in rows]


def _database_version(audit: dict, index_coverage: dict) -> str:
    payload = {"audit": audit, "index": index_coverage}
    return ParameterSet.create(payload).config_hash


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "UNKNOWN"


def _derive_experiment_metrics(trades: list[dict]) -> dict:
    signal_like = trades
    experiment_ids = [
        "E1_DUAL_DEFAULT", "E2_BOX_ONLY_INCREMENT", "E3_BOTH_ONLY",
        "E4_BOX_COMPACT_READY", "E5_BOX_SUPPORT_READY", "E5_BOX_STABLE",
        "E5_BOX_BREAKOUT_READY",
    ]
    return {
        experiment_id: calculate_trade_metrics(filter_experiment_signals(signal_like, experiment_id))
        for experiment_id in experiment_ids
    }


def resolve_run_completion_status(*, total: int, completed: int, skipped: int, failed: int) -> str:
    if failed > 0:
        return "COMPLETED_WITH_ERRORS"
    if completed + skipped != total:
        return "INCOMPLETE"
    if skipped > 0:
        return "COMPLETED_WITH_SKIPS"
    return "COMPLETED"
