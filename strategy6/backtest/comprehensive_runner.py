"""Resumable orchestration primitives for comprehensive Strategy6 research."""
from __future__ import annotations

import copy
from collections.abc import Callable
import json
import subprocess

from scanner import db
from scanner.config_io import load_yaml_config
from strategy6.backtest.models import ParameterSet
from strategy6.backtest.data import build_database_fingerprint
from strategy6.backtest.campaign import (
    OptimizationTrial,
    build_stage_trial_manifest,
    trials_needing_execution,
)
from strategy6.backtest.optimization import calculate_robust_score
from strategy6.backtest.parameter_registry import build_comprehensive_registry
from strategy6.backtest.selector import (
    confirm_validation_metrics,
    evaluate_coarse_gates,
    evaluate_hard_gates,
    select_stage_trials,
)
from strategy6.backtest.models import BacktestSignal
from strategy6.validation import resolve_strategy6_config, strategy6_config_hash


def initialize_campaign(
    *,
    campaign_id: str,
    base_config: dict,
    strategy_git_commit: str,
    data_version: str,
    random_seed: int,
    max_joint_trials: int,
    evaluation_step: int = 5,
) -> dict:
    existing = db.get_strategy6_optimization_campaign(campaign_id)
    if existing is not None:
        manifest = existing.get("manifest") or {}
        if (
            manifest.get("base_config") != base_config
            or existing["strategy_git_commit"] != strategy_git_commit
            or existing["data_version"] != data_version
            or int(manifest.get("random_seed", -1)) != int(random_seed)
            or int(manifest.get("max_joint_trials", -1)) != int(max_joint_trials)
            or int(manifest.get("evaluation_step", -1)) != int(evaluation_step)
        ):
            raise ValueError("campaign identity conflicts with existing campaign")
        return campaign_status(campaign_id)

    base_parameter = ParameterSet.create({"strategy6": base_config})
    registry = build_comprehensive_registry(base_config)
    manifest = {
        "base_config": copy.deepcopy(base_config),
        "base_parameter_set_id": base_parameter.parameter_set_id,
        "random_seed": int(random_seed),
        "max_joint_trials": int(max_joint_trials),
        "evaluation_step": int(evaluation_step),
        "stage_ids": [stage.stage_id for stage in registry],
        "oos_start": "2026-01-01",
        "production_config_modified": False,
    }
    db.save_strategy6_optimization_campaign({
        "campaign_id": campaign_id,
        "status": "PENDING",
        "strategy_git_commit": strategy_git_commit,
        "data_version": data_version,
        "base_config_hash": strategy6_config_hash(base_config),
        "manifest": manifest,
    })
    for stage in registry:
        db.save_strategy6_optimization_stage({
            "campaign_id": campaign_id,
            "stage_id": stage.stage_id,
            "stage_order": stage.order,
            "status": "PENDING",
            "parent_parameter_set_id": base_parameter.parameter_set_id,
            "detail": {"name": stage.name},
        })
    return campaign_status(campaign_id)


def campaign_status(campaign_id: str) -> dict:
    campaign = db.get_strategy6_optimization_campaign(campaign_id)
    if campaign is None:
        raise KeyError(f"unknown strategy6 optimization campaign: {campaign_id}")
    stages = db.get_strategy6_optimization_stages(campaign_id)
    trials = db.get_strategy6_optimization_trials(campaign_id)
    counts: dict[str, int] = {}
    for trial in trials:
        status = str(trial["status"])
        counts[status] = counts.get(status, 0) + 1
    return {"campaign": campaign, "stages": stages, "trial_status_counts": counts}


def assert_campaign_data_version(campaign: dict, current_data_version: str) -> None:
    if str(campaign.get("data_version") or "") != str(current_data_version):
        raise RuntimeError(
            "strategy6 optimization data version changed; create a new campaign "
            "instead of mixing snapshots"
        )


def assert_campaign_run_identity(campaign: dict, args) -> None:
    manifest = campaign.get("manifest") or {}
    if (
        int(manifest.get("evaluation_step", -1)) != int(args.evaluation_step)
        or int(manifest.get("max_joint_trials", -1)) != int(args.max_joint_trials)
    ):
        raise ValueError("campaign identity conflicts with run arguments")


