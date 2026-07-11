"""Auditable JSON, CSV and Markdown output for Strategy6 research."""
from __future__ import annotations

import csv
import json
from pathlib import Path


def write_backtest_report(result: dict, output_dir) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    run_id = str((result.get("run") or {}).get("run_id") or "strategy6-backtest")
    paths = {
        "markdown": output / f"{run_id}-report.md",
        "summary_json": output / f"{run_id}-summary.json",
        "signals_csv": output / f"{run_id}-daily-candidates.csv",
        "orders_csv": output / f"{run_id}-orders.csv",
        "trades_csv": output / f"{run_id}-trades.csv",
        "trials_csv": output / f"{run_id}-parameter-trials.csv",
    }
    summary_payload = {
        key: value for key, value in result.items()
        if key not in {"signals", "orders", "trades", "parameter_trials"}
    }
    paths["summary_json"].write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    _write_csv(paths["signals_csv"], result.get("signals") or [])
    _write_csv(paths["orders_csv"], result.get("orders") or [])
    _write_csv(paths["trades_csv"], result.get("trades") or [])
    _write_csv(paths["trials_csv"], result.get("parameter_trials") or [])
    run = result.get("run") or {}
    audit = result.get("data_audit") or {}
    oos = result.get("oos_lock") or {}
    summary = result.get("summary") or {}
    experiments = result.get("experiments") or {}
    lines = [
        "# 策略6双路径历史回测与参数调优报告",
        "",
        "## 可信度",
        "",
        f"- 运行ID：`{run_id}`",
        f"- 可信度：`{run.get('confidence_label', 'RESEARCH_ONLY_CURRENT_UNIVERSE')}`",
        f"- OOS状态：`{oos.get('status', 'OOS_LOCKED')}`",
        f"- OOS起始：`{oos.get('start_date', '')}`",
        f"- 幸存者偏差：{'存在' if audit.get('survivorship_bias', True) else '未发现'}",
        "- 历史ST、退市和停牌状态不完整，结果仅用于研究，不构成生产参数升级依据。",
        "",
        "## 汇总指标",
        "",
        _markdown_table(summary),
        "",
        "## 实验对比",
        "",
        _experiment_table(experiments),
        "",
        "## 明细文件",
        "",
        f"- 每日候选：`{paths['signals_csv'].name}`",
        f"- 订单：`{paths['orders_csv'].name}`",
        f"- 交易：`{paths['trades_csv'].name}`",
        f"- 参数试验：`{paths['trials_csv'].name}`",
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        if not fields:
            return
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _cell(row.get(key)) for key in fields})


def _cell(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _markdown_table(values: dict) -> str:
    if not values:
        return "无可用指标。"
    lines = ["| 指标 | 数值 |", "| --- | ---: |"]
    lines.extend(f"| {key} | {value} |" for key, value in sorted(values.items()))
    return "\n".join(lines)


def _experiment_table(experiments: dict) -> str:
    if not experiments:
        return "无实验结果。"
    lines = ["| 实验 | 结果 |", "| --- | --- |"]
    for name, values in sorted(experiments.items()):
        lines.append(f"| {name} | `{json.dumps(values, ensure_ascii=False, sort_keys=True)}` |")
    return "\n".join(lines)
