from strategy6.backtest.config import resolve_backtest_config
from strategy6.backtest.models import BacktestRunSpec, ParameterSet


def test_backtest_run_and_parameter_ids_are_deterministic():
    config = resolve_backtest_config({})
    first = BacktestRunSpec.create(
        experiment_id="E0_ORIGINAL_BASELINE",
        strategy_version="4.1.0",
        strategy_git_commit="4cff1ca",
        strategy_config={"box_tail": {"enabled": False}},
        backtest_config=config,
        data_version="fixture-v1",
    )
    second = BacktestRunSpec.create(
        experiment_id="E0_ORIGINAL_BASELINE",
        strategy_version="4.1.0",
        strategy_git_commit="4cff1ca",
        strategy_config={"box_tail": {"enabled": False}},
        backtest_config=config,
        data_version="fixture-v1",
    )
    assert first.identity_hash == second.identity_hash
    assert first.run_id == second.run_id
    assert first.confidence_label == "RESEARCH_ONLY_CURRENT_UNIVERSE"

    parameter = ParameterSet.create({"box_tail": {"normal_box_width_max": 0.18}})
    assert parameter.parameter_set_id == ParameterSet.create(parameter.parameters).parameter_set_id
    assert len(parameter.config_hash) == 64


def test_default_backtest_config_uses_confirmed_conservative_rules():
    config = resolve_backtest_config({})
    assert config["price_mode"] == "forward_adjusted"
    assert config["signal_generation_mode"] == "AS_OF_REBUILD"
    assert config["execution"]["below_buy_zone_open_mode"] == "CANCEL"
    assert config["execution"]["buy_zone_valid_days"] == 3
    assert config["execution"]["same_day_stop_target"] == "STOP_FIRST"
    assert config["execution"]["use_t_plus_one"] is True
    assert config["optimization"]["auto_write_production_config"] is False
    assert config["optimization"]["random_seed"] == 20260711