def assert_stage_can_start(stages: list[dict], stage_id: str) -> None:
    ordered = sorted(stages, key=lambda item: int(item["stage_order"]))
    target = next((item for item in ordered if item["stage_id"] == stage_id), None)
    if target is None:
        raise KeyError(f"unknown stage: {stage_id}")
    for stage in ordered:
        if int(stage["stage_order"]) >= int(target["stage_order"]):
            break
        if stage["status"] != "FROZEN":
            raise RuntimeError(f"previous stage {stage['stage_id']} must be FROZEN before {stage_id}")


def recover_interrupted_trials(trials: list[dict]) -> list[dict]:
    result = []
    for trial in trials:
        item = dict(trial)
        if item.get("status") == "RUNNING":
            item["status"] = "INTERRUPTED"
        result.append(item)
    return result


def execute_campaign_stage(
    campaign_id: str,
    stage_id: str,
    *,
    run_trial: Callable[[OptimizationTrial, str], dict],
) -> dict:
    status = campaign_status(campaign_id)
    assert_stage_can_start(status["stages"], stage_id)
    campaign = status["campaign"]
    stage_row = next(item for item in status["stages"] if item["stage_id"] == stage_id)
    if stage_row["status"] == "FROZEN":
        return {
            "decision": stage_row.get("decision") or "FROZEN",
            "selected_parameter_set_id": stage_row.get("selected_parameter_set_id"),
            "parent_parameter_set_id": stage_row["parent_parameter_set_id"],
            "reused": True,
        }

    parent_config, parent_parameter_set_id = _resolve_parent_config(campaign, status["stages"], stage_row)
    registry = build_comprehensive_registry(parent_config)
    stage_spec = next(stage for stage in registry if stage.stage_id == stage_id)
    manifest_cfg = campaign["manifest"]
    oat_manifest = build_stage_trial_manifest(
        stage_spec,
        parent_config,
        max_joint_trials=0,
        random_seed=int(manifest_cfg.get("random_seed", 20260712)) + int(stage_spec.order),
    )
    stage_detail = dict(stage_row.get("detail") or {})
    db.save_strategy6_optimization_stage({
        **stage_row,
        "parent_parameter_set_id": parent_parameter_set_id,
        "status": "RUNNING",
        "detail": {**stage_detail, "oat_trial_count": len(oat_manifest)},
    })
    _run_coarse_manifest(
        campaign_id, parent_parameter_set_id, oat_manifest, run_trial,
    )
    oat_rows = db.get_selectable_strategy6_optimization_trials(campaign_id, stage_id)
    overrides = stage_detail.get("joint_candidate_overrides")
    if not isinstance(overrides, dict):
        overrides = _approved_joint_candidates(
            stage_spec, oat_manifest, oat_rows,
            evaluation_step=int(manifest_cfg.get("evaluation_step", 5)),
        )
        stage_detail["joint_candidate_overrides"] = overrides
        db.save_strategy6_optimization_stage({
            **stage_row,
            "parent_parameter_set_id": parent_parameter_set_id,
            "status": "RUNNING",
            "detail": stage_detail,
        })
    manifest = build_stage_trial_manifest(
        stage_spec,
        parent_config,
        max_joint_trials=int(manifest_cfg.get("max_joint_trials", 24)),
        random_seed=int(manifest_cfg.get("random_seed", 20260712)) + int(stage_spec.order),
        joint_candidate_overrides={key: tuple(values) for key, values in overrides.items()},
    )
    _run_coarse_manifest(
        campaign_id, parent_parameter_set_id,
        tuple(item for item in manifest if item.trial_kind == "JOINT"),
        run_trial,
    )
    completed_rows = db.get_selectable_strategy6_optimization_trials(campaign_id, stage_id)
    by_id = {trial.trial_id: trial for trial in manifest}
    stage_detail["trial_count"] = len(manifest)
    selection = stage_detail.get("selector")
    if not isinstance(selection, dict):
        selector_input = _build_selector_input(
            completed_rows,
            evaluation_step=int(manifest_cfg.get("evaluation_step", 5)),
        )
        selection = select_stage_trials(
            selector_input,
            coarse_evaluation_step=int(manifest_cfg.get("evaluation_step", 5)),
        )
        stage_detail["selector"] = selection
        stage_detail["full_confirmations"] = {}
        db.save_strategy6_optimization_stage({
            **stage_row,
            "parent_parameter_set_id": parent_parameter_set_id,
            "status": "RUNNING",
            "detail": stage_detail,
        })
    full_confirmations = dict(stage_detail.get("full_confirmations") or {})
    confirmed = []
    selection_finalists = list(selection["finalist_parameter_set_ids"])
    full_parameter_ids = selection_finalists
    if not full_parameter_ids and int(stage_spec.order) == 1:
        full_parameter_ids = [parent_parameter_set_id]
    for parameter_id in full_parameter_ids:
        selection_eligible = parameter_id in selection_finalists
        trial_row = next(item for item in completed_rows if item["parameter_set_id"] == parameter_id)
        trial = by_id[trial_row["trial_id"]]
        prior_confirmation = full_confirmations.get(trial.trial_id)
        if isinstance(prior_confirmation, dict):
            if prior_confirmation.get("passed") and selection_eligible:
                confirmed.append((trial, prior_confirmation.get("training_metrics") or {}, prior_confirmation))
            continue
        try:
            result = run_trial(trial, "FULL_CONFIRMATION")
            run_status = str((result.get("run") or {}).get("status") or "FAILED")
            phases = result.get("phase_results") or {}
            train_metrics = (phases.get("TRAIN") or {}).get("selection_metrics") or {}
            validation_metrics = (phases.get("VALIDATION") or {}).get("selection_metrics") or {}
            confirmation = confirm_validation_metrics(train_metrics, validation_metrics)
            accepted = (
                selection_eligible
                and run_status in {"COMPLETED", "COMPLETED_WITH_SKIPS"}
                and confirmation["passed"]
            )
            confirmation_record = {
                **confirmation,
                "passed": accepted,
                "training_metrics": train_metrics,
                "validation_metrics": validation_metrics,
                "full_run_id": str((result.get("run") or {}).get("run_id") or ""),
                "run_status": run_status,
            }
            if accepted:
                confirmed.append((trial, train_metrics, confirmation_record))
            db.save_strategy6_optimization_trial(_trial_db_item(
                campaign_id, parent_parameter_set_id, trial,
                status=run_status if run_status in {"COMPLETED", "COMPLETED_WITH_SKIPS"} else "FAILED",
                coarse_run_id=trial_row.get("coarse_run_id"),
                full_run_id=str((result.get("run") or {}).get("run_id") or ""),
                selection_metrics=train_metrics,
                reject_reason=None if confirmation["passed"] else "VALIDATION_REJECTED",
            ))
            full_confirmations[trial.trial_id] = confirmation_record
            stage_detail["full_confirmations"] = full_confirmations
            db.save_strategy6_optimization_stage({
                **stage_row,
                "parent_parameter_set_id": parent_parameter_set_id,
                "status": "RUNNING",
                "detail": stage_detail,
            })
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            db.save_strategy6_optimization_trial(_trial_db_item(
                campaign_id, parent_parameter_set_id, trial, status="FAILED",
                coarse_run_id=trial_row.get("coarse_run_id"),
                reject_reason="FULL_RUN_EXCEPTION", error_message=str(exc),
            ))

    if confirmed:
        confirmed.sort(
            key=lambda item: calculate_robust_score(item[1])["robust_score"],
            reverse=True,
        )
        selected_trial = confirmed[0][0]
        selected_parameter_set_id = selected_trial.parameter_set_id
        selected_config = selected_trial.parameters
        decision = "FROZEN"
    else:
        selected_parameter_set_id = parent_parameter_set_id
        selected_config = parent_config
        decision = "KEEP_PREVIOUS_STAGE"
    db.save_strategy6_optimization_stage({
        **stage_row,
        "parent_parameter_set_id": parent_parameter_set_id,
        "selected_parameter_set_id": selected_parameter_set_id,
        "status": "FROZEN",
        "decision": decision,
        "detail": {
            **stage_detail,
            "selected_config": selected_config,
            "selector": selection,
            "confirmed_count": len(confirmed),
        },
    })
    return {
        "decision": decision,
        "selected_parameter_set_id": selected_parameter_set_id,
        "parent_parameter_set_id": parent_parameter_set_id,
        "selector": selection,
        "confirmed_count": len(confirmed),
    }


