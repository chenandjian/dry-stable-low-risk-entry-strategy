"""Deterministic audit helpers for Strategy6 selection-score research."""
from __future__ import annotations

from collections import Counter
import copy
import json
from math import sqrt
from statistics import fmean

from strategy6.backtest.metrics import calculate_trade_metrics
from strategy6.filters import (
    selection_blocks_ready,
    selection_hard_filter_reasons,
)
from strategy6.models import Strategy6SelectionDiagnostics


SCORE_COMPONENTS = (
    "strong_start_score",
    "pattern_score_component",
    "support_score",
    "tail_score",
    "objective_rr_score",
    "relative_strength_risk_score",
)

SCORE_BANDS = (
    ("<60", float("-inf"), 60),
    ("60-69", 60, 70),
    ("70-79", 70, 80),
    ("80-89", 80, 90),
    ("90-100", 90, 101),
    (">100", 101, float("inf")),
)

SELECTION_RULE_KEYS = (
    "support_confirmation_enabled",
    "conservative_rr_enabled",
    "rs_fading_downgrade_enabled",
    "tail_deterioration_filter_enabled",
    "matched_market_downgrade_enabled",
)

ACTIONABLE_CANDIDATE_TYPES = {"READY_CANDIDATE", "KEY_CANDIDATE"}

SELECTION_DIAGNOSTIC_FIELDS = (
    "selection_diagnostics_version",
    "relative_strength_5",
    "relative_strength_10",
    "relative_strength_20",
    "relative_strength_60",
    "relative_strength_periods_observed",
    "relative_strength_trend",
    "matched_market_symbol",
    "matched_market_status",
    "support_confirmation_status",
    "recent_tail_status",
    "conservative_rr",
    "selection_diagnostic_reasons",
    "selection_diagnostic_risk_tags",
)


def build_selection_trial_configs(base_config: dict) -> list[dict]:
    """Build auditable OAT trials followed by one explicit combined trial."""
    baseline = copy.deepcopy(base_config)
    baseline["selection_optimization"] = {key: False for key in SELECTION_RULE_KEYS}
    trials = [{"experiment_id": "S6_SELECT_E0_BASELINE", "config": baseline}]
    experiment_by_key = {
        "support_confirmation_enabled": "S6_SELECT_E1_SUPPORT",
        "conservative_rr_enabled": "S6_SELECT_E2_CONSERVATIVE_RR",
        "rs_fading_downgrade_enabled": "S6_SELECT_E3_RS_FADING",
        "tail_deterioration_filter_enabled": "S6_SELECT_E4_TAIL_DETERIORATION",
        "matched_market_downgrade_enabled": "S6_SELECT_E5_MATCHED_MARKET",
    }
    for key in SELECTION_RULE_KEYS:
        config = copy.deepcopy(baseline)
        config["selection_optimization"][key] = True
        trials.append({"experiment_id": experiment_by_key[key], "config": config})
    combined = copy.deepcopy(baseline)
    combined["selection_optimization"] = {key: True for key in SELECTION_RULE_KEYS}
    trials.append({"experiment_id": "S6_SELECT_E6_COMBINED", "config": combined})
    return trials


