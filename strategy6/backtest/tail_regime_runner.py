"""Resumable full-market runner for Strategy6 tail-regime research."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import copy
import csv
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import hashlib
import subprocess
import time

from scanner import db
from scanner.config_io import load_yaml_config
from strategy6.backtest.config import resolve_backtest_config
from strategy6.backtest.data import build_database_fingerprint, market_calendar_from_indexes
from strategy6.backtest.metrics import calculate_trade_metrics, group_trade_metrics
from strategy6.backtest.models import BacktestSignal, ParameterSet, stable_hash
from strategy6.backtest.stress import replay_stress_scenarios
from strategy6.backtest.tail_regime_research import (
    _filter_stress_results_for_research_periods,
    _partition_closed_trades,
    _research_gate,
    run_tail_regime_research,
)
from strategy6.engine import StrongVcpTailEngine
from strategy6.version import STRATEGY6_VERSION


_WORKER_CONTEXT: dict = {}


def init_tail_regime_checkpoint(
    path: str | Path,
    *,
    run_id: str,
    metadata: dict,
) -> sqlite3.Connection:
    checkpoint = Path(path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(checkpoint)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tail_regime_runs (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tail_regime_stock_progress (
            run_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            status TEXT NOT NULL,
            error_message TEXT DEFAULT '',
            labels_count INTEGER DEFAULT 0,
            signals_count INTEGER DEFAULT 0,
            trades_count INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (run_id, code)
        );
        CREATE TABLE IF NOT EXISTS tail_regime_labels (
            run_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            evaluation_date TEXT NOT NULL,
            group_name TEXT NOT NULL,
            fixed_pass INTEGER NOT NULL,
            fixed_reasons_json TEXT NOT NULL,
            regime_status TEXT,
            regime_start_date TEXT,
            regime_days INTEGER DEFAULT 0,
            regime_delta_bic REAL DEFAULT 0,
            regime_reasons_json TEXT NOT NULL,
            regime_risks_json TEXT NOT NULL,
            PRIMARY KEY (run_id, code, evaluation_date)
        );
        CREATE INDEX IF NOT EXISTS idx_tail_regime_labels_run_group_date
            ON tail_regime_labels(run_id, group_name, evaluation_date);
        CREATE TABLE IF NOT EXISTS tail_regime_signals (
            run_id TEXT NOT NULL,
            code TEXT NOT NULL,
            evaluation_date TEXT NOT NULL,
            detail_json TEXT NOT NULL,
            PRIMARY KEY (run_id, code, evaluation_date)
        );
        CREATE TABLE IF NOT EXISTS tail_regime_orders (
            run_id TEXT NOT NULL,
            code TEXT NOT NULL,
            order_id TEXT NOT NULL,
            detail_json TEXT NOT NULL,
            PRIMARY KEY (run_id, order_id)
        );
        CREATE TABLE IF NOT EXISTS tail_regime_trades (
            run_id TEXT NOT NULL,
            code TEXT NOT NULL,
            trade_id TEXT NOT NULL,
            detail_json TEXT NOT NULL,
            PRIMARY KEY (run_id, trade_id)
        );
    """)
    conn.execute(
        """INSERT OR IGNORE INTO tail_regime_runs
           (run_id, status, metadata_json) VALUES (?, 'RUNNING', ?)""",
        (run_id, _json(metadata)),
    )
    conn.commit()
    return conn


def completed_tail_regime_codes(conn: sqlite3.Connection, run_id: str) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            """SELECT code FROM tail_regime_stock_progress
               WHERE run_id=? AND status='COMPLETED'""",
            (run_id,),
        )
    }


def mark_tail_regime_stock_progress(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    code: str,
    name: str,
    status: str,
    error_message: str = "",
) -> None:
    with conn:
        conn.execute(
            """INSERT INTO tail_regime_stock_progress
               (run_id, code, name, status, error_message, updated_at)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(run_id, code) DO UPDATE SET
                   name=excluded.name,
                   status=excluded.status,
                   error_message=excluded.error_message,
                   updated_at=CURRENT_TIMESTAMP""",
            (run_id, code, name, status, error_message),
        )


