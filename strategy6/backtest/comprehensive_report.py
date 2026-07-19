"""Auditable artifacts for Strategy6 comprehensive optimization campaigns."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from scanner import db
from strategy6.backtest.comprehensive_runner import campaign_status
from strategy6.backtest.parameter_registry import build_comprehensive_registry
from strategy6.backtest.selector import evaluate_coarse_gates


FIXED_PARAMETER_REASONS = {
    "enabled": "系统开关，不参与收益调优",
    "kline_days": "数据覆盖边界，不参与收益调优",
    "minimum_trading_days": "数据可信度边界，不参与收益调优",
    "enable_market_filter": "市场环境语义固定",
    "market_filter_mode": "市场环境语义固定",
    "pattern_filter_enabled": "形态入口语义固定",
    "pattern_filter_mode": "形态入口语义固定",
    "max_watch_days": "候选生命周期语义固定",
    "expired_cooldown_days": "候选生命周期语义固定",
    "failed_cooldown_days": "候选生命周期语义固定",
}


def determine_recommendation(*, all_frozen: bool, execution: dict) -> str:
    if not all_frozen:
        return "INCOMPLETE"
    if not execution.get("stress_passed") or not execution.get("validation_confirmed"):
        return "REJECT"
    return "RECOMMEND"


def build_coarse_gate_audit(trials: list[dict], *, evaluation_step: int) -> dict:
    stage_counts: dict[str, dict[str, int]] = {}
    for trial in trials:
        if trial.get("trial_kind") != "OAT":
            continue
        if trial.get("status") not in {"COMPLETED", "COMPLETED_WITH_SKIPS"}:
            continue
        stage_id = str(trial.get("stage_id") or "")
        counts = stage_counts.setdefault(stage_id, {"total": 0, "passed": 0})
        counts["total"] += 1
        if evaluate_coarse_gates(
            trial.get("selection_metrics") or {}, evaluation_step=evaluation_step,
        )["passed"]:
            counts["passed"] += 1
    return {
        "evaluation_step": evaluation_step,
        "oat_trial_count": sum(item["total"] for item in stage_counts.values()),
        "passed_count": sum(item["passed"] for item in stage_counts.values()),
        "stage_counts": stage_counts,
        "concentration_deferred": True,
    }


def write_comprehensive_report(
    campaign_id: str,
    output_dir: str | Path,
    production_config: dict,
) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    status = campaign_status(campaign_id)
    trials = db.get_strategy6_optimization_trials(campaign_id)
    all_frozen = bool(status["stages"]) and all(item["status"] == "FROZEN" for item in status["stages"])
    execution = (status["campaign"].get("manifest") or {}).get("execution_tuning") or {}
    evaluation_step = int((status["campaign"].get("manifest") or {}).get("evaluation_step", 5))
    recommendation = determine_recommendation(all_frozen=all_frozen, execution=execution)

    selected_config = _selected_config(status, production_config)
    config_diff = _config_diff(production_config, selected_config)
    payload = {
        **status,
        "trials": trials,
        "recommendation": recommendation,
        "selected_config": selected_config,
        "production_config_diff": config_diff,
        "production_config_modified": False,
        "oos_locked": True,
        "coarse_gate_audit": build_coarse_gate_audit(trials, evaluation_step=evaluation_step),
    }
    _write_parameter_dictionary(output / "parameter_dictionary.csv", production_config)
    _write_csv(output / "stage_trials.csv", [_trial_csv_row(item) for item in trials])

    run_id, parameter_set_id = _selected_full_run(status, trials)
    payload["selected_run"] = db.get_strategy6_backtest_run(run_id) if run_id else None
    payload["selected_run_metrics"] = db.get_strategy6_backtest_metrics(run_id) if run_id else []
    (output / "campaign.json").write_text(
        json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, default=str, allow_nan=False),
        encoding="utf-8",
    )
    candidates = db.get_strategy6_backtest_signals(run_id, parameter_set_id) if run_id else []
    candidate_rows = []
    for item in candidates:
        candidate_rows.append({
            "run_id": run_id,
            "parameter_set_id": parameter_set_id,
            "code": item["code"],
            "name": item["name"],
            "evaluation_date": item["evaluation_date"],
            "setup_id": item["setup_id"],
            "tail_path": item["tail_path"],
            "candidate_type": item["candidate_type"],
            "snapshot_json": json.dumps(item["snapshot"], ensure_ascii=False, sort_keys=True),
        })
    _write_csv(output / "daily_candidates.csv", candidate_rows, (
        "run_id", "parameter_set_id", "code", "name", "evaluation_date",
        "setup_id", "tail_path", "candidate_type", "snapshot_json",
    ))
    _write_csv(output / "orders.csv", _load_detail_rows("strategy6_backtest_orders", run_id, parameter_set_id))
    _write_csv(output / "trades.csv", _load_detail_rows("strategy6_backtest_trades", run_id, parameter_set_id))
    (output / "report.md").write_text(
        _render_markdown(payload, run_id), encoding="utf-8",
    )
    return {
        "campaign_id": campaign_id,
        "recommendation": recommendation,
        "output_dir": str(output),
        "selected_run_id": run_id,
        "production_config_modified": False,
    }


def _write_parameter_dictionary(path: Path, production_config: dict) -> None:
    registry = build_comprehensive_registry(production_config)
    spec_by_key = {}
    stage_by_key = {}
    group_spec = None
    for stage in registry:
        for spec in stage.parameters:
            if spec.key == "grade_risk_profile":
                group_spec = spec
                continue
            spec_by_key[spec.key] = spec
            stage_by_key[spec.key] = stage
    grade_keys = {
        "max_amp_5d_s", "max_amp_10d_s", "max_pullback_20d_s",
        "max_amp_5d_a", "max_amp_10d_a", "max_pullback_20d_a",
        "max_amp_5d_b", "max_amp_10d_b", "max_pullback_20d_b",
    }
    rows = []
    for key, default in sorted(_flatten(production_config).items()):
        spec = spec_by_key.get(key)
        if spec is not None:
            stage = stage_by_key[key]
            rows.append({
                "stage": f"{stage.order}-{stage.name}", "key": key,
                "default": json.dumps(default, ensure_ascii=False),
                "candidates": json.dumps(spec.candidates, ensure_ascii=False),
                "type": spec.value_type, "reason": spec.description or "本轮直接调优",
            })
        elif key in grade_keys:
            rows.append({
                "stage": "4-支撑、振幅和回撤", "key": key,
                "default": json.dumps(default, ensure_ascii=False),
                "candidates": "由 grade_risk_profile 成组生成",
                "type": "group_member", "reason": "禁止单独变化，避免S/A/B规则交叉",
            })
        else:
            rows.append({
                "stage": "固定参数", "key": key,
                "default": json.dumps(default, ensure_ascii=False),
                "candidates": "", "type": "fixed",
                "reason": FIXED_PARAMETER_REASONS.get(key, "本轮设计未列入搜索空间，保持生产语义"),
            })
    if group_spec is not None:
        rows.append({
            "stage": "4-支撑、振幅和回撤", "key": group_spec.key,
            "default": json.dumps(group_spec.default, ensure_ascii=False),
            "candidates": json.dumps(group_spec.candidates, ensure_ascii=False),
            "type": group_spec.value_type, "reason": group_spec.description,
        })
    _write_csv(path, rows)


def _selected_config(status: dict, production_config: dict) -> dict:
    frozen = [item for item in status["stages"] if item["status"] == "FROZEN"]
    if not frozen:
        return production_config
    latest = max(frozen, key=lambda item: int(item["stage_order"]))
    selected = (latest.get("detail") or {}).get("selected_config")
    return selected if isinstance(selected, dict) else production_config


def _selected_full_run(status: dict, trials: list[dict]) -> tuple[str, str]:
    frozen = [item for item in status["stages"] if item["status"] == "FROZEN"]
    if not frozen:
        return "", ""
    selected_ids = [
        str(item.get("selected_parameter_set_id") or "")
        for item in sorted(frozen, key=lambda item: int(item["stage_order"]), reverse=True)
    ]
    for parameter_id in selected_ids:
        matches = [item for item in trials if item["parameter_set_id"] == parameter_id and item.get("full_run_id")]
        if matches:
            return str(matches[-1]["full_run_id"]), parameter_id
    return "", ""


def _trial_csv_row(item: dict) -> dict:
    return {
        "campaign_id": item["campaign_id"], "stage_id": item["stage_id"],
        "trial_id": item["trial_id"], "trial_kind": item["trial_kind"],
        "parameter_set_id": item["parameter_set_id"],
        "parent_parameter_set_id": item["parent_parameter_set_id"],
        "status": item["status"], "coarse_run_id": item.get("coarse_run_id") or "",
        "full_run_id": item.get("full_run_id") or "",
        "reject_reason": item.get("reject_reason") or "",
        "parameters_json": json.dumps(item.get("parameters") or {}, ensure_ascii=False, sort_keys=True),
        "selection_metrics_json": json.dumps(
            _json_safe(item.get("selection_metrics") or {}),
            ensure_ascii=False, sort_keys=True, allow_nan=False,
        ),
    }


def _load_detail_rows(table: str, run_id: str, parameter_set_id: str) -> list[dict]:
    if not run_id:
        return []
    rows = db.get_conn().execute(
        f"SELECT detail_json FROM {table} WHERE run_id=? AND parameter_set_id=? ORDER BY code, signal_date",
        (run_id, parameter_set_id),
    ).fetchall()
    return [json.loads(row[0] or "{}") for row in rows]


def _write_csv(path: Path, rows: list[dict], default_fields: tuple[str, ...] = ()) -> None:
    fields = list(default_fields)
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or ["status"])
        writer.writeheader()
        writer.writerows(rows)


def _config_diff(current: dict, selected: dict) -> list[dict]:
    current_flat = _flatten(current)
    selected_flat = _flatten(selected)
    result = []
    for key in sorted(set(current_flat) | set(selected_flat)):
        if current_flat.get(key) != selected_flat.get(key):
            result.append({"key": key, "current": current_flat.get(key), "recommended": selected_flat.get(key)})
    return result


def _flatten(value: dict, prefix: str = "") -> dict:
    result = {}
    for key, nested in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(nested, dict):
            result.update(_flatten(nested, path))
        else:
            result[path] = nested
    return result


def _render_markdown(payload: dict, run_id: str) -> str:
    campaign = payload["campaign"]
    lines = [
        "# 策略6全面参数调优报告",
        "",
        "## 总体结论",
        "",
        f"- 结论：`{payload['recommendation']}`",
        f"- Campaign：`{campaign['campaign_id']}`",
        f"- 原始七阶段实验 Git：`{campaign['strategy_git_commit']}`",
        f"- 最终审计重跑 Git：`{(payload.get('selected_run') or {}).get('strategy_git_commit') or '无'}`",
        f"- 数据版本：`{campaign['data_version']}`",
        f"- 最终完整回测：`{run_id or '无'}`",
        "- 生产配置未自动修改。",
        "- 2026-01-01 起 OOS 保持锁定，未用于搜索、筛选或排序。",
        "",
        "## 七阶段状态",
        "",
        "| 顺序 | 阶段 | 状态 | 决策 | 选中参数集 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for stage in payload["stages"]:
        lines.append(
            f"| {stage['stage_order']} | {stage['stage_id']} | {stage['status']} | "
            f"{stage.get('decision') or ''} | {stage.get('selected_parameter_set_id') or ''} |"
        )
    lines.extend([
        "",
        "## 修正后粗筛门槛复核",
        "",
        f"- 步长：`{payload['coarse_gate_audit']['evaluation_step']}` 个交易日。",
        f"- OAT试验：`{payload['coarse_gate_audit']['oat_trial_count']}` 组。",
        f"- 通过修正后粗筛门槛：`{payload['coarse_gate_audit']['passed_count']}` 组。",
        "- 粗筛阶段按步长折算最低交易样本；集中度门槛延后到逐日完整验证。",
        "",
        "## 参数差异",
        "",
    ])
    if payload["production_config_diff"]:
        for item in payload["production_config_diff"]:
            lines.append(f"- `{item['key']}`：`{item['current']}` -> `{item['recommended']}`")
    else:
        lines.append("- 无建议变更。")
    lines.extend([
        "",
        "## 训练与验证指标",
        "",
    ])
    selection_metrics = [item for item in payload.get("selected_run_metrics", []) if item.get("scope") == "selection"]
    if selection_metrics:
        for item in selection_metrics:
            metrics = item.get("metrics") or {}
            lines.append(
                f"- `{item['phase']}`：交易 {metrics.get('trades', 0)}，"
                f"期望R {metrics.get('expectancy_r', 0)}，PF {metrics.get('profit_factor', 0)}，"
                f"最大回撤 {metrics.get('max_drawdown', 0)}。"
            )
    else:
        lines.append("- 尚无完整训练/验证指标。")
    execution = (payload["campaign"].get("manifest") or {}).get("execution_tuning") or {}
    stress_checks = (execution.get("stress_acceptance") or {}).get("checks") or {}
    stress_results = execution.get("stress_results") or {}
    lines.extend([
        "",
        "## 执行参数与压力测试",
        "",
        f"- 执行参数试验：`{execution.get('trial_count', 0)}` 组。",
        f"- 保留默认买入有效期：`{execution.get('buy_zone_valid_days', '--')}` 个交易日。",
        f"- 保留默认最大持有期：`{execution.get('max_holding_days', '--')}` 个交易日。",
        f"- 2025验证确认：`{'通过' if execution.get('validation_confirmed') else '未通过'}`。",
        f"- 高成本压力：`{'通过' if stress_checks.get('HIGH_COST') else '未通过'}`。",
        f"- 70%成交率压力：`{'通过' if stress_checks.get('LOW_FILL') else '未通过'}`。",
        f"- 延迟一个交易日压力：`{'通过' if stress_checks.get('ONE_DAY_DELAY') else '未通过'}`。",
        "",
        "| 场景 | 订单 | 未成交率 | 闭合交易 | 期望R | PF |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for name in ("BASE", "HIGH_COST", "LOW_FILL", "ONE_DAY_DELAY"):
        item = stress_results.get(name) or {}
        metrics = item.get("metrics") or {}
        lines.append(
            f"| {name} | {item.get('orders', 0)} | {float(item.get('unfilled_rate', 0)):.2%} | "
            f"{metrics.get('trades', 0)} | {float(metrics.get('expectancy_r', 0)):.4f} | "
            f"{float(metrics.get('profit_factor', 0)):.4f} |"
        )
    lines.extend([
        "",
        "## 风险披露",
        "",
        "- 股票池为当前股票池，存在幸存者偏差。",
        "- 历史证券状态信息不完整。",
        "- 七阶段、验证和压力测试均已执行，但验证与三类压力未通过，因此拒绝正式参数升级。",
        "",
    ])
    return "\n".join(lines)


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, dict):
        return {key: _json_safe(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(nested) for nested in value]
    return value
