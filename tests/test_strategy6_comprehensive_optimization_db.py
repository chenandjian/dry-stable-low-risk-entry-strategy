import sqlite3

import scanner.db as db


def test_init_db_adds_strategy6_optimization_tables_to_existing_database(tmp_path):
    path = tmp_path / "legacy.db"
    sqlite3.connect(path).close()

    db.init_db(str(path))

    tables = {
        row[0]
        for row in db.get_conn().execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {
        "strategy6_optimization_campaigns",
        "strategy6_optimization_stages",
        "strategy6_optimization_trials",
    } <= tables


def test_campaign_stage_and_trial_round_trip_with_parent_and_metrics(tmp_path):
    db.init_db(str(tmp_path / "optimization.db"))
    db.save_strategy6_optimization_campaign({
        "campaign_id": "campaign-1",
        "status": "RUNNING",
        "strategy_git_commit": "abc123",
        "data_version": "data-v1",
        "base_config_hash": "cfg-1",
        "manifest": {"seed": 20260712},
    })
    db.save_strategy6_optimization_stage({
        "campaign_id": "campaign-1",
        "stage_id": "liquidity_rs",
        "stage_order": 1,
        "status": "RUNNING",
        "parent_parameter_set_id": "baseline",
        "selected_parameter_set_id": None,
        "decision": None,
        "detail": {"trial_count": 3},
    })
    db.save_strategy6_optimization_trial({
        "campaign_id": "campaign-1",
        "stage_id": "liquidity_rs",
        "trial_id": "trial-1",
        "parameter_set_id": "p1",
        "parent_parameter_set_id": "baseline",
        "trial_kind": "OAT",
        "status": "COMPLETED",
        "coarse_run_id": "run-coarse",
        "full_run_id": "run-full",
        "parameters": {"min_avg_amount_60d_yi": 4},
        "selection_metrics": {"expectancy_r": 0.2},
        "reject_reason": None,
    })

    campaign = db.get_strategy6_optimization_campaign("campaign-1")
    stage = db.get_strategy6_optimization_stages("campaign-1")[0]
    trial = db.get_strategy6_optimization_trials("campaign-1", "liquidity_rs")[0]

    assert campaign["manifest"] == {"seed": 20260712}
    assert stage["parent_parameter_set_id"] == "baseline"
    assert stage["detail"] == {"trial_count": 3}
    assert trial["coarse_run_id"] == "run-coarse"
    assert trial["full_run_id"] == "run-full"
    assert trial["parameters"] == {"min_avg_amount_60d_yi": 4}
    assert trial["selection_metrics"] == {"expectancy_r": 0.2}


def test_optimization_manifest_upserts_are_idempotent_and_preserve_identity(tmp_path):
    db.init_db(str(tmp_path / "idempotent.db"))
    item = {
        "campaign_id": "campaign-1", "stage_id": "pattern", "trial_id": "trial-1",
        "parameter_set_id": "p1", "parent_parameter_set_id": "p0", "trial_kind": "JOINT",
        "status": "PENDING", "parameters": {"cup_depth_min": 0.12},
    }
    db.save_strategy6_optimization_trial(item)
    db.save_strategy6_optimization_trial({**item, "status": "RUNNING", "coarse_run_id": "run-1"})

    rows = db.get_strategy6_optimization_trials("campaign-1", "pattern")
    assert len(rows) == 1
    assert rows[0]["status"] == "RUNNING"
    assert rows[0]["coarse_run_id"] == "run-1"
    assert rows[0]["parameters"] == {"cup_depth_min": 0.12}


def test_only_successful_trials_without_failed_stock_progress_are_selectable(tmp_path):
    db.init_db(str(tmp_path / "selectable.db"))
    base = {
        "campaign_id": "campaign-1", "stage_id": "dry_tail",
        "parent_parameter_set_id": "p0", "trial_kind": "JOINT", "parameters": {},
    }
    for trial_id, status in (
        ("good", "COMPLETED"),
        ("skips", "COMPLETED_WITH_SKIPS"),
        ("failed", "FAILED"),
        ("running", "RUNNING"),
    ):
        db.save_strategy6_optimization_trial({
            **base, "trial_id": trial_id, "parameter_set_id": trial_id,
            "status": status, "coarse_run_id": f"run-{trial_id}",
        })
    db.get_conn().execute(
        """INSERT INTO strategy6_backtest_stock_progress
           (run_id, parameter_set_id, code, status) VALUES (?, ?, ?, ?)""",
        ("run-skips", "skips", "000001", "FAILED_DATA"),
    )
    db.get_conn().commit()

    selectable = db.get_selectable_strategy6_optimization_trials("campaign-1", "dry_tail")

    assert [item["trial_id"] for item in selectable] == ["good"]