def persist_tail_regime_stock_result(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    code: str,
    name: str,
    result: dict,
) -> None:
    labels = list(result.get("daily_labels") or [])
    signals = list(result.get("signals") or [])
    orders = list(result.get("orders") or [])
    trades = list(result.get("trades") or [])
    with conn:
        for table in (
            "tail_regime_labels",
            "tail_regime_signals",
            "tail_regime_orders",
            "tail_regime_trades",
        ):
            conn.execute(
                f"DELETE FROM {table} WHERE run_id=? AND code=?",
                (run_id, code),
            )
        conn.executemany(
            """INSERT INTO tail_regime_labels (
                   run_id, code, name, evaluation_date, group_name,
                   fixed_pass, fixed_reasons_json, regime_status,
                   regime_start_date, regime_days, regime_delta_bic,
                   regime_reasons_json, regime_risks_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(
                run_id,
                code,
                name,
                str(item.get("evaluation_date") or ""),
                str(item.get("group") or "NEITHER"),
                int(bool(item.get("fixed_pass"))),
                _json(item.get("fixed_reasons") or []),
                str(item.get("regime_status") or ""),
                str(item.get("regime_start_date") or ""),
                int(item.get("regime_days") or 0),
                float(item.get("regime_delta_bic") or 0),
                _json(item.get("regime_reasons") or []),
                _json(item.get("regime_risks") or []),
            ) for item in labels],
        )
        conn.executemany(
            """INSERT INTO tail_regime_signals
               (run_id, code, evaluation_date, detail_json) VALUES (?, ?, ?, ?)""",
            [(
                run_id,
                code,
                str(item.get("evaluation_date") or ""),
                _json(item),
            ) for item in signals],
        )
        conn.executemany(
            """INSERT INTO tail_regime_orders
               (run_id, code, order_id, detail_json) VALUES (?, ?, ?, ?)""",
            [(
                run_id,
                code,
                str(item.get("order_id") or f"{code}-{index}"),
                _json(item),
            ) for index, item in enumerate(orders)],
        )
        conn.executemany(
            """INSERT INTO tail_regime_trades
               (run_id, code, trade_id, detail_json) VALUES (?, ?, ?, ?)""",
            [(
                run_id,
                code,
                str(item.get("trade_id") or f"{code}-{index}"),
                _json(item),
            ) for index, item in enumerate(trades)],
        )
        conn.execute(
            """INSERT INTO tail_regime_stock_progress (
                   run_id, code, name, status, error_message,
                   labels_count, signals_count, trades_count, updated_at
               ) VALUES (?, ?, ?, 'COMPLETED', '', ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(run_id, code) DO UPDATE SET
                   name=excluded.name,
                   status='COMPLETED',
                   error_message='',
                   labels_count=excluded.labels_count,
                   signals_count=excluded.signals_count,
                   trades_count=excluded.trades_count,
                   updated_at=CURRENT_TIMESTAMP""",
            (run_id, code, name, len(labels), len(signals), len(trades)),
        )


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def run_tail_regime_full_cli(args, coverage) -> int:
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    root_config = load_yaml_config(args.config)
    strategy_config = copy.deepcopy(root_config.get("strategy6") or {})
    strategy_config["decision_profile"] = "formal_original"
    backtest_config = resolve_backtest_config({})
    main_conn = db.get_conn()
    data_version = build_database_fingerprint(main_conn)
    commit = _git_commit()
    identity = {
        "kind": "TAIL_REGIME_FULL_V1",
        "strategy_version": STRATEGY6_VERSION,
        "strategy_commit": commit,
        "strategy_config": strategy_config,
        "backtest_config": backtest_config,
        "data_version": data_version,
        "start": args.start,
        "end": args.end,
        "oos_start": args.oos_start,
        "evaluation_step": int(args.evaluation_step),
    }
    run_id = f"s6tr-{stable_hash(identity)[:20]}"
    parameter = ParameterSet.create(strategy_config)
    market_dates = [
        date for date in market_calendar_from_indexes(coverage.data_by_symbol)
        if args.start <= date <= args.end and date < args.oos_start
    ][::max(1, int(args.evaluation_step))]
    metadata = {
        **identity,
        "run_id": run_id,
        "parameter_set_id": parameter.parameter_set_id,
        "evaluation_date_count": len(market_dates),
        "confidence_label": "RESEARCH_ONLY_CURRENT_UNIVERSE",
    }
    checkpoint_path = output_dir / "tail-regime-checkpoint.sqlite3"
    checkpoint = init_tail_regime_checkpoint(
        checkpoint_path,
        run_id=run_id,
        metadata=metadata,
    )
    completed = completed_tail_regime_codes(checkpoint, run_id)
    stocks = [
        (str(row[0]), str(row[1] or ""))
        for row in main_conn.execute("SELECT code, name FROM stock_pool ORDER BY code")
    ]
    minimum_history = int(strategy_config.get("minimum_trading_days", 500))
    row_counts = dict(main_conn.execute(
        """SELECT code, COUNT(*) FROM daily_ohlc
           WHERE date<=? GROUP BY code""",
        (args.end,),
    ))
    eligible: list[tuple[str, str]] = []
    for code, name in stocks:
        if code in completed:
            continue
        available = int(row_counts.get(code, 0))
        if available < minimum_history:
            mark_tail_regime_stock_progress(
                checkpoint,
                run_id=run_id,
                code=code,
                name=name,
                status="SKIPPED_INSUFFICIENT_HISTORY",
                error_message=f"available={available}, required={minimum_history}",
            )
        else:
            eligible.append((code, name))

    context = {
        "parameter_set_id": parameter.parameter_set_id,
        "evaluation_dates": market_dates,
        "market_data_by_symbol": coverage.data_by_symbol,
        "reference_market_dates": market_dates,
        "backtest_config": backtest_config,
        "strategy_config": strategy_config,
        "minimum_history": minimum_history,
        "oos_start": args.oos_start,
    }
    started = time.time()
    processed = len(stocks) - len(eligible)
    workers = max(1, int(args.workers))
    stock_iter = iter(eligible)

    def next_payload():
        stock = next(stock_iter, None)
        if stock is None:
            return None
        code, name = stock
        return {
            "code": code,
            "name": name,
            "rows": _load_stock_rows(main_conn, code, args.end),
        }

    def persist_worker_result(item: dict) -> None:
        nonlocal processed
        code = item["code"]
        name = item.get("name", "")
        if item["status"] == "COMPLETED":
            persist_tail_regime_stock_result(
                checkpoint,
                run_id=run_id,
                code=code,
                name=name,
                result=item["result"],
            )
        else:
            mark_tail_regime_stock_progress(
                checkpoint,
                run_id=run_id,
                code=code,
                name=name,
                status="FAILED",
                error_message=item.get("error_message", "unknown worker failure"),
            )
        processed += 1
        if processed % 25 == 0 or processed == len(stocks):
            elapsed = max(0.001, time.time() - started)
            rate = max(0, processed - (len(stocks) - len(eligible))) / elapsed
            remaining = len(stocks) - processed
            eta = remaining / rate if rate > 0 else 0
            print(
                f"[tail-regime-full] {processed}/{len(stocks)} "
                f"rate={rate:.2f} stocks/s eta={eta / 60:.1f}m",
                flush=True,
            )

    if workers == 1:
        _init_worker(context)
        while True:
            payload = next_payload()
            if payload is None:
                break
            persist_worker_result(_evaluate_stock(payload))
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_worker,
            initargs=(context,),
        ) as executor:
            pending = {}
            for _ in range(min(len(eligible), workers * 2)):
                payload = next_payload()
                if payload is not None:
                    pending[executor.submit(_evaluate_stock, payload)] = payload
            while pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    payload = pending.pop(future)
                    try:
                        item = future.result()
                    except Exception as exc:
                        item = {
                            "code": payload["code"],
                            "name": payload["name"],
                            "status": "FAILED",
                            "error_message": f"WORKER_PROCESS_FAILED: {exc}",
                        }
                    persist_worker_result(item)
                    payload = next_payload()
                    if payload is not None:
                        pending[executor.submit(_evaluate_stock, payload)] = payload

    summary = _finalize_tail_regime_run(
        checkpoint,
        run_id=run_id,
        output_dir=output_dir,
        main_conn=main_conn,
        market_dates=market_dates,
        backtest_config=backtest_config,
        metadata=metadata,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    checkpoint.close()
    return 0 if summary["status"] == "COMPLETED" else 2


def _init_worker(context: dict) -> None:
    global _WORKER_CONTEXT
    _WORKER_CONTEXT = context


def _evaluate_stock(payload: dict) -> dict:
    context = _WORKER_CONTEXT
    code = str(payload["code"])
    name = str(payload.get("name") or "")
    try:
        result = run_tail_regime_research(
            parameter_set_id=context["parameter_set_id"],
            data_by_code={code: {"name": name, "rows": payload["rows"]}},
            evaluation_dates=context["evaluation_dates"],
            market_data_by_symbol=context["market_data_by_symbol"],
            reference_market_dates=context["reference_market_dates"],
            backtest_config=context["backtest_config"],
            engine_factory=lambda: StrongVcpTailEngine({
                "strategy6": copy.deepcopy(context["strategy_config"]),
            }),
            minimum_history=context["minimum_history"],
            oos_start=context["oos_start"],
            run_stress=False,
        )
        return {"code": code, "name": name, "status": "COMPLETED", "result": result}
    except Exception as exc:
        return {
            "code": code,
            "name": name,
            "status": "FAILED",
            "error_message": f"{type(exc).__name__}: {exc}",
        }


def _finalize_tail_regime_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    output_dir: Path,
    main_conn: sqlite3.Connection,
    market_dates: list[str],
    backtest_config: dict,
    metadata: dict,
) -> dict:
    progress = dict(conn.execute(
        """SELECT status, COUNT(*) FROM tail_regime_stock_progress
           WHERE run_id=? GROUP BY status""",
        (run_id,),
    ))
    group_counts = dict(conn.execute(
        """SELECT group_name, COUNT(*) FROM tail_regime_labels
           WHERE run_id=? GROUP BY group_name""",
        (run_id,),
    ))
    signals = _load_details(conn, "tail_regime_signals", run_id)
    trades = _load_details(conn, "tail_regime_trades", run_id)
    closed_trades = [trade for trade in trades if trade.get("exit_date")]
    train, validation, cross_period = _partition_closed_trades(closed_trades)
    regime_signals = [
        BacktestSignal(
            parameter_set_id=str(item.get("parameter_set_id") or ""),
            code=str(item.get("code") or ""),
            name=str(item.get("name") or ""),
            evaluation_date=str(item.get("evaluation_date") or ""),
            setup_id=str(item.get("setup_id") or ""),
            tail_path="REGIME",
            candidate_type=str(item.get("candidate_type") or "REJECTED"),
            snapshot=item,
        )
        for item in signals
        if item.get("research_tail_path") == "REGIME"
    ]
    rows_cache: dict[str, list[dict]] = {}

    def load_rows(code: str) -> list[dict]:
        if code not in rows_cache:
            rows_cache[code] = _load_stock_rows(main_conn, code, "2025-12-31")
        return rows_cache[code]

    stress = {}
    if regime_signals:
        stress = _filter_stress_results_for_research_periods(
            replay_stress_scenarios(
                regime_signals,
                load_rows=load_rows,
                market_dates=market_dates,
                base_config=backtest_config,
            )
        )
    gate = _research_gate(train, validation, stress_results=stress)
    failed = int(progress.get("FAILED", 0))
    status = "COMPLETED" if failed == 0 else "COMPLETED_WITH_ERRORS"
    if failed:
        gate = {
            **gate,
            "status": "CONTINUE_SHADOW",
            "reasons": [*gate.get("reasons", []), "FAILED_STOCKS_PRESENT"],
        }
    summary = {
        "status": status,
        "run_id": run_id,
        "metadata": metadata,
        "stock_progress": progress,
        "group_counts": group_counts,
        "signal_count": len(signals),
        "trade_count": len(trades),
        "closed_trade_count": len(closed_trades),
        "summary": calculate_trade_metrics(closed_trades),
        "group_metrics": group_trade_metrics(closed_trades, "tail_regime_group"),
        "train_metrics": calculate_trade_metrics(train),
        "validation_metrics": calculate_trade_metrics(validation),
        "cross_period_trade_count": len(cross_period),
        "stress_tests": {
            name: {
                key: value for key, value in scenario.items() if key != "trades"
            }
            for name, scenario in stress.items()
        },
        "gate": gate,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    _write_daily_candidates_csv(conn, run_id, output_dir / "daily_candidates.csv")
    _write_details_csv(trades, output_dir / "trades.csv")
    with conn:
        conn.execute(
            """UPDATE tail_regime_runs SET status=?, updated_at=CURRENT_TIMESTAMP
               WHERE run_id=?""",
            (status, run_id),
        )
    return summary


def _write_daily_candidates_csv(
    conn: sqlite3.Connection,
    run_id: str,
    path: Path,
) -> None:
    headers = [
        "evaluation_date", "code", "name", "group", "fixed_pass",
        "fixed_reasons", "regime_status", "regime_start_date",
        "regime_days", "regime_delta_bic", "regime_reasons", "regime_risks",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        rows = conn.execute(
            """SELECT evaluation_date, code, name, group_name, fixed_pass,
                      fixed_reasons_json, regime_status, regime_start_date,
                      regime_days, regime_delta_bic, regime_reasons_json,
                      regime_risks_json
               FROM tail_regime_labels
               WHERE run_id=? AND group_name!='NEITHER'
               ORDER BY evaluation_date, code""",
            (run_id,),
        )
        writer.writerows(rows)


def _write_details_csv(items: list[dict], path: Path) -> None:
    keys = sorted({key for item in items for key in item})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for item in items:
            writer.writerow({
                key: _json(value) if isinstance(value, (dict, list)) else value
                for key, value in item.items()
            })


def _load_details(conn: sqlite3.Connection, table: str, run_id: str) -> list[dict]:
    return [
        json.loads(row[0])
        for row in conn.execute(
            f"SELECT detail_json FROM {table} WHERE run_id=?",
            (run_id,),
        )
    ]


def _load_stock_rows(
    conn: sqlite3.Connection,
    code: str,
    end_date: str,
) -> list[dict]:
    columns = ("date", "open", "high", "low", "close", "volume", "turnover")
    return [
        dict(zip(columns, row))
        for row in conn.execute(
            """SELECT date, open, high, low, close, volume, turnover
               FROM daily_ohlc WHERE code=? AND date<=? ORDER BY date""",
            (code, end_date),
        )
    ]


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"
