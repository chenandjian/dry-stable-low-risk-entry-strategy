"""Deterministic trial manifests for staged Strategy6 optimization."""
from __future__ import annotations

import copy
from dataclasses import dataclass
import random

from strategy6.backtest.models import ParameterSet, stable_hash
from strategy6.backtest.parameter_registry import (
    ParameterSpec,
    StageSpec,
    apply_parameter_value,
    compact_overlap_candidates,
    validate_stage_combination,
)


@dataclass(frozen=True)
class OptimizationTrial:
    trial_id: str
    stage_id: str
    trial_kind: str
    parameter_set_id: str
    parameters: dict
    changed_parameters: dict


def build_stage_trial_manifest(
    stage: StageSpec,
    parent_config: dict,
    *,
    max_joint_trials: int,
    random_seed: int,
    joint_candidate_overrides: dict[str, tuple] | None = None,
) -> tuple[OptimizationTrial, ...]:
    parent = validate_stage_combination(copy.deepcopy(parent_config))
    trials: list[OptimizationTrial] = []
    seen: set[str] = set()

    _append_trial(trials, seen, stage, "BASELINE", parent, {})
    for spec in stage.parameters:
        for value in spec.candidates:
            if value == spec.default:
                continue
            config = copy.deepcopy(parent)
            try:
                _apply_with_dependencies(config, spec, value)
                config = validate_stage_combination(config)
            except ValueError:
                continue
            _append_trial(trials, seen, stage, "OAT", config, {spec.key: value})

    rng = random.Random(random_seed)
    joint_added = 0
    attempts = 0
    max_attempts = max(100, max_joint_trials * 200)
    while joint_added < max(0, max_joint_trials) and attempts < max_attempts:
        attempts += 1
        config = copy.deepcopy(parent)
        changed = {}
        try:
            for spec in stage.parameters:
                candidates = _legal_candidates(spec, config, joint_candidate_overrides)
                value = rng.choice(candidates)
                _apply_with_dependencies(config, spec, value)
                if value != spec.default:
                    changed[spec.key] = value
            config = validate_stage_combination(config)
        except ValueError:
            continue
        before = len(trials)
        _append_trial(trials, seen, stage, "JOINT", config, changed)
        if len(trials) > before:
            joint_added += 1
    return tuple(trials)


def trials_needing_execution(
    manifest: tuple[OptimizationTrial, ...] | list[OptimizationTrial],
    existing: list[dict],
) -> list[OptimizationTrial]:
    statuses = {str(item["trial_id"]): str(item.get("status") or "") for item in existing}
    terminal_or_active = {"COMPLETED", "COMPLETED_WITH_SKIPS", "RUNNING"}
    return [trial for trial in manifest if statuses.get(trial.trial_id) not in terminal_or_active]


def _legal_candidates(
    spec: ParameterSpec,
    config: dict,
    overrides: dict[str, tuple] | None = None,
) -> tuple:
    legal = spec.candidates
    if spec.key == "box_tail.compact_kline.min_overlap_pair_count":
        window = int(config["box_tail"]["compact_kline"]["window_days"])
        legal = compact_overlap_candidates(window)
    if overrides is not None and spec.key in overrides:
        candidates = tuple(value for value in overrides[spec.key] if value in legal)
        if not candidates:
            raise ValueError(f"no legal joint candidates for {spec.key}")
        return candidates
    return legal


def _apply_with_dependencies(config: dict, spec: ParameterSpec, value) -> None:
    apply_parameter_value(config, spec, value)
    if spec.key == "box_tail.compact_kline.window_days":
        compact = config["box_tail"]["compact_kline"]
        legal = compact_overlap_candidates(int(value))
        if int(compact["min_overlap_pair_count"]) not in legal:
            compact["min_overlap_pair_count"] = legal[len(legal) // 2]


def _append_trial(
    trials: list[OptimizationTrial],
    seen: set[str],
    stage: StageSpec,
    kind: str,
    config: dict,
    changed: dict,
) -> None:
    parameter = ParameterSet.create({"strategy6": config})
    if parameter.parameter_set_id in seen:
        return
    seen.add(parameter.parameter_set_id)
    trial_hash = stable_hash({
        "stage_id": stage.stage_id,
        "trial_kind": kind,
        "parameter_set_id": parameter.parameter_set_id,
    })
    trials.append(OptimizationTrial(
        trial_id=f"s6trial-{trial_hash[:16]}",
        stage_id=stage.stage_id,
        trial_kind=kind,
        parameter_set_id=parameter.parameter_set_id,
        parameters=copy.deepcopy(config),
        changed_parameters=copy.deepcopy(changed),
    ))