def _resolve_parent_config(campaign: dict, stages: list[dict], target: dict) -> tuple[dict, str]:
    previous = [item for item in stages if int(item["stage_order"]) < int(target["stage_order"])]
    if not previous:
        manifest = campaign["manifest"]
        return copy.deepcopy(manifest["base_config"]), str(manifest["base_parameter_set_id"])
    parent = max(previous, key=lambda item: int(item["stage_order"]))
    if parent["status"] != "FROZEN":
        raise RuntimeError(f"previous stage {parent['stage_id']} is not frozen")
    config = (parent.get("detail") or {}).get("selected_config")
    if not isinstance(config, dict):
        raise RuntimeError(f"previous stage {parent['stage_id']} has no selected config")
    return copy.deepcopy(config), str(parent["selected_parameter_set_id"])


def _trial_db_item(
    campaign_id: str,
    parent_parameter_set_id: str,
    trial: OptimizationTrial,
    *,
    status: str,
    coarse_run_id: str | None = None,
    full_run_id: str | None = None,
    selection_metrics: dict | None = None,
    reject_reason: str | None = None,
    error_message: str | None = None,
) -> dict:
    return {
        "campaign_id": campaign_id,
        "stage_id": trial.stage_id,
        "trial_id": trial.trial_id,
        "parameter_set_id": trial.parameter_set_id,
        "parent_parameter_set_id": parent_parameter_set_id,
        "trial_kind": trial.trial_kind,
        "status": status,
        "coarse_run_id": coarse_run_id,
        "full_run_id": full_run_id,
        "parameters": trial.parameters,
        "selection_metrics": selection_metrics or {},
        "reject_reason": reject_reason,
        "error_message": error_message,
    }