def rebuild_frozen_selection_diagnostics(
    signals: list[dict],
    *,
    stock_rows_by_code: dict[str, list[dict]],
    market_data_by_symbol: dict[str, list[dict]],
    engine,
    minimum_history: int = 500,
) -> dict:
    """Rebuild only diagnostics at each frozen signal date without future rows."""
    rebuilt_signals: list[dict] = []
    failed: list[dict] = []
    for signal in signals:
        code = str(signal.get("code") or "")
        evaluation_date = str(signal.get("evaluation_date") or "")
        visible_rows = _visible_rows(stock_rows_by_code.get(code) or [], evaluation_date)
        if (
            len(visible_rows) < minimum_history
            or not visible_rows
            or str(visible_rows[-1].get("date") or "") != evaluation_date
        ):
            failed.append({
                "code": code,
                "evaluation_date": evaluation_date,
                "reason": "INSUFFICIENT_OR_MISSING_SIGNAL_DATE_HISTORY",
            })
            continue
        visible_market = {
            symbol: _visible_rows(rows, evaluation_date)
            for symbol, rows in market_data_by_symbol.items()
        }
        try:
            evaluation = engine.evaluate_at(
                visible_rows,
                code=code,
                name=str(signal.get("name") or ""),
                trading_days_override=len(visible_rows),
                market_data_by_symbol=visible_market,
            )
            rebuilt = evaluation.to_candidate_dict()
        except Exception as exc:  # research audit must retain exact failure context
            failed.append({
                "code": code,
                "evaluation_date": evaluation_date,
                "reason": f"EVALUATION_FAILED: {exc}",
            })
            continue
        snapshot = dict(signal.get("snapshot") or {})
        snapshot.update({
            field: rebuilt.get(field)
            for field in SELECTION_DIAGNOSTIC_FIELDS
            if field in rebuilt
        })
        rebuilt_signals.append({**signal, "snapshot": snapshot})
    return {"signals": rebuilt_signals, "failed": failed}


def _visible_rows(rows: list[dict], evaluation_date: str) -> list[dict]:
    return [
        row for row in rows
        if str(row.get("date") or "") <= evaluation_date
    ]


