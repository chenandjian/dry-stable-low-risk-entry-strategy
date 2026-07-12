import copy

from strategy6.backtest.campaign import build_stage_trial_manifest, trials_needing_execution
from strategy6.backtest.parameter_registry import build_comprehensive_registry
from strategy6.validation import DEFAULT_STRATEGY6_CONFIG


def _stage(stage_id):
    return next(stage for stage in build_comprehensive_registry(DEFAULT_STRATEGY6_CONFIG) if stage.stage_id == stage_id)


def test_stage_manifest_contains_one_baseline_and_each_legal_oat_candidate():
    stage = _stage("pattern")
    manifest = build_stage_trial_manifest(
        stage, DEFAULT_STRATEGY6_CONFIG, max_joint_trials=0, random_seed=7,
    )

    assert manifest[0].trial_kind == "BASELINE"
    assert manifest[0].parameters == DEFAULT_STRATEGY6_CONFIG
    oat = [trial for trial in manifest if trial.trial_kind == "OAT"]
    expected = sum(
        len({*spec.candidates} - {spec.default})
        for spec in stage.parameters
    )
    assert len(oat) == expected
    assert len({trial.parameter_set_id for trial in manifest}) == len(manifest)


def test_joint_manifest_is_deterministic_bounded_and_uses_only_legal_combinations():
    stage = _stage("strong_start")
    first = build_stage_trial_manifest(
        stage, DEFAULT_STRATEGY6_CONFIG, max_joint_trials=24, random_seed=20260712,
    )
    second = build_stage_trial_manifest(
        stage, DEFAULT_STRATEGY6_CONFIG, max_joint_trials=24, random_seed=20260712,
    )

    first_joint = [trial for trial in first if trial.trial_kind == "JOINT"]
    assert [trial.parameter_set_id for trial in first] == [trial.parameter_set_id for trial in second]
    assert len(first_joint) <= 24
    assert len(first_joint) == 24
    for trial in first_joint:
        cfg = trial.parameters
        assert cfg["start_age_min_days"] < cfg["start_age_max_days"]
        assert cfg["low_volume_limit_up_min_ratio"] < cfg["limit_up_volume_ratio"]


def test_stage_trials_do_not_mutate_parent_or_fields_outside_current_stage():
    parent = copy.deepcopy(DEFAULT_STRATEGY6_CONFIG)
    parent["min_relative_strength_20"] = 0.15
    parent["tail_volume_ratio_5_20"] = 0.65
    stage = _stage("pattern")
    stage_keys = {spec.key for spec in stage.parameters}

    manifest = build_stage_trial_manifest(stage, parent, max_joint_trials=8, random_seed=9)

    assert parent["cup_depth_min"] == DEFAULT_STRATEGY6_CONFIG["cup_depth_min"]
    for trial in manifest:
        assert trial.parameters["min_relative_strength_20"] == 0.15
        assert trial.parameters["tail_volume_ratio_5_20"] == 0.65
        changed = {
            key for key in DEFAULT_STRATEGY6_CONFIG
            if trial.parameters.get(key) != parent.get(key)
        }
        assert changed <= stage_keys


def test_compact_joint_trials_generate_overlap_count_legal_for_selected_window():
    manifest = build_stage_trial_manifest(
        _stage("box_compact"), DEFAULT_STRATEGY6_CONFIG,
        max_joint_trials=24, random_seed=11,
    )

    for trial in manifest:
        compact = trial.parameters["box_tail"]["compact_kline"]
        assert 1 <= compact["min_overlap_pair_count"] < compact["window_days"]


def test_resume_only_schedules_missing_and_failed_trials():
    manifest = build_stage_trial_manifest(
        _stage("liquidity_rs"), DEFAULT_STRATEGY6_CONFIG,
        max_joint_trials=2, random_seed=3,
    )
    existing = [
        {"trial_id": manifest[0].trial_id, "status": "COMPLETED"},
        {"trial_id": manifest[1].trial_id, "status": "RUNNING"},
        {"trial_id": manifest[2].trial_id, "status": "FAILED"},
    ]

    pending = trials_needing_execution(manifest, existing)

    assert manifest[0].trial_id not in {trial.trial_id for trial in pending}
    assert manifest[1].trial_id not in {trial.trial_id for trial in pending}
    assert manifest[2].trial_id in {trial.trial_id for trial in pending}
    assert len(pending) == len(manifest) - 2


def test_joint_manifest_only_uses_oat_approved_candidate_regions():
    stage = _stage("liquidity_rs")
    allowed = {
        spec.key: (spec.default,) for spec in stage.parameters
    }
    allowed["min_relative_strength_20"] = (0.05, 0.10)
    allowed["amount10_vs_30_min_ratio"] = (0.80, 0.90)

    manifest = build_stage_trial_manifest(
        stage, DEFAULT_STRATEGY6_CONFIG,
        max_joint_trials=8, random_seed=15,
        joint_candidate_overrides=allowed,
    )
    joint = [item for item in manifest if item.trial_kind == "JOINT"]

    assert joint
    assert {item.parameters["min_relative_strength_20"] for item in joint} <= {0.05, 0.10}
    for item in joint:
        assert item.parameters["min_avg_amount_60d_yi"] == DEFAULT_STRATEGY6_CONFIG["min_avg_amount_60d_yi"]