def _run_coarse_manifest(
    campaign_id: str,
    parent_parameter_set_id: str,
    manifest: tuple[OptimizationTrial, ...],
    run_trial: Callable[[OptimizationTrial, str], dict],
) -> None:
    if not manifest:
        return
    stage_id = manifest[0].stage_id
    existing = db.get_strategy6_optimization_trials(campaign_id, stage_id)
    existing_ids = {item["trial_id"] for item in existing}
    for trial in manifest:
        if trial.trial_id not in existing_ids:
            db.save_strategy6_optimization_trial(_trial_db_item(
                campaign_id, parent_parameter_set_id, trial, status="PENDING",
            ))
    recovered = recover_interrupted_trials(db.get_strategy6_optimization_trials(campaign_id, stage_id))
    for item in recovered:
        if item["status"] == "INTERRUPTED":
            db.save_strategy6_optimization_trial({**item, "status": "INTERRUPTED"})
    for trial in trials_needing_execution(manifest, recovered):
        db.save_strategy6_optimization_trial(_trial_db_item(
            campaign_id, parent_parameter_set_id, trial, status="RUNNING",
        ))
        try:
            result = run_trial(trial, "COARSE_TRAIN")
            run_status = str((result.get("run") or {}).get("status") or "FAILED")
            training = ((result.get("phase_results") or {}).get("TRAIN") or {}).get("selection_metrics") or {}
            completed = run_status in {"COMPLETED", "COMPLETED_WITH_SKIPS"}
            db.save_strategy6_optimization_trial(_trial_db_item(
                campaign_id, parent_parameter_set_id, trial,
                status=run_status if completed else "FAILED",
                coarse_run_id=str((result.get("run") or {}).get("run_id") or ""),
                selection_metrics=training,
                reject_reason=None if completed else "COARSE_RUN_INCOMPLETE",
            ))
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            db.save_strategy6_optimization_trial(_trial_db_item(
                campaign_id, parent_parameter_set_id, trial, status="FAILED",
                reject_reason="COARSE_RUN_EXCEPTION", error_message=str(exc),
            ))


