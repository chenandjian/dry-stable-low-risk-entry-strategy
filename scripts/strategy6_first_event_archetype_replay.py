"""Compare Strategy6 first-event selection and archetype execution on frozen signals."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scanner import db
from strategy6.backtest.config import resolve_backtest_config
from strategy6.backtest.data import market_calendar_from_indexes
from strategy6.backtest.entry_execution_research import (
    evaluate_entry_execution_trials,
    rebuild_frozen_entry_archetypes,
)
from strategy6.backtest.index_history import load_index_history
from strategy6.backtest.models import BacktestSignal
from strategy6.engine import StrongVcpTailEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay Strategy6 event selection and archetype entries")
    parser.add_argument("--db", default="data/cuphandle.db")
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--parameter-set-id", required=True)
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--train-end", default="2024-12-31")
    parser.add_argument("--validation-end", default="2025-12-31")
    parser.add_argument("--output", default="docs/reviews/strategy6-first-event-archetype/frozen-replay")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db.init_db(args.db)
    raw_signals = db.get_strategy6_backtest_signals(args.source_run_id, args.parameter_set_id)
    signals = [
        BacktestSignal(
            parameter_set_id=args.parameter_set_id,
            code=str(item.get("code") or ""),
            name=str(item.get("name") or ""),
            evaluation_date=str(item.get("evaluation_date") or ""),
            setup_id=str(item.get("setup_id") or ""),
            tail_path=str(item.get("tail_path") or "NONE"),
            candidate_type=str(item.get("candidate_type") or "REJECTED"),
            snapshot=dict(item.get("snapshot") or {}),
        )
        for item in raw_signals
        if args.start <= str(item.get("evaluation_date") or "") <= args.validation_end
    ]
    if not signals:
        raise ValueError("source run has no frozen signals in requested range")

    index_history = load_index_history(args.start, args.validation_end)
    if index_history.status != "READY":
        raise ValueError(f"real index history unavailable: {index_history.missing_symbols}")
    market_dates = [
        date for date in market_calendar_from_indexes(index_history.data_by_symbol)
        if args.start <= date <= args.validation_end
    ]
    source_signal_count = len(signals)
    rows_by_code = {code: db.get_ohlc(code) or [] for code in sorted({signal.code for signal in signals})}
    missing_codes = [code for code, rows in rows_by_code.items() if not rows]
    missing_signal_count = sum(signal.code in missing_codes for signal in signals)
    signals = [signal for signal in signals if signal.code not in missing_codes]
    if not signals:
        raise ValueError(f"all frozen signals lack stock history: {missing_codes[:20]}")
    strategy_parameters = _load_parameter_config(args.source_run_id, args.parameter_set_id)
    minimum_history = int((strategy_parameters.get("strategy6") or {}).get("minimum_trading_days", 500))
    rebuild = rebuild_frozen_entry_archetypes(
        signals,
        stock_rows_by_code=rows_by_code,
        market_data_by_symbol=index_history.data_by_symbol,
        engine=StrongVcpTailEngine(strategy_parameters),
        minimum_history=minimum_history,
    )
    signals = rebuild["signals"]
    if not signals:
        raise ValueError(f"no frozen signals could rebuild entry archetypes: {rebuild['failed'][:20]}")

    results = evaluate_entry_execution_trials(
        signals,
        load_rows=lambda code: rows_by_code[code],
        market_dates=market_dates,
        base_config=resolve_backtest_config({}),
        train_end=args.train_end,
        validation_end=args.validation_end,
    )
    summary = _build_summary(
        args, signals, index_history.coverage, results,
        source_signal_count=source_signal_count,
        missing_codes=missing_codes,
        missing_signal_count=missing_signal_count,
        entry_rebuild_failed=rebuild["failed"],
    )
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    (output / "report.md").write_text(_build_markdown(summary), encoding="utf-8")
    _write_candidates(output / "daily-candidates.csv", results[0]["signals"])
    _write_orders(output / "orders.csv", results)
    _write_trades(output / "trades.csv", results)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


def _build_summary(
    args,
    signals: list[BacktestSignal],
    coverage: dict,
    results: list[dict],
    *,
    source_signal_count: int,
    missing_codes: list[str],
    missing_signal_count: int,
    entry_rebuild_failed: list[dict],
) -> dict:
    baseline = results[0]
    experiments = []
    for result in results:
        experiments.append({
            "experiment_id": result["experiment_id"],
            "signal_selection_mode": result["signal_selection_mode"],
            "entry_mode": result["entry_mode"],
            "orders": result["orders_count"],
            "filled": result["filled_count"],
            "closed": result["closed_count"],
            "unfilled_rate": result["unfilled_rate"],
            "order_delta_vs_e0": result["orders_count"] - baseline["orders_count"],
            "closed_delta_vs_e0": result["closed_count"] - baseline["closed_count"],
            "fill_reason_counts": result["fill_reason_counts"],
            "full_metrics": result["full_metrics"],
            "train_metrics": result["train_metrics"],
            "validation_metrics": result["validation_metrics"],
            "gate": result["gate"],
        })
    qualified = [
        item["experiment_id"] for item in experiments[1:] if item["gate"]["passed"]
    ]
    return {
        "source_run_id": args.source_run_id,
        "parameter_set_id": args.parameter_set_id,
        "date_range": {"start": args.start, "train_end": args.train_end, "validation_end": args.validation_end},
        "source_signal_count": source_signal_count,
        "replayed_signal_count": len(signals),
        "missing_stock_codes": missing_codes,
        "missing_stock_signal_count": missing_signal_count,
        "entry_rebuild_failed": entry_rebuild_failed,
        "source_setup_count": len({signal.setup_id for signal in signals}),
        "source_stock_count": len({signal.code for signal in signals}),
        "index_status": "READY",
        "index_coverage": coverage,
        "price_basis": "FORWARD_ADJUSTED_LOCAL_OHLC",
        "entry_archetype_counts": dict(Counter(
            str(signal.snapshot.get("entry_archetype") or "UNKNOWN") for signal in signals
        )),
        "oos_status": "LOCKED_2026_PLUS",
        "production_config_modified": False,
        "experiments": experiments,
        "recommendation": {
            "decision": "FULL_CONFIRMATION_REQUIRED" if qualified else "KEEP_CURRENT_RULES",
            "reason": "TRIAL_PASSED_INITIAL_GATE" if qualified else "NO_TRIAL_PASSED_INITIAL_GATE",
            "qualified_experiments": qualified,
        },
    }


def _build_markdown(summary: dict) -> str:
    lines = [
        "# 策略6首次候选事件与分入场类型成交冻结重放报告",
        "",
        f"- 来源任务：`{summary['source_run_id']}`",
        f"- 参数集：`{summary['parameter_set_id']}`",
        f"- 冻结信号：{summary['source_signal_count']}；实际重放：{summary['replayed_signal_count']}；setup：{summary['source_setup_count']}；股票：{summary['source_stock_count']}",
        f"- 缺失个股日线：{', '.join(summary['missing_stock_codes']) or '无'}；排除信号：{summary['missing_stock_signal_count']}",
        f"- 入场原型逐日重建失败：{len(summary['entry_rebuild_failed'])}",
        f"- 入场原型分布：{', '.join(f'{key}={value}' for key, value in summary['entry_archetype_counts'].items())}",
        f"- 价格口径：`{summary['price_basis']}`；真实指数：`{summary['index_status']}`；2026+：`{summary['oos_status']}`",
        "- 四组实验使用完全相同的冻结候选信号，只比较事件去重和成交触发，未修改生产配置。",
        "",
        "| 实验 | 信号选择 | 成交方式 | 订单 | 成交 | 闭合 | 训练交易 | 训练期望R | 训练PF | 验证交易 | 验证期望R | 验证PF | 验证盈亏比 | 门禁 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in summary["experiments"]:
        train = item["train_metrics"]
        validation = item["validation_metrics"]
        lines.append(
            f"| `{item['experiment_id']}` | `{item['signal_selection_mode']}` | `{item['entry_mode']}` | "
            f"{item['orders']} | {item['filled']} | {item['closed']} | {int(train.get('trades') or 0)} | "
            f"{_number(train.get('expectancy_r'))} | {_number(train.get('profit_factor'))} | "
            f"{int(validation.get('trades') or 0)} | {_number(validation.get('expectancy_r'))} | "
            f"{_number(validation.get('profit_factor'))} | {_number(_win_loss_ratio(validation))} | "
            f"{'通过' if item['gate']['passed'] else '淘汰'} |"
        )
    lines.extend(["", "## 门禁明细", ""])
    for item in summary["experiments"]:
        reasons = ", ".join(item["gate"]["reasons"]) or "全部通过"
        lines.append(f"- `{item['experiment_id']}`：{reasons}")
    lines.extend([
        "",
        "## 最终结论",
        "",
        f"- 决策：`{summary['recommendation']['decision']}`",
        f"- 原因：`{summary['recommendation']['reason']}`",
        f"- 初筛入围：{', '.join(summary['recommendation']['qualified_experiments']) or '无'}",
        f"- 正式配置已修改：`{str(summary['production_config_modified']).lower()}`",
        "",
        "## 结论边界",
        "",
        "- 这是同一批真实历史日线和真实指数日历上的冻结信号重放，可以判断事件去重和成交模型是否值得继续。",
        "- 它不能发现来源任务没有生成的新候选；只有初筛通过后才应执行当前代码逐日完整确认和压力测试。",
        "- 训练期与验证期必须同时为正期望、PF>=1.20，验证闭合交易>=30，平均盈利R/平均亏损R>=2.5。",
        "- 本样本没有 PIVOT_BREAKOUT 或 FAILED_BREAKOUT_RECLAIM，分原型结果只验证 SUPPORT_PULLBACK，不能外推到未出现原型。",
        "",
        "## 交付文件",
        "",
        "- `daily-candidates.csv`：逐日冻结候选及首次事件字段。",
        "- `orders.csv`：四组实验全部订单和未成交原因。",
        "- `trades.csv`：四组实验交易明细。",
        "- `summary.json`：机器可读完整汇总。",
    ])
    return "\n".join(lines) + "\n"


def _load_parameter_config(run_id: str, parameter_set_id: str) -> dict:
    row = db.get_conn().execute(
        """SELECT parameter_json FROM strategy6_backtest_parameter_sets
           WHERE run_id=? AND parameter_set_id=?""",
        (run_id, parameter_set_id),
    ).fetchone()
    if not row:
        raise ValueError("source parameter set is missing")
    parameters = json.loads(row[0] or "{}")
    if not isinstance(parameters.get("strategy6"), dict):
        raise ValueError("source parameter set has no strategy6 configuration")
    return parameters


def _write_candidates(path: Path, signals: list[dict]) -> None:
    fields = [
        "evaluation_date", "code", "name", "setup_id", "candidate_type", "candidate_event_id",
        "candidate_event_sequence", "first_candidate_date", "first_executable_date",
        "is_first_candidate_event", "is_first_executable_event", "entry_archetype",
    ]
    _write_csv(path, fields, signals)


def _write_orders(path: Path, results: list[dict]) -> None:
    fields = [
        "experiment_id", "signal_date", "code", "name", "setup_id", "candidate_event_id",
        "candidate_event_sequence", "entry_archetype", "signal_selection_mode", "entry_mode",
        "status", "fill_reason", "expire_date", "audit_tags",
    ]
    rows = [
        {"experiment_id": result["experiment_id"], **order}
        for result in results for order in result["orders"]
    ]
    _write_csv(path, fields, rows)


def _write_trades(path: Path, results: list[dict]) -> None:
    fields = [
        "experiment_id", "signal_date", "entry_date", "exit_date", "code", "name", "setup_id",
        "candidate_event_id", "candidate_event_sequence", "entry_archetype", "signal_selection_mode",
        "entry_mode", "entry_price", "exit_price", "exit_reason", "net_return", "r_multiple",
        "net_profit", "commission", "tax", "slippage",
    ]
    rows = [
        {"experiment_id": result["experiment_id"], **trade}
        for result in results for trade in result["trades"]
    ]
    _write_csv(path, fields, rows)


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            normalized = {
                key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                for key, value in row.items()
            }
            writer.writerow(normalized)


def _number(value) -> str:
    return f"{float(value or 0):.3f}"


def _win_loss_ratio(metrics: dict) -> float:
    average_loss = float(metrics.get("avg_loss_r") or 0)
    return float(metrics.get("avg_win_r") or 0) / average_loss if average_loss > 0 else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
