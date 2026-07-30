"""Rebuild Strategy6 entry diagnostics and replay frozen candidate filters."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scanner import db
from scanner.config_io import load_yaml_config
from strategy6.backtest.index_history import load_index_history
from strategy6.backtest.runner import _formal_strategy_config
from strategy6.backtest.selection_optimization import (
    build_entry_quality_trial_configs,
    evaluate_frozen_selection_trials,
    rebuild_frozen_selection_diagnostics,
)
from strategy6.engine import StrongVcpTailEngine
from strategy6.validation import resolve_strategy6_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay Strategy6 entry timing and probability-RR over frozen signals",
    )
    parser.add_argument("--db", default="data/cuphandle.db")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--parameter-set-id", required=True)
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--train-end", default="2024-12-31")
    parser.add_argument("--output", default="docs/reviews/strategy6-entry-quality/frozen-replay")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db.init_db(args.db)
    signals = db.get_strategy6_backtest_signals(
        args.source_run_id,
        args.parameter_set_id,
    )
    if not signals:
        raise ValueError("source run has no frozen signals")
    trades = _load_trades(args.source_run_id, args.parameter_set_id)
    coverage = load_index_history(args.start, args.end)
    if coverage.status != "READY":
        raise ValueError(f"real index history unavailable: {coverage.missing_symbols}")

    root_config = load_yaml_config(args.config)
    strategy_config = resolve_strategy6_config({
        "strategy6": _formal_strategy_config(root_config.get("strategy6") or {}),
    })
    codes = sorted({str(signal.get("code") or "") for signal in signals})
    stock_rows = {code: db.get_ohlc(code) or [] for code in codes}
    rebuilt = rebuild_frozen_selection_diagnostics(
        signals,
        stock_rows_by_code=stock_rows,
        market_data_by_symbol=coverage.data_by_symbol,
        engine=StrongVcpTailEngine({"strategy6": strategy_config}),
        minimum_history=int(strategy_config.get("minimum_trading_days", 500)),
    )
    results = evaluate_frozen_selection_trials(
        rebuilt["signals"],
        trades,
        build_entry_quality_trial_configs(strategy_config),
        train_end=args.train_end,
    )
    experiment_summaries = [_summary_item(item) for item in results]
    qualified = [
        item["experiment_id"]
        for item in experiment_summaries[1:]
        if _passes_initial_gate(item)
    ]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "source_run_id": args.source_run_id,
        "parameter_set_id": args.parameter_set_id,
        "source_signal_count": len(signals),
        "source_trade_count": len(trades),
        "rebuilt_signal_count": len(rebuilt["signals"]),
        "rebuild_failed": rebuilt["failed"],
        "index_status": coverage.status,
        "oos_status": "LOCKED_2026_PLUS",
        "production_config_modified": False,
        "experiments": experiment_summaries,
        "recommendation": {
            "decision": "FULL_CONFIRMATION_REQUIRED" if qualified else "KEEP_CURRENT_RULES",
            "reason": "TRIAL_PASSED_INITIAL_SCREEN" if qualified else "NO_TRIAL_PASSED_SCREEN",
            "qualified_experiments": qualified,
        },
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    (output / "report.md").write_text(
        _build_markdown(summary),
        encoding="utf-8",
    )
    _write_candidates(output / "daily-candidates.csv", results)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


def _load_trades(run_id: str, parameter_set_id: str) -> list[dict]:
    rows = db.get_conn().execute(
        """SELECT detail_json FROM strategy6_backtest_trades
           WHERE run_id=? AND parameter_set_id=? ORDER BY signal_date, code""",
        (run_id, parameter_set_id),
    ).fetchall()
    return [json.loads(row[0] or "{}") for row in rows]


def _summary_item(item: dict) -> dict:
    return {
        "experiment_id": item["experiment_id"],
        "enabled_rules": item["enabled_rules"],
        "full": _scope_summary(item["full"]),
        "train": _scope_summary(item["train"]),
        "validation": _scope_summary(item["validation"]),
    }


def _scope_summary(scope: dict) -> dict:
    return {
        "signals": len(scope["signals"]),
        "removed_count": scope["removed_count"],
        "downgraded_count": scope["downgraded_count"],
        "candidate_counts": scope["candidate_counts"],
        "reason_counts": scope["reason_counts"],
        "trade_metrics": scope["trade_metrics"],
        "actionable_trade_metrics": scope["actionable_trade_metrics"],
    }


def _build_markdown(summary: dict) -> str:
    lines = [
        "# 策略6入场时机与概率修正RR冻结重放报告",
        "",
        f"- 来源任务：`{summary['source_run_id']}`",
        f"- 参数集：`{summary['parameter_set_id']}`",
        f"- 来源信号：{summary['source_signal_count']}，重建成功：{summary['rebuilt_signal_count']}，失败：{len(summary['rebuild_failed'])}",
        f"- 来源交易：{summary['source_trade_count']}",
        f"- 指数状态：`{summary['index_status']}`；2026+ OOS：`{summary['oos_status']}`",
        "- 该实验只重放冻结信号的末端过滤，不能发现基线未生成的新信号，也不自动修改生产配置。",
        "",
        "| 实验 | 规则 | 全期信号 | 删除 | 降级 | 训练可执行交易 | 训练期望R | 训练PF | 验证可执行交易 | 验证期望R | 验证PF | 验证盈亏比 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary["experiments"]:
        full = item["full"]
        train = item["train"]["actionable_trade_metrics"]
        validation = item["validation"]["actionable_trade_metrics"]
        ratio = _win_loss_ratio(validation)
        lines.append(
            f"| `{item['experiment_id']}` | {', '.join(item['enabled_rules']) or '基线'} | "
            f"{full['signals']} | {full['removed_count']} | {full['downgraded_count']} | "
            f"{int(train.get('trades') or 0)} | {_metric(train, 'expectancy_r')} | {_metric(train, 'profit_factor')} | "
            f"{int(validation.get('trades') or 0)} | {_metric(validation, 'expectancy_r')} | {_metric(validation, 'profit_factor')} | {ratio:.3f} |"
        )
    lines.extend([
        "",
        "## 最终建议",
        "",
        f"- 决策：`{summary['recommendation']['decision']}`",
        f"- 原因：`{summary['recommendation']['reason']}`",
        f"- 初筛入围：{', '.join(summary['recommendation']['qualified_experiments']) or '无'}",
        "- 当前生产开关继续保持关闭，不修改正式候选规则。",
        "",
        "## 结论口径",
        "",
        "只有训练和验证同时为正期望、PF>=1.20、验证闭合交易>=30、平均盈利R/平均亏损R>=2.5的方案，才有资格进入完整逐日回测与压力测试。冻结重放本身不能升级正式参数。",
        "",
        "## 重建失败",
        "",
    ])
    if summary["rebuild_failed"]:
        lines.extend(
            f"- `{item['code']}` @ `{item['evaluation_date']}`：{item['reason']}"
            for item in summary["rebuild_failed"]
        )
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def _metric(metrics: dict, key: str) -> str:
    try:
        return f"{float(metrics.get(key) or 0.0):.3f}"
    except (TypeError, ValueError):
        return "0.000"


def _win_loss_ratio(metrics: dict) -> float:
    loss = float(metrics.get("avg_loss_r") or 0.0)
    return float(metrics.get("avg_win_r") or 0.0) / loss if loss > 0 else 0.0


def _passes_initial_gate(item: dict) -> bool:
    for scope_name in ("train", "validation"):
        metrics = item[scope_name]["actionable_trade_metrics"]
        if float(metrics.get("expectancy_r") or 0.0) <= 0:
            return False
        if float(metrics.get("profit_factor") or 0.0) < 1.20:
            return False
        if _win_loss_ratio(metrics) < 2.5:
            return False
    return int(item["validation"]["actionable_trade_metrics"].get("trades") or 0) >= 30


def _write_candidates(path: Path, results: list[dict]) -> None:
    fields = (
        "experiment_id", "evaluation_date", "code", "name", "setup_id",
        "candidate_type", "entry_timing_state", "entry_timing_executable",
        "entry_timing_evidence_count", "probability_rr_status",
        "probability_rr_sample_count", "probability_rr_target_1_hit_probability",
        "probability_rr_target_2_hit_probability", "probability_adjusted_r",
    )
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            for signal in result["full"]["signals"]:
                snapshot = signal.get("snapshot") or {}
                writer.writerow({
                    "experiment_id": result["experiment_id"],
                    "evaluation_date": signal.get("evaluation_date"),
                    "code": signal.get("code"),
                    "name": signal.get("name"),
                    "setup_id": signal.get("setup_id"),
                    "candidate_type": signal.get("candidate_type"),
                    **{field: snapshot.get(field) for field in fields[6:]},
                })


if __name__ == "__main__":
    raise SystemExit(main())