def replay_selection_trial(signals: list[dict], trades: list[dict], config: dict) -> dict:
    """Replay final selection gates over frozen signals without recomputing indicators."""
    selected: list[dict] = []
    selected_signal_keys: set[tuple[str, str]] = set()
    actionable_signal_keys: set[tuple[str, str]] = set()
    removed_count = 0
    downgraded_count = 0
    reason_counts: Counter[str] = Counter()
    candidate_counts: Counter[str] = Counter()
    for signal in signals:
        snapshot = dict(signal.get("snapshot") or {})
        original_type = str(signal.get("candidate_type") or snapshot.get("candidate_type") or "REJECTED")
        diagnostics = _diagnostics_from_snapshot(snapshot)
        reasons = selection_hard_filter_reasons(diagnostics, config)
        effective_rr = (
            diagnostics.conservative_rr
            if config["selection_optimization"]["conservative_rr_enabled"]
            else float(snapshot.get("objective_rr_2") or 0.0)
        )
        if (
            config["selection_optimization"]["conservative_rr_enabled"]
            and effective_rr < float(config["rr2_min_watch"])
        ):
            reasons.append("CONSERVATIVE_RR_LT_WATCH")
        if reasons:
            removed_count += 1
            reason_counts.update(reasons)
            continue

        candidate_type = _rr_adjusted_candidate_type(original_type, effective_rr, config)
        if (
            selection_blocks_ready(diagnostics, config)
            and candidate_type in {"READY_CANDIDATE", "KEY_CANDIDATE"}
        ):
            candidate_type = "WATCH_CANDIDATE"
            reasons.append("SELECTION_DIAGNOSTIC_DOWNGRADED")
        if candidate_type != original_type:
            downgraded_count += 1
        setup_id = str(signal.get("setup_id") or snapshot.get("setup_id") or "")
        signal_date = str(
            signal.get("evaluation_date")
            or snapshot.get("evaluation_date")
            or ""
        )
        signal_key = (setup_id, signal_date)
        selected_signal_keys.add(signal_key)
        if candidate_type in ACTIONABLE_CANDIDATE_TYPES:
            actionable_signal_keys.add(signal_key)
        candidate_counts[candidate_type] += 1
        selected.append({
            **signal,
            "candidate_type": candidate_type,
            "snapshot": {
                **snapshot,
                "candidate_type": candidate_type,
                "selection_experiment_reasons": reasons,
            },
        })

    selected_trades = [
        trade for trade in trades
        if (
            str(trade.get("setup_id") or ""),
            str(trade.get("signal_date") or ""),
        ) in selected_signal_keys
    ]
    actionable_trades = [
        trade for trade in selected_trades
        if (
            str(trade.get("setup_id") or ""),
            str(trade.get("signal_date") or ""),
        ) in actionable_signal_keys
    ]
    closed_trades = [trade for trade in selected_trades if trade.get("exit_date")]
    actionable_closed_trades = [
        trade for trade in actionable_trades if trade.get("exit_date")
    ]
    return {
        "signals": selected,
        "trades": selected_trades,
        "actionable_trades": actionable_trades,
        "closed_trades": closed_trades,
        "actionable_closed_trades": actionable_closed_trades,
        "removed_count": removed_count,
        "downgraded_count": downgraded_count,
        "candidate_counts": dict(sorted(candidate_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "trade_metrics": calculate_trade_metrics(closed_trades),
        "actionable_trade_metrics": calculate_trade_metrics(actionable_closed_trades),
    }


def evaluate_frozen_selection_trials(
    signals: list[dict],
    trades: list[dict],
    trials: list[dict],
    *,
    train_end: str = "2024-12-31",
) -> list[dict]:
    """Compare OAT selection rules on one immutable signal/trade baseline."""
    result: list[dict] = []
    for trial in trials:
        config = trial["config"]
        full = replay_selection_trial(signals, trades, config)
        train_signals = [
            signal for signal in signals
            if str(signal.get("evaluation_date") or "") <= train_end
        ]
        validation_signals = [
            signal for signal in signals
            if str(signal.get("evaluation_date") or "") > train_end
        ]
        train_trades = [
            trade for trade in trades
            if str(trade.get("signal_date") or "") <= train_end
        ]
        validation_trades = [
            trade for trade in trades
            if str(trade.get("signal_date") or "") > train_end
        ]
        result.append({
            "experiment_id": trial["experiment_id"],
            "enabled_rules": [
                key for key, enabled in config["selection_optimization"].items()
                if enabled
            ],
            "full": full,
            "train": replay_selection_trial(train_signals, train_trades, config),
            "validation": replay_selection_trial(
                validation_signals,
                validation_trades,
                config,
            ),
        })
    return result


def build_selection_comparison_markdown(
    results: list[dict],
    *,
    source_run_id: str,
    parameter_set_id: str,
) -> str:
    lines = [
        "# 策略6直接选股单变量冻结重放报告",
        "",
        f"- 冻结信号任务：`{source_run_id}`",
        f"- 参数集：`{parameter_set_id}`",
        "- 说明：只重放末端选股规则，不重算指标、形态、支撑或交易计划。",
        "",
        "| 实验 | 启用规则 | 信号 | 删除 | 降级 | 训练可执行交易 | 训练期望R | 训练PF | 验证可执行交易 | 验证期望R | 验证PF |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in results:
        full = item["full"]
        train = item["train"]["actionable_trade_metrics"]
        validation = item["validation"]["actionable_trade_metrics"]
        lines.append(
            f"| `{item['experiment_id']}` | "
            f"{', '.join(item['enabled_rules']) or '基线'} | "
            f"{len(full['signals'])} | {full['removed_count']} | {full['downgraded_count']} | "
            f"{int(train.get('trades') or 0)} | {_metric(train, 'expectancy_r')} | {_metric(train, 'profit_factor')} | "
            f"{int(validation.get('trades') or 0)} | {_metric(validation, 'expectancy_r')} | {_metric(validation, 'profit_factor')} |"
        )
    lines.extend([
        "",
        "冻结重放只能淘汰或降级已有正式信号，不能发现基线未生成的新信号。入围规则仍必须执行完整逐日引擎回测和压力测试。",
        "",
    ])
    return "\n".join(lines)


def _metric(metrics: dict, key: str) -> str:
    value = metrics.get(key)
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "0.000"


def _diagnostics_from_snapshot(snapshot: dict) -> Strategy6SelectionDiagnostics:
    return Strategy6SelectionDiagnostics(
        relative_strength_trend=str(snapshot.get("relative_strength_trend") or "UNKNOWN"),
        matched_market_status=str(snapshot.get("matched_market_status") or "UNKNOWN"),
        support_confirmation_status=str(snapshot.get("support_confirmation_status") or "PENDING"),
        recent_tail_status=str(snapshot.get("recent_tail_status") or "UNKNOWN"),
        conservative_rr=float(snapshot.get("conservative_rr") or 0.0),
    )


def _rr_adjusted_candidate_type(candidate_type: str, effective_rr: float, config: dict) -> str:
    if not config["selection_optimization"]["conservative_rr_enabled"]:
        return candidate_type
    if candidate_type == "READY_CANDIDATE" and effective_rr < float(config["rr2_min_ready"]):
        return (
            "KEY_CANDIDATE"
            if effective_rr >= float(config["rr2_min_key"])
            else "WATCH_CANDIDATE"
        )
    if candidate_type == "KEY_CANDIDATE" and effective_rr < float(config["rr2_min_key"]):
        return "WATCH_CANDIDATE"
    return candidate_type


def audit_score_components(rows: list[dict], *, minimum_reliable_sample: int = 60) -> dict:
    """Describe score saturation and monotonicity without selecting parameters."""
    observed = [row for row in rows if _number(row.get("r_multiple")) is not None]
    components = {
        name: _component_audit(observed, name)
        for name in SCORE_COMPONENTS
        if any(_number(row.get(name)) is not None for row in observed)
    }
    pairwise: dict[str, float] = {}
    component_names = list(components)
    for index, left in enumerate(component_names):
        for right in component_names[index + 1:]:
            pairs = [
                (_number(row.get(left)), _number(row.get(right)))
                for row in observed
            ]
            valid = [(x, y) for x, y in pairs if x is not None and y is not None]
            pairwise[f"{left}|{right}"] = _spearman(valid)

    score_bands = _score_band_audit(observed)
    band_means = [band["mean_r"] for band in score_bands]
    monotonic = (
        len(band_means) >= 2
        and all(current >= previous for previous, current in zip(band_means, band_means[1:]))
    )
    return {
        "sample_size": len(observed),
        "minimum_reliable_sample": int(minimum_reliable_sample),
        "reliable": len(observed) >= int(minimum_reliable_sample),
        "components": components,
        "pairwise_spearman": pairwise,
        "score_bands": score_bands,
        "total_score_monotonic": monotonic,
    }


def assess_score_calibration(
    audit: dict,
    *,
    duplicate_correlation_min: float = 0.70,
    saturation_min: float = 0.90,
) -> dict:
    """Gate score changes; never infer production weights from correlations."""
    duplicate_pairs = [
        name for name, value in audit.get("pairwise_spearman", {}).items()
        if float(value) >= duplicate_correlation_min
    ]
    saturated_components = [
        name for name, item in audit.get("components", {}).items()
        if float(item.get("saturation_ratio") or 0.0) >= saturation_min
    ]
    if not audit.get("reliable"):
        decision = "BLOCKED_INSUFFICIENT_SAMPLE"
    elif duplicate_pairs:
        decision = "DUPLICATE_EVIDENCE_REQUIRES_EXPERIMENT"
    elif saturated_components or not audit.get("total_score_monotonic"):
        decision = "REDESIGN_REQUIRED_NO_DUPLICATE_EVIDENCE"
    else:
        decision = "KEEP_CURRENT_SCORE"
    return {
        "decision": decision,
        "duplicate_pairs": duplicate_pairs,
        "saturated_components": saturated_components,
        "automatic_weight_change_allowed": False,
    }


def load_score_audit_rows(conn, run_id: str, parameter_set_id: str) -> list[dict]:
    """Load closed trades with the signal snapshot used to create each order."""
    rows = conn.execute(
        """SELECT s.snapshot_json, t.r_multiple
           FROM strategy6_backtest_trades t
           JOIN strategy6_backtest_signals s
             ON s.run_id=t.run_id
            AND s.parameter_set_id=t.parameter_set_id
            AND s.code=t.code
            AND s.evaluation_date=t.signal_date
           WHERE t.run_id=? AND t.parameter_set_id=?
             AND COALESCE(t.exit_date, '')<>''
           ORDER BY t.signal_date, t.code""",
        (run_id, parameter_set_id),
    ).fetchall()
    result: list[dict] = []
    for snapshot_json, r_multiple in rows:
        try:
            snapshot = json.loads(snapshot_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            snapshot = {}
        if not isinstance(snapshot, dict):
            snapshot = {}
        result.append({**snapshot, "r_multiple": r_multiple})
    return result


def build_score_audit_markdown(
    audit: dict,
    *,
    run_id: str,
    parameter_set_id: str,
) -> str:
    reliability = "样本达到最低门槛" if audit.get("reliable") else "样本不足，仅用于诊断"
    lines = [
        "# 策略6评分重复与单调性审计",
        "",
        f"- 回测任务：`{run_id}`",
        f"- 参数集：`{parameter_set_id}`",
        f"- 闭合交易样本：{audit.get('sample_size', 0)}",
        f"- 可靠性：{reliability}",
        f"- 总分收益单调：{'是' if audit.get('total_score_monotonic') else '否'}",
        "",
        "## 分项饱和度",
        "",
        "| 分项 | 样本 | 唯一值 | 众数 | 众数占比 | 与R的Spearman |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, item in audit.get("components", {}).items():
        lines.append(
            f"| `{name}` | {item['sample_size']} | {item['unique_values']} | "
            f"{item['mode_value']:.3f} | {item['saturation_ratio']:.2%} | "
            f"{item['spearman_to_r']:.3f} |"
        )
    lines.extend([
        "",
        "## 总分分组",
        "",
        "| 分数段 | 样本 | 平均R | PF |",
        "|---|---:|---:|---:|",
    ])
    for band in audit.get("score_bands", []):
        profit_factor = band["profit_factor"]
        pf_text = "∞" if profit_factor == float("inf") else f"{profit_factor:.3f}"
        lines.append(
            f"| {band['band']} | {band['count']} | {band['mean_r']:.3f} | {pf_text} |"
        )
    lines.extend([
        "",
        "## 使用边界",
        "",
        "本报告只描述评分饱和、相关性和收益单调性，不自动生成权重，也不得直接修改正式配置。",
        "",
    ])
    return "\n".join(lines)


def _component_audit(rows: list[dict], name: str) -> dict:
    pairs = [
        (_number(row.get(name)), _number(row.get("r_multiple")))
        for row in rows
    ]
    valid = [(value, outcome) for value, outcome in pairs if value is not None and outcome is not None]
    values = [value for value, _ in valid]
    counts = Counter(values)
    mode_value, mode_count = counts.most_common(1)[0]
    return {
        "sample_size": len(valid),
        "unique_values": len(counts),
        "mode_value": mode_value,
        "mode_count": mode_count,
        "saturation_ratio": round(mode_count / len(valid), 6),
        "spearman_to_r": _spearman(valid),
    }


def _score_band_audit(rows: list[dict]) -> list[dict]:
    result: list[dict] = []
    for label, lower, upper in SCORE_BANDS:
        outcomes = [
            outcome
            for row in rows
            if (score := _number(row.get("total_score"))) is not None
            and lower <= score < upper
            and (outcome := _number(row.get("r_multiple"))) is not None
        ]
        if outcomes:
            result.append({
                "band": label,
                "count": len(outcomes),
                "mean_r": round(fmean(outcomes), 6),
                "profit_factor": _profit_factor(outcomes),
            })
    return result


def _profit_factor(outcomes: list[float]) -> float:
    gains = sum(value for value in outcomes if value > 0)
    losses = abs(sum(value for value in outcomes if value < 0))
    if losses <= 0:
        return 0.0 if gains <= 0 else float("inf")
    return round(gains / losses, 6)


def _spearman(pairs: list[tuple[float, float]]) -> float:
    if len(pairs) < 2:
        return 0.0
    left = _average_ranks([pair[0] for pair in pairs])
    right = _average_ranks([pair[1] for pair in pairs])
    left_mean = fmean(left)
    right_mean = fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_sum = sum((x - left_mean) ** 2 for x in left)
    right_sum = sum((y - right_mean) ** 2 for y in right)
    denominator = sqrt(left_sum * right_sum)
    return round(numerator / denominator, 6) if denominator > 0 else 0.0


def _average_ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = (index + 1 + end) / 2
        for original_index, _ in ordered[index:end]:
            ranks[original_index] = rank
        index = end
    return ranks


def _number(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