def _approved_joint_candidates(
    stage_spec,
    oat_manifest: tuple[OptimizationTrial, ...],
    rows: list[dict],
    *,
    evaluation_step: int,
) -> dict[str, list]:
    trial_by_id = {item.trial_id: item for item in oat_manifest}
    approved = {spec.key: [spec.default] for spec in stage_spec.parameters}
    for row in rows:
        trial = trial_by_id.get(row["trial_id"])
        if trial is None or trial.trial_kind != "OAT":
            continue
        if not evaluate_coarse_gates(
            row.get("selection_metrics") or {}, evaluation_step=evaluation_step,
        )["passed"]:
            continue
        for key, value in trial.changed_parameters.items():
            if value not in approved[key]:
                approved[key].append(value)
    return approved


def _build_selector_input(rows: list[dict], *, evaluation_step: int = 5) -> list[dict]:
    result = []
    for row in rows:
        metrics = row.get("selection_metrics") or {}
        neighbors = _nearest_neighbor_metrics(row, rows, evaluation_step=evaluation_step)
        result.append({
            "parameter_set_id": row["parameter_set_id"],
            "status": row["status"],
            "training_metrics": metrics,
            "neighbor_metrics": neighbors,
        })
    return result


def _nearest_neighbor_metrics(target: dict, rows: list[dict], *, evaluation_step: int) -> list[dict]:
    target_flat = _flatten(target.get("parameters") or {})
    distances = []
    for other in rows:
        if other["trial_id"] == target["trial_id"]:
            continue
        other_flat = _flatten(other.get("parameters") or {})
        keys = set(target_flat) | set(other_flat)
        distance = sum(target_flat.get(key) != other_flat.get(key) for key in keys)
        distances.append((distance, other))
    if not distances:
        return []
    minimum = min(item[0] for item in distances)
    neighbors = []
    for distance, item in distances:
        if distance != minimum:
            continue
        metrics = item.get("selection_metrics") or {}
        neighbors.append({
            "passed": evaluate_coarse_gates(metrics, evaluation_step=evaluation_step)["passed"],
            "robust_score": calculate_robust_score(metrics)["robust_score"],
        })
    return neighbors


def _flatten(value: dict, prefix: str = "") -> dict:
    result = {}
    for key, nested in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(nested, dict):
            result.update(_flatten(nested, path))
        else:
            result[path] = nested
    return result


