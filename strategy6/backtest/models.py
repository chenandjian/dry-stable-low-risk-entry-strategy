"""Traceable data models for Strategy6 historical research."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json


def stable_hash(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ParameterSet:
    parameter_set_id: str
    config_hash: str
    parameters: dict

    @classmethod
    def create(cls, parameters: dict) -> "ParameterSet":
        copied = json.loads(json.dumps(parameters, ensure_ascii=False))
        digest = stable_hash(copied)
        return cls(parameter_set_id=f"s6ps-{digest[:16]}", config_hash=digest, parameters=copied)


@dataclass(frozen=True)
class BacktestRunSpec:
    run_id: str
    identity_hash: str
    experiment_id: str
    strategy_version: str
    strategy_git_commit: str
    strategy_config_hash: str
    backtest_config_hash: str
    data_version: str
    confidence_label: str
    random_seed: int
    run_mode: str = "LEGACY_DAILY"
    stage_id: str = ""
    parent_parameter_set_id: str = ""
    evaluation_step: int = 1
    start_date: str = ""
    end_date: str = ""

    @classmethod
    def create(
        cls,
        *,
        experiment_id: str,
        strategy_version: str,
        strategy_git_commit: str,
        strategy_config: dict,
        backtest_config: dict,
        data_version: str,
        research_context: dict | None = None,
    ) -> "BacktestRunSpec":
        context = dict(research_context or {})
        identity = {
            "experiment_id": experiment_id,
            "strategy_version": strategy_version,
            "strategy_git_commit": strategy_git_commit,
            "strategy_config": strategy_config,
            "backtest_config": backtest_config,
            "data_version": data_version,
            "research_context": context,
        }
        digest = stable_hash(identity)
        return cls(
            run_id=f"s6bt-{digest[:20]}",
            identity_hash=digest,
            experiment_id=experiment_id,
            strategy_version=strategy_version,
            strategy_git_commit=strategy_git_commit,
            strategy_config_hash=stable_hash(strategy_config),
            backtest_config_hash=stable_hash(backtest_config),
            data_version=data_version,
            confidence_label=str(backtest_config.get("confidence_label") or "RESEARCH_ONLY_CURRENT_UNIVERSE"),
            random_seed=int((backtest_config.get("optimization") or {}).get("random_seed", 20260711)),
            run_mode=str(context.get("run_mode") or "LEGACY_DAILY"),
            stage_id=str(context.get("stage_id") or ""),
            parent_parameter_set_id=str(context.get("parent_parameter_set_id") or ""),
            evaluation_step=int(context.get("evaluation_step", 1)),
            start_date=str(context.get("start_date") or ""),
            end_date=str(context.get("end_date") or ""),
        )


@dataclass
class BacktestSignal:
    parameter_set_id: str
    code: str
    name: str
    evaluation_date: str
    setup_id: str
    tail_path: str
    candidate_type: str
    snapshot: dict = field(default_factory=dict)


@dataclass
class BacktestOrder:
    order_id: str
    signal: BacktestSignal
    created_date: str
    expire_date: str
    status: str = "PENDING"
    fill_reason: str = ""


@dataclass
class BacktestTrade:
    trade_id: str
    code: str
    signal_date: str
    entry_date: str = ""
    entry_price: float = 0.0
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    net_return: float = 0.0
    r_multiple: float = 0.0
    commission: float = 0.0
    tax: float = 0.0
    slippage: float = 0.0
    intraday_stop_breach: bool = False