def run_comprehensive_cli(args, coverage) -> int:
    from strategy6.backtest.config import resolve_backtest_config
    from strategy6.backtest.runner import run_local_parameter_set

    root_config = load_yaml_config(args.config)
    research_config = copy.deepcopy(root_config.get("strategy6") or {})
    research_config["decision_profile"] = "research_quality_v2"
    base_config = resolve_strategy6_config({"strategy6": research_config})
    data_version = build_database_fingerprint(db.get_conn())
    if args.command == "comprehensive-plan":
        result = initialize_campaign(
            campaign_id=args.campaign_id,
            base_config=base_config,
            strategy_git_commit=_git_commit(),
            data_version=data_version,
            random_seed=20260712,
            max_joint_trials=args.max_joint_trials,
            evaluation_step=args.evaluation_step,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "comprehensive-report":
        print(json.dumps(campaign_status(args.campaign_id), ensure_ascii=False, indent=2, default=str))
        return 0

    current = campaign_status(args.campaign_id)
    assert_campaign_run_identity(current["campaign"], args)
    assert_campaign_data_version(current["campaign"], data_version)
    stage_id = str(args.stage_id or "")
    if not stage_id:
        target = next((item for item in current["stages"] if item["status"] != "FROZEN"), None)
        if target is None:
            print(json.dumps({"campaign_id": args.campaign_id, "status": "COMPLETED"}, ensure_ascii=False))
            return 0
        stage_id = str(target["stage_id"])
    stage_row = next(item for item in current["stages"] if item["stage_id"] == stage_id)
    backtest_config = resolve_backtest_config({})

    def run_trial(trial: OptimizationTrial, mode: str) -> dict:
        run_args = copy.copy(args)
        run_args.run_mode = mode
        run_args.evaluation_step = int(args.evaluation_step) if mode == "COARSE_TRAIN" else 1
        run_args.start = "2023-01-01"
        run_args.end = "2024-12-31" if mode == "COARSE_TRAIN" else "2025-12-31"
        run_args.stage_id = stage_id
        live_stage = next(
            item for item in db.get_strategy6_optimization_stages(args.campaign_id)
            if item["stage_id"] == stage_id
        )
        run_args.parent_parameter_set_id = live_stage["parent_parameter_set_id"]
        run_args.data_version_override = current["campaign"]["data_version"]
        return run_local_parameter_set(
            experiment_id=f"{args.campaign_id}:{stage_id}:{trial.trial_id}:{mode}",
            strategy_config=copy.deepcopy(trial.parameters),
            backtest_config=backtest_config,
            coverage=coverage,
            args=run_args,
        )

    result = execute_campaign_stage(args.campaign_id, stage_id, run_trial=run_trial)
    refreshed = campaign_status(args.campaign_id)
    all_frozen = all(item["status"] == "FROZEN" for item in refreshed["stages"])
    execution_result = None
    if all_frozen:
        execution_result = execute_campaign_execution_tuning(
            args.campaign_id,
            market_dates=sorted({
                str(row.get("date") or "")
                for rows in coverage.data_by_symbol.values()
                for row in rows if row.get("date")
            }),
            base_backtest_config=backtest_config,
        )
    campaign = campaign_status(args.campaign_id)["campaign"]
    db.save_strategy6_optimization_campaign({
        "campaign_id": args.campaign_id,
        "status": "COMPLETED" if all_frozen and execution_result and execution_result.get("completed") else "RUNNING",
        "strategy_git_commit": campaign["strategy_git_commit"],
        "data_version": campaign["data_version"],
        "base_config_hash": campaign["base_config_hash"],
        "manifest": campaign["manifest"],
    })
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def execute_campaign_execution_tuning(
    campaign_id: str,
    *,
    market_dates: list[str],
    base_backtest_config: dict,
) -> dict:
    from strategy6.backtest.runner import build_phase_selection_results
    from strategy6.backtest.stress import (
        build_execution_tuning_configs,
        evaluate_stress_acceptance,
        replay_frozen_signals,
        replay_stress_scenarios,
    )

    status = campaign_status(campaign_id)
    if not all(item["status"] == "FROZEN" for item in status["stages"]):
        raise RuntimeError("all signal-parameter stages must be frozen before execution tuning")
    final_stage = max(status["stages"], key=lambda item: int(item["stage_order"]))
    parameter_id = str(final_stage.get("selected_parameter_set_id") or "")
    trials = db.get_strategy6_optimization_trials(campaign_id)
    matches = [item for item in trials if item["parameter_set_id"] == parameter_id and item.get("full_run_id")]
    if not matches:
        result = {
            "completed": False,
            "decision": "INSUFFICIENT_FULL_RUN",
            "stress_passed": False,
            "selected_parameter_set_id": parameter_id,
        }
        _save_execution_manifest(status["campaign"], result)
        return result
    selected_trial = matches[-1]
    run_id = str(selected_trial["full_run_id"])
    signal_rows = db.get_strategy6_backtest_signals(run_id, parameter_id)
    signals = [
        BacktestSignal(
            parameter_set_id=parameter_id,
            code=item["code"], name=item["name"],
            evaluation_date=item["evaluation_date"], setup_id=item["setup_id"],
            tail_path=item["tail_path"], candidate_type=item["candidate_type"],
            snapshot=item["snapshot"],
        )
        for item in signal_rows
    ]
    if not signals:
        result = {
            "completed": False,
            "decision": "INSUFFICIENT_SIGNALS",
            "stress_passed": False,
            "selected_parameter_set_id": parameter_id,
            "full_run_id": run_id,
        }
        _save_execution_manifest(status["campaign"], result)
        return result

    conn = db.get_conn()
    row_cache: dict[str, list[dict]] = {}

    def load_rows(code: str) -> list[dict]:
        if code not in row_cache:
            rows = conn.execute(
                '''SELECT date, open, high, low, close, volume, turnover
                   FROM daily_ohlc WHERE code=? AND date<='2025-12-31' ORDER BY date''',
                (code,),
            ).fetchall()
            row_cache[code] = [
                {"date": row[0], "open": row[1], "high": row[2], "low": row[3],
                 "close": row[4], "volume": row[5], "turnover": row[6]}
                for row in rows
            ]
        return row_cache[code]

    train_signals = [signal for signal in signals if signal.evaluation_date <= "2024-12-31"]
    validation_signals = [signal for signal in signals if "2025-01-01" <= signal.evaluation_date <= "2025-12-31"]
    train_market_dates = [date for date in market_dates if date <= "2024-12-31"]
    validation_market_dates = [date for date in market_dates if date <= "2025-12-31"]
    candidates = []
    for item in build_execution_tuning_configs(base_backtest_config):
        replay = replay_frozen_signals(
            train_signals, load_rows=load_rows, market_dates=train_market_dates, config=item["config"],
        )
        metrics = build_phase_selection_results(replay["trades"], base_backtest_config["position"])["TRAIN"]["selection_metrics"]
        gates = evaluate_hard_gates(metrics)
        candidates.append({**item, "training_metrics": metrics, "gate_passed": gates["passed"]})
    eligible = [item for item in candidates if item["gate_passed"]]
    eligible.sort(key=lambda item: calculate_robust_score(item["training_metrics"])["robust_score"], reverse=True)
    selected = eligible[0] if eligible else next(
        item for item in candidates
        if item["buy_zone_valid_days"] == base_backtest_config["execution"]["buy_zone_valid_days"]
        and item["max_holding_days"] == base_backtest_config["execution"]["max_holding_days"]
    )
    validation_replay = replay_frozen_signals(
        validation_signals, load_rows=load_rows, market_dates=validation_market_dates, config=selected["config"],
    )
    validation_metrics = build_phase_selection_results(
        validation_replay["trades"], base_backtest_config["position"],
    )["VALIDATION"]["selection_metrics"]
    confirmation = confirm_validation_metrics(selected["training_metrics"], validation_metrics)
    stress = replay_stress_scenarios(
        validation_signals,
        load_rows=load_rows,
        market_dates=validation_market_dates,
        base_config=selected["config"],
    )
    stress_acceptance = evaluate_stress_acceptance(stress)
    result = {
        "completed": True,
        "decision": "RECOMMEND" if confirmation["passed"] and stress_acceptance["passed"] else "KEEP_DEFAULT",
        "stress_passed": stress_acceptance["passed"],
        "validation_confirmed": confirmation["passed"],
        "selected_parameter_set_id": parameter_id,
        "full_run_id": run_id,
        "buy_zone_valid_days": selected["buy_zone_valid_days"],
        "max_holding_days": selected["max_holding_days"],
        "training_metrics": selected["training_metrics"],
        "validation_metrics": validation_metrics,
        "validation_confirmation": confirmation,
        "stress_acceptance": stress_acceptance,
        "stress_results": stress,
        "trial_count": len(candidates),
    }
    _save_execution_manifest(status["campaign"], result)
    return result


def _save_execution_manifest(campaign: dict, execution_result: dict) -> None:
    manifest = copy.deepcopy(campaign["manifest"])
    manifest["execution_tuning"] = execution_result
    db.save_strategy6_optimization_campaign({
        "campaign_id": campaign["campaign_id"],
        "status": campaign["status"],
        "strategy_git_commit": campaign["strategy_git_commit"],
        "data_version": campaign["data_version"],
        "base_config_hash": campaign["base_config_hash"],
        "manifest": manifest,
    })


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "UNKNOWN"
