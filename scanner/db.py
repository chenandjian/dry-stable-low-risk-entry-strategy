# scanner/db.py
"""SQLite database layer for CupHandleScan.

Single database file at data/cuphandle.db with tables:
  stock_pool, daily_ohlc, scan_tasks, candidates.
"""

import json
import sqlite3
import os
import threading
import datetime
from contextlib import contextmanager

DB_PATH = None
_local = threading.local()
STRATEGY2_DATA_REVISION_VERSION = "daily-ohlc-v2"


def init_db(path: str = "data/cuphandle.db"):
    """Initialize database and create tables if not exist."""
    global DB_PATH
    if hasattr(_local, 'conn') and _local.conn is not None:
        try:
            _local.conn.close()
        except sqlite3.Error:
            pass
        _local.conn = None
    DB_PATH = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with get_conn() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS stock_pool (
                code    TEXT PRIMARY KEY,
                name    TEXT NOT NULL,
                market  TEXT,
                updated TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS daily_ohlc (
                code     TEXT NOT NULL,
                date     TEXT NOT NULL,
                open     REAL,
                high     REAL,
                low      REAL,
                close    REAL,
                volume   REAL,
                turnover REAL,
                PRIMARY KEY (code, date)
            );
            CREATE INDEX IF NOT EXISTS idx_ohlc_code ON daily_ohlc(code);
            CREATE INDEX IF NOT EXISTS idx_ohlc_date ON daily_ohlc(date);

            CREATE TABLE IF NOT EXISTS market_index_ohlc (
                symbol     TEXT NOT NULL,
                date       TEXT NOT NULL,
                open       REAL,
                high       REAL,
                low        REAL,
                close      REAL,
                volume     REAL,
                turnover   REAL,
                source     TEXT,
                fetched_at TEXT,
                PRIMARY KEY (symbol, date)
            );
            CREATE INDEX IF NOT EXISTS idx_market_index_ohlc_symbol ON market_index_ohlc(symbol);
            CREATE INDEX IF NOT EXISTS idx_market_index_ohlc_date ON market_index_ohlc(date);

            CREATE TABLE IF NOT EXISTS scan_tasks (
                id               TEXT PRIMARY KEY,
                started_at       TEXT,
                finished_at      TEXT,
                status           TEXT DEFAULT 'running',
                total_stocks     INTEGER DEFAULT 0,
                scanned          INTEGER DEFAULT 0,
                skipped          INTEGER DEFAULT 0,
                candidates_count INTEGER DEFAULT 0,
                elapsed_seconds  REAL,
                error            TEXT
            );

            CREATE TABLE IF NOT EXISTS candidates (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id             TEXT NOT NULL,
                code                TEXT NOT NULL,
                name                TEXT NOT NULL,
                score               INTEGER,
                rating              TEXT,
                is_breakout         INTEGER DEFAULT 0,
                is_volume_breakout  INTEGER DEFAULT 0,
                breakout_price      REAL,
                vol_multiplier      REAL,
                cup_depth_pct       REAL,
                cup_duration        INTEGER,
                handle_depth_pct    REAL,
                handle_duration     INTEGER,
                lip_deviation_pct   REAL,
                left_high_price     REAL,
                cup_low_price       REAL,
                right_high_price    REAL,
                handle_low_price    REAL,
                left_high_date      TEXT,
                cup_low_date        TEXT,
                right_high_date     TEXT,
                handle_low_date     TEXT,
                latest_close        REAL,
                latest_turnover     REAL,
                dry_stable_verdict  TEXT,
                dry_stable_summary  TEXT,
                volume_dry_score    INTEGER,
                price_stable_score  INTEGER,
                pattern_score_20    INTEGER,
                pattern_type        TEXT,
                key_pattern_type    TEXT,
                risk_percent        REAL,
                rr1                 REAL,
                position_advice     TEXT,
                entry_zone_low      REAL,
                entry_zone_high     REAL,
                pivot               REAL,
                stop_loss           REAL,
                target_1            REAL,
                target_2            REAL,
                market_status       TEXT,
                market_position_advice TEXT,
                FOREIGN KEY (task_id) REFERENCES scan_tasks(id)
            );
            CREATE INDEX IF NOT EXISTS idx_candidates_task ON candidates(task_id);
            CREATE INDEX IF NOT EXISTS idx_candidates_score ON candidates(score DESC);
        ''')
        _ensure_candidate_columns(conn)
        _ensure_scan_task_columns(conn)
        _ensure_task_stocks_table(conn)
        _dedupe_candidates_before_unique_index(conn)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_task_code ON candidates(task_id, code)")
        _ensure_strategy2_candidates_table(conn)
        _ensure_strategy3_candidates_table(conn)
        _ensure_strategy4_tables(conn)
        _ensure_strategy5_candidates_table(conn)
        _ensure_strategy6_candidates_table(conn)
        _ensure_strategy6_market_snapshots_table(conn)
        _ensure_strategy6_lifecycle_table(conn)
        _ensure_strategy6_task_lifecycle_table(conn)
        _ensure_strategy6_backtest_tables(conn)
        _ensure_strategy6_optimization_tables(conn)
        _ensure_strategy2_backtest_tables(conn)
        _ensure_strategy3_backtest_tables(conn)
        _ensure_strategy1_backtest_tables(conn)
        conn.commit()


def _ensure_strategy6_backtest_tables(conn: sqlite3.Connection):
    """Create traceable Strategy6 research tables without changing production tables."""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS strategy6_backtest_runs (
            run_id TEXT PRIMARY KEY,
            experiment_id TEXT NOT NULL,
            strategy_version TEXT NOT NULL,
            strategy_git_commit TEXT,
            strategy_config_hash TEXT NOT NULL,
            backtest_config_hash TEXT NOT NULL,
            data_version TEXT NOT NULL,
            confidence_label TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            split_json TEXT NOT NULL DEFAULT '{}',
            error_message TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS strategy6_backtest_parameter_sets (
            run_id TEXT NOT NULL,
            parameter_set_id TEXT NOT NULL,
            config_hash TEXT NOT NULL,
            parameter_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            reject_reason TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (run_id, parameter_set_id)
        );
        CREATE TABLE IF NOT EXISTS strategy6_backtest_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            parameter_set_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            evaluation_date TEXT NOT NULL,
            setup_id TEXT NOT NULL,
            tail_path TEXT NOT NULL,
            candidate_type TEXT NOT NULL,
            snapshot_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE (run_id, parameter_set_id, code, evaluation_date)
        );
        CREATE TABLE IF NOT EXISTS strategy6_backtest_orders (
            order_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            parameter_set_id TEXT NOT NULL,
            setup_id TEXT NOT NULL,
            code TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            status TEXT NOT NULL,
            detail_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS strategy6_backtest_trades (
            trade_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            parameter_set_id TEXT NOT NULL,
            setup_id TEXT NOT NULL,
            code TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            entry_date TEXT,
            exit_date TEXT,
            net_return REAL DEFAULT 0,
            r_multiple REAL DEFAULT 0,
            detail_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS strategy6_backtest_metrics (
            run_id TEXT NOT NULL,
            parameter_set_id TEXT NOT NULL,
            phase TEXT NOT NULL,
            scope TEXT NOT NULL,
            metric_json TEXT NOT NULL,
            PRIMARY KEY (run_id, parameter_set_id, phase, scope)
        );
        CREATE TABLE IF NOT EXISTS strategy6_backtest_walk_forward (
            run_id TEXT NOT NULL,
            window_id TEXT NOT NULL,
            train_start TEXT NOT NULL,
            train_end TEXT NOT NULL,
            validation_start TEXT NOT NULL,
            validation_end TEXT NOT NULL,
            selected_parameter_set_id TEXT,
            result_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (run_id, window_id)
        );
        CREATE TABLE IF NOT EXISTS strategy6_backtest_stock_progress (
            run_id TEXT NOT NULL,
            parameter_set_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            signals_count INTEGER DEFAULT 0,
            orders_count INTEGER DEFAULT 0,
            trades_count INTEGER DEFAULT 0,
            error_message TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (run_id, parameter_set_id, code)
        );
        CREATE INDEX IF NOT EXISTS idx_s6_bt_signal_run_date
            ON strategy6_backtest_signals(run_id, parameter_set_id, evaluation_date);
        CREATE INDEX IF NOT EXISTS idx_s6_bt_signal_setup
            ON strategy6_backtest_signals(run_id, parameter_set_id, setup_id);
        CREATE INDEX IF NOT EXISTS idx_s6_bt_trade_run
            ON strategy6_backtest_trades(run_id, parameter_set_id, entry_date);
    ''')


def _ensure_strategy6_optimization_tables(conn: sqlite3.Connection):
    """Create resumable comprehensive-optimization metadata tables."""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS strategy6_optimization_campaigns (
            campaign_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'PENDING',
            strategy_git_commit TEXT,
            data_version TEXT NOT NULL,
            base_config_hash TEXT NOT NULL,
            manifest_json TEXT NOT NULL DEFAULT '{}',
            error_message TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS strategy6_optimization_stages (
            campaign_id TEXT NOT NULL,
            stage_id TEXT NOT NULL,
            stage_order INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            parent_parameter_set_id TEXT NOT NULL,
            selected_parameter_set_id TEXT,
            decision TEXT,
            detail_json TEXT NOT NULL DEFAULT '{}',
            error_message TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            PRIMARY KEY (campaign_id, stage_id)
        );
        CREATE TABLE IF NOT EXISTS strategy6_optimization_trials (
            campaign_id TEXT NOT NULL,
            stage_id TEXT NOT NULL,
            trial_id TEXT NOT NULL,
            parameter_set_id TEXT NOT NULL,
            parent_parameter_set_id TEXT NOT NULL,
            trial_kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            coarse_run_id TEXT,
            full_run_id TEXT,
            parameter_json TEXT NOT NULL DEFAULT '{}',
            selection_metric_json TEXT NOT NULL DEFAULT '{}',
            reject_reason TEXT,
            error_message TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            PRIMARY KEY (campaign_id, stage_id, trial_id),
            UNIQUE (campaign_id, stage_id, parameter_set_id)
        );
        CREATE INDEX IF NOT EXISTS idx_s6_opt_stage_status
            ON strategy6_optimization_stages(campaign_id, stage_order, status);
        CREATE INDEX IF NOT EXISTS idx_s6_opt_trial_status
            ON strategy6_optimization_trials(campaign_id, stage_id, status);
    ''')


def save_strategy6_optimization_campaign(item: dict) -> None:
    conn = get_conn()
    conn.execute(
        '''INSERT INTO strategy6_optimization_campaigns
           (campaign_id, status, strategy_git_commit, data_version,
            base_config_hash, manifest_json, error_message, completed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(campaign_id) DO UPDATE SET
             status=excluded.status,
             manifest_json=excluded.manifest_json,
             error_message=excluded.error_message,
             completed_at=excluded.completed_at,
             updated_at=datetime('now')''',
        (
            item["campaign_id"], item.get("status", "PENDING"),
            item.get("strategy_git_commit", ""), item["data_version"],
            item["base_config_hash"],
            json.dumps(item.get("manifest") or {}, ensure_ascii=False, sort_keys=True),
            item.get("error_message"), item.get("completed_at"),
        ),
    )
    conn.commit()


def get_strategy6_optimization_campaign(campaign_id: str) -> dict | None:
    row = get_conn().execute(
        '''SELECT campaign_id, status, strategy_git_commit, data_version,
                  base_config_hash, manifest_json, error_message, created_at,
                  updated_at, completed_at
           FROM strategy6_optimization_campaigns WHERE campaign_id=?''',
        (campaign_id,),
    ).fetchone()
    if not row:
        return None
    keys = (
        "campaign_id", "status", "strategy_git_commit", "data_version",
        "base_config_hash", "manifest", "error_message", "created_at",
        "updated_at", "completed_at",
    )
    result = dict(zip(keys, row))
    result["manifest"] = json.loads(result["manifest"] or "{}")
    return result


def save_strategy6_optimization_stage(item: dict) -> None:
    conn = get_conn()
    conn.execute(
        '''INSERT INTO strategy6_optimization_stages
           (campaign_id, stage_id, stage_order, status,
            parent_parameter_set_id, selected_parameter_set_id, decision,
            detail_json, error_message, completed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(campaign_id, stage_id) DO UPDATE SET
             status=excluded.status,
             parent_parameter_set_id=excluded.parent_parameter_set_id,
             selected_parameter_set_id=excluded.selected_parameter_set_id,
             decision=excluded.decision,
             detail_json=excluded.detail_json,
             error_message=excluded.error_message,
             completed_at=excluded.completed_at,
             updated_at=datetime('now')''',
        (
            item["campaign_id"], item["stage_id"], int(item["stage_order"]),
            item.get("status", "PENDING"), item["parent_parameter_set_id"],
            item.get("selected_parameter_set_id"), item.get("decision"),
            json.dumps(item.get("detail") or {}, ensure_ascii=False, sort_keys=True),
            item.get("error_message"), item.get("completed_at"),
        ),
    )
    conn.commit()


def get_strategy6_optimization_stages(campaign_id: str) -> list[dict]:
    rows = get_conn().execute(
        '''SELECT campaign_id, stage_id, stage_order, status,
                  parent_parameter_set_id, selected_parameter_set_id, decision,
                  detail_json, error_message, created_at, updated_at, completed_at
           FROM strategy6_optimization_stages WHERE campaign_id=?
           ORDER BY stage_order, stage_id''',
        (campaign_id,),
    ).fetchall()
    keys = (
        "campaign_id", "stage_id", "stage_order", "status",
        "parent_parameter_set_id", "selected_parameter_set_id", "decision",
        "detail", "error_message", "created_at", "updated_at", "completed_at",
    )
    result = []
    for row in rows:
        item = dict(zip(keys, row))
        item["detail"] = json.loads(item["detail"] or "{}")
        result.append(item)
    return result


def save_strategy6_optimization_trial(item: dict) -> None:
    conn = get_conn()
    conn.execute(
        '''INSERT INTO strategy6_optimization_trials
           (campaign_id, stage_id, trial_id, parameter_set_id,
            parent_parameter_set_id, trial_kind, status, coarse_run_id,
            full_run_id, parameter_json, selection_metric_json,
            reject_reason, error_message, completed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(campaign_id, stage_id, trial_id) DO UPDATE SET
             status=excluded.status,
             coarse_run_id=COALESCE(excluded.coarse_run_id, coarse_run_id),
             full_run_id=COALESCE(excluded.full_run_id, full_run_id),
             selection_metric_json=excluded.selection_metric_json,
             reject_reason=excluded.reject_reason,
             error_message=excluded.error_message,
             completed_at=excluded.completed_at,
             updated_at=datetime('now')''',
        (
            item["campaign_id"], item["stage_id"], item["trial_id"],
            item["parameter_set_id"], item["parent_parameter_set_id"],
            item["trial_kind"], item.get("status", "PENDING"),
            item.get("coarse_run_id"), item.get("full_run_id"),
            json.dumps(item.get("parameters") or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(item.get("selection_metrics") or {}, ensure_ascii=False, sort_keys=True),
            item.get("reject_reason"), item.get("error_message"), item.get("completed_at"),
        ),
    )
    conn.commit()


def get_strategy6_optimization_trials(campaign_id: str, stage_id: str | None = None) -> list[dict]:
    query = '''SELECT campaign_id, stage_id, trial_id, parameter_set_id,
                      parent_parameter_set_id, trial_kind, status,
                      coarse_run_id, full_run_id, parameter_json,
                      selection_metric_json, reject_reason, error_message,
                      created_at, updated_at, completed_at
               FROM strategy6_optimization_trials WHERE campaign_id=?'''
    params: list = [campaign_id]
    if stage_id is not None:
        query += " AND stage_id=?"
        params.append(stage_id)
    query += " ORDER BY stage_id, created_at, trial_id"
    rows = get_conn().execute(query, params).fetchall()
    keys = (
        "campaign_id", "stage_id", "trial_id", "parameter_set_id",
        "parent_parameter_set_id", "trial_kind", "status", "coarse_run_id",
        "full_run_id", "parameters", "selection_metrics", "reject_reason",
        "error_message", "created_at", "updated_at", "completed_at",
    )
    result = []
    for row in rows:
        item = dict(zip(keys, row))
        item["parameters"] = json.loads(item["parameters"] or "{}")
        item["selection_metrics"] = json.loads(item["selection_metrics"] or "{}")
        result.append(item)
    return result


def get_selectable_strategy6_optimization_trials(campaign_id: str, stage_id: str) -> list[dict]:
    result = []
    for item in get_strategy6_optimization_trials(campaign_id, stage_id):
        if item["status"] not in {"COMPLETED", "COMPLETED_WITH_SKIPS"}:
            continue
        run_id = item.get("full_run_id") or item.get("coarse_run_id")
        if not run_id:
            continue
        failed = get_conn().execute(
            '''SELECT 1 FROM strategy6_backtest_stock_progress
               WHERE run_id=? AND parameter_set_id=? AND status LIKE 'FAILED%' LIMIT 1''',
            (run_id, item["parameter_set_id"]),
        ).fetchone()
        if not failed:
            result.append(item)
    return result


def save_strategy6_backtest_run(item: dict) -> None:
    conn = get_conn()
    conn.execute(
        '''INSERT INTO strategy6_backtest_runs
           (run_id, experiment_id, strategy_version, strategy_git_commit,
            strategy_config_hash, backtest_config_hash, data_version,
            confidence_label, status, split_json, error_message, completed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(run_id) DO UPDATE SET
             status=excluded.status, error_message=excluded.error_message,
             completed_at=excluded.completed_at''',
        (
            item["run_id"], item["experiment_id"], item["strategy_version"],
            item.get("strategy_git_commit", ""), item["strategy_config_hash"],
            item["backtest_config_hash"], item["data_version"],
            item.get("confidence_label", "RESEARCH_ONLY_CURRENT_UNIVERSE"),
            item.get("status", "PENDING"),
            json.dumps(item.get("split_json") or {}, ensure_ascii=False, sort_keys=True),
            item.get("error_message"), item.get("completed_at"),
        ),
    )
    conn.commit()


def get_strategy6_backtest_run(run_id: str) -> dict | None:
    row = get_conn().execute(
        '''SELECT run_id, experiment_id, strategy_version, strategy_git_commit,
                  strategy_config_hash, backtest_config_hash, data_version,
                  confidence_label, status, split_json, error_message,
                  created_at, completed_at
           FROM strategy6_backtest_runs WHERE run_id=?''',
        (run_id,),
    ).fetchone()
    if not row:
        return None
    keys = (
        "run_id", "experiment_id", "strategy_version", "strategy_git_commit",
        "strategy_config_hash", "backtest_config_hash", "data_version",
        "confidence_label", "status", "split_json", "error_message",
        "created_at", "completed_at",
    )
    item = dict(zip(keys, row))
    item["split_json"] = json.loads(item["split_json"] or "{}")
    return item


def save_strategy6_backtest_parameter_set(run_id: str, item: dict) -> None:
    conn = get_conn()
    conn.execute(
        '''INSERT INTO strategy6_backtest_parameter_sets
           (run_id, parameter_set_id, config_hash, parameter_json, status, reject_reason)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(run_id, parameter_set_id) DO UPDATE SET
             status=excluded.status, reject_reason=excluded.reject_reason''',
        (
            run_id, item["parameter_set_id"], item["config_hash"],
            json.dumps(item.get("parameters") or {}, ensure_ascii=False, sort_keys=True),
            item.get("status", "PENDING"), item.get("reject_reason"),
        ),
    )
    conn.commit()


def replace_strategy6_backtest_signals(
    run_id: str,
    parameter_set_id: str,
    code: str,
    signals: list[dict],
) -> None:
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM strategy6_backtest_signals WHERE run_id=? AND parameter_set_id=? AND code=?",
            (run_id, parameter_set_id, code),
        )
        conn.executemany(
            '''INSERT INTO strategy6_backtest_signals
               (run_id, parameter_set_id, code, name, evaluation_date,
                setup_id, tail_path, candidate_type, snapshot_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            [
                (
                    run_id, parameter_set_id, code, item.get("name", ""),
                    item["evaluation_date"], item["setup_id"], item["tail_path"],
                    item["candidate_type"],
                    json.dumps(item.get("snapshot") or {}, ensure_ascii=False, sort_keys=True),
                )
                for item in signals
            ],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_strategy6_backtest_signals(run_id: str, parameter_set_id: str) -> list[dict]:
    rows = get_conn().execute(
        '''SELECT code, name, evaluation_date, setup_id, tail_path,
                  candidate_type, snapshot_json
           FROM strategy6_backtest_signals
           WHERE run_id=? AND parameter_set_id=?
           ORDER BY evaluation_date, code''',
        (run_id, parameter_set_id),
    ).fetchall()
    result = []
    for row in rows:
        result.append({
            "code": row[0], "name": row[1], "evaluation_date": row[2],
            "setup_id": row[3], "tail_path": row[4], "candidate_type": row[5],
            "snapshot": json.loads(row[6] or "{}"),
        })
    return result


def replace_strategy6_backtest_orders(
    run_id: str,
    parameter_set_id: str,
    code: str,
    orders: list[dict],
) -> None:
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM strategy6_backtest_orders WHERE run_id=? AND parameter_set_id=? AND code=?",
            (run_id, parameter_set_id, code),
        )
        conn.executemany(
            '''INSERT INTO strategy6_backtest_orders
               (order_id, run_id, parameter_set_id, setup_id, code,
                signal_date, status, detail_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            [
                (
                    f"{run_id}:{parameter_set_id}:{item['order_id']}",
                    run_id, parameter_set_id, item["setup_id"], code,
                    item["signal_date"], item["status"],
                    json.dumps(item, ensure_ascii=False, sort_keys=True),
                )
                for item in orders
            ],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def replace_strategy6_backtest_trades(
    run_id: str,
    parameter_set_id: str,
    code: str,
    trades: list[dict],
) -> None:
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM strategy6_backtest_trades WHERE run_id=? AND parameter_set_id=? AND code=?",
            (run_id, parameter_set_id, code),
        )
        conn.executemany(
            '''INSERT INTO strategy6_backtest_trades
               (trade_id, run_id, parameter_set_id, setup_id, code,
                signal_date, entry_date, exit_date, net_return, r_multiple, detail_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            [
                (
                    f"{run_id}:{parameter_set_id}:{item['trade_id']}",
                    run_id, parameter_set_id, item["setup_id"], code,
                    item["signal_date"], item.get("entry_date", ""), item.get("exit_date", ""),
                    item.get("net_return", 0), item.get("r_multiple", 0),
                    json.dumps(item, ensure_ascii=False, sort_keys=True),
                )
                for item in trades
            ],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def save_strategy6_backtest_stock_progress(
    run_id: str,
    parameter_set_id: str,
    code: str,
    *,
    name: str = "",
    status: str,
    signals_count: int = 0,
    orders_count: int = 0,
    trades_count: int = 0,
    error_message: str = "",
) -> None:
    conn = get_conn()
    conn.execute(
        '''INSERT INTO strategy6_backtest_stock_progress
           (run_id, parameter_set_id, code, name, status, signals_count,
            orders_count, trades_count, error_message, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(run_id, parameter_set_id, code) DO UPDATE SET
             name=excluded.name, status=excluded.status,
             signals_count=excluded.signals_count,
             orders_count=excluded.orders_count,
             trades_count=excluded.trades_count,
             error_message=excluded.error_message,
             updated_at=datetime('now')''',
        (
            run_id, parameter_set_id, code, name, status,
            signals_count, orders_count, trades_count, error_message,
        ),
    )
    conn.commit()


def get_completed_strategy6_backtest_codes(run_id: str, parameter_set_id: str) -> set[str]:
    rows = get_conn().execute(
        '''SELECT code FROM strategy6_backtest_stock_progress
           WHERE run_id=? AND parameter_set_id=?
             AND (status='COMPLETED' OR status LIKE 'SKIPPED_%') ''',
        (run_id, parameter_set_id),
    ).fetchall()
    return {row[0] for row in rows}


def save_strategy6_backtest_metric(
    run_id: str,
    parameter_set_id: str,
    phase: str,
    scope: str,
    metrics: dict,
) -> None:
    conn = get_conn()
    conn.execute(
        '''INSERT INTO strategy6_backtest_metrics
           (run_id, parameter_set_id, phase, scope, metric_json)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(run_id, parameter_set_id, phase, scope) DO UPDATE SET
             metric_json=excluded.metric_json''',
        (
            run_id, parameter_set_id, phase, scope,
            json.dumps(metrics or {}, ensure_ascii=False, sort_keys=True),
        ),
    )
    conn.commit()


def get_strategy6_backtest_metrics(run_id: str, *, allow_oos: bool = False) -> list[dict]:
    rows = get_conn().execute(
        '''SELECT parameter_set_id, phase, scope, metric_json
           FROM strategy6_backtest_metrics WHERE run_id=?
           ORDER BY parameter_set_id, phase, scope''',
        (run_id,),
    ).fetchall()
    if not allow_oos and any(str(row[1]).upper().startswith("OOS") for row in rows):
        raise PermissionError("OOS metrics are locked")
    return [
        {
            "parameter_set_id": row[0], "phase": row[1], "scope": row[2],
            "metrics": json.loads(row[3] or "{}"),
        }
        for row in rows
    ]


def _ensure_candidate_columns(conn: sqlite3.Connection):
    """Add strategy columns for databases created by older versions."""
    existing = {d[1] for d in conn.execute("PRAGMA table_info(candidates)").fetchall()}
    columns = {
        "dry_stable_verdict": "TEXT",
        "dry_stable_summary": "TEXT",
        "volume_dry_score": "INTEGER",
        "price_stable_score": "INTEGER",
        "pattern_score_20": "INTEGER",
        "pattern_type": "TEXT",
        "cup_handle_score": "INTEGER",
        "vcp_score": "INTEGER",
        "vcp_contractions": "INTEGER",
        "key_pattern_type": "TEXT",
        "risk_percent": "REAL",
        "rr1": "REAL",
        "position_advice": "TEXT",
        "entry_zone_low": "REAL",
        "entry_zone_high": "REAL",
        "pivot": "REAL",
        "stop_loss": "REAL",
        "target_1": "REAL",
        "target_2": "REAL",
        "market_status": "TEXT",
        "market_position_advice": "TEXT",
        "verdict_key": "TEXT",
        "positive_factors": "TEXT",
        "warnings": "TEXT",
        "reject_reasons": "TEXT",
        "raw_volume_dry_score": "INTEGER",
        "raw_price_stable_score": "INTEGER",
        "score_caps": "TEXT",
    }
    for name, typ in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE candidates ADD COLUMN {name} {typ}")




def _ensure_scan_task_columns(conn: sqlite3.Connection):
    """Add scan task tracking columns for databases created by older versions."""
    existing = {d[1] for d in conn.execute("PRAGMA table_info(scan_tasks)").fetchall()}
    columns = {
        "success_count": "INTEGER DEFAULT 0",
        "failed_count": "INTEGER DEFAULT 0",
        "stock_pool_source": "TEXT",
        "stock_pool_error": "TEXT",
        "retry_mode": "TEXT DEFAULT 'full'",
        "data_fresh_policy": "TEXT DEFAULT 'force_refresh'",
        "latest_trade_date": "TEXT",
        "strategy_type": "TEXT DEFAULT 'STRATEGY_1_CUP_HANDLE'",
    }
    for name, typ in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE scan_tasks ADD COLUMN {name} {typ}")
    # Ensure strategy2 index exists
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scan_tasks_strategy_started "
        "ON scan_tasks(strategy_type, started_at DESC)"
    )



def _ensure_task_stocks_table(conn: sqlite3.Connection):
    """Create per-task stock tracking table used by scan progress and retries."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS task_stocks (
            task_id TEXT NOT NULL,
            idx INTEGER NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            market TEXT,
            status TEXT DEFAULT 'pending',
            status_reason TEXT,
            error_detail TEXT,
            primary_source TEXT,
            fallback_source TEXT,
            primary_attempts INTEGER DEFAULT 0,
            fallback_attempts INTEGER DEFAULT 0,
            primary_error TEXT,
            fallback_error TEXT,
            source_errors TEXT,
            kline_latest_date TEXT,
            quote_status TEXT DEFAULT 'not_requested',
            quote_error TEXT,
            kline_fetched_at TEXT,
            kline_target_trade_date TEXT,
            started_at TEXT,
            finished_at TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (task_id, code),
            FOREIGN KEY (task_id) REFERENCES scan_tasks(id)
        )
    ''')
    existing = {d[1] for d in conn.execute("PRAGMA table_info(task_stocks)").fetchall()}
    columns = {
        "market": "TEXT",
        "status": "TEXT DEFAULT 'pending'",
        "status_reason": "TEXT",
        "error_detail": "TEXT",
        "primary_source": "TEXT",
        "fallback_source": "TEXT",
        "primary_attempts": "INTEGER DEFAULT 0",
        "fallback_attempts": "INTEGER DEFAULT 0",
        "primary_error": "TEXT",
        "fallback_error": "TEXT",
        "source_errors": "TEXT",
        "kline_latest_date": "TEXT",
        "quote_status": "TEXT DEFAULT 'not_requested'",
        "quote_error": "TEXT",
        "kline_fetched_at": "TEXT",
        "kline_target_trade_date": "TEXT",
        "started_at": "TEXT",
        "finished_at": "TEXT",
        "updated_at": "TEXT",
    }
    for name, typ in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE task_stocks ADD COLUMN {name} {typ}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_stocks_task_status ON task_stocks(task_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_stocks_task_idx ON task_stocks(task_id, idx)")



def _dedupe_candidates_before_unique_index(conn: sqlite3.Connection):
    """Keep the newest row for each task/code before adding a unique index."""
    conn.execute('''
        DELETE FROM candidates
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM candidates
            GROUP BY task_id, code
        )
    ''')


def get_conn() -> sqlite3.Connection:
    """Get thread-local database connection."""
    if DB_PATH is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    if not hasattr(_local, 'conn') or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.execute("PRAGMA journal_mode=WAL")
    return _local.conn


# ====== Stock Pool ======

def save_stock_pool(stocks: list[dict]):
    """Replace stock pool table with new data."""
    conn = get_conn()
    conn.execute("DELETE FROM stock_pool")
    conn.executemany(
        "INSERT INTO stock_pool (code, name, market) VALUES (?, ?, ?)",
        [(s["code"], s["name"], s.get("market", "")) for s in stocks]
    )
    conn.commit()


def get_stock_pool() -> list[dict]:
    """Get all stocks from pool."""
    conn = get_conn()
    rows = conn.execute("SELECT code, name, market FROM stock_pool").fetchall()
    return [{"code": r[0], "name": r[1], "market": r[2]} for r in rows]


def get_stock_pool_count() -> int:
    conn = get_conn()
    return conn.execute("SELECT COUNT(*) FROM stock_pool").fetchone()[0]


# ====== Daily OHLC Cache ======

def save_ohlc(code: str, data: list[dict]):
    """Insert or replace OHLC data for a stock."""
    conn = get_conn()
    conn.execute("DELETE FROM daily_ohlc WHERE code = ?", (code,))
    conn.executemany(
        """INSERT INTO daily_ohlc (code, date, open, high, low, close, volume, turnover)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [(code, d["date"], d.get("open"), d.get("high"), d.get("low"),
          d.get("close"), d.get("volume"), d.get("turnover")) for d in data]
    )
    conn.commit()


def get_ohlc(code: str, max_rows: int = 0) -> list[dict] | None:
    """Get cached OHLC data for a stock, sorted by date.

    Args:
        max_rows: if > 0, return only the most recent N rows.
    """
    conn = get_conn()
    query = "SELECT date, open, high, low, close, volume, turnover FROM daily_ohlc WHERE code = ? ORDER BY date"
    rows = conn.execute(query, (code,)).fetchall()
    if not rows:
        return None
    if max_rows and len(rows) > max_rows:
        rows = rows[-max_rows:]
    return [
        {"date": r[0], "open": r[1], "high": r[2], "low": r[3],
         "close": r[4], "volume": r[5], "turnover": r[6]}
        for r in rows
    ]


# ====== Market Index OHLC Cache ======

def save_market_index_ohlc(
    symbol: str,
    data: list[dict],
    *,
    source: str = "sina",
    fetched_at: str | None = None,
):
    """Insert or replace cached OHLC rows for a market index."""
    conn = get_conn()
    fetched_at = fetched_at or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("DELETE FROM market_index_ohlc WHERE symbol = ?", (symbol,))
    conn.executemany(
        """INSERT INTO market_index_ohlc
           (symbol, date, open, high, low, close, volume, turnover, source, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                symbol,
                d["date"],
                d.get("open"),
                d.get("high"),
                d.get("low"),
                d.get("close"),
                d.get("volume"),
                d.get("turnover", 0.0),
                source,
                fetched_at,
            )
            for d in data
        ],
    )
    conn.commit()


def upsert_market_index_ohlc(
    symbol: str,
    data: list[dict],
    *,
    source: str = "sina",
    fetched_at: str | None = None,
):
    """Merge index OHLC rows without deleting older cached history."""
    if not data:
        return
    conn = get_conn()
    fetched_at = fetched_at or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.executemany(
        """INSERT INTO market_index_ohlc
           (symbol, date, open, high, low, close, volume, turnover, source, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(symbol, date) DO UPDATE SET
             open=excluded.open,
             high=excluded.high,
             low=excluded.low,
             close=excluded.close,
             volume=excluded.volume,
             turnover=excluded.turnover,
             source=excluded.source,
             fetched_at=excluded.fetched_at""",
        [
            (
                symbol,
                d["date"],
                d.get("open"),
                d.get("high"),
                d.get("low"),
                d.get("close"),
                d.get("volume"),
                d.get("turnover", 0.0),
                source,
                fetched_at,
            )
            for d in data
        ],
    )
    conn.commit()


def get_market_index_ohlc(
    symbol: str,
    *,
    end_date: str | None = None,
    max_rows: int = 0,
) -> list[dict]:
    """Get cached market index OHLC rows sorted by date."""
    conn = get_conn()
    params: list = [symbol]
    query = (
        "SELECT date, open, high, low, close, volume, turnover "
        "FROM market_index_ohlc WHERE symbol=?"
    )
    if end_date:
        query += " AND date<=?"
        params.append(end_date[:10])
    query += " ORDER BY date"
    rows = conn.execute(query, params).fetchall()
    if max_rows and len(rows) > max_rows:
        rows = rows[-max_rows:]
    return [
        {
            "date": r[0],
            "open": r[1],
            "high": r[2],
            "low": r[3],
            "close": r[4],
            "volume": r[5],
            "turnover": r[6],
        }
        for r in rows
    ]


def get_market_index_coverage(symbol: str) -> dict:
    """Return row count and date coverage for a cached market index."""
    conn = get_conn()
    row = conn.execute(
        """SELECT COUNT(*), MIN(date), MAX(date), MAX(source), MAX(fetched_at)
           FROM market_index_ohlc WHERE symbol=?""",
        (symbol,),
    ).fetchone()
    return {
        "symbol": symbol,
        "rows": row[0] or 0,
        "min_date": row[1],
        "max_date": row[2],
        "source": row[3],
        "fetched_at": row[4],
    }


def get_ohlc_latest_date(code: str) -> str | None:
    """Get the latest date in cached OHLC data."""
    conn = get_conn()
    row = conn.execute(
        "SELECT MAX(date) FROM daily_ohlc WHERE code = ?", (code,)
    ).fetchone()
    return row[0] if row else None


def get_ohlc_history_page(
    code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Return a paginated slice of cached OHLC history, newest rows first."""
    page = max(1, int(page or 1))
    page_size = min(200, max(1, int(page_size or 50)))
    offset = (page - 1) * page_size

    clauses = ["code = ?"]
    params: list = [code]
    if start_date:
        clauses.append("date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("date <= ?")
        params.append(end_date)
    where = " AND ".join(clauses)

    conn = get_conn()
    total = conn.execute(
        f"SELECT COUNT(*) FROM daily_ohlc WHERE {where}",
        params,
    ).fetchone()[0]
    rows = conn.execute(
        f"""SELECT date, open, high, low, close, volume, turnover
            FROM daily_ohlc
            WHERE {where}
            ORDER BY date DESC
            LIMIT ? OFFSET ?""",
        [*params, page_size, offset],
    ).fetchall()
    return {
        "rows": [
            {
                "date": r[0],
                "open": r[1],
                "high": r[2],
                "low": r[3],
                "close": r[4],
                "volume": r[5],
                "turnover": r[6],
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_latest_task_stock_kline_metadata(code: str) -> dict | None:
    """Return the newest scan task K-line metadata for one stock."""
    conn = get_conn()
    row = conn.execute(
        """SELECT kline_latest_date, kline_fetched_at,
                  kline_target_trade_date, quote_status
           FROM task_stocks
           WHERE code = ?
             AND (kline_latest_date IS NOT NULL OR kline_fetched_at IS NOT NULL)
           ORDER BY kline_fetched_at DESC, updated_at DESC
           LIMIT 1""",
        (code,),
    ).fetchone()
    if not row:
        return None
    return {
        "kline_latest_date": row[0],
        "kline_fetched_at": row[1],
        "kline_target_trade_date": row[2],
        "quote_status": row[3] or "not_requested",
    }


def get_reusable_task_stock_kline_context(
    code: str,
    target_trade_date: str,
    min_fetch_time: str | None,
    exclude_task_id: str | None = None,
) -> dict | None:
    """Return prior task K-line freshness metadata reusable for a new scan.

    Freshness is tied to the latest completed trade date, not calendar today.
    Suspended/no-trade rows may have latest K-line before target_trade_date,
    but only when a prior scan fetched after the target close time.
    """
    conn = get_conn()
    params: list = [code, target_trade_date]
    min_fetch_clause = ""
    if min_fetch_time:
        min_fetch_clause = "AND ts.kline_fetched_at >= ?"
        params.append(min_fetch_time)
    params.append(target_trade_date)
    exclude_clause = ""
    if exclude_task_id:
        exclude_clause = "AND ts.task_id != ?"
        params.append(exclude_task_id)
    rows = conn.execute(
        f"""SELECT ts.kline_latest_date, ts.kline_fetched_at,
                  ts.kline_target_trade_date, ts.quote_status,
                  ts.source_errors
            FROM task_stocks ts
            WHERE ts.code = ?
              AND ts.kline_target_trade_date = ?
              AND ts.kline_fetched_at IS NOT NULL
              {min_fetch_clause}
              AND ts.kline_latest_date IS NOT NULL
              AND ts.status IN ('scanned', 'skipped', 'candidate')
              AND (
                    ts.kline_latest_date >= ?
                    OR ts.quote_status IN ('suspended', 'no_trade')
                  )
              {exclude_clause}
            ORDER BY ts.kline_fetched_at DESC, ts.updated_at DESC
            LIMIT 20""",
        params,
    ).fetchall()
    for row in rows:
        latest_date = row[0]
        quote_status = row[3] or "not_requested"
        if latest_date >= target_trade_date or (
            quote_status in {"suspended", "no_trade"}
            and _source_errors_confirm_no_trade(row[4])
        ):
            return {
                "kline_latest_date": latest_date,
                "kline_fetched_at": row[1],
                "kline_target_trade_date": row[2],
                "quote_status": quote_status,
            }
    return None


def _source_errors_confirm_no_trade(source_errors: str | None) -> bool:
    if not source_errors:
        return False
    try:
        parsed = json.loads(source_errors)
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(parsed, dict) or not parsed:
        return False
    return all(_source_error_confirms_no_trade(error) for error in parsed.values())


def _source_error_confirms_no_trade(error: str | None) -> bool:
    if not isinstance(error, str):
        return False
    return (
        "missing target trade date" in error
        or "zero-volume target trade date" in error
    )


def get_today_task_stock_latest_date(code: str, today: str, exclude_task_id: str | None = None) -> str | None:
    """Return this stock's latest K-line date recorded by a task started today."""
    conn = get_conn()
    params: list = [code, f"{today}%"]
    exclude_clause = ""
    if exclude_task_id:
        exclude_clause = "AND ts.task_id != ?"
        params.append(exclude_task_id)
    row = conn.execute(
        f"""SELECT ts.kline_latest_date
            FROM task_stocks ts
            JOIN scan_tasks st ON st.id = ts.task_id
            WHERE ts.code = ?
              AND st.started_at LIKE ?
              AND ts.kline_latest_date IS NOT NULL
              AND ts.status IN ('scanned', 'skipped', 'candidate')
              {exclude_clause}
            ORDER BY st.started_at DESC, ts.updated_at DESC
            LIMIT 1""",
        params,
    ).fetchone()
    return row[0] if row else None


# ====== Scan Tasks ======

def create_scan_task(task_id: str, started_at: str, total_stocks: int = 0,
                     stock_pool_source: str = None, stock_pool_error: str = None,
                     retry_mode: str = "full",
                     strategy_type: str = "STRATEGY_1_CUP_HANDLE") -> int:
    """Insert a new scan task. Returns row id."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO scan_tasks
           (id, started_at, status, total_stocks, stock_pool_source,
            stock_pool_error, retry_mode, data_fresh_policy, strategy_type)
           VALUES (?, ?, 'running', ?, ?, ?, ?, 'force_refresh', ?)""",
        (task_id, started_at, total_stocks, stock_pool_source, stock_pool_error, retry_mode, strategy_type),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_scan_progress(task_id: str, scanned: int, skipped: int = 0, candidates_count: int = 0):
    """Update scan progress in real-time."""
    conn = get_conn()
    conn.execute(
        "UPDATE scan_tasks SET scanned=?, skipped=?, candidates_count=? WHERE id=?",
        (scanned, skipped, candidates_count, task_id)
    )
    conn.commit()


def update_scan_task_total(task_id: str, total: int, source: str = ""):
    """Update the total stock count and source after pool is ready."""
    conn = get_conn()
    conn.execute(
        "UPDATE scan_tasks SET total_stocks=?, stock_pool_source=? WHERE id=?",
        (total, source, task_id),
    )
    conn.commit()


def finish_scan_task(task_id: str, finished_at: str, candidates_count: int,
                     elapsed_seconds: float, scanned: int = 0, skipped: int = 0):
    """Mark scan task as completed."""
    conn = get_conn()
    conn.execute(
        """UPDATE scan_tasks
           SET status='completed', finished_at=?, candidates_count=?,
               elapsed_seconds=?, scanned=?, skipped=?, error=NULL
           WHERE id=?""",
        (finished_at, candidates_count, elapsed_seconds, scanned, skipped, task_id)
    )
    conn.commit()


def mark_dead_tasks_as_failed():
    """Mark any running tasks as failed — they were interrupted by server restart.
    Also reset fetching stocks to pending so auto-resume can re-process them.
    Also handle crashed tasks (failed without finished_at) by resetting their
    fetching stocks so they can be picked up by get_interrupted_task()."""
    conn = get_conn()
    running_ids = conn.execute(
        "SELECT id FROM scan_tasks WHERE status='running'"
    ).fetchall()
    for (task_id,) in running_ids:
        conn.execute(
            "UPDATE task_stocks SET status='pending', status_reason=NULL, error_detail=NULL "
            "WHERE task_id=? AND status='fetching'",
            (task_id,),
        )
    conn.execute(
        "UPDATE scan_tasks SET status='failed', error='Interrupted by current server startup' WHERE status='running'"
    )
    # Also reset fetching stocks for crashed tasks (status=failed but never finished)
    crashed = conn.execute(
        "SELECT id FROM scan_tasks WHERE status='failed' AND finished_at IS NULL"
    ).fetchall()
    for (task_id,) in crashed:
        conn.execute(
            "UPDATE task_stocks SET status='pending', status_reason=NULL, error_detail=NULL "
            "WHERE task_id=? AND status='fetching'",
            (task_id,),
        )
    conn.commit()
    conn.commit()


def get_interrupted_task() -> dict | None:
    """Get the most recent interrupted task for resume.

    Returns any task that didn't finish all stocks (scanned < total_stocks)
    regardless of the specific error string.  This covers:
    - Server restart (mark_dead_tasks_as_failed)
    - User stop (cancelled)
    - Code bugs caught by the scan thread
    - Unexpected process termination

    Returns dict with id, scanned, total_stocks, strategy_type.
    NULL strategy_type → STRATEGY_1_CUP_HANDLE.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT id, scanned, total_stocks, strategy_type FROM scan_tasks "
        "WHERE (status='failed' OR status='cancelled') "
        "  AND finished_at IS NULL "
        "ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if not row or row[1] >= row[2]:
        return None
    return {
        "id": row[0], "scanned": row[1], "total_stocks": row[2],
        "strategy_type": row[3] or "STRATEGY_1_CUP_HANDLE",
    }


def save_task_stocks(task_id: str, stocks: list[dict]):
    """Save the complete stock list for a scan task."""
    conn = get_conn()
    conn.execute("DELETE FROM task_stocks WHERE task_id = ?", (task_id,))
    conn.executemany(
        """INSERT INTO task_stocks (task_id, idx, code, name, market, status)
           VALUES (?, ?, ?, ?, ?, 'pending')""",
        [(task_id, i, s["code"], s.get("name", ""), s.get("market", "")) for i, s in enumerate(stocks)]
    )
    conn.execute("UPDATE scan_tasks SET total_stocks=? WHERE id=?", (len(stocks), task_id))
    conn.commit()


def update_task_stock(task_id: str, code: str, **fields):
    """Update fields for one task stock row."""
    allowed = {
        "status", "status_reason", "error_detail", "primary_source", "fallback_source",
        "primary_attempts", "fallback_attempts", "primary_error", "fallback_error",
        "kline_latest_date", "quote_status", "quote_error", "started_at", "finished_at",
        "source_errors", "kline_fetched_at", "kline_target_trade_date",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    assignments = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [task_id, code]
    conn = get_conn()
    conn.execute(f"UPDATE task_stocks SET {assignments} WHERE task_id=? AND code=?", values)
    conn.commit()


def get_task_stocks(task_id: str, status: str = None, limit: int = 100, offset: int = 0) -> list[dict]:
    """Return tracked stocks for a task, optionally filtered by status."""
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM task_stocks WHERE task_id=? AND status=? ORDER BY idx LIMIT ? OFFSET ?",
            (task_id, status, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM task_stocks WHERE task_id=? ORDER BY idx LIMIT ? OFFSET ?",
            (task_id, limit, offset),
        ).fetchall()
    columns = [d[1] for d in conn.execute("PRAGMA table_info(task_stocks)").fetchall()]
    return [dict(zip(columns, row)) for row in rows]


def get_pending_stocks(task_id: str, from_idx: int = 0) -> list[dict]:
    """Get unfinished stocks for a resumed task.

    Resume must not trust scan_tasks.scanned as an idx offset: multi-threaded scans
    and source-busy requeues can leave low-idx rows unfinished while later rows are
    already processed.
    """
    conn = get_conn()
    rows = conn.execute(
        """SELECT code, name, market FROM task_stocks
           WHERE task_id=? AND status IN ('pending', 'fetching')
           ORDER BY idx""",
        (task_id,),
    ).fetchall()
    return [{"code": r[0], "name": r[1], "market": r[2]} for r in rows]


def get_failed_task_stocks(task_id: str) -> list[dict]:
    """Return failed stocks for retry."""
    return get_task_stocks(task_id, status="failed", limit=100000, offset=0)


def reset_failed_task_stocks(task_id: str):
    """Move failed stocks back to pending before a retry run."""
    conn = get_conn()
    conn.execute(
        """UPDATE task_stocks
           SET status='pending', status_reason=NULL, error_detail=NULL,
               primary_attempts=0, fallback_attempts=0,
               primary_error=NULL, fallback_error=NULL,
               quote_status='not_requested', quote_error=NULL,
               updated_at=datetime('now')
           WHERE task_id=? AND status='failed'""",
        (task_id,),
    )
    conn.commit()


def summarize_task_stocks(task_id: str) -> dict:
    """Count task stocks by status."""
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM task_stocks WHERE task_id=?", (task_id,)).fetchone()[0]
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM task_stocks WHERE task_id=? GROUP BY status",
        (task_id,),
    ).fetchall()
    counts = {r[0]: r[1] for r in rows}
    return {
        "total_stocks": total,
        "pending": counts.get("pending", 0),
        "fetching": counts.get("fetching", 0),
        "scanned": counts.get("scanned", 0),
        "skipped": counts.get("skipped", 0),
        "failed": counts.get("failed", 0),
        "candidate": counts.get("candidate", 0),
    }


def refresh_scan_task_counts(task_id: str) -> dict:
    """Persist scan task aggregate counts from task_stocks."""
    s = summarize_task_stocks(task_id)
    processed = s["scanned"] + s["skipped"] + s["failed"] + s["candidate"]
    candidates_count = s["candidate"]
    latest_row = get_conn().execute(
        "SELECT MAX(kline_latest_date) FROM task_stocks WHERE task_id=?",
        (task_id,),
    ).fetchone()
    latest_trade_date = latest_row[0] if latest_row else None
    conn = get_conn()
    conn.execute(
        """UPDATE scan_tasks
           SET total_stocks=?, scanned=?, skipped=?, failed_count=?,
               success_count=?, candidates_count=?, latest_trade_date=?
           WHERE id=?""",
        (
            s["total_stocks"], processed, s["skipped"], s["failed"],
            s["scanned"] + s["candidate"], candidates_count, latest_trade_date, task_id,
        ),
    )
    conn.commit()
    stock_pool_source = get_conn().execute(
        "SELECT stock_pool_source FROM scan_tasks WHERE id=?", (task_id,)
    ).fetchone()
    return {
        **s,
        "processed": processed,
        "success_count": s["scanned"] + s["candidate"],
        "failed_count": s["failed"],
        "candidates_count": candidates_count,
        "latest_trade_date": latest_trade_date,
        "stock_pool_source": stock_pool_source[0] if stock_pool_source else "",
    }


def get_scan_task(task_id: str) -> dict | None:
    """Get a single scan task by ID (RECHECK-S2-003)."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, started_at, finished_at, status, total_stocks, scanned, skipped, "
        "candidates_count, elapsed_seconds, failed_count, stock_pool_source, "
        "latest_trade_date, strategy_type "
        "FROM scan_tasks WHERE id=?",
        (task_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0], "date": row[1] or "", "finished_at": row[2],
        "running": row[3] == 'running', "status": row[3],
        "total_stocks": row[4], "scanned": row[5], "total": row[4],
        "skipped": row[6], "candidates": row[7], "elapsed_seconds": row[8],
        "duration": f"{row[8]:.0f}s" if row[8] is not None else None,
        "failed": row[9], "stock_pool_source": row[10], "latest_trade_date": row[11],
        "strategy_type": row[12] or "STRATEGY_1_CUP_HANDLE",
    }


def get_task_strategy_type(task_id: str) -> str | None:
    """Return the strategy_type for a task, or None if not found (RECHECK-S2-003)."""
    conn = get_conn()
    row = conn.execute(
        "SELECT strategy_type FROM scan_tasks WHERE id=?", (task_id,),
    ).fetchone()
    if not row:
        return None
    return row[0] or "STRATEGY_1_CUP_HANDLE"


def get_scan_tasks(strategy_type: str = None) -> list[dict]:
    """Get scan tasks, optionally filtered by strategy_type (RECHECK-S2-003)."""
    conn = get_conn()
    if strategy_type:
        rows = conn.execute(
            """SELECT id, started_at, finished_at, status, total_stocks, scanned, skipped,
                      candidates_count, elapsed_seconds, failed_count, stock_pool_source,
                      latest_trade_date, strategy_type
               FROM scan_tasks WHERE (strategy_type=? OR (strategy_type IS NULL AND ?='STRATEGY_1_CUP_HANDLE'))
               ORDER BY started_at DESC""",
            (strategy_type, strategy_type),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, started_at, finished_at, status, total_stocks, scanned, skipped,
                      candidates_count, elapsed_seconds, failed_count, stock_pool_source,
                      latest_trade_date, strategy_type
               FROM scan_tasks ORDER BY started_at DESC"""
        ).fetchall()
    return [
        {"id": r[0], "date": r[1] or "", "finished_at": r[2],
         "running": r[3] == 'running', "status": r[3], "scope": f"全市场 · {r[4]}只",
         "total_stocks": r[4], "scanned": r[5], "total": r[4],
         "skipped": r[6], "candidates": r[7], "elapsed_seconds": r[8],
         "duration": f"{r[8]:.0f}s" if r[8] is not None else None,
         "failed": r[9], "stock_pool_source": r[10], "latest_trade_date": r[11],
         "strategy_type": r[12] or "STRATEGY_1_CUP_HANDLE"}
        for r in rows
    ]


def get_running_task_id() -> str | None:
    """Get the ID of the currently running scan task, if any."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM scan_tasks WHERE status='running' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def get_running_task() -> dict | None:
    """Get the currently running scan task with strategy type, if any."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, strategy_type FROM scan_tasks WHERE status='running' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return {"id": row[0], "strategy_type": row[1] or "STRATEGY_1_CUP_HANDLE"}


# ====== Candidates ======

def _json_list(value):
    """Encode a list as JSON string for TEXT column storage, or return empty string."""
    if not value:
        return ""
    import json
    return json.dumps(list(value), ensure_ascii=False)


def delete_candidates(task_id: str):
    """Delete all candidates for a task (so re-evaluate can replace them)."""
    conn = get_conn()
    conn.execute("DELETE FROM candidates WHERE task_id=?", (task_id,))
    conn.commit()


def upsert_candidate(task_id: str, d: dict):
    """Insert or update a single candidate (for real-time discovery)."""
    conn = get_conn()
    rating = "强候选" if d["score"] >= 80 else "中等候选" if d["score"] >= 70 else "弱候选"
    columns = [
        "task_id", "code", "name", "score", "rating",
        "is_breakout", "is_volume_breakout", "breakout_price", "vol_multiplier",
        "cup_depth_pct", "cup_duration", "handle_depth_pct", "handle_duration",
        "lip_deviation_pct", "left_high_price", "cup_low_price", "right_high_price",
        "handle_low_price", "left_high_date", "cup_low_date", "right_high_date",
        "handle_low_date", "latest_close", "latest_turnover",
        "dry_stable_verdict", "dry_stable_summary",
        "volume_dry_score", "price_stable_score", "pattern_score_20",
        "cup_handle_score", "vcp_score", "vcp_contractions",
        "pattern_type", "key_pattern_type",
        "risk_percent", "rr1", "position_advice",
        "entry_zone_low", "entry_zone_high", "pivot", "stop_loss", "target_1", "target_2",
        "market_status", "market_position_advice",
        "verdict_key", "positive_factors", "warnings", "reject_reasons",
        "raw_volume_dry_score", "raw_price_stable_score", "score_caps",
    ]
    values = (
        task_id, d["code"], d["name"], d["score"], rating,
        d.get("is_breakout", 0), d.get("is_volume_breakout", 0),
        d.get("breakout_price", 0), d.get("vol_multiplier", 0),
        d.get("cup_depth_pct", 0), d.get("cup_duration", 0),
        d.get("handle_depth_pct", 0), d.get("handle_duration", 0),
        d.get("lip_deviation_pct", 0), d.get("left_high_price", 0),
        d.get("cup_low_price", 0), d.get("right_high_price", 0),
        d.get("handle_low_price", 0),
        d.get("left_high_date", ""), d.get("cup_low_date", ""),
        d.get("right_high_date", ""), d.get("handle_low_date", ""),
        d.get("latest_close", 0),
        0,
        d.get("dry_stable_verdict", ""),
        d.get("dry_stable_summary", ""),
        d.get("volume_dry_score", 0),
        d.get("price_stable_score", 0),
        d.get("pattern_score_20", 0),
        d.get("cup_handle_score", 0),
        d.get("vcp_score", 0),
        d.get("vcp_contractions", 0),
        d.get("pattern_type", ""),
        d.get("key_pattern_type", ""),
        d.get("risk_percent", 0),
        d.get("rr1", 0),
        d.get("position_advice", ""),
        d.get("entry_zone_low", 0),
        d.get("entry_zone_high", 0),
        d.get("pivot", 0),
        d.get("stop_loss", 0),
        d.get("target_1", 0),
        d.get("target_2", 0),
        d.get("market_status", ""),
        d.get("market_position_advice", ""),
        d.get("verdict_key", ""),
        _json_list(d.get("positive_factors")),
        _json_list(d.get("warnings")),
        _json_list(d.get("reject_reasons")),
        d.get("raw_volume_dry_score", 0),
        d.get("raw_price_stable_score", 0),
        _json_list(d.get("score_caps")),
    )
    value_marks = ", ".join("?" for _ in columns)
    update_assignments = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("task_id", "code"))
    conn.execute(
        f"""INSERT INTO candidates ({', '.join(columns)}) VALUES ({value_marks})
            ON CONFLICT(task_id, code) DO UPDATE SET {update_assignments}""",
        values,
    )
    conn.commit()


def save_candidates(task_id: str, candidates: list, strong: int = 80, medium: int = 70):
    """Save candidate results for a scan task.

    Args:
        task_id: scan task id
        candidates: list of (stock_dict, CupHandleResult) tuples
        strong: threshold for 强候选 (default 80)
        medium: threshold for 中等候选 (default 70)
    """
    conn = get_conn()
    rows = []
    for stock, r in candidates:
        rating = "强候选" if r.score >= strong else "中等候选" if r.score >= medium else "弱候选"
        dry = stock.get("dry_stable", {})
        decision = dry.get("decision", {})
        volume_dry = dry.get("volume_dry", {})
        price_stable = dry.get("price_stable", {})
        pattern = dry.get("pattern_score", {})
        rr = dry.get("risk_reward", {})
        key = dry.get("key_prices", {})
        market = dry.get("market_environment", {})
        rows.append((
            task_id, r.code, r.name, r.score, rating,
            1 if r.is_breakout else 0,
            1 if r.is_volume_breakout else 0,
            r.breakout_price, r.vol_multiplier,
            r.cup_depth_pct, r.cup_duration,
            r.handle_depth_pct, r.handle_duration,
            r.lip_deviation_pct,
            r.left_high_price, r.cup_low_price,
            r.right_high_price, r.handle_low_price,
            r.left_high_date, r.cup_low_date,
            r.right_high_date, r.handle_low_date,
            stock.get("latest_close", 0),
            stock.get("latest_turnover", 0),
            decision.get("verdict", ""),
            decision.get("summary", ""),
            volume_dry.get("score", 0),
            price_stable.get("score", 0),
            pattern.get("score", 0),
            pattern.get("cup_handle_score", 0),
            pattern.get("vcp_score", 0),
            pattern.get("vcp_contractions", 0),
            pattern.get("type", ""),
            pattern.get("key_pattern_type", ""),
            rr.get("risk_percent", 0),
            rr.get("rr1", 0),
            rr.get("position_advice", ""),
            key.get("entry_zone_low", 0),
            key.get("entry_zone_high", 0),
            key.get("pivot", 0),
            key.get("stop_loss", 0),
            key.get("target_1", 0),
            key.get("target_2", 0),
            market.get("status", ""),
            market.get("position_advice", ""),
            decision.get("verdict_key", ""),
            _json_list(decision.get("positive_factors")),
            _json_list(decision.get("warnings")),
            _json_list(decision.get("reject_reasons")),
            volume_dry.get("raw_score", 0),
            price_stable.get("raw_score", 0),
            _json_list(volume_dry.get("caps", []) + price_stable.get("caps", [])),
        ))
    columns = [
        "task_id", "code", "name", "score", "rating",
        "is_breakout", "is_volume_breakout", "breakout_price", "vol_multiplier",
        "cup_depth_pct", "cup_duration", "handle_depth_pct", "handle_duration",
        "lip_deviation_pct", "left_high_price", "cup_low_price", "right_high_price",
        "handle_low_price", "left_high_date", "cup_low_date", "right_high_date",
        "handle_low_date", "latest_close", "latest_turnover",
        "dry_stable_verdict", "dry_stable_summary",
        "volume_dry_score", "price_stable_score", "pattern_score_20",
        "cup_handle_score", "vcp_score", "vcp_contractions",
        "pattern_type", "key_pattern_type",
        "risk_percent", "rr1", "position_advice",
        "entry_zone_low", "entry_zone_high", "pivot", "stop_loss", "target_1", "target_2",
        "market_status", "market_position_advice",
        "verdict_key", "positive_factors", "warnings", "reject_reasons",
        "raw_volume_dry_score", "raw_price_stable_score", "score_caps",
    ]
    value_marks = ", ".join("?" for _ in columns)
    update_assignments = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("task_id", "code"))
    conn.executemany(
        f"""INSERT INTO candidates ({', '.join(columns)}) VALUES ({value_marks})
            ON CONFLICT(task_id, code) DO UPDATE SET {update_assignments}""",
        rows,
    )
    conn.commit()


def get_candidates(task_id: str = None) -> list[dict]:
    """Get candidates, optionally filtered by task_id. Latest task if not specified."""
    conn = get_conn()
    if task_id:
        rows = conn.execute(
            "SELECT * FROM candidates WHERE task_id = ? ORDER BY score DESC", (task_id,)
        ).fetchall()
    else:
        # Get latest completed STRATEGY1 task's candidates (BUG-S2-007)
        latest = conn.execute(
            "SELECT id FROM scan_tasks WHERE status='completed' "
            "AND (strategy_type IS NULL OR strategy_type='STRATEGY_1_CUP_HANDLE') "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not latest:
            return []
        rows = conn.execute(
            "SELECT * FROM candidates WHERE task_id = ? ORDER BY score DESC", (latest[0],)
        ).fetchall()

    col_names = [d[1] for d in conn.execute("PRAGMA table_info(candidates)").fetchall()]
    return [dict(zip(col_names, r)) for r in rows]


def get_candidate(code: str, task_id: str = None) -> dict | None:
    """Get single candidate detail."""
    conn = get_conn()
    if task_id:
        row = conn.execute(
            "SELECT * FROM candidates WHERE code = ? AND task_id = ?", (code, task_id)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM candidates WHERE code = ? ORDER BY id DESC LIMIT 1", (code,)
        ).fetchone()
    if not row:
        return None
    col_names = [d[1] for d in conn.execute("PRAGMA table_info(candidates)").fetchall()]
    return dict(zip(col_names, row))


# ====== Strategy2 Candidates ======

def _ensure_strategy2_candidates_table(conn: sqlite3.Connection):
    """Create strategy2_candidates table if not exists (compatible migration)."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy2_candidates (
            id                         INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id                    TEXT NOT NULL,
            code                       TEXT NOT NULL,
            name                       TEXT NOT NULL,
            evaluation_date            TEXT NOT NULL,
            total_score                INTEGER NOT NULL,
            level                      TEXT NOT NULL,
            volume_dry_score           INTEGER NOT NULL,
            price_stable_score         INTEGER NOT NULL,
            current_close              REAL NOT NULL,
            v3                         REAL,
            v5                         REAL,
            v10                        REAL,
            v20                        REAL,
            volume_ratio_5_20          REAL,
            volume_percentile          REAL,
            volume_percentile_days     INTEGER,
            range_5                    REAL,
            close_range_5              REAL,
            return_3                   REAL,
            return_5                   REAL,
            key_support                REAL NOT NULL,
            buy_zone_low               REAL NOT NULL,
            buy_zone_high              REAL NOT NULL,
            stop_loss                  REAL NOT NULL,
            risk_ratio                 REAL NOT NULL,
            risk_level                 TEXT NOT NULL,
            score_reasons              TEXT,
            reject_reasons             TEXT,
            data_source                TEXT,
            created_at                 TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (task_id) REFERENCES scan_tasks(id),
            UNIQUE (task_id, code)
        )
    ''')
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy2_candidates_task_score "
        "ON strategy2_candidates(task_id, total_score DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy2_candidates_task_risk "
        "ON strategy2_candidates(task_id, risk_ratio ASC)"
    )
    # 趋势字段兼容式迁移（V2 价格路径+120日长期确认）
    _ensure_column(conn, "strategy2_candidates", "trend_type", "TEXT")
    _ensure_column(conn, "strategy2_candidates", "short_mid_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_candidates", "long_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_candidates", "total_evidence_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_candidates", "necessary_conditions_met", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_candidates", "ma20", "REAL")
    _ensure_column(conn, "strategy2_candidates", "ma60", "REAL")
    _ensure_column(conn, "strategy2_candidates", "ma120", "REAL")
    _ensure_column(conn, "strategy2_candidates", "ma20_slope", "REAL")
    _ensure_column(conn, "strategy2_candidates", "ma60_slope", "REAL")
    _ensure_column(conn, "strategy2_candidates", "drawdown_from_high_60", "REAL")
    _ensure_column(conn, "strategy2_candidates", "center_shift_20", "REAL")
    _ensure_column(conn, "strategy2_candidates", "price_position_60", "REAL")
    _ensure_column(conn, "strategy2_candidates", "linear_trend_60", "REAL")
    _ensure_column(conn, "strategy2_candidates", "drawdown_from_high_120", "REAL")
    _ensure_column(conn, "strategy2_candidates", "center_shift_40", "REAL")
    _ensure_column(conn, "strategy2_candidates", "return_20", "REAL")
    _ensure_column(conn, "strategy2_candidates", "return_60", "REAL")
    _ensure_column(conn, "strategy2_candidates", "downtrend_conditions", "TEXT")
    _ensure_column(conn, "strategy2_candidates", "short_term_time_exit_days", "INTEGER DEFAULT 0")


def _ensure_strategy3_candidates_table(conn: sqlite3.Connection):
    """Create strategy3_candidates table if not exists (compatible migration)."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy3_candidates (
            id                         INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id                    TEXT NOT NULL,
            code                       TEXT NOT NULL,
            name                       TEXT NOT NULL,
            evaluation_date            TEXT NOT NULL,
            total_score                INTEGER NOT NULL,
            level                      TEXT NOT NULL,
            trend_score                INTEGER DEFAULT 0,
            pullback_score             INTEGER DEFAULT 0,
            volume_stability_score     INTEGER DEFAULT 0,
            second_breakout_score      INTEGER DEFAULT 0,
            risk_reward_score          INTEGER DEFAULT 0,
            current_close              REAL DEFAULT 0,
            ma5                        REAL,
            ma10                       REAL,
            ma20                       REAL,
            ma60                       REAL,
            ma120                      REAL,
            recent_high                REAL,
            pullback_pct               REAL,
            relative_strength_60       REAL,
            volume_ratio_5_20          REAL,
            range_5                    REAL,
            range_10                   REAL,
            range_20                   REAL,
            range_compression_ok       INTEGER DEFAULT 0,
            close_range_5              REAL,
            direction_efficiency_5     REAL,
            max_up_5                   REAL,
            max_down_5                 REAL,
            avg_close_position_5       REAL,
            support_price              REAL,
            stop_loss                  REAL,
            target_1                   REAL,
            risk_ratio                 REAL,
            rr1                        REAL,
            structural_support         REAL,
            structural_stop_loss       REAL,
            structural_risk_ratio      REAL,
            structural_rr1             REAL,
            tactical_support           REAL,
            tactical_stop_loss         REAL,
            tactical_risk_ratio        REAL,
            tactical_rr1               REAL,
            support_quality            TEXT,
            score_reasons              TEXT,
            reject_reasons             TEXT,
            data_source                TEXT,
            created_at                 TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (task_id) REFERENCES scan_tasks(id),
            UNIQUE (task_id, code)
        )
    ''')
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy3_candidates_task_score "
        "ON strategy3_candidates(task_id, total_score DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy3_candidates_task_risk "
        "ON strategy3_candidates(task_id, risk_ratio ASC)"
    )
    _ensure_column(conn, "strategy3_candidates", "structural_support", "REAL")
    _ensure_column(conn, "strategy3_candidates", "structural_stop_loss", "REAL")
    _ensure_column(conn, "strategy3_candidates", "structural_risk_ratio", "REAL")
    _ensure_column(conn, "strategy3_candidates", "structural_rr1", "REAL")
    _ensure_column(conn, "strategy3_candidates", "tactical_support", "REAL")
    _ensure_column(conn, "strategy3_candidates", "tactical_stop_loss", "REAL")
    _ensure_column(conn, "strategy3_candidates", "tactical_risk_ratio", "REAL")
    _ensure_column(conn, "strategy3_candidates", "tactical_rr1", "REAL")
    _ensure_column(conn, "strategy3_candidates", "support_quality", "TEXT")
    _ensure_column(conn, "strategy3_candidates", "v3", "REAL")
    _ensure_column(conn, "strategy3_candidates", "v5", "REAL")
    _ensure_column(conn, "strategy3_candidates", "v10", "REAL")
    _ensure_column(conn, "strategy3_candidates", "v20", "REAL")
    _ensure_column(conn, "strategy3_candidates", "return_5", "REAL")
    _ensure_column(conn, "strategy3_candidates", "min_close_5", "REAL")
    _ensure_column(conn, "strategy3_candidates", "min_close_10", "REAL")
    _ensure_column(conn, "strategy3_candidates", "no_new_low", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "support_price_10", "REAL")
    _ensure_column(conn, "strategy3_candidates", "support_test_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "support_valid", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "bear_body_shrink", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "lower_shadow_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "down_volume_ratio_5", "REAL")
    _ensure_column(conn, "strategy3_candidates", "atr_ratio_5_20", "REAL")
    _ensure_column(conn, "strategy3_candidates", "has_big_down_volume", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "range_10", "REAL")
    _ensure_column(conn, "strategy3_candidates", "range_20", "REAL")
    _ensure_column(conn, "strategy3_candidates", "range_compression_ok", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "direction_efficiency_5", "REAL")
    _ensure_column(conn, "strategy3_candidates", "max_up_5", "REAL")
    _ensure_column(conn, "strategy3_candidates", "max_down_5", "REAL")
    _ensure_column(conn, "strategy3_candidates", "avg_close_position_5", "REAL")
    _ensure_column(conn, "strategy3_candidates", "short_support", "REAL")
    _ensure_column(conn, "strategy3_candidates", "short_support_zone_low", "REAL")
    _ensure_column(conn, "strategy3_candidates", "short_support_zone_high", "REAL")
    _ensure_column(conn, "strategy3_candidates", "key_support", "REAL")
    _ensure_column(conn, "strategy3_candidates", "key_support_zone_low", "REAL")
    _ensure_column(conn, "strategy3_candidates", "key_support_zone_high", "REAL")
    _ensure_column(conn, "strategy3_candidates", "strong_support", "REAL")
    _ensure_column(conn, "strategy3_candidates", "strong_support_zone_low", "REAL")
    _ensure_column(conn, "strategy3_candidates", "strong_support_zone_high", "REAL")
    _ensure_column(conn, "strategy3_candidates", "support_status", "TEXT")
    _ensure_column(conn, "strategy3_candidates", "break_status", "TEXT")
    _ensure_column(conn, "strategy3_candidates", "nearest_support_distance", "REAL")
    _ensure_column(conn, "strategy3_candidates", "support_sources", "TEXT")
    _ensure_column(conn, "strategy3_candidates", "trade_quality_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "volume_dry_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "price_stability_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "cannot_fall_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "balance_powerless_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "support_distance_pct", "REAL")
    _ensure_column(conn, "strategy3_candidates", "key_support_distance_pct", "REAL")
    _ensure_column(conn, "strategy3_candidates", "target_price", "REAL")
    _ensure_column(conn, "strategy3_candidates", "target_room_pct", "REAL")
    _ensure_column(conn, "strategy3_candidates", "estimated_rr", "REAL")
    _ensure_column(conn, "strategy3_candidates", "trade_state", "TEXT")
    _ensure_column(conn, "strategy3_candidates", "trade_state_label", "TEXT")
    _ensure_column(conn, "strategy3_candidates", "trigger_reasons", "TEXT")
    _ensure_column(conn, "strategy3_candidates", "risk_warnings", "TEXT")
    _ensure_column(conn, "strategy3_candidates", "invalid_conditions", "TEXT")


def _ensure_strategy4_tables(conn: sqlite3.Connection):
    """Create strategy4 snapshot/candidate tables if not exists."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy4_hot_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            topic_name TEXT NOT NULL,
            topic_type TEXT NOT NULL,
            source TEXT NOT NULL,
            snapshot_time TEXT NOT NULL,
            status TEXT NOT NULL,
            hot_topic_score REAL NOT NULL,
            price_strength_score REAL DEFAULT 0,
            amount_strength_score REAL DEFAULT 0,
            fund_flow_score REAL DEFAULT 0,
            breadth_score REAL DEFAULT 0,
            leader_limit_score REAL DEFAULT 0,
            breakout_score REAL DEFAULT 0,
            signal_count INTEGER DEFAULT 0,
            noise_reason TEXT,
            leading_stock_code TEXT,
            leading_stock_name TEXT,
            raw_snapshot TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy4_leaders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            topic_name TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            leader_type TEXT NOT NULL,
            leader_strength_score REAL NOT NULL,
            tradability_score REAL NOT NULL,
            price_limit_rule TEXT,
            limit_shape TEXT,
            limit_pct REAL,
            return_1d REAL,
            return_5d REAL,
            return_10d REAL,
            return_20d REAL,
            amount_1d REAL,
            avg_amount_5d REAL,
            avg_amount_10d REAL,
            first_wave_max_amount REAL,
            last_non_limit_amount REAL,
            consecutive_limit_count INTEGER DEFAULT 0,
            relative_strength_vs_topic REAL,
            membership_source TEXT,
            status TEXT NOT NULL,
            raw_snapshot TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy4_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            topic_name TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            evaluation_date TEXT NOT NULL,
            status TEXT NOT NULL,
            strategy4_score REAL NOT NULL,
            hot_topic_score REAL NOT NULL,
            leader_strength_score REAL NOT NULL,
            tradability_score REAL NOT NULL,
            first_wave_score REAL DEFAULT 0,
            pullback_score REAL DEFAULT 0,
            second_wave_score REAL DEFAULT 0,
            reward_risk_score REAL DEFAULT 0,
            leader_type TEXT,
            price_limit_rule TEXT,
            limit_shape TEXT,
            first_wave_return REAL,
            pullback_pct REAL,
            pullback_days INTEGER,
            current_close REAL,
            support_price REAL,
            stop_loss REAL,
            target_price REAL,
            risk_ratio REAL,
            reward_risk_ratio REAL,
            entry_note TEXT,
            reject_reason TEXT,
            evaluation_snapshot TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(task_id, code, topic_id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy4_topic_index_ohlc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id TEXT NOT NULL,
            topic_name TEXT NOT NULL,
            topic_type TEXT NOT NULL,
            source TEXT NOT NULL,
            source_topic_code TEXT,
            source_topic_name TEXT,
            date TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL DEFAULT 0,
            amount REAL DEFAULT 0,
            turnover REAL DEFAULT 0,
            change_pct REAL DEFAULT 0,
            fetched_at TEXT NOT NULL,
            data_version TEXT DEFAULT 'v1',
            raw_snapshot TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(topic_id, source, date)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy4_topic_index_fetch_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id TEXT NOT NULL,
            topic_name TEXT NOT NULL,
            topic_type TEXT NOT NULL,
            source TEXT NOT NULL,
            source_topic_code TEXT,
            source_topic_name TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT NOT NULL,
            latest_date TEXT,
            rows_count INTEGER DEFAULT 0,
            error_code TEXT,
            error_message TEXT,
            fetched_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy4_topic_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id TEXT NOT NULL,
            topic_name TEXT NOT NULL,
            topic_type TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            membership_snapshot_date TEXT NOT NULL,
            membership_mode TEXT NOT NULL,
            raw_snapshot TEXT,
            first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(topic_id, code, membership_snapshot_date, source)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy4_derived_hot_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            evaluation_date TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            topic_name TEXT NOT NULL,
            topic_type TEXT NOT NULL,
            source TEXT NOT NULL,
            membership_mode TEXT NOT NULL,
            derived_hot_score REAL NOT NULL,
            status TEXT NOT NULL,
            topic_index_latest_date TEXT,
            topic_index_phase TEXT,
            topic_index_context TEXT,
            breadth_snapshot TEXT,
            reasons TEXT,
            warnings TEXT,
            raw_snapshot TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy4_derived_leaders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            evaluation_date TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            topic_name TEXT NOT NULL,
            topic_type TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            membership_mode TEXT NOT NULL,
            derived_leader_score REAL NOT NULL,
            leader_type TEXT,
            status TEXT NOT NULL,
            leader_rs_5d REAL,
            leader_rs_10d REAL,
            leader_rs_20d REAL,
            return_rank_in_topic INTEGER,
            amount_rank_in_topic INTEGER,
            raw_snapshot TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(task_id, evaluation_date, topic_id, code)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy4_tracked_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id TEXT NOT NULL UNIQUE,
            topic_name TEXT NOT NULL,
            topic_type TEXT NOT NULL,
            first_detected_date TEXT NOT NULL,
            last_confirmed_date TEXT,
            last_evaluated_date TEXT,
            age_calendar_days INTEGER DEFAULT 0,
            tracking_status TEXT NOT NULL,
            tracking_phase TEXT,
            source_status TEXT,
            peak_hot_score REAL DEFAULT 0,
            latest_hot_score REAL DEFAULT 0,
            topic_index_phase TEXT,
            topic_index_latest_date TEXT,
            source_modes_json TEXT,
            membership_mode TEXT,
            invalid_reason TEXT,
            risk_flags TEXT,
            raw_snapshot TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy4_tracked_leaders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id TEXT NOT NULL,
            topic_name TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            first_detected_date TEXT NOT NULL,
            last_confirmed_date TEXT,
            last_evaluated_date TEXT,
            tracking_status TEXT NOT NULL,
            tracking_phase TEXT,
            source_status TEXT,
            peak_leader_score REAL DEFAULT 0,
            latest_leader_score REAL DEFAULT 0,
            first_wave_high REAL DEFAULT 0,
            first_wave_high_date TEXT,
            pullback_pct REAL DEFAULT 0,
            pullback_days INTEGER DEFAULT 0,
            support_price REAL DEFAULT 0,
            stop_loss REAL DEFAULT 0,
            target_price REAL DEFAULT 0,
            risk_ratio REAL DEFAULT 0,
            reward_risk_ratio REAL DEFAULT 0,
            candidate_origin TEXT,
            topic_first_detected_date TEXT,
            topic_last_confirmed_date TEXT,
            leader_first_detected_date TEXT,
            leader_last_confirmed_date TEXT,
            tracking_age_days INTEGER DEFAULT 0,
            membership_mode TEXT,
            invalid_reason TEXT,
            risk_flags TEXT,
            raw_snapshot TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(topic_id, code)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy4_tracking_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_date TEXT NOT NULL,
            task_id TEXT,
            entity_type TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            code TEXT,
            previous_status TEXT,
            new_status TEXT,
            event_type TEXT NOT NULL,
            reason TEXT,
            metrics_snapshot TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ''')
    for column, col_type in {
        "topic_index_source": "TEXT",
        "topic_index_latest_date": "TEXT",
        "topic_index_rows": "INTEGER DEFAULT 0",
        "topic_index_observed": "INTEGER DEFAULT 0",
        "topic_index_status": "TEXT",
        "topic_index_trend_score": "REAL DEFAULT 0",
        "topic_index_breakout_score": "REAL DEFAULT 0",
        "topic_index_volume_score": "REAL DEFAULT 0",
        "topic_index_risk_penalty": "REAL DEFAULT 0",
        "topic_index_phase": "TEXT",
        "snapshot_source": "TEXT",
        "source_modes_json": "TEXT",
        "live_hot_score": "REAL",
        "derived_hot_score": "REAL",
        "merge_confidence": "TEXT",
        "merge_warnings": "TEXT",
        "membership_mode": "TEXT",
        "derived_evaluation_date": "TEXT",
    }.items():
        _ensure_column(conn, "strategy4_hot_topics", column, col_type)
    for column, col_type in {
        "snapshot_source": "TEXT",
        "source_modes_json": "TEXT",
        "live_leader_score": "REAL",
        "derived_leader_score": "REAL",
        "merge_confidence": "TEXT",
        "merge_warnings": "TEXT",
        "membership_mode": "TEXT",
        "derived_evaluation_date": "TEXT",
    }.items():
        _ensure_column(conn, "strategy4_leaders", column, col_type)
    for column, col_type in {
        "snapshot_source": "TEXT",
        "source_modes_json": "TEXT",
        "live_hot_score": "REAL",
        "derived_hot_score": "REAL",
        "live_leader_score": "REAL",
        "derived_leader_score": "REAL",
        "merge_confidence": "TEXT",
        "merge_warnings": "TEXT",
        "membership_mode": "TEXT",
        "derived_evaluation_date": "TEXT",
        "candidate_origin": "TEXT DEFAULT 'current_hot'",
        "tracking_topic_status": "TEXT",
        "tracking_leader_status": "TEXT",
        "topic_first_detected_date": "TEXT",
        "topic_last_confirmed_date": "TEXT",
        "leader_first_detected_date": "TEXT",
        "leader_last_confirmed_date": "TEXT",
        "tracking_age_days": "INTEGER DEFAULT 0",
        "tracking_phase": "TEXT",
        "tracking_reasons": "TEXT",
        "tracking_risk_flags": "TEXT",
        "invalid_conditions": "TEXT",
    }.items():
        _ensure_column(conn, "strategy4_candidates", column, col_type)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_strategy4_hot_topics_task ON strategy4_hot_topics(task_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy4_hot_topics_score "
        "ON strategy4_hot_topics(task_id, hot_topic_score DESC)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_strategy4_leaders_task ON strategy4_leaders(task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_strategy4_leaders_code ON strategy4_leaders(code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_strategy4_candidates_task ON strategy4_candidates(task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s4_topic_index_topic_date ON strategy4_topic_index_ohlc(topic_id, date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s4_topic_index_source_name ON strategy4_topic_index_ohlc(source, source_topic_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s4_topic_members_topic ON strategy4_topic_members(topic_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s4_derived_topics_date ON strategy4_derived_hot_topics(evaluation_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s4_derived_leaders_date ON strategy4_derived_leaders(evaluation_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s4_tracked_topics_status ON strategy4_tracked_topics(tracking_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s4_tracked_leaders_topic ON strategy4_tracked_leaders(topic_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s4_tracked_leaders_status ON strategy4_tracked_leaders(tracking_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s4_tracking_events_topic ON strategy4_tracking_events(topic_id, code)")


def _ensure_strategy5_candidates_table(conn: sqlite3.Connection):
    """Create strategy5_candidates table if not exists."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy5_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            evaluation_date TEXT NOT NULL,
            close REAL DEFAULT 0,
            daily_return REAL DEFAULT 0,
            change_pct REAL DEFAULT 0,
            trading_days INTEGER DEFAULT 0,
            avg_turnover_60d REAL DEFAULT 0,
            avg_turnover_30d REAL DEFAULT 0,
            avg_turnover_10d REAL DEFAULT 0,
            ma5 REAL,
            ma10 REAL,
            ma20 REAL,
            ma50 REAL,
            ma100 REAL,
            ma120 REAL,
            ma250 REAL,
            distance_to_ma5 REAL,
            distance_to_ma10 REAL,
            distance_to_ma20 REAL,
            recent_5d_return REAL,
            recent_10d_return REAL,
            recent_20d_return REAL,
            drawdown_from_20d_high REAL,
            amplitude_5d REAL,
            amplitude_10d REAL,
            support_status TEXT,
            main_support_ma TEXT,
            main_support_price REAL,
            main_support_distance REAL,
            support_score INTEGER DEFAULT 0,
            candidate_type TEXT NOT NULL,
            classification TEXT NOT NULL,
            range_5_tag TEXT,
            range_10_tag TEXT,
            pullback_tag TEXT,
            risk_tags TEXT,
            warn_tags TEXT,
            near_120d_high_ratio REAL,
            close_20d_high REAL,
            close_120d_high REAL,
            strength_trigger TEXT,
            short_strength_score INTEGER DEFAULT 0,
            high_trigger TEXT,
            ma20_slope_5d REAL,
            ma50_slope_10d REAL,
            max_decline_5d REAL,
            v3 REAL,
            v5 REAL,
            v10 REAL,
            v20 REAL,
            v50 REAL,
            volume_ratio_5_20 REAL,
            volume_ratio_5_50 REAL,
            volume_percentile_60 REAL,
            down_volume_ratio_5 REAL,
            down_day_avg_volume_ratio_20 REAL,
            close_range_5 REAL,
            atr_ratio_5_20 REAL,
            direction_efficiency_5 REAL,
            dry_support_price REAL,
            dry_support_distance REAL,
            dry_support_valid INTEGER DEFAULT 0,
            volume_dry_score INTEGER DEFAULT 0,
            volume_dry_level TEXT,
            volume_dry_reasons TEXT,
            volume_dry_warnings TEXT,
            volume_dry_rejects TEXT,
            technical_score REAL DEFAULT 0,
            capital_score REAL DEFAULT 0,
            trend_score REAL DEFAULT 0,
            support_quality_score REAL DEFAULT 0,
            total_score REAL DEFAULT 0,
            reject_reasons TEXT,
            score_reasons TEXT,
            data_source TEXT,
            kline_latest_date TEXT,
            kline_fetched_at TEXT,
            quote_status TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (task_id) REFERENCES scan_tasks(id),
            UNIQUE(task_id, code)
        )
    ''')
    for column, col_type in {
        "main_support_price": "REAL",
        "main_support_distance": "REAL",
        "data_source": "TEXT",
        "kline_latest_date": "TEXT",
        "kline_fetched_at": "TEXT",
        "quote_status": "TEXT",
        "v3": "REAL",
        "v5": "REAL",
        "v10": "REAL",
        "v50": "REAL",
        "volume_ratio_5_20": "REAL",
        "volume_ratio_5_50": "REAL",
        "volume_percentile_60": "REAL",
        "down_volume_ratio_5": "REAL",
        "down_day_avg_volume_ratio_20": "REAL",
        "close_range_5": "REAL",
        "atr_ratio_5_20": "REAL",
        "direction_efficiency_5": "REAL",
        "dry_support_price": "REAL",
        "dry_support_distance": "REAL",
        "dry_support_valid": "INTEGER DEFAULT 0",
        "volume_dry_score": "INTEGER DEFAULT 0",
        "volume_dry_level": "TEXT",
        "volume_dry_reasons": "TEXT",
        "volume_dry_warnings": "TEXT",
        "volume_dry_rejects": "TEXT",
        "short_strength_score": "INTEGER DEFAULT 0",
    }.items():
        _ensure_column(conn, "strategy5_candidates", column, col_type)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy5_candidates_task_score "
        "ON strategy5_candidates(task_id, total_score DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy5_candidates_type_score "
        "ON strategy5_candidates(task_id, candidate_type, total_score DESC)"
    )


def _ensure_strategy6_candidates_table(conn: sqlite3.Connection):
    """Create strategy6_candidates table if not exists."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy6_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            sector_name TEXT,
            evaluation_date TEXT NOT NULL,
            candidate_type TEXT NOT NULL,
            classification TEXT NOT NULL,
            lifecycle_status TEXT,
            first_pool_date TEXT,
            pool_age_trading_days INTEGER DEFAULT 0,
            first_seen_date TEXT,
            last_seen_date TEXT,
            days_in_pool INTEGER DEFAULT 0,
            exit_date TEXT,
            exit_reason TEXT,
            cooldown_until_date TEXT,
            reentry_count INTEGER DEFAULT 0,
            strategy_version TEXT,
            config_hash TEXT,
            price_basis TEXT,
            current_price_adj REAL,
            current_price_raw REAL,
            current_price REAL DEFAULT 0,
            close REAL DEFAULT 0,
            daily_return REAL DEFAULT 0,
            current_close_position REAL DEFAULT 0,
            trading_days INTEGER DEFAULT 0,
            ma5 REAL,
            ma10 REAL,
            ma20 REAL,
            ma50 REAL,
            ma120 REAL,
            ma250 REAL,
            atr14 REAL,
            return_5 REAL,
            return_10 REAL,
            return_20 REAL,
            relative_strength_20 REAL DEFAULT 0,
            relative_strength_20_observed INTEGER DEFAULT 0,
            amount_avg_10 REAL,
            amount_avg_30 REAL,
            amount_avg_60 REAL,
            v3 REAL,
            v5 REAL,
            v10 REAL,
            v20 REAL,
            volume_ratio_5_20 REAL,
            current_volume_ratio_20 REAL,
            highest_close_20 REAL,
            highest_close_120 REAL,
            pullback_from_20d_high REAL,
            range_5 REAL,
            range_10 REAL,
            close_range_5 REAL,
            start_date TEXT,
            start_type TEXT,
            start_grade TEXT,
            start_day_return REAL,
            start_day_volume_ratio REAL,
            start_day_amount REAL,
            start_day_close_position REAL,
            start_day_self_amount_percentile REAL DEFAULT 0,
            start_low REAL,
            is_limit_up INTEGER DEFAULT 0,
            is_one_word_limit_up INTEGER DEFAULT 0,
            limit_up_pct REAL,
            days_since_start INTEGER DEFAULT 0,
            high_trigger TEXT,
            phase_status TEXT,
            consolidation_start_date TEXT,
            tail_start_date TEXT,
            signal_date TEXT,
            start_age_days INTEGER DEFAULT 0,
            consolidation_days INTEGER DEFAULT 0,
            tail_days INTEGER DEFAULT 0,
            pattern_type TEXT,
            pattern_score INTEGER DEFAULT 0,
            pattern_start_date TEXT,
            pattern_end_date TEXT,
            pivot_source TEXT,
            pattern_low REAL,
            pattern_height REAL,
            pattern_depth_pct REAL,
            contraction_count INTEGER DEFAULT 0,
            key_support_price REAL,
            tactical_support_price REAL,
            prior_key_support_price REAL,
            support_zone_low REAL,
            support_zone_high REAL,
            defense_support_price REAL,
            main_support_ma TEXT,
            support_status TEXT,
            support_test_count INTEGER DEFAULT 0,
            pivot_price REAL,
            box_height REAL,
            support_score INTEGER DEFAULT 0,
            support_cluster_sources TEXT,
            support_cluster_score INTEGER DEFAULT 0,
            suggested_buy_price REAL,
            buy_zone_low REAL,
            buy_zone_high REAL,
            stop_loss_price REAL,
            target_price_1 REAL,
            target_price_2 REAL,
            target_price_3 REAL,
            objective_target_1 REAL,
            objective_target_2 REAL,
            execution_target_1_5r REAL,
            execution_target_2r REAL,
            execution_target_2_5r REAL,
            execution_target_3_5r REAL,
            risk_amount REAL,
            reward_amount_1 REAL,
            reward_amount_2 REAL,
            reward_amount_3 REAL,
            risk_reward_ratio_1 REAL,
            risk_reward_ratio_2 REAL,
            risk_reward_ratio_3 REAL,
            objective_rr_1 REAL,
            objective_rr_2 REAL,
            valid_from_date TEXT,
            valid_until_date TEXT,
            buy_zone_valid_days INTEGER DEFAULT 0,
            suggested_limit_price REAL,
            execution_notes TEXT,
            strong_start_score INTEGER DEFAULT 0,
            dry_stable_score INTEGER DEFAULT 0,
            risk_reward_score INTEGER DEFAULT 0,
            risk_control_score INTEGER DEFAULT 0,
            total_score REAL DEFAULT 0,
            pattern_score_component INTEGER DEFAULT 0,
            tail_score INTEGER DEFAULT 0,
            objective_rr_score INTEGER DEFAULT 0,
            relative_strength_risk_score INTEGER DEFAULT 0,
            tail_avg_volume REAL,
            pre_tail_avg_volume_20 REAL,
            tail_volume_ratio REAL,
            volume_slope_10 REAL,
            market_status TEXT,
            enable_market_filter INTEGER DEFAULT 0,
            market_filter_mode TEXT,
            risk_tags TEXT,
            warn_tags TEXT,
            reject_reasons TEXT,
            score_reasons TEXT,
            suggestion TEXT,
            data_source TEXT,
            kline_latest_date TEXT,
            kline_fetched_at TEXT,
            quote_status TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (task_id) REFERENCES scan_tasks(id),
            UNIQUE(task_id, code)
        )
    ''')
    for column, col_type in {
        "sector_name": "TEXT",
        "lifecycle_status": "TEXT",
        "first_pool_date": "TEXT",
        "pool_age_trading_days": "INTEGER DEFAULT 0",
        "first_seen_date": "TEXT",
        "last_seen_date": "TEXT",
        "days_in_pool": "INTEGER DEFAULT 0",
        "exit_date": "TEXT",
        "exit_reason": "TEXT",
        "cooldown_until_date": "TEXT",
        "reentry_count": "INTEGER DEFAULT 0",
        "strategy_version": "TEXT",
        "config_hash": "TEXT",
        "price_basis": "TEXT",
        "current_price_adj": "REAL",
        "current_price_raw": "REAL",
        "current_price": "REAL DEFAULT 0",
        "current_close_position": "REAL DEFAULT 0",
        "atr14": "REAL",
        "relative_strength_20": "REAL DEFAULT 0",
        "current_volume_ratio_20": "REAL",
        "relative_strength_20_observed": "INTEGER DEFAULT 0",
        "start_low": "REAL",
        "start_day_self_amount_percentile": "REAL DEFAULT 0",
        "days_since_start": "INTEGER DEFAULT 0",
        "phase_status": "TEXT",
        "consolidation_start_date": "TEXT",
        "tail_start_date": "TEXT",
        "signal_date": "TEXT",
        "start_age_days": "INTEGER DEFAULT 0",
        "consolidation_days": "INTEGER DEFAULT 0",
        "tail_days": "INTEGER DEFAULT 0",
        "pattern_type": "TEXT",
        "pattern_score": "INTEGER DEFAULT 0",
        "pattern_start_date": "TEXT",
        "pattern_end_date": "TEXT",
        "pivot_source": "TEXT",
        "pattern_low": "REAL",
        "pattern_height": "REAL",
        "pattern_depth_pct": "REAL",
        "contraction_count": "INTEGER DEFAULT 0",
        "tactical_support_price": "REAL",
        "prior_key_support_price": "REAL",
        "support_cluster_sources": "TEXT",
        "support_cluster_score": "INTEGER DEFAULT 0",
        "objective_target_1": "REAL",
        "objective_target_2": "REAL",
        "execution_target_1_5r": "REAL",
        "execution_target_2r": "REAL",
        "execution_target_2_5r": "REAL",
        "execution_target_3_5r": "REAL",
        "objective_rr_1": "REAL",
        "objective_rr_2": "REAL",
        "valid_from_date": "TEXT",
        "valid_until_date": "TEXT",
        "buy_zone_valid_days": "INTEGER DEFAULT 0",
        "suggested_limit_price": "REAL",
        "execution_notes": "TEXT",
        "pattern_score_component": "INTEGER DEFAULT 0",
        "tail_score": "INTEGER DEFAULT 0",
        "objective_rr_score": "INTEGER DEFAULT 0",
        "relative_strength_risk_score": "INTEGER DEFAULT 0",
        "tail_avg_volume": "REAL",
        "pre_tail_avg_volume_20": "REAL",
        "tail_volume_ratio": "REAL",
        "volume_slope_10": "REAL",
        "risk_tags": "TEXT",
        "warn_tags": "TEXT",
        "reject_reasons": "TEXT",
        "score_reasons": "TEXT",
        "suggestion": "TEXT",
        "data_source": "TEXT",
        "kline_latest_date": "TEXT",
        "kline_fetched_at": "TEXT",
        "quote_status": "TEXT",
        "original_tail_pass": "INTEGER DEFAULT 0",
        "original_tail_score": "INTEGER DEFAULT 0",
        "box_tail_enabled": "INTEGER DEFAULT 0",
        "box_tail_pass": "INTEGER DEFAULT 0",
        "box_tail_score": "INTEGER DEFAULT 0",
        "box_status": "TEXT",
        "tail_pass": "INTEGER DEFAULT 0",
        "tail_path": "TEXT",
        "box_start_date": "TEXT",
        "box_end_date": "TEXT",
        "box_days": "INTEGER DEFAULT 0",
        "box_high": "REAL",
        "box_low": "REAL",
        "box_width": "REAL",
        "box_position": "REAL",
        "box_position_raw": "REAL",
        "box_low_test_count": "INTEGER DEFAULT 0",
        "box_high_test_count": "INTEGER DEFAULT 0",
        "box_first_half_volume": "REAL",
        "box_second_half_volume": "REAL",
        "box_volume_contraction_ratio": "REAL",
        "first_half_median_close": "REAL",
        "second_half_median_close": "REAL",
        "box_center_shift": "REAL",
        "box_break_reason": "TEXT",
        "box_selection_reason": "TEXT",
        "compact_kline_enabled": "INTEGER DEFAULT 0",
        "compact_kline_pass": "INTEGER DEFAULT 0",
        "compact_kline_score": "INTEGER DEFAULT 0",
        "box_quality_score": "INTEGER DEFAULT 0",
        "box_quality_tag": "TEXT",
        "avg_body_ratio_5": "REAL",
        "max_body_ratio_5": "REAL",
        "compact_close_range_5": "REAL",
        "kline_overlap_pair_count": "INTEGER DEFAULT 0",
        "avg_kline_overlap_ratio": "REAL",
        "gap_count_5": "INTEGER DEFAULT 0",
        "max_gap_ratio_5": "REAL",
        "atr5": "REAL",
        "atr20": "REAL",
        "atr_contraction_ratio": "REAL",
        "compact_kline_reasons": "TEXT",
        "compact_kline_risk_tags": "TEXT",
        "brooks_tail_enabled": "INTEGER DEFAULT 0",
        "brooks_tail_pass": "INTEGER DEFAULT 0",
        "brooks_tail_score": "INTEGER DEFAULT 0",
        "brooks_tail_premium": "INTEGER DEFAULT 0",
        "brooks_status": "TEXT",
        "brooks_trade_ready": "INTEGER DEFAULT 0",
        "brooks_trade_trigger_type": "TEXT",
        "brooks_trigger_price": "REAL",
        "brooks_trigger_valid_until": "TEXT",
        "tail_paths": "TEXT",
        "tail_path_summary": "TEXT",
        "tail_primary_path": "TEXT",
        "passed_path_count": "INTEGER DEFAULT 0",
        "multi_path_confirmed": "INTEGER DEFAULT 0",
        "brooks_result_json": "TEXT",
        "start_event_quality_score": "INTEGER DEFAULT 0",
        "start_follow_through_return_5": "REAL DEFAULT 0",
        "start_gain_retention_ratio": "REAL DEFAULT 0",
        "start_max_close_drawdown_5": "REAL DEFAULT 0",
        "start_failure_reasons": "TEXT",
        "tail_segmentation_status": "TEXT",
        "tail_segmentation_score": "INTEGER DEFAULT 0",
        "tail_range_contraction_ratio": "REAL DEFAULT 0",
        "tail_atr_contraction_ratio": "REAL DEFAULT 0",
        "tail_body_contraction_ratio": "REAL DEFAULT 0",
        "setup_quality_score": "INTEGER DEFAULT 0",
        "setup_gain_retention_ratio": "REAL DEFAULT 0",
        "distribution_day_count": "INTEGER DEFAULT 0",
        "up_down_volume_ratio": "REAL DEFAULT 0",
        "volatility_contraction_ratio": "REAL DEFAULT 0",
        "failed_breakout_count": "INTEGER DEFAULT 0",
        "relative_strength_trend": "TEXT",
        "setup_quality_reasons": "TEXT",
        "setup_quality_risk_tags": "TEXT",
        "support_reaction_score": "INTEGER DEFAULT 0",
        "support_reaction_reasons": "TEXT",
        "support_reaction_risk_tags": "TEXT",
        "path_evidence_score": "INTEGER DEFAULT 0",
        "entry_archetype": "TEXT",
        "score_model_version": "TEXT",
        "vcp_observation_eligible": "INTEGER DEFAULT 0",
        "vcp_lifecycle_status": "TEXT DEFAULT 'VCP_NONE'",
        "vcp_origin_start_date": "TEXT",
        "vcp_pattern_start_date": "TEXT",
        "vcp_pattern_end_date": "TEXT",
        "vcp_contraction_count": "INTEGER DEFAULT 0",
        "vcp_contractions": "TEXT",
        "vcp_pivot_price": "REAL DEFAULT 0",
        "vcp_structure_low": "REAL DEFAULT 0",
        "vcp_distance_to_pivot_pct": "REAL DEFAULT 0",
        "vcp_breakout_date": "TEXT",
        "vcp_days_since_breakout": "INTEGER DEFAULT 0",
        "vcp_observation_reasons": "TEXT",
        "vcp_observation_risk_tags": "TEXT",
        "vcp_invalidation_reason": "TEXT",
        "vcp_exit_audit": "INTEGER DEFAULT 0",
        "vcp_history_qualified": "INTEGER DEFAULT 0",
        "vcp_history_candidate_date": "TEXT",
        "vcp_history_candidate_type": "TEXT",
        "vcp_history_candidate_score": "INTEGER DEFAULT 0",
        "vcp_history_source": "TEXT",
        "vcp_history_origin_start_date": "TEXT",
        "vcp_quality_score": "INTEGER",
        "vcp_quality_grade": "TEXT",
        "vcp_quality_contraction_score": "INTEGER",
        "vcp_quality_range_score": "INTEGER",
        "vcp_quality_volume_score": "INTEGER",
        "vcp_quality_low_score": "INTEGER",
        "vcp_quality_time_score": "INTEGER",
        "vcp_quality_pivot_score": "INTEGER",
        "vcp_quality_reasons": "TEXT",
        "vcp_quality_warnings": "TEXT",
        "vcp_quality_model_version": "TEXT",
    }.items():
        _ensure_column(conn, "strategy6_candidates", column, col_type)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy6_candidates_task_score "
        "ON strategy6_candidates(task_id, total_score DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy6_candidates_type_score "
        "ON strategy6_candidates(task_id, candidate_type, total_score DESC)"
    )


def _ensure_strategy6_market_snapshots_table(conn: sqlite3.Connection):
    """Create Strategy6 task-level market snapshot table if not exists."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy6_market_snapshots (
            task_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            name TEXT,
            latest_date TEXT,
            latest_close REAL DEFAULT 0,
            ma20 REAL DEFAULT 0,
            ma50 REAL DEFAULT 0,
            return_20 REAL DEFAULT 0,
            above_ma20 INTEGER DEFAULT 0,
            ma20_above_ma50 INTEGER DEFAULT 0,
            volume_down_risk INTEGER DEFAULT 0,
            weak INTEGER DEFAULT 0,
            rows_count INTEGER DEFAULT 0,
            source TEXT,
            data_status TEXT DEFAULT 'MISSING',
            market_status TEXT,
            market_reasons TEXT,
            market_return_20 REAL DEFAULT 0,
            fetched_at TEXT,
            PRIMARY KEY (task_id, symbol),
            FOREIGN KEY (task_id) REFERENCES scan_tasks(id)
        )
    ''')
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy6_market_snapshots_task "
        "ON strategy6_market_snapshots(task_id)"
    )
    _ensure_column(conn, "strategy6_market_snapshots", "data_status", "TEXT DEFAULT 'MISSING'")


def _ensure_strategy6_lifecycle_table(conn: sqlite3.Connection):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy6_candidate_lifecycle (
            code TEXT PRIMARY KEY,
            lifecycle_status TEXT NOT NULL,
            first_seen_date TEXT,
            last_seen_date TEXT,
            days_in_pool INTEGER DEFAULT 0,
            exit_date TEXT,
            exit_reason TEXT,
            cooldown_until_date TEXT,
            reentry_count INTEGER DEFAULT 0,
            last_event_key TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ''')


def _ensure_strategy6_task_lifecycle_table(conn: sqlite3.Connection):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy6_task_lifecycle (
            task_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            evaluation_date TEXT,
            candidate_type TEXT,
            lifecycle_status TEXT,
            first_seen_date TEXT,
            last_seen_date TEXT,
            days_in_pool INTEGER DEFAULT 0,
            exit_date TEXT,
            exit_reason TEXT,
            cooldown_until_date TEXT,
            reentry_count INTEGER DEFAULT 0,
            blocked INTEGER DEFAULT 0,
            reject_reasons TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (task_id, code),
            FOREIGN KEY (task_id) REFERENCES scan_tasks(id)
        )
    ''')
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy6_task_lifecycle_task "
        "ON strategy6_task_lifecycle(task_id, blocked, lifecycle_status)"
    )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, col_type: str):
    """Compatible add-column-if-not-exists helper."""
    existing = [d[1] for d in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def _json_dumps(value):
    """Encode a list as JSON string, or return empty string."""
    if not value:
        return ""
    import json
    return json.dumps(list(value), ensure_ascii=False)


def upsert_strategy2_candidate(task_id: str, d: dict):
    """Insert or update a single strategy2 candidate."""
    conn = get_conn()
    columns = [
        "task_id", "code", "name", "evaluation_date", "total_score", "level",
        "volume_dry_score", "price_stable_score", "current_close",
        "v3", "v5", "v10", "v20", "volume_ratio_5_20",
        "volume_percentile", "volume_percentile_days",
        "range_5", "close_range_5", "return_3", "return_5",
        "key_support", "buy_zone_low", "buy_zone_high", "stop_loss",
        "risk_ratio", "risk_level", "score_reasons", "reject_reasons", "data_source",
        "trend_type", "short_mid_score", "long_score", "total_evidence_score",
        "necessary_conditions_met", "ma20", "ma60", "ma120",
        "ma20_slope", "ma60_slope",
        "drawdown_from_high_60", "center_shift_20", "price_position_60",
        "linear_trend_60", "drawdown_from_high_120", "center_shift_40",
        "return_20", "return_60", "downtrend_conditions",
        "short_term_time_exit_days",
    ]
    values = (
        task_id, d["code"], d["name"], d["evaluation_date"],
        d["total_score"], d["level"],
        d["volume_dry_score"], d["price_stable_score"], d["current_close"],
        d.get("v3"), d.get("v5"), d.get("v10"), d.get("v20"),
        d.get("volume_ratio_5_20"), d.get("volume_percentile"), d.get("volume_percentile_days"),
        d.get("range_5"), d.get("close_range_5"), d.get("return_3"), d.get("return_5"),
        d["key_support"], d["buy_zone_low"], d["buy_zone_high"], d["stop_loss"],
        d["risk_ratio"], d["risk_level"],
        _json_dumps(d.get("score_reasons")),
        _json_dumps(d.get("reject_reasons")),
        d.get("data_source", ""),
        d.get("trend_type", ""),
        d.get("short_mid_score", 0), d.get("long_score", 0), d.get("total_evidence_score", 0),
        d.get("necessary_conditions_met", 0),
        d.get("ma20", 0.0), d.get("ma60", 0.0), d.get("ma120"),
        d.get("ma20_slope", 0.0), d.get("ma60_slope"),
        d.get("drawdown_from_high_60", 0.0), d.get("center_shift_20", 0.0),
        d.get("price_position_60", 0.5), d.get("linear_trend_60", 0.0),
        d.get("drawdown_from_high_120", 0.0), d.get("center_shift_40", 0.0),
        d.get("return_20", 0.0), d.get("return_60", 0.0),
        d.get("downtrend_conditions", "[]"),
        d.get("short_term_time_exit_days", 0),
    )
    value_marks = ", ".join("?" for _ in columns)
    update_assignments = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("task_id", "code"))
    conn.execute(
        f"""INSERT INTO strategy2_candidates ({', '.join(columns)}) VALUES ({value_marks})
            ON CONFLICT(task_id, code) DO UPDATE SET {update_assignments}""",
        values,
    )
    conn.commit()


def get_strategy2_candidates(task_id: str = None) -> list[dict]:
    """Get strategy2 candidates, optionally filtered by task_id.

    Returns JSON array fields as deserialized lists (BUG-S2-011).
    Sorted by total_score DESC, risk_ratio ASC, code ASC (BUG-S2-011).
    """
    conn = get_conn()
    if task_id:
        rows = conn.execute(
            "SELECT * FROM strategy2_candidates WHERE task_id=? "
            "ORDER BY total_score DESC, risk_ratio ASC, code ASC",
            (task_id,),
        ).fetchall()
    else:
        latest = conn.execute(
            "SELECT id FROM scan_tasks WHERE status='completed' AND strategy_type='STRATEGY_2_EXTREME_DRY_STABLE' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not latest:
            return []
        rows = conn.execute(
            "SELECT * FROM strategy2_candidates WHERE task_id=? "
            "ORDER BY total_score DESC, risk_ratio ASC, code ASC",
            (latest[0],),
        ).fetchall()
    col_names = [d[1] for d in conn.execute("PRAGMA table_info(strategy2_candidates)").fetchall()]
    return [_deserialize_strategy2_candidate(dict(zip(col_names, r))) for r in rows]


def get_strategy2_candidate(code: str, task_id: str = None) -> dict | None:
    """Get single strategy2 candidate detail.

    Returns JSON array fields as deserialized lists (BUG-S2-011).
    """
    conn = get_conn()
    if task_id:
        row = conn.execute(
            "SELECT * FROM strategy2_candidates WHERE code=? AND task_id=?",
            (code, task_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM strategy2_candidates WHERE code=? ORDER BY id DESC LIMIT 1",
            (code,),
        ).fetchone()
    if not row:
        return None
    col_names = [d[1] for d in conn.execute("PRAGMA table_info(strategy2_candidates)").fetchall()]
    return _deserialize_strategy2_candidate(dict(zip(col_names, row)))


def _deserialize_strategy2_candidate(row: dict) -> dict:
    """Convert JSON string fields to Python lists (BUG-S2-011)."""
    json_fields = ("score_reasons", "reject_reasons")
    for field in json_fields:
        value = row.get(field)
        if isinstance(value, str) and value:
            try:
                import json
                row[field] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                row[field] = []
        elif not value:
            row[field] = []
    return row


def upsert_strategy3_candidate(task_id: str, d: dict):
    """Insert or update a single strategy3 candidate."""
    conn = get_conn()
    columns = [
        "task_id", "code", "name", "evaluation_date", "total_score", "level",
        "trend_score", "pullback_score", "volume_stability_score",
        "second_breakout_score", "risk_reward_score", "current_close",
        "ma5", "ma10", "ma20", "ma60", "ma120", "recent_high",
        "pullback_pct", "relative_strength_60", "volume_ratio_5_20",
        "v3", "v5", "v10", "v20", "return_5", "min_close_5", "min_close_10",
        "no_new_low", "support_price_10", "support_test_count", "support_valid",
        "bear_body_shrink", "lower_shadow_count", "down_volume_ratio_5",
        "atr_ratio_5_20", "has_big_down_volume",
        "range_5", "range_10", "range_20", "range_compression_ok",
        "close_range_5", "direction_efficiency_5", "max_up_5", "max_down_5",
        "avg_close_position_5", "support_price", "stop_loss",
        "target_1", "risk_ratio", "rr1",
        "structural_support", "structural_stop_loss", "structural_risk_ratio",
        "structural_rr1", "tactical_support", "tactical_stop_loss",
        "tactical_risk_ratio", "tactical_rr1", "support_quality",
        "short_support", "short_support_zone_low", "short_support_zone_high",
        "key_support", "key_support_zone_low", "key_support_zone_high",
        "strong_support", "strong_support_zone_low", "strong_support_zone_high",
        "support_status", "break_status", "nearest_support_distance", "support_sources",
        "trade_quality_score", "volume_dry_score", "price_stability_score",
        "cannot_fall_score", "balance_powerless_score", "support_distance_pct",
        "key_support_distance_pct", "target_price", "target_room_pct",
        "estimated_rr", "trade_state", "trade_state_label", "trigger_reasons",
        "risk_warnings", "invalid_conditions",
        "score_reasons", "reject_reasons", "data_source",
    ]
    values = (
        task_id,
        d["code"],
        d.get("name", ""),
        d.get("evaluation_date", ""),
        d.get("total_score", 0),
        d.get("level", ""),
        d.get("trend_score", 0),
        d.get("pullback_score", 0),
        d.get("volume_stability_score", 0),
        d.get("second_breakout_score", 0),
        d.get("risk_reward_score", 0),
        d.get("current_close", 0.0),
        d.get("ma5"),
        d.get("ma10"),
        d.get("ma20"),
        d.get("ma60"),
        d.get("ma120"),
        d.get("recent_high"),
        d.get("pullback_pct"),
        d.get("relative_strength_60"),
        d.get("volume_ratio_5_20"),
        d.get("v3"),
        d.get("v5"),
        d.get("v10"),
        d.get("v20"),
        d.get("return_5"),
        d.get("min_close_5"),
        d.get("min_close_10"),
        int(bool(d.get("no_new_low"))),
        d.get("support_price_10"),
        d.get("support_test_count", 0),
        int(bool(d.get("support_valid"))),
        int(bool(d.get("bear_body_shrink"))),
        d.get("lower_shadow_count", 0),
        d.get("down_volume_ratio_5"),
        d.get("atr_ratio_5_20"),
        int(bool(d.get("has_big_down_volume"))),
        d.get("range_5"),
        d.get("range_10"),
        d.get("range_20"),
        int(bool(d.get("range_compression_ok"))),
        d.get("close_range_5"),
        d.get("direction_efficiency_5"),
        d.get("max_up_5"),
        d.get("max_down_5"),
        d.get("avg_close_position_5"),
        d.get("support_price"),
        d.get("stop_loss"),
        d.get("target_1"),
        d.get("risk_ratio"),
        d.get("rr1"),
        d.get("structural_support"),
        d.get("structural_stop_loss"),
        d.get("structural_risk_ratio"),
        d.get("structural_rr1"),
        d.get("tactical_support"),
        d.get("tactical_stop_loss"),
        d.get("tactical_risk_ratio"),
        d.get("tactical_rr1"),
        d.get("support_quality", ""),
        d.get("short_support"),
        d.get("short_support_zone_low"),
        d.get("short_support_zone_high"),
        d.get("key_support"),
        d.get("key_support_zone_low"),
        d.get("key_support_zone_high"),
        d.get("strong_support"),
        d.get("strong_support_zone_low"),
        d.get("strong_support_zone_high"),
        d.get("support_status", ""),
        d.get("break_status", ""),
        d.get("nearest_support_distance"),
        _json_dumps(d.get("support_sources")),
        d.get("trade_quality_score", 0),
        d.get("volume_dry_score", 0),
        d.get("price_stability_score", 0),
        d.get("cannot_fall_score", 0),
        d.get("balance_powerless_score", 0),
        d.get("support_distance_pct"),
        d.get("key_support_distance_pct"),
        d.get("target_price"),
        d.get("target_room_pct"),
        d.get("estimated_rr"),
        d.get("trade_state", ""),
        d.get("trade_state_label", ""),
        _json_dumps(d.get("trigger_reasons")),
        _json_dumps(d.get("risk_warnings")),
        _json_dumps(d.get("invalid_conditions")),
        _json_dumps(d.get("score_reasons")),
        _json_dumps(d.get("reject_reasons")),
        d.get("data_source", ""),
    )
    marks = ", ".join("?" for _ in columns)
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("task_id", "code"))
    conn.execute(
        f"""INSERT INTO strategy3_candidates ({', '.join(columns)}) VALUES ({marks})
            ON CONFLICT(task_id, code) DO UPDATE SET {updates}""",
        values,
    )
    conn.commit()


def get_strategy3_candidates(task_id: str = None) -> list[dict]:
    """Get strategy3 candidates, optionally filtered by task_id."""
    conn = get_conn()
    if task_id:
        rows = conn.execute(
            "SELECT * FROM strategy3_candidates WHERE task_id=? "
            "ORDER BY total_score DESC, risk_ratio ASC, code ASC",
            (task_id,),
        ).fetchall()
    else:
        latest = conn.execute(
            "SELECT id FROM scan_tasks WHERE status='completed' "
            "AND strategy_type='STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT' "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not latest:
            return []
        rows = conn.execute(
            "SELECT * FROM strategy3_candidates WHERE task_id=? "
            "ORDER BY total_score DESC, risk_ratio ASC, code ASC",
            (latest[0],),
        ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy3_candidates)").fetchall()]
    return [_deserialize_strategy3_candidate(dict(zip(cols, row))) for row in rows]


def get_strategy3_candidate(code: str, task_id: str = None) -> dict | None:
    """Get single strategy3 candidate detail."""
    conn = get_conn()
    if task_id:
        row = conn.execute(
            "SELECT * FROM strategy3_candidates WHERE code=? AND task_id=?",
            (code, task_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM strategy3_candidates WHERE code=? ORDER BY id DESC LIMIT 1",
            (code,),
        ).fetchone()
    if not row:
        return None
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy3_candidates)").fetchall()]
    return _deserialize_strategy3_candidate(dict(zip(cols, row)))


def _deserialize_strategy3_candidate(row: dict) -> dict:
    """Convert strategy3 JSON string fields to Python lists."""
    for field in (
        "score_reasons", "reject_reasons", "support_sources",
        "trigger_reasons", "risk_warnings", "invalid_conditions",
    ):
        value = row.get(field)
        if isinstance(value, str) and value:
            try:
                row[field] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                row[field] = []
        elif not value:
            row[field] = []
    return row


def replace_strategy4_hot_topics(task_id: str, topics: list[dict]):
    """Replace Strategy4 hot-topic snapshots for one task."""
    conn = get_conn()
    columns = [
        "task_id", "topic_id", "topic_name", "topic_type", "source", "snapshot_time",
        "status", "hot_topic_score", "price_strength_score", "amount_strength_score",
        "fund_flow_score", "breadth_score", "leader_limit_score", "breakout_score",
        "signal_count", "noise_reason", "leading_stock_code", "leading_stock_name",
        "raw_snapshot", "topic_index_source", "topic_index_latest_date", "topic_index_rows",
        "topic_index_observed", "topic_index_status", "topic_index_trend_score",
        "topic_index_breakout_score", "topic_index_volume_score", "topic_index_risk_penalty",
        "topic_index_phase", "snapshot_source", "source_modes_json", "live_hot_score",
        "derived_hot_score", "merge_confidence", "merge_warnings", "membership_mode",
        "derived_evaluation_date",
    ]
    with conn:
        conn.execute("DELETE FROM strategy4_hot_topics WHERE task_id=?", (task_id,))
        for item in topics:
            values = [
                task_id,
                item.get("topic_id", ""),
                item.get("topic_name", ""),
                item.get("topic_type", ""),
                item.get("source", ""),
                item.get("snapshot_time", ""),
                item.get("status", ""),
                item.get("hot_topic_score", 0.0),
                item.get("price_strength_score", 0.0),
                item.get("amount_strength_score", 0.0),
                item.get("fund_flow_score", 0.0),
                item.get("breadth_score", 0.0),
                item.get("leader_limit_score", 0.0),
                item.get("breakout_score", 0.0),
                item.get("signal_count", 0),
                item.get("noise_reason", ""),
                item.get("leading_stock_code", ""),
                item.get("leading_stock_name", ""),
                _json_any(item.get("raw_snapshot")),
                item.get("topic_index_source", ""),
                item.get("topic_index_latest_date", ""),
                item.get("topic_index_rows", 0),
                1 if item.get("topic_index_observed") else 0,
                item.get("topic_index_status", ""),
                item.get("topic_index_trend_score", 0.0),
                item.get("topic_index_breakout_score", 0.0),
                item.get("topic_index_volume_score", 0.0),
                item.get("topic_index_risk_penalty", 0.0),
                item.get("topic_index_phase", ""),
                item.get("snapshot_source", item.get("source", "")),
                _json_any(item.get("source_modes")),
                item.get("live_hot_score"),
                item.get("derived_hot_score"),
                item.get("merge_confidence", ""),
                _json_any(item.get("merge_warnings")),
                item.get("membership_mode", ""),
                item.get("derived_evaluation_date", ""),
            ]
            conn.execute(
                f"INSERT INTO strategy4_hot_topics ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                values,
            )


def replace_strategy4_leaders(task_id: str, leaders: list[dict]):
    """Replace Strategy4 leader snapshots for one task."""
    conn = get_conn()
    columns = [
        "task_id", "topic_id", "topic_name", "code", "name", "leader_type",
        "leader_strength_score", "tradability_score", "price_limit_rule", "limit_shape",
        "limit_pct", "return_1d", "return_5d", "return_10d", "return_20d",
        "amount_1d", "avg_amount_5d", "avg_amount_10d", "first_wave_max_amount",
        "last_non_limit_amount", "consecutive_limit_count", "relative_strength_vs_topic",
        "membership_source", "status", "raw_snapshot", "snapshot_source", "source_modes_json",
        "live_leader_score", "derived_leader_score", "merge_confidence", "merge_warnings",
        "membership_mode", "derived_evaluation_date",
    ]
    with conn:
        conn.execute("DELETE FROM strategy4_leaders WHERE task_id=?", (task_id,))
        for item in leaders:
            values = [
                task_id,
                item.get("topic_id", ""),
                item.get("topic_name", ""),
                item.get("code", ""),
                item.get("name", ""),
                item.get("leader_type", ""),
                item.get("leader_strength_score", 0.0),
                item.get("tradability_score", 0.0),
                item.get("price_limit_rule", ""),
                item.get("limit_shape", ""),
                item.get("limit_pct"),
                item.get("return_1d"),
                item.get("return_5d"),
                item.get("return_10d"),
                item.get("return_20d"),
                item.get("amount_1d"),
                item.get("avg_amount_5d"),
                item.get("avg_amount_10d"),
                item.get("first_wave_max_amount"),
                item.get("last_non_limit_amount"),
                item.get("consecutive_limit_count", 0),
                item.get("relative_strength_vs_topic"),
                item.get("membership_source", ""),
                item.get("status", ""),
                _json_any(item.get("raw_snapshot")),
                item.get("snapshot_source", item.get("source", "")),
                _json_any(item.get("source_modes")),
                item.get("live_leader_score"),
                item.get("derived_leader_score"),
                item.get("merge_confidence", ""),
                _json_any(item.get("merge_warnings")),
                item.get("membership_mode", ""),
                item.get("derived_evaluation_date", ""),
            ]
            conn.execute(
                f"INSERT INTO strategy4_leaders ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                values,
            )


def upsert_strategy4_candidate(task_id: str, d: dict):
    """Insert or update one Strategy4 candidate snapshot."""
    conn = get_conn()
    columns = [
        "task_id", "topic_id", "topic_name", "code", "name", "evaluation_date",
        "status", "strategy4_score", "hot_topic_score", "leader_strength_score",
        "tradability_score", "first_wave_score", "pullback_score", "second_wave_score",
        "reward_risk_score", "leader_type", "price_limit_rule", "limit_shape",
        "first_wave_return", "pullback_pct", "pullback_days", "current_close",
        "support_price", "stop_loss", "target_price", "risk_ratio",
        "reward_risk_ratio", "entry_note", "reject_reason", "evaluation_snapshot",
        "snapshot_source", "source_modes_json", "live_hot_score", "derived_hot_score",
        "live_leader_score", "derived_leader_score", "merge_confidence", "merge_warnings",
        "membership_mode", "derived_evaluation_date", "candidate_origin",
        "tracking_topic_status", "tracking_leader_status", "topic_first_detected_date",
        "topic_last_confirmed_date", "leader_first_detected_date", "leader_last_confirmed_date",
        "tracking_age_days", "tracking_phase", "tracking_reasons", "tracking_risk_flags",
        "invalid_conditions",
    ]
    values = [
        task_id,
        d.get("topic_id", ""),
        d.get("topic_name", ""),
        d.get("code", ""),
        d.get("name", ""),
        d.get("evaluation_date", ""),
        d.get("status", ""),
        d.get("strategy4_score", 0.0),
        d.get("hot_topic_score", 0.0),
        d.get("leader_strength_score", 0.0),
        d.get("tradability_score", 0.0),
        d.get("first_wave_score", 0.0),
        d.get("pullback_score", 0.0),
        d.get("second_wave_score", 0.0),
        d.get("reward_risk_score", 0.0),
        d.get("leader_type", ""),
        d.get("price_limit_rule", ""),
        d.get("limit_shape", ""),
        d.get("first_wave_return"),
        d.get("pullback_pct"),
        d.get("pullback_days"),
        d.get("current_close"),
        d.get("support_price"),
        d.get("stop_loss"),
        d.get("target_price"),
        d.get("risk_ratio"),
        d.get("reward_risk_ratio"),
        d.get("entry_note", ""),
        d.get("reject_reason", ""),
        _json_any(d.get("evaluation_snapshot")),
        d.get("snapshot_source", ""),
        _json_any(d.get("source_modes")),
        d.get("live_hot_score"),
        d.get("derived_hot_score"),
        d.get("live_leader_score"),
        d.get("derived_leader_score"),
        d.get("merge_confidence", ""),
        _json_any(d.get("merge_warnings")),
        d.get("membership_mode", ""),
        d.get("derived_evaluation_date", ""),
        d.get("candidate_origin", "current_hot"),
        d.get("tracking_topic_status", ""),
        d.get("tracking_leader_status", ""),
        d.get("topic_first_detected_date", ""),
        d.get("topic_last_confirmed_date", ""),
        d.get("leader_first_detected_date", ""),
        d.get("leader_last_confirmed_date", ""),
        d.get("tracking_age_days", 0),
        d.get("tracking_phase", ""),
        _json_any(d.get("tracking_reasons")),
        _json_any(d.get("tracking_risk_flags")),
        _json_any(d.get("invalid_conditions")),
    ]
    updates = ", ".join(
        f"{c}=excluded.{c}" for c in columns if c not in ("task_id", "topic_id", "code")
    )
    conn.execute(
        f"""INSERT INTO strategy4_candidates ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})
            ON CONFLICT(task_id, code, topic_id) DO UPDATE SET {updates}, updated_at=datetime('now')""",
        values,
    )
    conn.commit()


def get_strategy4_hot_topics(task_id: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM strategy4_hot_topics WHERE task_id=? ORDER BY hot_topic_score DESC, topic_name ASC",
        (task_id,),
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy4_hot_topics)").fetchall()]
    return [_deserialize_strategy4_row(dict(zip(cols, row))) for row in rows]


def get_strategy4_leaders(task_id: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM strategy4_leaders WHERE task_id=? ORDER BY leader_strength_score DESC, tradability_score DESC, code ASC",
        (task_id,),
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy4_leaders)").fetchall()]
    return [_deserialize_strategy4_row(dict(zip(cols, row))) for row in rows]


def get_strategy4_candidates(task_id: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM strategy4_candidates WHERE task_id=? ORDER BY strategy4_score DESC, reward_risk_ratio DESC, code ASC",
        (task_id,),
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy4_candidates)").fetchall()]
    return [_deserialize_strategy4_row(dict(zip(cols, row))) for row in rows]


def get_strategy4_candidate(code: str, task_id: str = None) -> dict | None:
    conn = get_conn()
    if task_id:
        row = conn.execute(
            "SELECT * FROM strategy4_candidates WHERE code=? AND task_id=? ORDER BY id DESC LIMIT 1",
            (code, task_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM strategy4_candidates WHERE code=? ORDER BY id DESC LIMIT 1",
            (code,),
        ).fetchone()
    if not row:
        return None
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy4_candidates)").fetchall()]
    return _deserialize_strategy4_row(dict(zip(cols, row)))


def upsert_strategy5_candidate(task_id: str, d: dict):
    """Insert or update one Strategy5 candidate."""
    conn = get_conn()
    columns = [
        "task_id", "code", "name", "evaluation_date", "close", "daily_return", "change_pct",
        "trading_days", "avg_turnover_60d", "avg_turnover_30d", "avg_turnover_10d",
        "ma5", "ma10", "ma20", "ma50", "ma100", "ma120", "ma250",
        "distance_to_ma5", "distance_to_ma10", "distance_to_ma20",
        "recent_5d_return", "recent_10d_return", "recent_20d_return",
        "drawdown_from_20d_high", "amplitude_5d", "amplitude_10d",
        "support_status", "main_support_ma", "main_support_price", "main_support_distance",
        "support_score", "candidate_type", "classification",
        "range_5_tag", "range_10_tag", "pullback_tag", "risk_tags", "warn_tags",
        "near_120d_high_ratio", "close_20d_high", "close_120d_high",
        "strength_trigger", "short_strength_score", "high_trigger", "ma20_slope_5d", "ma50_slope_10d",
        "max_decline_5d", "v3", "v5", "v10", "v20", "v50",
        "volume_ratio_5_20", "volume_ratio_5_50", "volume_percentile_60",
        "down_volume_ratio_5", "down_day_avg_volume_ratio_20",
        "close_range_5", "atr_ratio_5_20", "direction_efficiency_5",
        "dry_support_price", "dry_support_distance", "dry_support_valid",
        "volume_dry_score", "volume_dry_level", "volume_dry_reasons",
        "volume_dry_warnings", "volume_dry_rejects",
        "technical_score", "capital_score", "trend_score",
        "support_quality_score", "total_score", "reject_reasons", "score_reasons",
        "data_source", "kline_latest_date", "kline_fetched_at", "quote_status",
    ]
    values = [
        task_id,
        d.get("code", ""),
        d.get("name", ""),
        d.get("evaluation_date", ""),
        d.get("close", 0.0),
        d.get("daily_return", 0.0),
        d.get("change_pct", 0.0),
        d.get("trading_days", 0),
        d.get("avg_turnover_60d", 0.0),
        d.get("avg_turnover_30d", 0.0),
        d.get("avg_turnover_10d", 0.0),
        d.get("ma5"),
        d.get("ma10"),
        d.get("ma20"),
        d.get("ma50"),
        d.get("ma100"),
        d.get("ma120"),
        d.get("ma250"),
        d.get("distance_to_ma5"),
        d.get("distance_to_ma10"),
        d.get("distance_to_ma20"),
        d.get("recent_5d_return"),
        d.get("recent_10d_return"),
        d.get("recent_20d_return"),
        d.get("drawdown_from_20d_high"),
        d.get("amplitude_5d"),
        d.get("amplitude_10d"),
        d.get("support_status", ""),
        d.get("main_support_ma", ""),
        d.get("main_support_price"),
        d.get("main_support_distance"),
        d.get("support_score", 0),
        d.get("candidate_type", "REJECTED"),
        d.get("classification", "rejected"),
        d.get("range_5_tag", ""),
        d.get("range_10_tag", ""),
        d.get("pullback_tag", ""),
        _json_any(d.get("risk_tags", [])),
        _json_any(d.get("warn_tags", [])),
        d.get("near_120d_high_ratio"),
        d.get("close_20d_high"),
        d.get("close_120d_high"),
        d.get("strength_trigger", ""),
        d.get("short_strength_score", 0),
        d.get("high_trigger", ""),
        d.get("ma20_slope_5d"),
        d.get("ma50_slope_10d"),
        d.get("max_decline_5d"),
        d.get("v3"),
        d.get("v5"),
        d.get("v10"),
        d.get("v20"),
        d.get("v50"),
        d.get("volume_ratio_5_20"),
        d.get("volume_ratio_5_50"),
        d.get("volume_percentile_60"),
        d.get("down_volume_ratio_5"),
        d.get("down_day_avg_volume_ratio_20"),
        d.get("close_range_5"),
        d.get("atr_ratio_5_20"),
        d.get("direction_efficiency_5"),
        d.get("dry_support_price"),
        d.get("dry_support_distance"),
        1 if d.get("dry_support_valid") else 0,
        d.get("volume_dry_score", 0),
        d.get("volume_dry_level", ""),
        _json_any(d.get("volume_dry_reasons", [])),
        _json_any(d.get("volume_dry_warnings", [])),
        _json_any(d.get("volume_dry_rejects", [])),
        d.get("technical_score", 0.0),
        d.get("capital_score", 0.0),
        d.get("trend_score", 0.0),
        d.get("support_quality_score", 0.0),
        d.get("total_score", 0.0),
        _json_any(d.get("reject_reasons", [])),
        _json_any(d.get("score_reasons", [])),
        d.get("data_source", ""),
        d.get("kline_latest_date", ""),
        d.get("kline_fetched_at", ""),
        d.get("quote_status", ""),
    ]
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("task_id", "code"))
    conn.execute(
        f"""INSERT INTO strategy5_candidates ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})
            ON CONFLICT(task_id, code) DO UPDATE SET {updates}, updated_at=datetime('now')""",
        values,
    )
    conn.commit()


def get_strategy5_candidates(task_id: str = None) -> list[dict]:
    """Get Strategy5 candidates, optionally for a task."""
    conn = get_conn()
    if task_id:
        rows = conn.execute(
            "SELECT * FROM strategy5_candidates WHERE task_id=? "
            "ORDER BY CASE candidate_type WHEN 'KEY_CANDIDATE' THEN 0 WHEN 'WATCH_CANDIDATE' THEN 1 ELSE 2 END, "
            "total_score DESC, code ASC",
            (task_id,),
        ).fetchall()
    else:
        row = conn.execute(
            "SELECT id FROM scan_tasks WHERE status='completed' "
            "AND strategy_type='STRATEGY_5_SHORT_SPRINT_SUPPORT' "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return []
        rows = conn.execute(
            "SELECT * FROM strategy5_candidates WHERE task_id=? "
            "ORDER BY CASE candidate_type WHEN 'KEY_CANDIDATE' THEN 0 WHEN 'WATCH_CANDIDATE' THEN 1 ELSE 2 END, "
            "total_score DESC, code ASC",
            (row[0],),
        ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy5_candidates)").fetchall()]
    return [_deserialize_strategy5_row(dict(zip(cols, row))) for row in rows]


def get_strategy5_candidate(code: str, task_id: str = None) -> dict | None:
    conn = get_conn()
    if task_id:
        row = conn.execute(
            "SELECT * FROM strategy5_candidates WHERE code=? AND task_id=? ORDER BY id DESC LIMIT 1",
            (code, task_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM strategy5_candidates WHERE code=? ORDER BY id DESC LIMIT 1",
            (code,),
        ).fetchone()
    if not row:
        return None
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy5_candidates)").fetchall()]
    return _deserialize_strategy5_row(dict(zip(cols, row)))


def upsert_strategy6_candidate(
    task_id: str,
    d: dict,
    *,
    _conn: sqlite3.Connection | None = None,
    _commit: bool = True,
):
    """Insert or update one Strategy6 candidate."""
    conn = _conn or get_conn()
    observation_only = bool(
        d.get("candidate_type") == "REJECTED"
        and d.get("classification") == "observation"
    )
    first_pool_date = "" if observation_only else str(
        d.get("first_seen_date") or d.get("first_pool_date") or d.get("evaluation_date") or ""
    )
    pool_age = int(d.get("days_in_pool", d.get("pool_age_trading_days", 0)) or 0)
    lifecycle_status = d.get("lifecycle_status", "")
    columns = [
        "task_id", "code", "name", "sector_name", "evaluation_date",
        "candidate_type", "classification", "lifecycle_status", "first_pool_date", "pool_age_trading_days",
        "current_price", "close", "daily_return", "current_close_position", "trading_days",
        "ma5", "ma10", "ma20", "ma50", "ma120", "ma250",
        "return_5", "return_10", "return_20",
        "relative_strength_20", "relative_strength_20_observed",
        "amount_avg_10", "amount_avg_30", "amount_avg_60",
        "v3", "v5", "v10", "v20", "volume_ratio_5_20",
        "current_volume_ratio_20",
        "highest_close_20", "highest_close_120", "pullback_from_20d_high",
        "range_5", "range_10", "close_range_5",
        "start_date", "start_type", "start_grade", "start_day_return",
        "start_day_volume_ratio", "start_day_amount", "start_day_close_position", "start_low",
        "is_limit_up", "is_one_word_limit_up", "limit_up_pct", "days_since_start", "high_trigger",
        "key_support_price", "prior_key_support_price", "support_zone_low", "support_zone_high",
        "defense_support_price", "main_support_ma", "support_status",
        "support_test_count", "pivot_price", "box_height", "support_score",
        "suggested_buy_price", "buy_zone_low", "buy_zone_high", "stop_loss_price",
        "target_price_1", "target_price_2", "target_price_3",
        "risk_amount", "reward_amount_1", "reward_amount_2", "reward_amount_3",
        "risk_reward_ratio_1", "risk_reward_ratio_2", "risk_reward_ratio_3",
        "strong_start_score", "dry_stable_score", "risk_reward_score",
        "risk_control_score", "total_score",
        "market_status", "enable_market_filter", "market_filter_mode",
        "risk_tags", "warn_tags", "reject_reasons", "score_reasons", "suggestion",
        "data_source", "kline_latest_date", "kline_fetched_at", "quote_status",
    ]
    values = [
        task_id,
        d.get("code", ""),
        d.get("name", ""),
        d.get("sector_name", ""),
        d.get("evaluation_date", ""),
        d.get("candidate_type", "REJECTED"),
        d.get("classification", "rejected"),
        lifecycle_status,
        first_pool_date,
        pool_age,
        d.get("current_price", d.get("close", 0.0)),
        d.get("close", d.get("current_price", 0.0)),
        d.get("daily_return", 0.0),
        d.get("current_close_position", 0.0),
        d.get("trading_days", 0),
        d.get("ma5"),
        d.get("ma10"),
        d.get("ma20"),
        d.get("ma50"),
        d.get("ma120"),
        d.get("ma250"),
        d.get("return_5"),
        d.get("return_10"),
        d.get("return_20"),
        d.get("relative_strength_20", 0.0),
        1 if d.get("relative_strength_20_observed") else 0,
        d.get("amount_avg_10"),
        d.get("amount_avg_30"),
        d.get("amount_avg_60"),
        d.get("v3"),
        d.get("v5"),
        d.get("v10"),
        d.get("v20"),
        d.get("volume_ratio_5_20"),
        d.get("current_volume_ratio_20"),
        d.get("highest_close_20"),
        d.get("highest_close_120"),
        d.get("pullback_from_20d_high"),
        d.get("range_5"),
        d.get("range_10"),
        d.get("close_range_5"),
        d.get("start_date", ""),
        d.get("start_type", ""),
        d.get("start_grade", ""),
        d.get("start_day_return"),
        d.get("start_day_volume_ratio"),
        d.get("start_day_amount"),
        d.get("start_day_close_position"),
        d.get("start_low"),
        1 if d.get("is_limit_up") else 0,
        1 if d.get("is_one_word_limit_up") else 0,
        d.get("limit_up_pct"),
        d.get("days_since_start", 0),
        d.get("high_trigger", ""),
        d.get("key_support_price"),
        d.get("prior_key_support_price"),
        d.get("support_zone_low"),
        d.get("support_zone_high"),
        d.get("defense_support_price"),
        d.get("main_support_ma", ""),
        d.get("support_status", ""),
        d.get("support_test_count", 0),
        d.get("pivot_price"),
        d.get("box_height"),
        d.get("support_score", 0),
        d.get("suggested_buy_price"),
        d.get("buy_zone_low"),
        d.get("buy_zone_high"),
        d.get("stop_loss_price"),
        d.get("target_price_1"),
        d.get("target_price_2"),
        d.get("target_price_3"),
        d.get("risk_amount"),
        d.get("reward_amount_1"),
        d.get("reward_amount_2"),
        d.get("reward_amount_3"),
        d.get("risk_reward_ratio_1"),
        d.get("risk_reward_ratio_2"),
        d.get("risk_reward_ratio_3"),
        d.get("strong_start_score", 0),
        d.get("dry_stable_score", 0),
        d.get("risk_reward_score", 0),
        d.get("risk_control_score", 0),
        d.get("total_score", 0.0),
        d.get("market_status", "UNKNOWN"),
        1 if d.get("enable_market_filter") else 0,
        d.get("market_filter_mode", "downgrade"),
        _json_any(d.get("risk_tags", [])),
        _json_any(d.get("warn_tags", [])),
        _json_any(d.get("reject_reasons", [])),
        _json_any(d.get("score_reasons", [])),
        d.get("suggestion", ""),
        d.get("data_source", ""),
        d.get("kline_latest_date", ""),
        d.get("kline_fetched_at", ""),
        d.get("quote_status", ""),
    ]
    extra_columns = [
        "first_seen_date", "last_seen_date", "days_in_pool", "exit_date", "exit_reason", "cooldown_until_date", "reentry_count",
        "strategy_version", "config_hash", "price_basis", "current_price_adj", "current_price_raw",
        "atr14", "start_day_self_amount_percentile",
        "phase_status", "consolidation_start_date", "tail_start_date", "signal_date",
        "start_age_days", "consolidation_days", "tail_days",
        "pattern_type", "pattern_score", "pattern_start_date", "pattern_end_date",
        "pivot_source", "pattern_low", "pattern_height", "pattern_depth_pct", "contraction_count",
        "tactical_support_price", "support_cluster_sources", "support_cluster_score",
        "objective_target_1", "objective_target_2",
        "execution_target_1_5r", "execution_target_2r", "execution_target_2_5r", "execution_target_3_5r",
        "objective_rr_1", "objective_rr_2", "valid_from_date", "valid_until_date",
        "buy_zone_valid_days", "suggested_limit_price", "execution_notes",
        "pattern_score_component", "tail_score", "objective_rr_score", "relative_strength_risk_score",
        "tail_avg_volume", "pre_tail_avg_volume_20", "tail_volume_ratio", "volume_slope_10",
        "original_tail_pass", "original_tail_score", "box_tail_enabled", "box_tail_pass",
        "box_tail_score", "box_status", "tail_pass", "tail_path",
        "box_start_date", "box_end_date", "box_days", "box_high", "box_low", "box_width",
        "box_position", "box_position_raw", "box_low_test_count", "box_high_test_count",
        "box_first_half_volume", "box_second_half_volume", "box_volume_contraction_ratio",
        "first_half_median_close", "second_half_median_close", "box_center_shift",
        "box_break_reason", "box_selection_reason", "compact_kline_enabled",
        "compact_kline_pass", "compact_kline_score", "box_quality_score", "box_quality_tag",
        "avg_body_ratio_5", "max_body_ratio_5", "compact_close_range_5",
        "kline_overlap_pair_count", "avg_kline_overlap_ratio", "gap_count_5",
        "max_gap_ratio_5", "atr5", "atr20", "atr_contraction_ratio",
        "compact_kline_reasons", "compact_kline_risk_tags",
        "brooks_tail_enabled", "brooks_tail_pass", "brooks_tail_score",
        "brooks_tail_premium", "brooks_status", "brooks_trade_ready",
        "brooks_trade_trigger_type", "brooks_trigger_price", "brooks_trigger_valid_until", "tail_paths",
        "tail_path_summary", "tail_primary_path", "passed_path_count",
        "multi_path_confirmed", "brooks_result_json",
        "start_event_quality_score", "start_follow_through_return_5",
        "start_gain_retention_ratio", "start_max_close_drawdown_5", "start_failure_reasons",
        "tail_segmentation_status", "tail_segmentation_score",
        "tail_range_contraction_ratio", "tail_atr_contraction_ratio", "tail_body_contraction_ratio",
        "setup_quality_score", "setup_gain_retention_ratio", "distribution_day_count",
        "up_down_volume_ratio", "volatility_contraction_ratio", "failed_breakout_count",
        "relative_strength_trend", "setup_quality_reasons", "setup_quality_risk_tags",
        "support_reaction_score", "support_reaction_reasons", "support_reaction_risk_tags",
        "path_evidence_score", "entry_archetype", "score_model_version",
        "vcp_observation_eligible", "vcp_lifecycle_status",
        "vcp_origin_start_date", "vcp_pattern_start_date", "vcp_pattern_end_date",
        "vcp_contraction_count", "vcp_contractions", "vcp_pivot_price",
        "vcp_structure_low", "vcp_distance_to_pivot_pct", "vcp_breakout_date",
        "vcp_days_since_breakout", "vcp_observation_reasons",
        "vcp_observation_risk_tags", "vcp_invalidation_reason", "vcp_exit_audit",
        "vcp_history_qualified", "vcp_history_candidate_date",
        "vcp_history_candidate_type", "vcp_history_candidate_score",
        "vcp_history_source", "vcp_history_origin_start_date",
        "vcp_quality_score", "vcp_quality_grade",
        "vcp_quality_contraction_score", "vcp_quality_range_score",
        "vcp_quality_volume_score", "vcp_quality_low_score",
        "vcp_quality_time_score", "vcp_quality_pivot_score",
        "vcp_quality_reasons", "vcp_quality_warnings",
        "vcp_quality_model_version",
    ]
    extra_values = [
        "" if observation_only else d.get("first_seen_date", first_pool_date),
        "" if observation_only else d.get("last_seen_date", d.get("evaluation_date", "")),
        d.get("days_in_pool", pool_age),
        d.get("exit_date", ""),
        d.get("exit_reason", ""),
        d.get("cooldown_until_date", ""),
        d.get("reentry_count", 0),
        d.get("strategy_version", ""),
        d.get("config_hash", ""),
        d.get("price_basis", "FORWARD_ADJUSTED"),
        d.get("current_price_adj", d.get("current_price")),
        None,
        d.get("atr14"),
        d.get("start_day_self_amount_percentile", 0),
        d.get("phase_status", ""),
        d.get("consolidation_start_date", ""),
        d.get("tail_start_date", ""),
        d.get("signal_date", d.get("evaluation_date", "")),
        d.get("start_age_days", 0),
        d.get("consolidation_days", 0),
        d.get("tail_days", 0),
        d.get("pattern_type", "UNKNOWN"),
        d.get("pattern_score", 0),
        d.get("pattern_start_date", ""),
        d.get("pattern_end_date", ""),
        d.get("pivot_source", ""),
        d.get("pattern_low"),
        d.get("pattern_height"),
        d.get("pattern_depth_pct"),
        d.get("contraction_count", 0),
        d.get("tactical_support_price"),
        _json_any(d.get("support_cluster_sources", [])),
        d.get("support_cluster_score", 0),
        d.get("objective_target_1"),
        d.get("objective_target_2"),
        d.get("execution_target_1_5r"),
        d.get("execution_target_2r"),
        d.get("execution_target_2_5r"),
        d.get("execution_target_3_5r"),
        d.get("objective_rr_1"),
        d.get("objective_rr_2"),
        d.get("valid_from_date", ""),
        d.get("valid_until_date", ""),
        d.get("buy_zone_valid_days", 0),
        d.get("suggested_limit_price"),
        _json_any(d.get("execution_notes", [])),
        d.get("pattern_score_component", 0),
        d.get("tail_score", 0),
        d.get("objective_rr_score", 0),
        d.get("relative_strength_risk_score", 0),
        d.get("tail_avg_volume"),
        d.get("pre_tail_avg_volume_20"),
        d.get("tail_volume_ratio"),
        d.get("volume_slope_10"),
        1 if d.get("original_tail_pass") else 0,
        d.get("original_tail_score", 0),
        1 if d.get("box_tail_enabled") else 0,
        1 if d.get("box_tail_pass") else 0,
        d.get("box_tail_score", 0),
        d.get("box_status", "NO_BOX"),
        1 if d.get("tail_pass") else 0,
        d.get("tail_path", "NONE"),
        d.get("box_start_date", ""),
        d.get("box_end_date", ""),
        d.get("box_days", 0),
        d.get("box_high"),
        d.get("box_low"),
        d.get("box_width"),
        d.get("box_position"),
        d.get("box_position_raw"),
        d.get("box_low_test_count", 0),
        d.get("box_high_test_count", 0),
        d.get("box_first_half_volume"),
        d.get("box_second_half_volume"),
        d.get("box_volume_contraction_ratio"),
        d.get("first_half_median_close"),
        d.get("second_half_median_close"),
        d.get("box_center_shift"),
        d.get("box_break_reason", ""),
        d.get("box_selection_reason", ""),
        1 if d.get("compact_kline_enabled") else 0,
        1 if d.get("compact_kline_pass") else 0,
        d.get("compact_kline_score", 0),
        d.get("box_quality_score", 0),
        d.get("box_quality_tag", "NONE"),
        d.get("avg_body_ratio_5"),
        d.get("max_body_ratio_5"),
        d.get("compact_close_range_5"),
        d.get("kline_overlap_pair_count", 0),
        d.get("avg_kline_overlap_ratio"),
        d.get("gap_count_5", 0),
        d.get("max_gap_ratio_5"),
        d.get("atr5"),
        d.get("atr20"),
        d.get("atr_contraction_ratio"),
        _json_any(d.get("compact_kline_reasons", [])),
        _json_any(d.get("compact_kline_risk_tags", [])),
        1 if d.get("brooks_tail_enabled") else 0,
        1 if d.get("brooks_tail_pass") else 0,
        d.get("brooks_tail_score", 0),
        1 if d.get("brooks_tail_premium") else 0,
        d.get("brooks_status", "BROOKS_DISABLED"),
        1 if d.get("brooks_trade_ready") else 0,
        d.get("brooks_trade_trigger_type", ""),
        d.get("brooks_trigger_price"),
        d.get("brooks_trigger_valid_until", ""),
        _json_any(d.get("tail_paths", [])),
        d.get("tail_path_summary", "NONE"),
        d.get("tail_primary_path", "NONE"),
        d.get("passed_path_count", 0),
        1 if d.get("multi_path_confirmed") else 0,
        json.dumps(
            d.get("brooks_result") or {},
            ensure_ascii=False,
            sort_keys=True,
            default=_json_default,
        ),
        d.get("start_event_quality_score", 0),
        d.get("start_follow_through_return_5", 0.0),
        d.get("start_gain_retention_ratio", 0.0),
        d.get("start_max_close_drawdown_5", 0.0),
        _json_any(d.get("start_failure_reasons", [])),
        d.get("tail_segmentation_status", "FIXED_WINDOW"),
        d.get("tail_segmentation_score", 0),
        d.get("tail_range_contraction_ratio", 0.0),
        d.get("tail_atr_contraction_ratio", 0.0),
        d.get("tail_body_contraction_ratio", 0.0),
        d.get("setup_quality_score", 0),
        d.get("setup_gain_retention_ratio", 0.0),
        d.get("distribution_day_count", 0),
        d.get("up_down_volume_ratio", 0.0),
        d.get("volatility_contraction_ratio", 0.0),
        d.get("failed_breakout_count", 0),
        d.get("relative_strength_trend", "UNKNOWN"),
        _json_any(d.get("setup_quality_reasons", [])),
        _json_any(d.get("setup_quality_risk_tags", [])),
        d.get("support_reaction_score", 0),
        _json_any(d.get("support_reaction_reasons", [])),
        _json_any(d.get("support_reaction_risk_tags", [])),
        d.get("path_evidence_score", 0),
        d.get("entry_archetype", "NONE"),
        d.get("score_model_version", "S6_QUALITY_V2"),
        1 if d.get("vcp_observation_eligible") else 0,
        d.get("vcp_lifecycle_status", "VCP_NONE"),
        d.get("vcp_origin_start_date", ""),
        d.get("vcp_pattern_start_date", ""),
        d.get("vcp_pattern_end_date", ""),
        d.get("vcp_contraction_count", 0),
        _json_any(d.get("vcp_contractions", [])),
        d.get("vcp_pivot_price", 0.0),
        d.get("vcp_structure_low", 0.0),
        d.get("vcp_distance_to_pivot_pct", 0.0),
        d.get("vcp_breakout_date", ""),
        d.get("vcp_days_since_breakout", 0),
        _json_any(d.get("vcp_observation_reasons", [])),
        _json_any(d.get("vcp_observation_risk_tags", [])),
        d.get("vcp_invalidation_reason", ""),
        1 if d.get("vcp_exit_audit") else 0,
        1 if d.get("vcp_history_qualified") else 0,
        d.get("vcp_history_candidate_date", ""),
        d.get("vcp_history_candidate_type", ""),
        d.get("vcp_history_candidate_score", 0),
        d.get("vcp_history_source", ""),
        d.get("vcp_history_origin_start_date", ""),
        d.get("vcp_quality_score"),
        d.get("vcp_quality_grade"),
        d.get("vcp_quality_contraction_score"),
        d.get("vcp_quality_range_score"),
        d.get("vcp_quality_volume_score"),
        d.get("vcp_quality_low_score"),
        d.get("vcp_quality_time_score"),
        d.get("vcp_quality_pivot_score"),
        _json_any(d.get("vcp_quality_reasons", [])),
        _json_any(d.get("vcp_quality_warnings", [])),
        d.get("vcp_quality_model_version"),
    ]
    columns.extend(extra_columns)
    values.extend(extra_values)
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("task_id", "code"))
    conn.execute(
        f"""INSERT INTO strategy6_candidates ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})
            ON CONFLICT(task_id, code) DO UPDATE SET {updates}, updated_at=datetime('now')""",
        values,
    )
    if _commit:
        conn.commit()


def _weekday_distance(start_date: str, end_date: str) -> int:
    from datetime import date, timedelta

    try:
        start = date.fromisoformat(str(start_date)[:10])
        end = date.fromisoformat(str(end_date)[:10])
    except ValueError:
        return 0
    if end <= start:
        return 0
    days = 0
    current = start + timedelta(days=1)
    while current <= end:
        if current.weekday() < 5:
            days += 1
        current += timedelta(days=1)
    return days


def get_strategy6_candidates(task_id: str = None) -> list[dict]:
    """Get Strategy6 candidates, optionally for a task."""
    conn = get_conn()
    if task_id:
        rows = conn.execute(
            "SELECT * FROM strategy6_candidates WHERE task_id=? "
            "ORDER BY CASE candidate_type WHEN 'READY_CANDIDATE' THEN 0 WHEN 'KEY_CANDIDATE' THEN 1 "
            "WHEN 'WATCH_CANDIDATE' THEN 2 ELSE 3 END, total_score DESC, code ASC",
            (task_id,),
        ).fetchall()
    else:
        row = conn.execute(
            "SELECT id FROM scan_tasks WHERE status='completed' "
            "AND strategy_type='STRATEGY_6_STRONG_VCP_TAIL' "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return []
        rows = conn.execute(
            "SELECT * FROM strategy6_candidates WHERE task_id=? "
            "ORDER BY total_score DESC, code ASC",
            (row[0],),
        ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy6_candidates)").fetchall()]
    return [_deserialize_strategy6_row(dict(zip(cols, row))) for row in rows]


def get_strategy6_candidate(code: str, task_id: str = None) -> dict | None:
    conn = get_conn()
    if task_id:
        row = conn.execute(
            "SELECT * FROM strategy6_candidates WHERE code=? AND task_id=? ORDER BY id DESC LIMIT 1",
            (code, task_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM strategy6_candidates WHERE code=? ORDER BY id DESC LIMIT 1",
            (code,),
        ).fetchone()
    if not row:
        return None
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy6_candidates)").fetchall()]
    return _deserialize_strategy6_row(dict(zip(cols, row)))


def get_latest_strategy6_vcp_states(exclude_task_id: str | None = None) -> dict[str, dict]:
    """Return each stock's latest VCP state from completed scans only."""
    conn = get_conn()
    params: tuple = ()
    where = (
        "WHERE LOWER(COALESCE(t.status, ''))='completed' "
        "AND ((c.vcp_observation_eligible=1 AND c.vcp_history_qualified=1) "
        "OR c.vcp_exit_audit=1)"
    )
    if exclude_task_id:
        where += " AND c.task_id<>?"
        params = (exclude_task_id,)
    rows = conn.execute(
        f"SELECT c.* FROM strategy6_candidates c "
        f"JOIN scan_tasks t ON t.id=c.task_id {where} ORDER BY c.id DESC",
        params,
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy6_candidates)").fetchall()]
    latest: dict[str, dict] = {}
    for raw in rows:
        row = _deserialize_strategy6_row(dict(zip(cols, raw)))
        latest.setdefault(str(row.get("code") or ""), row)
    return latest


def save_strategy6_market_snapshot(task_id: str, snapshot: dict):
    """Persist task-level Strategy6 market index snapshot for frontend audit."""
    conn = get_conn()
    _ensure_strategy6_market_snapshots_table(conn)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    market_status = str(snapshot.get("market_status") or "UNKNOWN")
    market_reasons = _json_any(snapshot.get("market_reasons", []))
    market_return_20 = float(snapshot.get("market_return_20") or 0.0)
    rows = snapshot.get("indexes") or []
    with conn:
        conn.execute("DELETE FROM strategy6_market_snapshots WHERE task_id=?", (task_id,))
        for row in rows:
            symbol = str(row.get("symbol") or "")
            if not symbol:
                continue
            conn.execute(
                """INSERT INTO strategy6_market_snapshots (
                       task_id, symbol, name, latest_date, latest_close, ma20, ma50, return_20,
                       above_ma20, ma20_above_ma50, volume_down_risk, weak, rows_count, source, data_status,
                       market_status, market_reasons, market_return_20, fetched_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    symbol,
                    row.get("name", ""),
                    row.get("latest_date", ""),
                    float(row.get("latest_close") or 0.0),
                    float(row.get("ma20") or 0.0),
                    float(row.get("ma50") or 0.0),
                    float(row.get("return_20") or 0.0),
                    1 if row.get("above_ma20") else 0,
                    1 if row.get("ma20_above_ma50") else 0,
                    1 if row.get("volume_down_risk") else 0,
                    1 if row.get("weak") else 0,
                    int(row.get("rows_count") or 0),
                    row.get("source", ""),
                    row.get("data_status", "MISSING"),
                    market_status,
                    market_reasons,
                    market_return_20,
                    row.get("fetched_at") or now,
                ),
            )


def get_strategy6_market_snapshot(task_id: str) -> dict:
    """Return persisted Strategy6 market snapshot for a task."""
    conn = get_conn()
    _ensure_strategy6_market_snapshots_table(conn)
    rows = conn.execute(
        """SELECT task_id, symbol, name, latest_date, latest_close, ma20, ma50, return_20,
                  above_ma20, ma20_above_ma50, volume_down_risk, weak, rows_count, source, data_status,
                  market_status, market_reasons, market_return_20, fetched_at
           FROM strategy6_market_snapshots
           WHERE task_id=?
           ORDER BY CASE symbol
               WHEN 'sh000001' THEN 0
               WHEN 'sz399001' THEN 1
               WHEN 'sz399006' THEN 2
               WHEN 'hs300' THEN 3
               ELSE 9
           END, symbol ASC""",
        (task_id,),
    ).fetchall()
    if not rows:
        return {
            "task_id": task_id,
            "market_status": "UNKNOWN",
            "market_reasons": [],
            "market_return_20": 0.0,
            "indexes": [],
        }
    cols = [
        "task_id", "symbol", "name", "latest_date", "latest_close", "ma20", "ma50", "return_20",
        "above_ma20", "ma20_above_ma50", "volume_down_risk", "weak", "rows_count", "source", "data_status",
        "market_status", "market_reasons", "market_return_20", "fetched_at",
    ]
    items = [dict(zip(cols, row)) for row in rows]
    first = items[0]
    indexes = []
    for item in items:
        indexes.append({
            "symbol": item["symbol"],
            "name": item.get("name") or item["symbol"],
            "latest_date": item.get("latest_date") or "",
            "latest_close": item.get("latest_close") or 0.0,
            "ma20": item.get("ma20") or 0.0,
            "ma50": item.get("ma50") or 0.0,
            "return_20": item.get("return_20") or 0.0,
            "above_ma20": bool(item.get("above_ma20")),
            "ma20_above_ma50": bool(item.get("ma20_above_ma50")),
            "volume_down_risk": bool(item.get("volume_down_risk")),
            "weak": bool(item.get("weak")),
            "rows_count": item.get("rows_count") or 0,
            "source": item.get("source") or "",
            "data_status": item.get("data_status") or "MISSING",
            "fetched_at": item.get("fetched_at") or "",
        })
    reasons = []
    raw_reasons = first.get("market_reasons")
    if isinstance(raw_reasons, str) and raw_reasons:
        try:
            parsed = json.loads(raw_reasons)
            reasons = parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            reasons = []
    return {
        "task_id": task_id,
        "market_status": first.get("market_status") or "UNKNOWN",
        "market_reasons": reasons,
        "market_return_20": first.get("market_return_20") or 0.0,
        "indexes": indexes,
    }


def get_strategy6_lifecycle(code: str) -> dict | None:
    conn = get_conn()
    _ensure_strategy6_lifecycle_table(conn)
    return _get_strategy6_lifecycle_from_conn(conn, code)


def save_strategy6_task_lifecycle(
    task_id: str,
    *,
    code: str,
    name: str,
    evaluation_date: str,
    candidate_type: str,
    lifecycle: dict,
    reject_reasons: list[str],
    _conn: sqlite3.Connection | None = None,
    _commit: bool = True,
) -> None:
    conn = _conn or get_conn()
    if _commit:
        _ensure_strategy6_task_lifecycle_table(conn)
    conn.execute(
        """INSERT INTO strategy6_task_lifecycle (
               task_id, code, name, evaluation_date, candidate_type, lifecycle_status,
               first_seen_date, last_seen_date, days_in_pool, exit_date, exit_reason,
               cooldown_until_date, reentry_count, blocked, reject_reasons, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(task_id, code) DO UPDATE SET
               name=excluded.name,
               evaluation_date=excluded.evaluation_date,
               candidate_type=excluded.candidate_type,
               lifecycle_status=excluded.lifecycle_status,
               first_seen_date=excluded.first_seen_date,
               last_seen_date=excluded.last_seen_date,
               days_in_pool=excluded.days_in_pool,
               exit_date=excluded.exit_date,
               exit_reason=excluded.exit_reason,
               cooldown_until_date=excluded.cooldown_until_date,
               reentry_count=excluded.reentry_count,
               blocked=excluded.blocked,
               reject_reasons=excluded.reject_reasons,
               updated_at=datetime('now')""",
        (
            task_id, code, name, evaluation_date, candidate_type,
            lifecycle.get("lifecycle_status", ""), lifecycle.get("first_seen_date", ""),
            lifecycle.get("last_seen_date", ""), int(lifecycle.get("days_in_pool") or 0),
            lifecycle.get("exit_date", ""), lifecycle.get("exit_reason", ""),
            lifecycle.get("cooldown_until_date", ""), int(lifecycle.get("reentry_count") or 0),
            1 if lifecycle.get("blocked") else 0, _json_any(reject_reasons),
        ),
    )
    if _commit:
        conn.commit()


def get_strategy6_task_lifecycle(task_id: str) -> list[dict]:
    conn = get_conn()
    _ensure_strategy6_task_lifecycle_table(conn)
    rows = conn.execute(
        """SELECT task_id, code, name, evaluation_date, candidate_type, lifecycle_status,
                  first_seen_date, last_seen_date, days_in_pool, exit_date, exit_reason,
                  cooldown_until_date, reentry_count, blocked, reject_reasons
           FROM strategy6_task_lifecycle WHERE task_id=?
           ORDER BY blocked DESC, lifecycle_status, code""",
        (task_id,),
    ).fetchall()
    columns = [
        "task_id", "code", "name", "evaluation_date", "candidate_type", "lifecycle_status",
        "first_seen_date", "last_seen_date", "days_in_pool", "exit_date", "exit_reason",
        "cooldown_until_date", "reentry_count", "blocked", "reject_reasons",
    ]
    result = []
    for row in rows:
        item = dict(zip(columns, row))
        item["blocked"] = bool(item.get("blocked"))
        try:
            decoded = json.loads(item.get("reject_reasons") or "[]")
            item["reject_reasons"] = decoded if isinstance(decoded, list) else []
        except (json.JSONDecodeError, TypeError):
            item["reject_reasons"] = []
        result.append(item)
    return result


def _get_strategy6_lifecycle_from_conn(conn: sqlite3.Connection, code: str) -> dict | None:
    row = conn.execute(
        """SELECT code, lifecycle_status, first_seen_date, last_seen_date, days_in_pool,
                  exit_date, exit_reason, cooldown_until_date, reentry_count, last_event_key
           FROM strategy6_candidate_lifecycle WHERE code=?""",
        (code,),
    ).fetchone()
    if not row:
        return None
    columns = [
        "code", "lifecycle_status", "first_seen_date", "last_seen_date", "days_in_pool",
        "exit_date", "exit_reason", "cooldown_until_date", "reentry_count", "last_event_key",
    ]
    return dict(zip(columns, row))


def update_strategy6_lifecycle(
    *,
    code: str,
    evaluation_date: str,
    candidate_type: str,
    lifecycle_status: str,
    event_key: str,
    reject_reasons: list[str],
    max_watch_days: int,
    expired_cooldown_days: int,
    failed_cooldown_days: int,
    _conn: sqlite3.Connection | None = None,
    _commit: bool = True,
) -> dict:
    conn = _conn or get_conn()
    if _commit:
        _ensure_strategy6_lifecycle_table(conn)
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
    try:
        previous = _get_strategy6_lifecycle_from_conn(conn, code)
        is_candidate = candidate_type != "REJECTED"
        state = {
            "code": code,
            "lifecycle_status": lifecycle_status,
            "first_seen_date": evaluation_date if is_candidate else "",
            "last_seen_date": evaluation_date,
            "days_in_pool": 0,
            "exit_date": "",
            "exit_reason": "",
            "cooldown_until_date": "",
            "reentry_count": 0,
            "last_event_key": event_key,
            "blocked": not is_candidate,
        }

        if previous:
            state.update(previous)
            state["last_seen_date"] = evaluation_date
            state["blocked"] = False
            if not is_candidate:
                if lifecycle_status == "EXTENDED" or "BREAKOUT_EXTENDED" in reject_reasons:
                    state.update({
                        "lifecycle_status": "EXTENDED",
                        "exit_date": evaluation_date,
                        "exit_reason": "BREAKOUT_EXTENDED",
                        "cooldown_until_date": "",
                        "blocked": True,
                    })
                else:
                    natural_expiry = lifecycle_status == "EXPIRED" or any(
                        reason in {"START_TOO_OLD", "CONSOLIDATION_TOO_LONG"}
                        for reason in reject_reasons
                    )
                    state.update({
                        "lifecycle_status": "EXPIRED" if natural_expiry else "FAILED",
                        "exit_date": evaluation_date,
                        "exit_reason": (reject_reasons or ["STRATEGY_REJECTED"])[0],
                        "cooldown_until_date": _add_weekdays_iso(
                            evaluation_date,
                            expired_cooldown_days if natural_expiry else failed_cooldown_days,
                        ),
                        "blocked": True,
                    })
            elif previous["lifecycle_status"] in {"FAILED", "EXPIRED", "COOLDOWN"}:
                cooldown = str(previous.get("cooldown_until_date") or "")
                same_event = event_key == str(previous.get("last_event_key") or "")
                support_recovered = (
                    previous["lifecycle_status"] in {"FAILED", "COOLDOWN"}
                    and previous.get("exit_reason") != "MAX_WATCH_DAYS_REACHED"
                    and lifecycle_status in {"READY", "BUY_ZONE", "BREAKOUT_CONFIRMED"}
                )
                if (cooldown and evaluation_date <= cooldown) or (same_event and not support_recovered):
                    state.update({
                        "lifecycle_status": "COOLDOWN",
                        "blocked": True,
                    })
                else:
                    state.update({
                        "lifecycle_status": lifecycle_status,
                        "first_seen_date": evaluation_date,
                        "last_seen_date": evaluation_date,
                        "days_in_pool": 0,
                        "exit_date": "",
                        "exit_reason": "",
                        "cooldown_until_date": "",
                        "reentry_count": int(previous.get("reentry_count") or 0) + 1,
                        "last_event_key": event_key,
                        "blocked": False,
                    })
            else:
                first_seen = str(previous.get("first_seen_date") or evaluation_date)
                days_in_pool = _weekday_distance(first_seen, evaluation_date)
                state.update({
                    "lifecycle_status": lifecycle_status,
                    "first_seen_date": first_seen,
                    "days_in_pool": days_in_pool,
                    "last_event_key": event_key,
                })
                if days_in_pool >= max_watch_days:
                    state.update({
                        "lifecycle_status": "EXPIRED",
                        "exit_date": evaluation_date,
                        "exit_reason": "MAX_WATCH_DAYS_REACHED",
                        "cooldown_until_date": _add_weekdays_iso(evaluation_date, expired_cooldown_days),
                        "blocked": True,
                    })

        if not previous and not is_candidate:
            if _commit:
                conn.rollback()
            return state

        conn.execute(
            """INSERT INTO strategy6_candidate_lifecycle (
                   code, lifecycle_status, first_seen_date, last_seen_date, days_in_pool,
                   exit_date, exit_reason, cooldown_until_date, reentry_count, last_event_key, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(code) DO UPDATE SET
                   lifecycle_status=excluded.lifecycle_status,
                   first_seen_date=excluded.first_seen_date,
                   last_seen_date=excluded.last_seen_date,
                   days_in_pool=excluded.days_in_pool,
                   exit_date=excluded.exit_date,
                   exit_reason=excluded.exit_reason,
                   cooldown_until_date=excluded.cooldown_until_date,
                   reentry_count=excluded.reentry_count,
                   last_event_key=excluded.last_event_key,
                   updated_at=datetime('now')""",
            (
                state["code"], state["lifecycle_status"], state["first_seen_date"],
                state["last_seen_date"], state["days_in_pool"], state["exit_date"],
                state["exit_reason"], state["cooldown_until_date"], state["reentry_count"],
                state["last_event_key"],
            ),
        )
        if _commit:
            conn.commit()
        return state
    except Exception:
        if _commit:
            conn.rollback()
        raise


def persist_strategy6_evaluation(
    task_id: str,
    *,
    code: str,
    name: str,
    evaluation_date: str,
    candidate_type: str,
    lifecycle_status: str,
    event_key: str,
    reject_reasons: list[str],
    max_watch_days: int,
    expired_cooldown_days: int,
    failed_cooldown_days: int,
    candidate: dict | None,
    observation_candidate: dict | None = None,
) -> tuple[dict, dict | None]:
    """Atomically persist Strategy6 lifecycle, task audit and active candidate."""
    conn = get_conn()
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        lifecycle = update_strategy6_lifecycle(
            code=code,
            evaluation_date=evaluation_date,
            candidate_type=candidate_type,
            lifecycle_status=lifecycle_status,
            event_key=event_key,
            reject_reasons=reject_reasons,
            max_watch_days=max_watch_days,
            expired_cooldown_days=expired_cooldown_days,
            failed_cooldown_days=failed_cooldown_days,
            _conn=conn,
            _commit=False,
        )
        if lifecycle.get("first_seen_date"):
            save_strategy6_task_lifecycle(
                task_id,
                code=code,
                name=name,
                evaluation_date=evaluation_date,
                candidate_type=candidate_type,
                lifecycle=lifecycle,
                reject_reasons=reject_reasons,
                _conn=conn,
                _commit=False,
            )

        discovery = None
        if candidate is not None and not lifecycle["blocked"]:
            discovery = dict(candidate)
            discovery.update({
                "lifecycle_status": lifecycle["lifecycle_status"],
                "first_seen_date": lifecycle["first_seen_date"],
                "last_seen_date": lifecycle["last_seen_date"],
                "days_in_pool": lifecycle["days_in_pool"],
                "exit_date": lifecycle["exit_date"],
                "exit_reason": lifecycle["exit_reason"],
                "cooldown_until_date": lifecycle["cooldown_until_date"],
                "reentry_count": lifecycle["reentry_count"],
                "first_pool_date": lifecycle["first_seen_date"],
                "pool_age_trading_days": lifecycle["days_in_pool"],
            })
            upsert_strategy6_candidate(
                task_id,
                discovery,
                _conn=conn,
                _commit=False,
            )
        elif observation_candidate is not None:
            observation = dict(observation_candidate)
            if candidate is not None and lifecycle.get("blocked"):
                observation["vcp_observation_risk_tags"] = list(dict.fromkeys([
                    *observation.get("vcp_observation_risk_tags", []),
                    "TRADING_LIFECYCLE_BLOCKED",
                ]))
            upsert_strategy6_candidate(
                task_id,
                observation,
                _conn=conn,
                _commit=False,
            )
        conn.commit()
        return lifecycle, discovery
    except Exception:
        conn.rollback()
        raise


def _add_weekdays_iso(value: str, days: int) -> str:
    try:
        current = datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return ""
    added = 0
    while added < days:
        current += datetime.timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current.isoformat()


def save_strategy4_topic_index_ohlc(
    *,
    topic_id: str,
    topic_name: str,
    topic_type: str,
    source: str,
    rows: list[dict],
    source_topic_code: str = "",
    source_topic_name: str = "",
):
    """Save normalized Strategy4 topic index OHLC rows idempotently."""
    conn = get_conn()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with conn:
        for row in rows:
            conn.execute(
                """INSERT INTO strategy4_topic_index_ohlc (
                       topic_id, topic_name, topic_type, source, source_topic_code, source_topic_name,
                       date, open, high, low, close, volume, amount, turnover, change_pct,
                       fetched_at, data_version, raw_snapshot
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(topic_id, source, date) DO UPDATE SET
                       topic_name=excluded.topic_name,
                       topic_type=excluded.topic_type,
                       source_topic_code=excluded.source_topic_code,
                       source_topic_name=excluded.source_topic_name,
                       open=excluded.open,
                       high=excluded.high,
                       low=excluded.low,
                       close=excluded.close,
                       volume=excluded.volume,
                       amount=excluded.amount,
                       turnover=excluded.turnover,
                       change_pct=excluded.change_pct,
                       fetched_at=excluded.fetched_at,
                       data_version=excluded.data_version,
                       raw_snapshot=excluded.raw_snapshot,
                       updated_at=datetime('now')""",
                (
                    topic_id,
                    topic_name,
                    topic_type,
                    source,
                    source_topic_code,
                    source_topic_name or topic_name,
                    row.get("date", ""),
                    row.get("open", 0.0),
                    row.get("high", 0.0),
                    row.get("low", 0.0),
                    row.get("close", 0.0),
                    row.get("volume", 0.0),
                    row.get("amount", 0.0),
                    row.get("turnover", 0.0),
                    row.get("change_pct", 0.0),
                    row.get("fetched_at") or now,
                    row.get("data_version", "v1"),
                    _json_any(row.get("raw_snapshot")),
                ),
            )


def get_strategy4_topic_index_ohlc(
    topic_id: str,
    *,
    source: str | None = None,
    end_date: str | None = None,
    max_rows: int = 0,
) -> list[dict]:
    """Return Strategy4 topic index OHLC rows sorted ascending."""
    conn = get_conn()
    clauses = ["topic_id=?"]
    params: list = [topic_id]
    if source:
        clauses.append("source=?")
        params.append(source)
    if end_date:
        clauses.append("date<=?")
        params.append(end_date[:10])
    limit = ""
    if max_rows and max_rows > 0:
        limit = " LIMIT ?"
        params.append(max_rows)
    rows = conn.execute(
        f"""SELECT * FROM (
                SELECT * FROM strategy4_topic_index_ohlc
                WHERE {' AND '.join(clauses)}
                ORDER BY date DESC{limit}
            ) ORDER BY date ASC""",
        params,
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy4_topic_index_ohlc)").fetchall()]
    return [_deserialize_topic_index_row(dict(zip(cols, row))) for row in rows]


def save_strategy4_topic_index_fetch_status(
    *,
    topic_id: str,
    topic_name: str,
    topic_type: str,
    source: str,
    status: str,
    source_topic_code: str = "",
    source_topic_name: str = "",
    start_date: str = "",
    end_date: str = "",
    latest_date: str = "",
    rows_count: int = 0,
    error_code: str = "",
    error_message: str = "",
):
    """Record Strategy4 topic index fetch status for audit."""
    conn = get_conn()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with conn:
        conn.execute(
            """INSERT INTO strategy4_topic_index_fetch_status (
                   topic_id, topic_name, topic_type, source, source_topic_code, source_topic_name,
                   start_date, end_date, status, latest_date, rows_count, error_code, error_message, fetched_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                topic_id,
                topic_name,
                topic_type,
                source,
                source_topic_code,
                source_topic_name or topic_name,
                start_date,
                end_date,
                status,
                latest_date,
                rows_count,
                error_code,
                error_message,
                now,
            ),
        )


def get_latest_strategy4_topic_index_fetch_status(topic_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM strategy4_topic_index_fetch_status WHERE topic_id=? ORDER BY id DESC LIMIT 1",
        (topic_id,),
    ).fetchone()
    if not row:
        return None
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy4_topic_index_fetch_status)").fetchall()]
    return dict(zip(cols, row))


def get_strategy4_topic_index_topics(*, end_date: str | None = None) -> list[dict]:
    """Return distinct Strategy4 topic index identities with rows before end_date."""
    conn = get_conn()
    clauses = []
    params: list = []
    if end_date:
        clauses.append("date<=?")
        params.append(end_date[:10])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""SELECT topic_id, topic_name, topic_type, source, MAX(date) AS latest_date, COUNT(*) AS rows
            FROM strategy4_topic_index_ohlc
            {where}
            GROUP BY topic_id
            ORDER BY latest_date DESC, topic_id ASC""",
        params,
    ).fetchall()
    return [
        {
            "topic_id": row[0],
            "topic_name": row[1],
            "topic_type": row[2],
            "source": row[3],
            "latest_date": row[4],
            "rows": row[5],
        }
        for row in rows
    ]


def save_strategy4_topic_members(
    *,
    topic_id: str,
    topic_name: str,
    topic_type: str,
    source: str,
    membership_snapshot_date: str,
    membership_mode: str,
    members: list[dict],
):
    """Save Strategy4 topic members idempotently."""
    conn = get_conn()
    with conn:
        for member in members:
            code = str(member.get("code") or member.get("代码") or "")
            if not code:
                continue
            name = str(member.get("name") or member.get("名称") or "")
            conn.execute(
                """INSERT INTO strategy4_topic_members (
                       topic_id, topic_name, topic_type, code, name, source,
                       membership_snapshot_date, membership_mode, raw_snapshot, first_seen_at, last_seen_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                   ON CONFLICT(topic_id, code, membership_snapshot_date, source) DO UPDATE SET
                       topic_name=excluded.topic_name,
                       topic_type=excluded.topic_type,
                       name=excluded.name,
                       membership_mode=excluded.membership_mode,
                       raw_snapshot=excluded.raw_snapshot,
                       last_seen_at=datetime('now'),
                       updated_at=datetime('now')""",
                (
                    topic_id,
                    topic_name,
                    topic_type,
                    code,
                    name,
                    source,
                    membership_snapshot_date[:10],
                    membership_mode,
                    _json_any(member),
                ),
            )


def get_strategy4_topic_members(topic_id: str, *, evaluation_date: str | None = None) -> list[dict]:
    """Return latest members for a topic.

    Historical member snapshots on or before evaluation_date are preferred. If
    none exist, the latest current_members_proxy snapshot is returned and marked
    by its membership_mode so callers can surface the bias.
    """
    conn = get_conn()
    if evaluation_date:
        row = conn.execute(
            """SELECT membership_snapshot_date, source
               FROM strategy4_topic_members
               WHERE topic_id=? AND membership_mode!='current_members_proxy'
                 AND membership_snapshot_date<=?
               ORDER BY membership_snapshot_date DESC, id DESC LIMIT 1""",
            (topic_id, evaluation_date[:10]),
        ).fetchone()
        if row:
            return _strategy4_members_for_snapshot(topic_id, row[0], row[1])
    row = conn.execute(
        """SELECT membership_snapshot_date, source
           FROM strategy4_topic_members
           WHERE topic_id=?
           ORDER BY CASE WHEN membership_mode='current_members_proxy' THEN 0 ELSE 1 END,
                    membership_snapshot_date DESC, id DESC
           LIMIT 1""",
        (topic_id,),
    ).fetchone()
    if not row:
        return []
    return _strategy4_members_for_snapshot(topic_id, row[0], row[1])


def get_strategy4_topics_for_member(code: str, *, evaluation_date: str | None = None) -> list[dict]:
    """Return Strategy4 topics whose latest eligible member snapshot contains code."""
    conn = get_conn()
    clauses = ["code=?"]
    params: list = [code]
    if evaluation_date:
        clauses.append("membership_snapshot_date<=?")
        params.append(evaluation_date[:10])
    rows = conn.execute(
        f"""SELECT topic_id, topic_name, topic_type, source, membership_snapshot_date, membership_mode
            FROM strategy4_topic_members
            WHERE {' AND '.join(clauses)}
            ORDER BY CASE WHEN membership_mode='current_members_proxy' THEN 1 ELSE 0 END,
                     membership_snapshot_date DESC, id DESC""",
        params,
    ).fetchall()
    seen: set[str] = set()
    topics: list[dict] = []
    for row in rows:
        topic_id = row[0]
        if topic_id in seen:
            continue
        seen.add(topic_id)
        topics.append({
            "topic_id": topic_id,
            "topic_name": row[1],
            "topic_type": row[2],
            "source": row[3],
            "membership_snapshot_date": row[4],
            "membership_mode": row[5],
        })
    return topics


def _strategy4_members_for_snapshot(topic_id: str, snapshot_date: str, source: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM strategy4_topic_members
           WHERE topic_id=? AND membership_snapshot_date=? AND source=?
           ORDER BY code ASC""",
        (topic_id, snapshot_date, source),
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy4_topic_members)").fetchall()]
    result = []
    for row in rows:
        item = dict(zip(cols, row))
        raw = item.get("raw_snapshot")
        if isinstance(raw, str) and raw:
            try:
                item["raw_snapshot"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                item["raw_snapshot"] = {}
        elif not raw:
            item["raw_snapshot"] = {}
        result.append(item)
    return result


def replace_strategy4_derived_hot_topics(task_id: str, evaluation_date: str, topics: list[dict]):
    """Replace derived hot-topic audit rows for one task/date."""
    conn = get_conn()
    with conn:
        conn.execute(
            "DELETE FROM strategy4_derived_hot_topics WHERE task_id=? AND evaluation_date=?",
            (task_id, evaluation_date[:10]),
        )
        for item in topics:
            raw = item.get("raw_snapshot") or {}
            conn.execute(
                """INSERT INTO strategy4_derived_hot_topics (
                       task_id, evaluation_date, topic_id, topic_name, topic_type, source,
                       membership_mode, derived_hot_score, status, topic_index_latest_date,
                       topic_index_phase, topic_index_context, breadth_snapshot, reasons,
                       warnings, raw_snapshot
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    evaluation_date[:10],
                    item.get("topic_id", ""),
                    item.get("topic_name", ""),
                    item.get("topic_type", ""),
                    item.get("source", ""),
                    item.get("membership_mode", ""),
                    item.get("derived_hot_score", item.get("hot_topic_score", 0.0)),
                    item.get("status", ""),
                    item.get("topic_index_latest_date", ""),
                    item.get("topic_index_phase", ""),
                    _json_any(raw.get("topic_index_context")),
                    _json_any(raw.get("breadth_snapshot")),
                    _json_any(item.get("reasons")),
                    _json_any(item.get("merge_warnings")),
                    _json_any(raw),
                ),
            )


def replace_strategy4_derived_leaders(task_id: str, evaluation_date: str, leaders: list[dict]):
    """Replace derived leader audit rows for one task/date."""
    conn = get_conn()
    with conn:
        conn.execute(
            "DELETE FROM strategy4_derived_leaders WHERE task_id=? AND evaluation_date=?",
            (task_id, evaluation_date[:10]),
        )
        for item in leaders:
            raw = item.get("raw_snapshot") or {}
            conn.execute(
                """INSERT INTO strategy4_derived_leaders (
                       task_id, evaluation_date, topic_id, topic_name, topic_type, code,
                       name, source, membership_mode, derived_leader_score, leader_type,
                       status, leader_rs_5d, leader_rs_10d, leader_rs_20d,
                       return_rank_in_topic, amount_rank_in_topic, raw_snapshot
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    evaluation_date[:10],
                    item.get("topic_id", ""),
                    item.get("topic_name", ""),
                    item.get("topic_type", ""),
                    item.get("code", ""),
                    item.get("name", ""),
                    item.get("source", ""),
                    item.get("membership_mode", ""),
                    item.get("derived_leader_score", item.get("leader_strength_score", 0.0)),
                    item.get("leader_type", ""),
                    item.get("status", ""),
                    raw.get("leader_rs_5d"),
                    raw.get("leader_rs_10d"),
                    raw.get("leader_rs_20d"),
                    item.get("return_rank_in_topic"),
                    item.get("amount_rank_in_topic"),
                    _json_any(raw),
                ),
            )


def upsert_strategy4_tracked_topic(item: dict):
    """Insert or update one Strategy4 tracked topic lifecycle row."""
    conn = get_conn()
    columns = [
        "topic_id", "topic_name", "topic_type", "first_detected_date",
        "last_confirmed_date", "last_evaluated_date", "age_calendar_days",
        "tracking_status", "tracking_phase", "source_status", "peak_hot_score",
        "latest_hot_score", "topic_index_phase", "topic_index_latest_date",
        "source_modes_json", "membership_mode", "invalid_reason", "risk_flags",
        "raw_snapshot",
    ]
    values = [
        item.get("topic_id", ""),
        item.get("topic_name", ""),
        item.get("topic_type", ""),
        item.get("first_detected_date", ""),
        item.get("last_confirmed_date", ""),
        item.get("last_evaluated_date", ""),
        item.get("age_calendar_days", 0),
        item.get("tracking_status", ""),
        item.get("tracking_phase", ""),
        item.get("source_status", ""),
        item.get("peak_hot_score", 0.0),
        item.get("latest_hot_score", 0.0),
        item.get("topic_index_phase", ""),
        item.get("topic_index_latest_date", ""),
        _json_any(item.get("source_modes")),
        item.get("membership_mode", ""),
        item.get("invalid_reason", ""),
        _json_any(item.get("risk_flags")),
        _json_any(item.get("raw_snapshot")),
    ]
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c != "topic_id")
    conn.execute(
        f"""INSERT INTO strategy4_tracked_topics ({', '.join(columns)})
            VALUES ({', '.join('?' for _ in columns)})
            ON CONFLICT(topic_id) DO UPDATE SET {updates}, updated_at=datetime('now')""",
        values,
    )
    conn.commit()


def upsert_strategy4_tracked_leader(item: dict):
    """Insert or update one Strategy4 tracked leader lifecycle row."""
    conn = get_conn()
    columns = [
        "topic_id", "topic_name", "code", "name", "first_detected_date",
        "last_confirmed_date", "last_evaluated_date", "tracking_status",
        "tracking_phase", "source_status", "peak_leader_score", "latest_leader_score",
        "first_wave_high", "first_wave_high_date", "pullback_pct", "pullback_days",
        "support_price", "stop_loss", "target_price", "risk_ratio",
        "reward_risk_ratio", "candidate_origin", "topic_first_detected_date",
        "topic_last_confirmed_date", "leader_first_detected_date",
        "leader_last_confirmed_date", "tracking_age_days", "membership_mode",
        "invalid_reason", "risk_flags", "raw_snapshot",
    ]
    values = [
        item.get("topic_id", ""),
        item.get("topic_name", ""),
        item.get("code", ""),
        item.get("name", ""),
        item.get("first_detected_date", ""),
        item.get("last_confirmed_date", ""),
        item.get("last_evaluated_date", ""),
        item.get("tracking_status", ""),
        item.get("tracking_phase", ""),
        item.get("source_status", ""),
        item.get("peak_leader_score", 0.0),
        item.get("latest_leader_score", 0.0),
        item.get("first_wave_high", 0.0),
        item.get("first_wave_high_date", ""),
        item.get("pullback_pct", 0.0),
        item.get("pullback_days", 0),
        item.get("support_price", 0.0),
        item.get("stop_loss", 0.0),
        item.get("target_price", 0.0),
        item.get("risk_ratio", 0.0),
        item.get("reward_risk_ratio", 0.0),
        item.get("candidate_origin", "tracking_pool"),
        item.get("topic_first_detected_date", ""),
        item.get("topic_last_confirmed_date", ""),
        item.get("leader_first_detected_date", item.get("first_detected_date", "")),
        item.get("leader_last_confirmed_date", item.get("last_confirmed_date", "")),
        item.get("tracking_age_days", 0),
        item.get("membership_mode", ""),
        item.get("invalid_reason", ""),
        _json_any(item.get("risk_flags")),
        _json_any(item.get("raw_snapshot")),
    ]
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("topic_id", "code"))
    conn.execute(
        f"""INSERT INTO strategy4_tracked_leaders ({', '.join(columns)})
            VALUES ({', '.join('?' for _ in columns)})
            ON CONFLICT(topic_id, code) DO UPDATE SET {updates}, updated_at=datetime('now')""",
        values,
    )
    conn.commit()


def get_strategy4_tracked_topic(topic_id: str) -> dict | None:
    rows = get_strategy4_tracked_topics(topic_id=topic_id, include_expired=True)
    return rows[0] if rows else None


def get_strategy4_tracked_leader(topic_id: str, code: str) -> dict | None:
    rows = get_strategy4_tracked_leaders(topic_id=topic_id, code=code, include_expired=True)
    return rows[0] if rows else None


def get_strategy4_tracked_topics(
    *,
    status: str | None = None,
    topic_id: str | None = None,
    include_expired: bool = True,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    conn = get_conn()
    clauses = []
    params: list = []
    if status:
        clauses.append("tracking_status=?")
        params.append(status)
    if topic_id:
        clauses.append("topic_id=?")
        params.append(topic_id)
    if not include_expired:
        clauses.append("tracking_status NOT IN ('EXPIRED', 'INVALIDATED')")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    rows = conn.execute(
        f"""SELECT * FROM strategy4_tracked_topics
            {where}
            ORDER BY last_evaluated_date DESC, peak_hot_score DESC, topic_name ASC
            LIMIT ? OFFSET ?""",
        params,
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy4_tracked_topics)").fetchall()]
    return [_deserialize_strategy4_tracking_row(dict(zip(cols, row))) for row in rows]


def get_strategy4_tracked_leaders(
    *,
    status: str | None = None,
    topic_id: str | None = None,
    code: str | None = None,
    include_expired: bool = True,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    conn = get_conn()
    clauses = []
    params: list = []
    if status:
        clauses.append("tracking_status=?")
        params.append(status)
    if topic_id:
        clauses.append("topic_id=?")
        params.append(topic_id)
    if code:
        clauses.append("code=?")
        params.append(code)
    if not include_expired:
        clauses.append("tracking_status NOT IN ('EXPIRED', 'INVALIDATED')")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    rows = conn.execute(
        f"""SELECT * FROM strategy4_tracked_leaders
            {where}
            ORDER BY last_evaluated_date DESC, reward_risk_ratio DESC, latest_leader_score DESC, code ASC
            LIMIT ? OFFSET ?""",
        params,
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy4_tracked_leaders)").fetchall()]
    return [_deserialize_strategy4_tracking_row(dict(zip(cols, row))) for row in rows]


def insert_strategy4_tracking_event(item: dict):
    """Append one lifecycle audit event."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO strategy4_tracking_events (
               evaluation_date, task_id, entity_type, topic_id, code,
               previous_status, new_status, event_type, reason, metrics_snapshot
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            item.get("evaluation_date", ""),
            item.get("task_id", ""),
            item.get("entity_type", ""),
            item.get("topic_id", ""),
            item.get("code", ""),
            item.get("previous_status", ""),
            item.get("new_status", ""),
            item.get("event_type", ""),
            item.get("reason", ""),
            _json_any(item.get("metrics_snapshot")),
        ),
    )
    conn.commit()


def get_strategy4_tracking_events(
    *,
    topic_id: str | None = None,
    code: str | None = None,
    task_id: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    conn = get_conn()
    clauses = []
    params: list = []
    if topic_id:
        clauses.append("topic_id=?")
        params.append(topic_id)
    if code:
        clauses.append("code=?")
        params.append(code)
    if task_id:
        clauses.append("task_id=?")
        params.append(task_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    rows = conn.execute(
        f"""SELECT * FROM strategy4_tracking_events
            {where}
            ORDER BY evaluation_date DESC, id DESC
            LIMIT ? OFFSET ?""",
        params,
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy4_tracking_events)").fetchall()]
    return [_deserialize_strategy4_tracking_row(dict(zip(cols, row))) for row in rows]


def _json_any(value):
    if value is None or value == "":
        return ""
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _json_default(value):
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, set):
        return list(value)
    return str(value)


def _deserialize_topic_index_row(row: dict) -> dict:
    value = row.get("raw_snapshot")
    if isinstance(value, str) and value:
        try:
            row["raw_snapshot"] = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            row["raw_snapshot"] = {}
    elif not value:
        row["raw_snapshot"] = {}
    return row


def _deserialize_strategy4_row(row: dict) -> dict:
    for field in (
        "raw_snapshot", "evaluation_snapshot", "source_modes_json", "merge_warnings",
        "tracking_reasons", "tracking_risk_flags", "invalid_conditions",
    ):
        value = row.get(field)
        if isinstance(value, str) and value:
            try:
                parsed = json.loads(value)
                if field == "source_modes_json":
                    row["source_modes"] = parsed
                else:
                    row[field] = parsed
            except (json.JSONDecodeError, TypeError):
                if field == "source_modes_json":
                    row["source_modes"] = []
                elif field in {"merge_warnings", "tracking_reasons", "tracking_risk_flags", "invalid_conditions"}:
                    row[field] = []
                else:
                    row[field] = {}
        elif not value:
            if field == "source_modes_json":
                row["source_modes"] = []
            elif field in {"merge_warnings", "tracking_reasons", "tracking_risk_flags", "invalid_conditions"}:
                row[field] = []
            else:
                row[field] = {}
    return row


def _deserialize_strategy5_row(row: dict) -> dict:
    for field in (
        "risk_tags", "warn_tags", "reject_reasons", "score_reasons",
        "volume_dry_reasons", "volume_dry_warnings", "volume_dry_rejects",
    ):
        value = row.get(field)
        if isinstance(value, str) and value:
            try:
                row[field] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                row[field] = []
        elif not value:
            row[field] = []
    if "dry_support_valid" in row:
        row["dry_support_valid"] = bool(row.get("dry_support_valid"))
    return row


def _strategy6_safe_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _strategy6_safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def _deserialize_strategy6_row(row: dict) -> dict:
    for field in (
        "enable_sector_filter",
        "sector_filter_mode",
        "sector_strength_status",
        "relative_strength_10_sector",
        "sector_member_new_high_count",
    ):
        row.pop(field, None)
    for field in (
        "risk_tags", "warn_tags", "reject_reasons", "score_reasons",
        "support_cluster_sources", "execution_notes",
        "compact_kline_reasons", "compact_kline_risk_tags",
        "start_failure_reasons", "setup_quality_reasons", "setup_quality_risk_tags",
        "support_reaction_reasons", "support_reaction_risk_tags",
        "vcp_contractions", "vcp_observation_reasons", "vcp_observation_risk_tags",
        "vcp_quality_reasons", "vcp_quality_warnings",
    ):
        value = row.get(field)
        if isinstance(value, str) and value:
            try:
                row[field] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                row[field] = []
        elif not value:
            row[field] = []
    for field in (
        "is_limit_up", "is_one_word_limit_up", "enable_market_filter",
        "relative_strength_20_observed", "original_tail_pass", "box_tail_enabled",
        "box_tail_pass", "tail_pass", "compact_kline_enabled", "compact_kline_pass",
        "brooks_tail_enabled", "brooks_tail_pass", "brooks_tail_premium",
        "brooks_trade_ready", "multi_path_confirmed",
        "vcp_observation_eligible", "vcp_exit_audit", "vcp_history_qualified",
    ):
        if field in row:
            row[field] = _strategy6_safe_bool(row.get(field))
    for field in ("original_tail_score", "box_tail_score", "brooks_tail_score"):
        if field in row:
            row[field] = _strategy6_safe_int(row.get(field))
    raw_tail_paths = row.get("tail_paths")
    if isinstance(raw_tail_paths, str) and raw_tail_paths:
        try:
            tail_paths = json.loads(raw_tail_paths)
        except (json.JSONDecodeError, TypeError):
            tail_paths = []
    elif isinstance(raw_tail_paths, list):
        tail_paths = raw_tail_paths
    else:
        tail_paths = []
    if not isinstance(tail_paths, list):
        tail_paths = []
    tail_paths = [str(path) for path in tail_paths if path]
    legacy_paths = not tail_paths
    if legacy_paths:
        if row.get("original_tail_pass"):
            tail_paths.append("ORIGINAL")
        if row.get("box_tail_pass"):
            tail_paths.append("BOX")
        if row.get("brooks_tail_pass"):
            tail_paths.append("BROOKS")
    row["tail_paths"] = tail_paths

    brooks_json = row.pop("brooks_result_json", None)
    if isinstance(brooks_json, str) and brooks_json:
        try:
            brooks_result = json.loads(brooks_json)
        except (json.JSONDecodeError, TypeError):
            brooks_result = {}
    elif isinstance(brooks_json, dict):
        brooks_result = brooks_json
    else:
        brooks_result = {}
    row["brooks_result"] = brooks_result if isinstance(brooks_result, dict) else {}

    if not row.get("brooks_status"):
        row["brooks_status"] = "BROOKS_DISABLED"
    row["brooks_trade_trigger_type"] = row.get("brooks_trade_trigger_type") or ""
    row["brooks_trigger_price"] = row.get("brooks_trigger_price")
    row["brooks_trigger_valid_until"] = row.get("brooks_trigger_valid_until") or ""
    if not row.get("tail_path_summary"):
        row["tail_path_summary"] = (
            "MULTI" if len(tail_paths) > 1 else tail_paths[0] if tail_paths else "NONE"
        )
    if not row.get("tail_primary_path"):
        score_by_path = {
            "ORIGINAL": row.get("original_tail_score", 0),
            "BOX": row.get("box_tail_score", 0),
            "BROOKS": row.get("brooks_tail_score", 0),
        }
        priority = {"ORIGINAL": 0, "BOX": 1, "BROOKS": 2}
        row["tail_primary_path"] = max(
            tail_paths,
            key=lambda path: (score_by_path.get(path, 0), priority.get(path, -1)),
            default="NONE",
        )
    if legacy_paths:
        row["passed_path_count"] = len(tail_paths)
        row["multi_path_confirmed"] = len(tail_paths) > 1
    row["tail_segmentation_status"] = row.get("tail_segmentation_status") or "FIXED_WINDOW"
    row["relative_strength_trend"] = row.get("relative_strength_trend") or "UNKNOWN"
    row["entry_archetype"] = row.get("entry_archetype") or "NONE"
    # A missing version identifies a pre-V2 row.  Keep it empty so clients do
    # not present migration defaults such as zero scores as measured V2 data.
    row["score_model_version"] = row.get("score_model_version") or ""
    row["vcp_lifecycle_status"] = row.get("vcp_lifecycle_status") or "VCP_NONE"
    for field in (
        "vcp_origin_start_date", "vcp_pattern_start_date", "vcp_pattern_end_date",
        "vcp_breakout_date", "vcp_invalidation_reason",
    ):
        row[field] = row.get(field) or ""
    for field in ("vcp_contraction_count", "vcp_days_since_breakout"):
        row[field] = _strategy6_safe_int(row.get(field))
    for field in ("vcp_pivot_price", "vcp_structure_low", "vcp_distance_to_pivot_pct"):
        row[field] = float(row.get(field) or 0.0)
    return row


def _deserialize_strategy4_tracking_row(row: dict) -> dict:
    for field in ("source_modes_json", "risk_flags", "raw_snapshot", "metrics_snapshot"):
        value = row.get(field)
        if isinstance(value, str) and value:
            try:
                parsed = json.loads(value)
                if field == "source_modes_json":
                    row["source_modes"] = parsed
                else:
                    row[field] = parsed
            except (json.JSONDecodeError, TypeError):
                if field == "source_modes_json":
                    row["source_modes"] = []
                elif field == "risk_flags":
                    row[field] = []
                else:
                    row[field] = {}
        elif not value:
            if field == "source_modes_json":
                row["source_modes"] = []
            elif field == "risk_flags":
                row[field] = []
            else:
                row[field] = {}
    return row


# ═══════════════════════════════════════════════════════════════════════════════
# Strategy2 Backtest Tables
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_strategy2_backtest_tables(conn: sqlite3.Connection):
    """Create strategy2 backtest tables if not exists (Phase 1 compatible migration)."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy2_backtest_tasks (
            id                       TEXT PRIMARY KEY,
            status                   TEXT NOT NULL DEFAULT 'running',
            requested_start_date     TEXT,
            requested_end_date       TEXT,
            actual_start_date        TEXT,
            actual_end_date          TEXT,
            actual_evaluation_start_date TEXT,
            actual_evaluation_end_date TEXT,
            observation_data_end_date   TEXT,
            scope_type               TEXT NOT NULL DEFAULT 'market',
            requested_codes          TEXT,
            max_stocks               INTEGER,
            config_snapshot          TEXT NOT NULL,
            total_stocks             INTEGER DEFAULT 0,
            processed_stocks         INTEGER DEFAULT 0,
            stocks_with_opportunities INTEGER DEFAULT 0,
            opportunities_count      INTEGER DEFAULT 0,
            insufficient_stocks_count INTEGER DEFAULT 0,
            failed_stocks_count      INTEGER DEFAULT 0,
            started_at               TEXT,
            finished_at              TEXT,
            elapsed_seconds          REAL,
            current_code             TEXT,
            current_name             TEXT,
            error                    TEXT,
            backtest_engine_version  TEXT,
            strategy_engine_version  TEXT,
            credibility_status       TEXT,
            execution_model          TEXT,
            sampling_method          TEXT,
            sampling_seed            INTEGER,
            data_snapshot_date       TEXT,
            data_revision_version    TEXT,
            estimated_evaluations    INTEGER DEFAULT 0,
            completed_evaluations    INTEGER DEFAULT 0,
            raw_signals_count        INTEGER DEFAULT 0,
            evaluation_error_days    INTEGER DEFAULT 0,
            summary_json             TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy2_backtest_opportunities (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id               TEXT NOT NULL,
            code                  TEXT NOT NULL,
            name                  TEXT,
            first_detected_date   TEXT NOT NULL,
            last_detected_date    TEXT NOT NULL,
            consecutive_hit_days  INTEGER NOT NULL,
            first_score           INTEGER NOT NULL,
            max_score             INTEGER NOT NULL,
            level                 TEXT,
            entry_close           REAL NOT NULL,
            stop_loss             REAL NOT NULL,
            risk_ratio            REAL,
            trend_type            TEXT,
            trend_evidence_score  INTEGER,
            evaluation_snapshot   TEXT,
            horizon_3             TEXT,
            horizon_5             TEXT,
            horizon_10            TEXT,
            horizon_20            TEXT,
            created_at            TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (task_id) REFERENCES strategy2_backtest_tasks(id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy2_backtest_signals (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id               TEXT NOT NULL,
            code                  TEXT NOT NULL,
            name                  TEXT,
            evaluation_date       TEXT NOT NULL,
            evaluation_index      INTEGER NOT NULL,
            score                 INTEGER NOT NULL,
            level                 TEXT,
            current_close         REAL NOT NULL,
            stop_loss             REAL,
            risk_ratio            REAL,
            volume_dry_score      INTEGER,
            price_stable_score    INTEGER,
            trend_type            TEXT,
            trend_evidence_score  INTEGER,
            evaluation_snapshot   TEXT NOT NULL,
            UNIQUE (task_id, code, evaluation_date)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy2_backtest_insufficient_stocks (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id          TEXT NOT NULL,
            code             TEXT NOT NULL,
            name             TEXT,
            reason_code      TEXT NOT NULL,
            available_days   INTEGER DEFAULT 0,
            required_days    INTEGER DEFAULT 0,
            earliest_date    TEXT,
            latest_date      TEXT,
            actual_start_date    TEXT,
            actual_end_date      TEXT,
            detail               TEXT,
            FOREIGN KEY (task_id) REFERENCES strategy2_backtest_tasks(id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy2_backtest_task_stocks (
            task_id                  TEXT NOT NULL,
            code                     TEXT NOT NULL,
            name                     TEXT,
            status                   TEXT NOT NULL DEFAULT 'PENDING',
            available_days           INTEGER DEFAULT 0,
            actual_eval_start_date   TEXT,
            actual_eval_end_date     TEXT,
            evaluation_days          INTEGER DEFAULT 0,
            liquidity_filtered_days  INTEGER DEFAULT 0,
            trend_filtered_days      INTEGER DEFAULT 0,
            rejection_failed_days    INTEGER DEFAULT 0,
            score_failed_days        INTEGER DEFAULT 0,
            risk_failed_days         INTEGER DEFAULT 0,
            invalid_data_days        INTEGER DEFAULT 0,
            evaluation_error_days    INTEGER DEFAULT 0,
            raw_signals_count        INTEGER DEFAULT 0,
            opportunities_count      INTEGER DEFAULT 0,
            error_code               TEXT,
            error_detail             TEXT,
            started_at               TEXT,
            finished_at              TEXT,
            PRIMARY KEY (task_id, code)
        )
    ''')
    # Indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s2_bt_task_status ON strategy2_backtest_tasks(status, started_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s2_bt_opp_task ON strategy2_backtest_opportunities(task_id, first_detected_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s2_bt_opp_stock ON strategy2_backtest_opportunities(task_id, code, first_detected_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s2_bt_insuf_task ON strategy2_backtest_insufficient_stocks(task_id, reason_code)")
    # Phase 1 unique indexes
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_s2_bt_signal ON strategy2_backtest_signals(task_id, code, evaluation_date)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_s2_bt_opp ON strategy2_backtest_opportunities(task_id, code, first_detected_date)")

    # Compatible migration: add execution columns to opportunities
    _ensure_column(conn, "strategy2_backtest_opportunities", "first_signal_id", "INTEGER")
    _ensure_column(conn, "strategy2_backtest_opportunities", "last_signal_id", "INTEGER")
    _ensure_column(conn, "strategy2_backtest_opportunities", "signal_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_opportunities", "execution_model", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "entry_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "entry_price", "REAL")
    _ensure_column(conn, "strategy2_backtest_opportunities", "exit_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "exit_price", "REAL")
    _ensure_column(conn, "strategy2_backtest_opportunities", "exit_reason", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "realized_return", "REAL")
    _ensure_column(conn, "strategy2_backtest_opportunities", "mark_to_market_end_return", "REAL")
    _ensure_column(conn, "strategy2_backtest_opportunities", "holding_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_opportunities", "available_forward_days", "INTEGER DEFAULT 0")

    # Task table migration: add Phase 1 fields
    _ensure_column(conn, "strategy2_backtest_tasks", "backtest_engine_version", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "strategy_engine_version", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "credibility_status", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "execution_model", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "sampling_method", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "sampling_seed", "INTEGER")
    _ensure_column(conn, "strategy2_backtest_tasks", "data_snapshot_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "data_revision_id", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "data_revision_version", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "actual_evaluation_start_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "actual_evaluation_end_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "observation_data_end_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "estimated_evaluations", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "completed_evaluations", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "raw_signals_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "evaluation_error_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "summary_json", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "experiment_snapshot", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "baseline_task_id", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "comparison_summary_json", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "experiment_filtered_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "experiment_volume_filtered_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "experiment_score_filtered_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "entry_confirmation_failed_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "time_exit_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_signals", "baseline_passed", "INTEGER DEFAULT 1")
    _ensure_column(conn, "strategy2_backtest_signals", "experiment_passed", "INTEGER DEFAULT 1")
    _ensure_column(conn, "strategy2_backtest_signals", "experiment_filter_reason", "TEXT")
    _ensure_column(conn, "strategy2_backtest_signals", "opportunity_type", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "opportunity_type", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "volume_dry_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_opportunities", "price_stable_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_opportunities", "entry_confirmation_type", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "entry_confirmation_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "entry_confirmation_price", "REAL")
    _ensure_column(conn, "strategy2_backtest_opportunities", "entry_confirmation_status", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "time_exit_days", "INTEGER")
    _ensure_column(conn, "strategy2_backtest_opportunities", "market_context_json", "TEXT")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "experiment_filtered_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "experiment_volume_filtered_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "experiment_score_filtered_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "entry_confirmation_failed_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "time_exit_count", "INTEGER DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s2_bt_task_baseline ON strategy2_backtest_tasks(baseline_task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s2_bt_signal_experiment ON strategy2_backtest_signals(task_id, experiment_passed, experiment_filter_reason)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s2_bt_opp_type ON strategy2_backtest_opportunities(task_id, opportunity_type)")

    # Mark old tasks as untrusted
    conn.execute(
        "UPDATE strategy2_backtest_tasks SET credibility_status='LEGACY_UNTRUSTED', "
        "backtest_engine_version='legacy-v1' "
        "WHERE credibility_status IS NULL"
    )
    # task_stocks missing columns
    _ensure_column(conn, "strategy2_backtest_task_stocks", "required_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "observation_data_end_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "available_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "earliest_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "latest_date", "TEXT")

    from strategy2.version import (
        STRATEGY2_BACKTEST_ENGINE_VERSION,
        STRATEGY2_STRATEGY_ENGINE_VERSION,
    )
    # Historical tasks cannot remain trusted if they fail current baseline rules.
    conn.execute(
        "UPDATE strategy2_backtest_tasks "
        "SET credibility_status='LEGACY_UNTRUSTED', "
        "backtest_engine_version=COALESCE(backtest_engine_version, 'legacy-v1') "
        "WHERE credibility_status='TRUSTED_BASELINE' AND ("
        "LOWER(COALESCE(status, '')) <> 'completed' "
        "OR COALESCE(data_revision_id, '') = '' "
        "OR COALESCE(data_revision_version, '') <> ? "
        "OR COALESCE(backtest_engine_version, '') <> ? "
        "OR COALESCE(strategy_engine_version, '') <> ? "
        "OR summary_json IS NULL "
        "OR COALESCE(processed_stocks, 0) <> COALESCE(total_stocks, 0) "
        "OR COALESCE(failed_stocks_count, 0) > 0 "
        "OR COALESCE(evaluation_error_days, 0) > 0 "
        "OR EXISTS (SELECT 1 FROM strategy2_backtest_task_stocks s "
        "           WHERE s.task_id=strategy2_backtest_tasks.id "
        "             AND s.status IN ('PENDING','RUNNING'))"
        ")",
        (
            STRATEGY2_DATA_REVISION_VERSION,
            STRATEGY2_BACKTEST_ENGINE_VERSION,
            STRATEGY2_STRATEGY_ENGINE_VERSION,
        ),
    )


def _ensure_strategy3_backtest_tables(conn: sqlite3.Connection):
    """Create strategy3 local DB backtest tables with compatible schema."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy3_backtest_tasks (
            id                           TEXT PRIMARY KEY,
            status                       TEXT NOT NULL DEFAULT 'running',
            requested_start_date          TEXT,
            requested_end_date            TEXT,
            scope_type                    TEXT,
            requested_codes               TEXT,
            max_stocks                    INTEGER DEFAULT 0,
            config_snapshot               TEXT NOT NULL,
            total_stocks                  INTEGER DEFAULT 0,
            processed_stocks              INTEGER DEFAULT 0,
            stocks_with_opportunities      INTEGER DEFAULT 0,
            opportunities_count            INTEGER DEFAULT 0,
            insufficient_stocks_count      INTEGER DEFAULT 0,
            failed_stocks_count           INTEGER DEFAULT 0,
            started_at                    TEXT,
            finished_at                   TEXT,
            elapsed_seconds                REAL,
            error                         TEXT,
            backtest_engine_version       TEXT,
            strategy_engine_version       TEXT,
            credibility_status            TEXT,
            execution_model               TEXT,
            sampling_method               TEXT,
            sampling_seed                 INTEGER,
            data_snapshot_date            TEXT,
            data_revision_id              TEXT,
            data_revision_version         TEXT,
            actual_evaluation_start_date  TEXT,
            actual_evaluation_end_date    TEXT,
            observation_data_end_date      TEXT,
            estimated_evaluations         INTEGER DEFAULT 0,
            completed_evaluations         INTEGER DEFAULT 0,
            raw_signals_count             INTEGER DEFAULT 0,
            evaluation_error_days         INTEGER DEFAULT 0,
            summary_json                  TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy3_backtest_signals (
            id                         INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id                    TEXT NOT NULL,
            code                       TEXT NOT NULL,
            name                       TEXT,
            evaluation_date            TEXT NOT NULL,
            evaluation_index           INTEGER NOT NULL,
            total_score                INTEGER DEFAULT 0,
            level                      TEXT,
            current_close              REAL,
            trend_score                INTEGER DEFAULT 0,
            pullback_score             INTEGER DEFAULT 0,
            volume_stability_score     INTEGER DEFAULT 0,
            second_breakout_score      INTEGER DEFAULT 0,
            risk_reward_score          INTEGER DEFAULT 0,
            trade_state                TEXT,
            trade_state_label          TEXT,
            trade_quality_score        INTEGER DEFAULT 0,
            volume_dry_score           INTEGER DEFAULT 0,
            price_stability_score      INTEGER DEFAULT 0,
            cannot_fall_score          INTEGER DEFAULT 0,
            balance_powerless_score    INTEGER DEFAULT 0,
            support_price              REAL,
            stop_loss                  REAL,
            target_price               REAL,
            risk_ratio                 REAL,
            rr1                        REAL,
            pullback_pct               REAL,
            volume_ratio_5_20          REAL,
            evaluation_snapshot        TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES strategy3_backtest_tasks(id),
            UNIQUE (task_id, code, evaluation_date)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy3_backtest_opportunities (
            id                         INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id                    TEXT NOT NULL,
            code                       TEXT NOT NULL,
            name                       TEXT,
            first_detected_date        TEXT NOT NULL,
            last_detected_date         TEXT NOT NULL,
            consecutive_hit_days       INTEGER DEFAULT 0,
            first_score                INTEGER DEFAULT 0,
            max_score                  INTEGER DEFAULT 0,
            level                      TEXT,
            trade_state                TEXT,
            trade_state_label          TEXT,
            trade_quality_score        INTEGER DEFAULT 0,
            entry_close                REAL,
            support_price              REAL,
            stop_loss                  REAL,
            target_price               REAL,
            risk_ratio                 REAL,
            rr1                        REAL,
            trend_score                INTEGER DEFAULT 0,
            pullback_score             INTEGER DEFAULT 0,
            volume_stability_score     INTEGER DEFAULT 0,
            second_breakout_score      INTEGER DEFAULT 0,
            risk_reward_score          INTEGER DEFAULT 0,
            volume_dry_score           INTEGER DEFAULT 0,
            price_stability_score      INTEGER DEFAULT 0,
            cannot_fall_score          INTEGER DEFAULT 0,
            balance_powerless_score    INTEGER DEFAULT 0,
            pullback_pct               REAL,
            volume_ratio_5_20          REAL,
            evaluation_snapshot        TEXT NOT NULL,
            horizon_5                  TEXT,
            horizon_10                 TEXT,
            horizon_20                 TEXT,
            signal_count               INTEGER DEFAULT 0,
            execution_model            TEXT,
            entry_date                 TEXT,
            entry_price                REAL,
            exit_date                  TEXT,
            exit_price                 REAL,
            exit_reason                TEXT,
            realized_return            REAL,
            mark_to_market_end_return  REAL,
            holding_days               INTEGER DEFAULT 0,
            available_forward_days     INTEGER DEFAULT 0,
            first_signal_id            INTEGER,
            last_signal_id             INTEGER,
            FOREIGN KEY (task_id) REFERENCES strategy3_backtest_tasks(id),
            UNIQUE (task_id, code, first_detected_date)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy3_backtest_insufficient_stocks (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id            TEXT NOT NULL,
            code               TEXT NOT NULL,
            name               TEXT,
            reason_code        TEXT NOT NULL,
            available_days     INTEGER DEFAULT 0,
            required_days      INTEGER DEFAULT 0,
            earliest_date      TEXT,
            latest_date        TEXT,
            actual_start_date  TEXT,
            actual_end_date    TEXT,
            detail             TEXT,
            FOREIGN KEY (task_id) REFERENCES strategy3_backtest_tasks(id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy3_backtest_task_stocks (
            task_id                       TEXT NOT NULL,
            code                          TEXT NOT NULL,
            name                          TEXT,
            status                        TEXT NOT NULL DEFAULT 'PENDING',
            available_days                INTEGER DEFAULT 0,
            required_days                 INTEGER DEFAULT 0,
            earliest_date                 TEXT,
            latest_date                   TEXT,
            actual_eval_start_date        TEXT,
            actual_eval_end_date          TEXT,
            observation_data_end_date      TEXT,
            evaluation_days               INTEGER DEFAULT 0,
            liquidity_filtered_days       INTEGER DEFAULT 0,
            trend_filtered_days           INTEGER DEFAULT 0,
            setup_failed_days             INTEGER DEFAULT 0,
            volume_failed_days            INTEGER DEFAULT 0,
            second_breakout_failed_days   INTEGER DEFAULT 0,
            risk_failed_days              INTEGER DEFAULT 0,
            trade_quality_failed_days     INTEGER DEFAULT 0,
            score_failed_days             INTEGER DEFAULT 0,
            invalid_data_days             INTEGER DEFAULT 0,
            evaluation_error_days         INTEGER DEFAULT 0,
            raw_signals_count             INTEGER DEFAULT 0,
            opportunities_count           INTEGER DEFAULT 0,
            error_code                    TEXT,
            error_detail                  TEXT,
            started_at                    TEXT,
            finished_at                   TEXT,
            PRIMARY KEY (task_id, code)
        )
    ''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s3_bt_task_status ON strategy3_backtest_tasks(status, started_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s3_bt_opp_task ON strategy3_backtest_opportunities(task_id, first_detected_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s3_bt_opp_stock ON strategy3_backtest_opportunities(task_id, code, first_detected_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s3_bt_insuf_task ON strategy3_backtest_insufficient_stocks(task_id, reason_code)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_s3_bt_signal ON strategy3_backtest_signals(task_id, code, evaluation_date)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_s3_bt_opp ON strategy3_backtest_opportunities(task_id, code, first_detected_date)")


def mark_running_strategy2_backtests_interrupted() -> list[str]:
    """Make backtests left running by a previous process explicitly resumable."""
    conn = get_conn()
    task_ids = [
        row[0] for row in conn.execute(
            "SELECT id FROM strategy2_backtest_tasks WHERE LOWER(status)='running'"
        ).fetchall()
    ]
    if not task_ids:
        return []
    try:
        conn.execute("BEGIN IMMEDIATE")
        for task_id in task_ids:
            conn.execute(
                "UPDATE strategy2_backtest_tasks "
                "SET status='INTERRUPTED', credibility_status='PHASE1_INCOMPLETE', "
                "error='Interrupted by server restart' WHERE id=?",
                (task_id,),
            )
            conn.execute(
                "UPDATE strategy2_backtest_task_stocks SET status='PENDING' "
                "WHERE task_id=? AND status='RUNNING'",
                (task_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return task_ids


def create_strategy2_backtest_task(task_id: str, payload: dict, config_snapshot: str):
    from strategy2.version import (
        STRATEGY2_BACKTEST_ENGINE_VERSION,
        STRATEGY2_STRATEGY_ENGINE_VERSION,
    )
    conn = get_conn()
    conn.execute(
        """INSERT INTO strategy2_backtest_tasks
           (id, status, requested_start_date, requested_end_date,
            scope_type, requested_codes, max_stocks, config_snapshot,
            total_stocks, started_at, backtest_engine_version, strategy_engine_version)
           VALUES (?, 'running', ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
        (task_id, payload.get("startDate", ""), payload.get("endDate", ""),
         "market" if not payload.get("codes") else "single",
         ",".join(payload.get("codes") or []),
         payload.get("maxStocks", 200),
         config_snapshot,
         datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         STRATEGY2_BACKTEST_ENGINE_VERSION,
         STRATEGY2_STRATEGY_ENGINE_VERSION),
    )
    updates = {}
    experiment_snapshot = payload.get("experiment_snapshot")
    if experiment_snapshot is None and payload.get("experiment") is not None:
        experiment_snapshot = payload.get("experiment")
    if experiment_snapshot is not None:
        updates["experiment_snapshot"] = (
            experiment_snapshot if isinstance(experiment_snapshot, str)
            else json.dumps(experiment_snapshot, ensure_ascii=False)
        )
    if payload.get("baselineTaskId"):
        updates["baseline_task_id"] = payload.get("baselineTaskId")
    if updates:
        sets = ", ".join(f"{key}=?" for key in updates)
        conn.execute(f"UPDATE strategy2_backtest_tasks SET {sets} WHERE id=?", list(updates.values()) + [task_id])
    conn.commit()


def update_strategy2_backtest_task(task_id: str, **kwargs):
    if not kwargs:
        return
    conn = get_conn()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [task_id]
    conn.execute(f"UPDATE strategy2_backtest_tasks SET {sets} WHERE id=?", values)
    conn.commit()


def get_strategy2_backtest_task(task_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM strategy2_backtest_tasks WHERE id=?", (task_id,)
    ).fetchone()
    if not row:
        return None
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy2_backtest_tasks)")]
    return dict(zip(cols, row))


def get_strategy2_backtest_tasks(
    page: int = 1, page_size: int = 20, status: str | None = None,
) -> tuple[list[dict], int]:
    conn = get_conn()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    where = ""
    params = []
    if status:
        where = " WHERE LOWER(status)=LOWER(?)"
        params.append(status)
    total = conn.execute(
        "SELECT COUNT(*) FROM strategy2_backtest_tasks" + where, params
    ).fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM strategy2_backtest_tasks" + where
        + " ORDER BY started_at DESC LIMIT ? OFFSET ?",
        params + [page_size, (page - 1) * page_size],
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy2_backtest_tasks)")]
    return [dict(zip(cols, r)) for r in rows], total


def save_strategy2_backtest_signal(task_id: str, signal):
    """保存原始命中信号（幂等：ON CONFLICT 更新）。"""
    conn = get_conn()
    if hasattr(signal, 'evaluation_date'):
        # BacktestSignal dataclass
        snapshot_json = json.dumps(signal.evaluation_snapshot, ensure_ascii=False) if signal.evaluation_snapshot else "{}"
        conn.execute(
            """INSERT INTO strategy2_backtest_signals
               (task_id, code, name, evaluation_date, evaluation_index,
                score, level, current_close, stop_loss, risk_ratio,
                volume_dry_score, price_stable_score, trend_type, trend_evidence_score,
                evaluation_snapshot, baseline_passed, experiment_passed,
                experiment_filter_reason, opportunity_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(task_id, code, evaluation_date) DO UPDATE SET
                score=excluded.score, level=excluded.level,
                current_close=excluded.current_close, stop_loss=excluded.stop_loss,
                risk_ratio=excluded.risk_ratio,
                experiment_passed=excluded.experiment_passed,
                experiment_filter_reason=excluded.experiment_filter_reason,
                opportunity_type=excluded.opportunity_type""",
            (task_id, signal.code, signal.name, signal.evaluation_date,
             signal.evaluation_index, signal.score, signal.level,
             signal.current_close, signal.stop_loss, signal.risk_ratio,
             signal.volume_dry_score, signal.price_stable_score,
             signal.trend_type, signal.trend_evidence_score, snapshot_json,
             1 if getattr(signal, "baseline_passed", True) else 0,
             1 if getattr(signal, "experiment_passed", True) else 0,
             getattr(signal, "experiment_filter_reason", ""),
             getattr(signal, "opportunity_type", "")),
        )
    else:
        # 兼容 dict
        conn.execute(
            """INSERT INTO strategy2_backtest_signals
               (task_id, code, name, evaluation_date, evaluation_index,
                score, level, current_close, stop_loss, risk_ratio,
                volume_dry_score, price_stable_score, trend_type, trend_evidence_score,
                evaluation_snapshot, baseline_passed, experiment_passed,
                experiment_filter_reason, opportunity_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(task_id, code, evaluation_date) DO NOTHING""",
            (task_id, signal.get("code"), signal.get("name"),
             signal.get("evaluation_date"), signal.get("evaluation_index", 0),
             signal.get("score", 0), signal.get("level", ""),
             signal.get("current_close", 0.0), signal.get("stop_loss", 0.0),
             signal.get("risk_ratio", 0.0), signal.get("volume_dry_score", 0),
             signal.get("price_stable_score", 0), signal.get("trend_type", ""),
             signal.get("trend_evidence_score", 0),
             json.dumps(signal.get("evaluation_snapshot", {}), ensure_ascii=False),
             1 if signal.get("baseline_passed", True) else 0,
             1 if signal.get("experiment_passed", True) else 0,
             signal.get("experiment_filter_reason", ""),
             signal.get("opportunity_type", "")),
        )
    conn.commit()


def save_strategy2_backtest_opportunity(task_id: str, opp: dict):
    conn = get_conn()
    conn.execute(
        """INSERT INTO strategy2_backtest_opportunities
           (task_id, code, name, first_detected_date, last_detected_date,
            consecutive_hit_days, first_score, max_score, level,
            entry_close, stop_loss, risk_ratio, trend_type, trend_evidence_score,
            evaluation_snapshot, horizon_3, horizon_5, horizon_10, horizon_20,
            signal_count, execution_model, entry_date, entry_price,
            exit_date, exit_price, exit_reason, realized_return,
            mark_to_market_end_return, holding_days, available_forward_days,
            opportunity_type, volume_dry_score, price_stable_score,
            entry_confirmation_type, entry_confirmation_date,
            entry_confirmation_price, entry_confirmation_status, time_exit_days,
            market_context_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (task_id, opp["code"], opp.get("name", ""), opp["first_detected_date"],
         opp["last_detected_date"], opp["consecutive_hit_days"],
         opp["first_score"], opp["max_score"], opp.get("level", ""),
         opp["entry_close"], opp["stop_loss"], opp.get("risk_ratio"),
         opp.get("trend_type", ""), opp.get("trend_evidence_score", 0),
         opp.get("evaluation_snapshot", "{}"),
         opp.get("horizon_3", "{}"), opp.get("horizon_5", "{}"),
         opp.get("horizon_10", "{}"), opp.get("horizon_20", "{}"),
         opp.get("signal_count", 0),
         opp.get("execution_model", ""), opp.get("entry_date", ""),
         opp.get("entry_price", 0), opp.get("exit_date", ""),
         opp.get("exit_price", 0), opp.get("exit_reason", ""),
         opp.get("realized_return", 0), opp.get("mark_to_market_end_return", 0),
         opp.get("holding_days", 0), opp.get("available_forward_days", 0),
         opp.get("opportunity_type", ""),
         opp.get("volume_dry_score", 0),
         opp.get("price_stable_score", 0),
         opp.get("entry_confirmation_type", ""),
         opp.get("entry_confirmation_date", ""),
         opp.get("entry_confirmation_price", 0),
         opp.get("entry_confirmation_status", ""),
         opp.get("time_exit_days"),
         opp.get("market_context_json", "{}")),
    )
    conn.commit()


def save_strategy2_backtest_task_stock(task_id: str, code: str, **kwargs):
    conn = get_conn()
    existing = conn.execute(
        "SELECT 1 FROM strategy2_backtest_task_stocks WHERE task_id=? AND code=?", (task_id, code)
    ).fetchone()
    if existing:
        sets = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [task_id, code]
        conn.execute(f"UPDATE strategy2_backtest_task_stocks SET {sets} WHERE task_id=? AND code=?", vals)
    else:
        cols = ["task_id", "code"] + list(kwargs.keys())
        placeholders = ", ".join("?" for _ in cols)
        vals = [task_id, code] + list(kwargs.values())
        conn.execute(f"INSERT INTO strategy2_backtest_task_stocks ({', '.join(cols)}) VALUES ({placeholders})", vals)
    conn.commit()


def get_strategy2_backtest_task_stocks(task_id: str, status: str = None) -> list[dict]:
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM strategy2_backtest_task_stocks WHERE task_id=? AND status=? ORDER BY code",
            (task_id, status)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM strategy2_backtest_task_stocks WHERE task_id=? ORDER BY code",
            (task_id,)).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy2_backtest_task_stocks)")]
    return [dict(zip(cols, r)) for r in rows]


def build_strategy2_backtest_summary(task_id: str) -> dict:
    """从数据库完整明细生成汇总。horizon统计使用 horizon_N JSON 字段。"""
    import statistics as _st
    conn = get_conn()
    opps = conn.execute(
        "SELECT * FROM strategy2_backtest_opportunities WHERE task_id=?", (task_id,)
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy2_backtest_opportunities)")]
    opps = [dict(zip(cols, r)) for r in opps]

    # ── 周期观察统计（使用 horizon_N JSON）──
    horizon_stats = {}
    for h in ["3", "5", "10", "20"]:
        end_returns, max_upsides, max_drawdowns = [], [], []
        days_to_target, days_to_stop = [], []
        observed, success, failed, unresolved, unobserved = 0, 0, 0, 0, 0
        for o in opps:
            try:
                raw = o.get(f"horizon_{h}", "{}")
                d = __import__("json").loads(raw) if raw else {}
            except Exception:
                d = {}
            r = d.get("result", "UNOBSERVED")
            if r == "UNOBSERVED":
                unobserved += 1
            else:
                observed += 1
                end_returns.append(d.get("end_return", 0))
                max_upsides.append(d.get("max_upside", 0))
                max_drawdowns.append(d.get("max_drawdown", 0))
                if r == "SUCCESS":
                    success += 1
                    if d.get("days_to_target") is not None:
                        days_to_target.append(d["days_to_target"])
                elif r == "FAILED":
                    failed += 1
                    if d.get("days_to_stop") is not None:
                        days_to_stop.append(d["days_to_stop"])
                elif r == "UNRESOLVED":
                    unresolved += 1
        decisive = success + failed
        horizon_stats[h] = {
            "observed": observed, "unobserved": unobserved,
            "success": success, "failed": failed, "unresolved": unresolved,
            "success_rate": round(success / observed * 100, 2) if observed else 0,       # 前端兼容
            "failed_rate": round(failed / observed * 100, 2) if observed else 0,          # 前端兼容
            "target_hit_rate": round(success / observed * 100, 2) if observed else 0,
            "stop_hit_rate": round(failed / observed * 100, 2) if observed else 0,
            "unresolved_rate": round(unresolved / observed * 100, 2) if observed else 0,
            "decisive_win_rate": round(success / decisive * 100, 2) if decisive else 0,
            "avg_end_return": round(_st.mean(end_returns), 6) if end_returns else 0,
            "median_end_return": round(_st.median(end_returns), 6) if end_returns else 0,
            "avg_max_upside": round(_st.mean(max_upsides), 6) if max_upsides else 0,
            "median_max_upside": round(_st.median(max_upsides), 6) if max_upsides else 0,
            "avg_max_drawdown": round(_st.mean(max_drawdowns), 6) if max_drawdowns else 0,
            "median_max_drawdown": round(_st.median(max_drawdowns), 6) if max_drawdowns else 0,
            "avg_days_to_target": round(_st.mean(days_to_target), 1) if days_to_target else None,
            "avg_days_to_stop": round(_st.mean(days_to_stop), 1) if days_to_stop else None,
        }

    # ── 整笔交易执行统计（使用机会执行字段）──
    entered_opps = [o for o in opps if o.get("entry_price") and o["entry_price"] > 0]
    entered = len(entered_opps)
    target = sum(1 for o in opps if o.get("exit_reason") == "TARGET")
    stop = sum(1 for o in opps if o.get("exit_reason") == "STOP")
    unresolved = sum(1 for o in opps if o.get("exit_reason") == "UNRESOLVED")
    not_entered = len(opps) - entered
    realized_returns = [o["realized_return"] or 0 for o in entered_opps]
    holding_days = [o.get("holding_days") or 0 for o in entered_opps if o.get("holding_days")]
    positive = sum(1 for rr in realized_returns if rr > 0)

    funnel_columns = [
        "evaluation_days",
        "liquidity_filtered_days",
        "trend_filtered_days",
        "rejection_failed_days",
        "score_failed_days",
        "risk_failed_days",
        "invalid_data_days",
        "evaluation_error_days",
        "raw_signals_count",
        "opportunities_count",
    ]
    funnel_row = conn.execute(
        "SELECT " + ", ".join(f"COALESCE(SUM({column}), 0)" for column in funnel_columns)
        + " FROM strategy2_backtest_task_stocks WHERE task_id=?",
        (task_id,),
    ).fetchone()
    funnel = dict(zip(funnel_columns, funnel_row))
    experiment_columns = [
        "experiment_filtered_days",
        "experiment_volume_filtered_days",
        "experiment_score_filtered_days",
        "entry_confirmation_failed_count",
        "time_exit_count",
    ]
    experiment_row = conn.execute(
        "SELECT " + ", ".join(f"COALESCE(SUM({column}), 0)" for column in experiment_columns)
        + " FROM strategy2_backtest_task_stocks WHERE task_id=?",
        (task_id,),
    ).fetchone()
    experiment_funnel = dict(zip(experiment_columns, experiment_row))

    def _score_band(value) -> str:
        try:
            ivalue = int(value or 0)
        except Exception:
            ivalue = 0
        lower = max(0, min(100, (ivalue // 10) * 10))
        if lower == 100:
            return "100"
        return f"{lower}-{lower + 9}"

    def _group_key(row: dict, kind: str) -> str:
        if kind == "month":
            return str(row.get("first_detected_date") or "")[:7] or "UNKNOWN"
        if kind == "opportunity_type":
            return row.get("opportunity_type") or "UNKNOWN"
        if kind == "volume_dry_score_band":
            return _score_band(row.get("volume_dry_score"))
        if kind == "price_stable_score_band":
            return _score_band(row.get("price_stable_score"))
        if kind == "total_score_band":
            return _score_band(row.get("first_score"))
        if kind == "entry_confirmation_status":
            return row.get("entry_confirmation_status") or "UNKNOWN"
        return "UNKNOWN"

    def _summarize_group(rows: list[dict]) -> dict:
        entered_rows = [row for row in rows if row.get("entry_price") and row["entry_price"] > 0]
        realized_returns = [row.get("realized_return") or 0 for row in entered_rows]
        target = sum(1 for row in rows if row.get("exit_reason") == "TARGET")
        stop = sum(1 for row in rows if row.get("exit_reason") == "STOP")
        entered = len(entered_rows)
        return {
            "opportunities": len(rows),
            "entered": entered,
            "target": target,
            "stop": stop,
            "target_hit_rate": round(target / entered * 100, 2) if entered else 0,
            "stop_hit_rate": round(stop / entered * 100, 2) if entered else 0,
            "average_realized_return": round(_st.mean(realized_returns), 6) if realized_returns else 0,
            "median_realized_return": round(_st.median(realized_returns), 6) if realized_returns else 0,
        }

    def _group_by(kind: str) -> dict:
        grouped = {}
        for row in opps:
            grouped.setdefault(_group_key(row, kind), []).append(row)
        return {key: _summarize_group(rows) for key, rows in sorted(grouped.items())}

    groups = {
        "by_month": _group_by("month"),
        "by_opportunity_type": _group_by("opportunity_type"),
        "by_volume_dry_score_band": _group_by("volume_dry_score_band"),
        "by_price_stable_score_band": _group_by("price_stable_score_band"),
        "by_total_score_band": _group_by("total_score_band"),
        "by_entry_confirmation_status": _group_by("entry_confirmation_status"),
    }

    return {
        "horizon_stats": horizon_stats,
        "execution_stats": {
            "opportunities": len(opps), "entered": entered,
            "target": target, "stop": stop, "unresolved": unresolved,
            "not_entered": not_entered,
            "target_hit_rate": round(target / entered * 100, 2) if entered else 0,
            "avg_realized_return": round(_st.mean(realized_returns), 6) if realized_returns else 0,
            "median_realized_return": round(_st.median(realized_returns), 6) if realized_returns else 0,
            "positive_rate": round(positive / entered * 100, 2) if entered else 0,
            "avg_holding_days": round(_st.mean(holding_days), 1) if holding_days else 0,
        },
        "funnel": funnel,
        "experiment_funnel": experiment_funnel,
        "groups": groups,
        "integrity": {},
    }


def validate_strategy2_backtest_integrity(task_id: str) -> tuple:
    """校验任务完整性。返回 (passed: bool, errors: list[str])。"""
    conn = get_conn()
    errors = []
    task = conn.execute("SELECT * FROM strategy2_backtest_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        return False, ["task_not_found"]
    tcols = [d[1] for d in conn.execute("PRAGMA table_info(strategy2_backtest_tasks)")]
    t = dict(zip(tcols, task))

    if str(t.get("status", "")).lower() != "completed":
        errors.append(f"task status is {t.get('status')}, expected completed")
    if not t.get("data_revision_id"):
        errors.append("missing data_revision_id")
    if t.get("data_revision_version") != STRATEGY2_DATA_REVISION_VERSION:
        errors.append(f"invalid data_revision_version: {t.get('data_revision_version')}")
    from strategy2.version import (
        STRATEGY2_BACKTEST_ENGINE_VERSION,
        STRATEGY2_STRATEGY_ENGINE_VERSION,
    )
    if t.get("backtest_engine_version") != STRATEGY2_BACKTEST_ENGINE_VERSION:
        errors.append(f"invalid backtest_engine_version: {t.get('backtest_engine_version')}")
    if t.get("strategy_engine_version") != STRATEGY2_STRATEGY_ENGINE_VERSION:
        errors.append(f"invalid strategy_engine_version: {t.get('strategy_engine_version')}")

    total = t.get("total_stocks", 0)
    processed = t.get("processed_stocks", 0)
    stocks_cnt = conn.execute("SELECT COUNT(*) FROM strategy2_backtest_task_stocks WHERE task_id=?", (task_id,)).fetchone()[0]
    if stocks_cnt != total:
        errors.append(f"task_stocks count mismatch: {stocks_cnt} != {total}")
    pending = conn.execute("SELECT COUNT(*) FROM strategy2_backtest_task_stocks WHERE task_id=? AND status IN ('PENDING','RUNNING')", (task_id,)).fetchone()[0]
    if pending > 0:
        errors.append(f"{pending} stocks still PENDING/RUNNING")
    if processed != total:
        errors.append(f"processed {processed} != total {total}")

    sig_cnt = conn.execute("SELECT COUNT(*) FROM strategy2_backtest_signals WHERE task_id=?", (task_id,)).fetchone()[0]
    stock_sig = conn.execute("SELECT COALESCE(SUM(raw_signals_count),0) FROM strategy2_backtest_task_stocks WHERE task_id=?", (task_id,)).fetchone()[0]
    if sig_cnt != stock_sig:
        errors.append(f"signal delta: {sig_cnt} vs {stock_sig}")

    opp_cnt = conn.execute("SELECT COUNT(*) FROM strategy2_backtest_opportunities WHERE task_id=?", (task_id,)).fetchone()[0]
    stock_opp = conn.execute("SELECT COALESCE(SUM(opportunities_count),0) FROM strategy2_backtest_task_stocks WHERE task_id=?", (task_id,)).fetchone()[0]
    if opp_cnt != stock_opp:
        errors.append(f"opportunity delta: {opp_cnt} vs {stock_opp}")

    if not t.get("observation_data_end_date"):
        errors.append("missing observation_data_end_date")
    if not t.get("summary_json"):
        errors.append("missing summary_json")
    else:
        try:
            s = __import__("json").loads(t["summary_json"])
            hs = s.get("horizon_stats", {})
            for h in ["3", "5", "10", "20"]:
                if h not in hs:
                    errors.append(f"missing horizon_stats {h}")
        except Exception:
            errors.append("invalid summary_json")

    if t.get("evaluation_error_days", 0) > 0:
        errors.append(f"evaluation_error_days={t['evaluation_error_days']} > 0")
    failed = t.get("failed_stocks_count", 0)
    if failed > 0:
        errors.append(f"failed_stocks_count={failed} > 0")

    return (len(errors) == 0), errors


def replace_strategy2_stock_backtest_result(
    task_id: str, code: str, name: str, result: dict,
) -> None:
    """原子替换单只股票的回测结果（事务化）。"""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        # 删除旧结果
        conn.execute("DELETE FROM strategy2_backtest_opportunities WHERE task_id=? AND code=?", (task_id, code))
        conn.execute("DELETE FROM strategy2_backtest_signals WHERE task_id=? AND code=?", (task_id, code))

        # 插入信号，记录日期→ID映射
        signal_id_by_date = {}
        for sig in (result.get("signals") or []):
            if hasattr(sig, 'evaluation_date'):
                edate = sig.evaluation_date
                snapshot = (json.dumps(sig.evaluation_snapshot, ensure_ascii=False)
                            if sig.evaluation_snapshot else "{}")
                c = conn.execute(
                    """INSERT INTO strategy2_backtest_signals
                       (task_id, code, name, evaluation_date, evaluation_index,
                        score, level, current_close, stop_loss, risk_ratio,
                        volume_dry_score, price_stable_score, trend_type, trend_evidence_score,
                        evaluation_snapshot, baseline_passed, experiment_passed,
                        experiment_filter_reason, opportunity_type)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (task_id, code, name, edate, sig.evaluation_index, sig.score,
                     sig.level, sig.current_close, sig.stop_loss, sig.risk_ratio,
                     sig.volume_dry_score, sig.price_stable_score, sig.trend_type,
                     sig.trend_evidence_score, snapshot,
                     1 if getattr(sig, "baseline_passed", True) else 0,
                     1 if getattr(sig, "experiment_passed", True) else 0,
                     getattr(sig, "experiment_filter_reason", ""),
                     getattr(sig, "opportunity_type", "")),
                )
                signal_id_by_date[edate] = c.lastrowid
            else:
                edate = sig.get("evaluation_date", "")
                c = conn.execute(
                    """INSERT INTO strategy2_backtest_signals
                       (task_id, code, name, evaluation_date, evaluation_index, score, level,
                        current_close, stop_loss, risk_ratio, volume_dry_score,
                        price_stable_score, trend_type, trend_evidence_score, evaluation_snapshot,
                        baseline_passed, experiment_passed, experiment_filter_reason, opportunity_type)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (task_id, code, name, edate, sig.get("evaluation_index", 0),
                     sig.get("score", 0), sig.get("level", ""), sig.get("current_close", 0),
                     sig.get("stop_loss", 0), sig.get("risk_ratio", 0), sig.get("volume_dry_score", 0),
                     sig.get("price_stable_score", 0), sig.get("trend_type", ""),
                     sig.get("trend_evidence_score", 0),
                     json.dumps(sig.get("evaluation_snapshot", {}), ensure_ascii=False),
                     1 if sig.get("baseline_passed", True) else 0,
                     1 if sig.get("experiment_passed", True) else 0,
                     sig.get("experiment_filter_reason", ""),
                     sig.get("opportunity_type", "")),
                )
                signal_id_by_date[edate] = c.lastrowid

        # 插入机会，关联信号ID
        for opp in (result.get("opportunities") or []):
            first_sid = signal_id_by_date.get(opp["first_detected_date"])
            last_sid = signal_id_by_date.get(opp["last_detected_date"])
            conn.execute(
                """INSERT INTO strategy2_backtest_opportunities
                   (task_id, code, name, first_detected_date, last_detected_date,
                    consecutive_hit_days, first_score, max_score, level,
                    entry_close, stop_loss, risk_ratio, trend_type, trend_evidence_score,
                    evaluation_snapshot, horizon_3, horizon_5, horizon_10, horizon_20,
                    signal_count, execution_model, entry_date, entry_price,
                    exit_date, exit_price, exit_reason, realized_return,
                    mark_to_market_end_return, holding_days, available_forward_days,
                    first_signal_id, last_signal_id, opportunity_type,
                    volume_dry_score, price_stable_score,
                    entry_confirmation_type, entry_confirmation_date,
                    entry_confirmation_price, entry_confirmation_status,
                    time_exit_days, market_context_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task_id, code, name, opp["first_detected_date"], opp["last_detected_date"],
                 opp["consecutive_hit_days"], opp["first_score"], opp["max_score"],
                 opp.get("level", ""), opp["entry_close"], opp["stop_loss"],
                 opp.get("risk_ratio"), opp.get("trend_type", ""),
                 opp.get("trend_evidence_score", 0), opp.get("evaluation_snapshot", "{}"),
                 opp.get("horizon_3", "{}"), opp.get("horizon_5", "{}"),
                 opp.get("horizon_10", "{}"), opp.get("horizon_20", "{}"),
                 opp.get("signal_count", 0), opp.get("execution_model", ""),
                 opp.get("entry_date", ""), opp.get("entry_price", 0),
                 opp.get("exit_date", ""), opp.get("exit_price", 0),
                 opp.get("exit_reason", ""), opp.get("realized_return", 0),
                 opp.get("mark_to_market_end_return", 0), opp.get("holding_days", 0),
                 opp.get("available_forward_days", 0), first_sid, last_sid,
                 opp.get("opportunity_type", ""),
                 opp.get("volume_dry_score", 0),
                 opp.get("price_stable_score", 0),
                 opp.get("entry_confirmation_type", ""),
                 opp.get("entry_confirmation_date", ""),
                 opp.get("entry_confirmation_price", 0),
                 opp.get("entry_confirmation_status", ""),
                 opp.get("time_exit_days"),
                 opp.get("market_context_json", "{}")),
            )

        # 更新股票终态
        update_kwargs = {k: v for k, v in {
            "status": "COMPLETED", "name": name,
            "evaluation_days": result.get("eval_days", 0),
            "liquidity_filtered_days": result.get("liquidity_filtered_days", 0),
            "trend_filtered_days": result.get("trend_filtered_days", 0),
            "rejection_failed_days": result.get("rejection_failed_days", 0),
            "score_failed_days": result.get("score_failed_days", 0),
            "risk_failed_days": result.get("risk_failed_days", 0),
            "invalid_data_days": result.get("invalid_data_days", 0),
            "evaluation_error_days": result.get("evaluation_error_days", 0),
            "raw_signals_count": result.get("raw_signals_count", 0),
            "opportunities_count": result.get("opportunities_count", 0),
            "actual_eval_start_date": result.get("actual_eval_start_date"),
            "actual_eval_end_date": result.get("actual_eval_end_date"),
            "observation_data_end_date": result.get("observation_data_end_date"),
            "available_days": result.get("available_days", 0),
            "required_days": result.get("required_days", 250),
            "earliest_date": result.get("earliest_date"),
            "latest_date": result.get("latest_date"),
            "experiment_filtered_days": result.get("experiment_filtered_days", 0),
            "experiment_volume_filtered_days": result.get("experiment_volume_filtered_days", 0),
            "experiment_score_filtered_days": result.get("experiment_score_filtered_days", 0),
            "entry_confirmation_failed_count": result.get("entry_confirmation_failed_count", 0),
            "time_exit_count": result.get("time_exit_count", 0),
            "started_at": result.get("started_at"),
            "finished_at": result.get("finished_at"),
        }.items() if v is not None}
        if update_kwargs:
            sets = ", ".join(f"{k}=?" for k in update_kwargs)
            vals = list(update_kwargs.values()) + [task_id, code]
            conn.execute(f"UPDATE strategy2_backtest_task_stocks SET {sets} WHERE task_id=? AND code=?", vals)

        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_strategy2_backtest_opportunities(
    task_id: str, code: str = None, limit: int = 500, offset: int = 0,
) -> list[dict]:
    conn = get_conn()
    if code:
        rows = conn.execute(
            "SELECT * FROM strategy2_backtest_opportunities "
            "WHERE task_id=? AND code=? ORDER BY first_detected_date LIMIT ? OFFSET ?",
            (task_id, code, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM strategy2_backtest_opportunities "
            "WHERE task_id=? ORDER BY first_detected_date LIMIT ? OFFSET ?",
            (task_id, limit, offset),
        ).fetchall()
    cols = [d[1] for d in conn.execute(
        "PRAGMA table_info(strategy2_backtest_opportunities)"
    )]
    return [dict(zip(cols, r)) for r in rows]


def create_strategy3_backtest_task(task_id: str, payload: dict, config_snapshot: str):
    """Create a strategy3 local DB backtest task."""
    from strategy3.version import (
        STRATEGY3_BACKTEST_ENGINE_VERSION,
        STRATEGY3_DATA_REVISION_VERSION,
        STRATEGY3_STRATEGY_ENGINE_VERSION,
    )
    conn = get_conn()
    codes = payload.get("codes") or []
    conn.execute(
        """INSERT INTO strategy3_backtest_tasks
           (id, status, requested_start_date, requested_end_date,
            scope_type, requested_codes, max_stocks, config_snapshot,
            total_stocks, started_at, backtest_engine_version,
            strategy_engine_version, credibility_status, execution_model,
            data_revision_version)
           VALUES (?, 'running', ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 'NEXT_OPEN', ?)""",
        (
            task_id,
            payload.get("startDate", ""),
            payload.get("endDate", ""),
            "single" if codes else "market",
            ",".join(codes),
            payload.get("maxStocks", 0),
            config_snapshot,
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            STRATEGY3_BACKTEST_ENGINE_VERSION,
            STRATEGY3_STRATEGY_ENGINE_VERSION,
            "PHASE1_INCOMPLETE",
            STRATEGY3_DATA_REVISION_VERSION,
        ),
    )
    conn.commit()


def update_strategy3_backtest_task(task_id: str, **kwargs):
    if not kwargs:
        return
    conn = get_conn()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    conn.execute(
        f"UPDATE strategy3_backtest_tasks SET {sets} WHERE id=?",
        list(kwargs.values()) + [task_id],
    )
    conn.commit()


def get_strategy3_backtest_task(task_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM strategy3_backtest_tasks WHERE id=?", (task_id,)
    ).fetchone()
    if not row:
        return None
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy3_backtest_tasks)")]
    return dict(zip(cols, row))


def save_strategy3_backtest_task_stock(task_id: str, code: str, **kwargs):
    conn = get_conn()
    _upsert_strategy3_backtest_task_stock_conn(conn, task_id, code, kwargs)
    conn.commit()


def get_strategy3_backtest_task_stocks(task_id: str, status: str = None) -> list[dict]:
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM strategy3_backtest_task_stocks WHERE task_id=? AND status=? ORDER BY code",
            (task_id, status),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM strategy3_backtest_task_stocks WHERE task_id=? ORDER BY code",
            (task_id,),
        ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy3_backtest_task_stocks)")]
    return [dict(zip(cols, r)) for r in rows]


def replace_strategy3_stock_backtest_result(
    task_id: str, code: str, name: str, result: dict,
) -> None:
    """Atomically replace one stock's strategy3 backtest details."""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM strategy3_backtest_opportunities WHERE task_id=? AND code=?", (task_id, code))
        conn.execute("DELETE FROM strategy3_backtest_signals WHERE task_id=? AND code=?", (task_id, code))

        signal_id_by_date = {}
        for sig in (result.get("signals") or []):
            row = _strategy3_signal_row(sig, code, name)
            c = conn.execute(
                """INSERT INTO strategy3_backtest_signals
                   (task_id, code, name, evaluation_date, evaluation_index,
                    total_score, level, current_close, trend_score, pullback_score,
                    volume_stability_score, second_breakout_score, risk_reward_score,
                    trade_state, trade_state_label, trade_quality_score,
                    volume_dry_score, price_stability_score, cannot_fall_score,
                    balance_powerless_score, support_price, stop_loss, target_price,
                    risk_ratio, rr1, pullback_pct, volume_ratio_5_20,
                    evaluation_snapshot)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    task_id,
                    row["code"],
                    row["name"],
                    row["evaluation_date"],
                    row["evaluation_index"],
                    row["total_score"],
                    row["level"],
                    row["current_close"],
                    row["trend_score"],
                    row["pullback_score"],
                    row["volume_stability_score"],
                    row["second_breakout_score"],
                    row["risk_reward_score"],
                    row["trade_state"],
                    row["trade_state_label"],
                    row["trade_quality_score"],
                    row["volume_dry_score"],
                    row["price_stability_score"],
                    row["cannot_fall_score"],
                    row["balance_powerless_score"],
                    row["support_price"],
                    row["stop_loss"],
                    row["target_price"],
                    row["risk_ratio"],
                    row["rr1"],
                    row["pullback_pct"],
                    row["volume_ratio_5_20"],
                    row["evaluation_snapshot"],
                ),
            )
            signal_id_by_date[row["evaluation_date"]] = c.lastrowid

        for opp in (result.get("opportunities") or []):
            first_sid = signal_id_by_date.get(opp.get("first_detected_date"))
            last_sid = signal_id_by_date.get(opp.get("last_detected_date"))
            conn.execute(
                """INSERT INTO strategy3_backtest_opportunities
                   (task_id, code, name, first_detected_date, last_detected_date,
                    consecutive_hit_days, first_score, max_score, level,
                    trade_state, trade_state_label, trade_quality_score,
                    entry_close, support_price, stop_loss, target_price,
                    risk_ratio, rr1, trend_score, pullback_score,
                    volume_stability_score, second_breakout_score, risk_reward_score,
                    volume_dry_score, price_stability_score, cannot_fall_score,
                    balance_powerless_score, pullback_pct, volume_ratio_5_20,
                    evaluation_snapshot, horizon_5, horizon_10, horizon_20,
                    signal_count, execution_model, entry_date, entry_price,
                    exit_date, exit_price, exit_reason, realized_return,
                    mark_to_market_end_return, holding_days, available_forward_days,
                    first_signal_id, last_signal_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    task_id,
                    opp.get("code", code),
                    opp.get("name", name),
                    opp["first_detected_date"],
                    opp["last_detected_date"],
                    opp.get("consecutive_hit_days", 0),
                    opp.get("first_score", 0),
                    opp.get("max_score", 0),
                    opp.get("level", ""),
                    opp.get("trade_state", ""),
                    opp.get("trade_state_label", ""),
                    opp.get("trade_quality_score", 0),
                    opp.get("entry_close", 0),
                    opp.get("support_price", 0),
                    opp.get("stop_loss", 0),
                    opp.get("target_price", 0),
                    opp.get("risk_ratio", 0),
                    opp.get("rr1", 0),
                    opp.get("trend_score", 0),
                    opp.get("pullback_score", 0),
                    opp.get("volume_stability_score", 0),
                    opp.get("second_breakout_score", 0),
                    opp.get("risk_reward_score", 0),
                    opp.get("volume_dry_score", 0),
                    opp.get("price_stability_score", 0),
                    opp.get("cannot_fall_score", 0),
                    opp.get("balance_powerless_score", 0),
                    opp.get("pullback_pct", 0),
                    opp.get("volume_ratio_5_20", 0),
                    _json_text(opp.get("evaluation_snapshot", "{}")),
                    _json_text(opp.get("horizon_5", "{}")),
                    _json_text(opp.get("horizon_10", "{}")),
                    _json_text(opp.get("horizon_20", "{}")),
                    opp.get("signal_count", 0),
                    opp.get("execution_model", ""),
                    opp.get("entry_date", ""),
                    opp.get("entry_price", 0),
                    opp.get("exit_date", ""),
                    opp.get("exit_price", 0),
                    opp.get("exit_reason", ""),
                    opp.get("realized_return", 0),
                    opp.get("mark_to_market_end_return", 0),
                    opp.get("holding_days", 0),
                    opp.get("available_forward_days", 0),
                    first_sid,
                    last_sid,
                ),
            )

        counters = _strategy3_eval_result_counters(result.get("eval_results") or {})
        update_kwargs = {k: v for k, v in {
            "status": "COMPLETED",
            "name": name,
            "evaluation_days": result.get("eval_days", 0),
            "liquidity_filtered_days": result.get("liquidity_filtered_days", 0),
            "trend_filtered_days": counters["trend_filtered_days"],
            "setup_failed_days": counters["setup_failed_days"],
            "volume_failed_days": counters["volume_failed_days"],
            "second_breakout_failed_days": counters["second_breakout_failed_days"],
            "risk_failed_days": counters["risk_failed_days"],
            "trade_quality_failed_days": counters["trade_quality_failed_days"],
            "score_failed_days": counters["score_failed_days"],
            "invalid_data_days": counters["invalid_data_days"],
            "evaluation_error_days": result.get("evaluation_error_days", 0),
            "raw_signals_count": result.get("raw_signals_count", 0),
            "opportunities_count": result.get("opportunities_count", 0),
            "actual_eval_start_date": result.get("actual_eval_start_date"),
            "actual_eval_end_date": result.get("actual_eval_end_date"),
            "observation_data_end_date": result.get("observation_data_end_date"),
            "available_days": result.get("available_days", 0),
            "required_days": result.get("required_days", 0),
            "earliest_date": result.get("earliest_date"),
            "latest_date": result.get("latest_date"),
            "error_code": result.get("error_code"),
            "error_detail": result.get("error_detail"),
            "started_at": result.get("started_at"),
            "finished_at": result.get("finished_at"),
        }.items() if v is not None}
        _upsert_strategy3_backtest_task_stock_conn(conn, task_id, code, update_kwargs)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_strategy3_backtest_opportunities(
    task_id: str, code: str = None, limit: int = 500, offset: int = 0,
) -> list[dict]:
    conn = get_conn()
    if code:
        rows = conn.execute(
            "SELECT * FROM strategy3_backtest_opportunities "
            "WHERE task_id=? AND code=? ORDER BY first_detected_date LIMIT ? OFFSET ?",
            (task_id, code, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM strategy3_backtest_opportunities "
            "WHERE task_id=? ORDER BY first_detected_date LIMIT ? OFFSET ?",
            (task_id, limit, offset),
        ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy3_backtest_opportunities)")]
    return [dict(zip(cols, r)) for r in rows]


def build_strategy3_backtest_summary(task_id: str) -> dict:
    """Build strategy3 backtest summary from persisted details only."""
    import statistics as _st
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM strategy3_backtest_opportunities WHERE task_id=?",
        (task_id,),
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy3_backtest_opportunities)")]
    opps = [dict(zip(cols, row)) for row in rows]

    horizon_stats = {}
    for h in ["5", "10", "20"]:
        observed = success = failed = unresolved = unobserved = 0
        end_returns, max_upsides, max_drawdowns = [], [], []
        days_to_target, days_to_stop = [], []
        for opp in opps:
            data = _json_loads(opp.get(f"horizon_{h}"))
            result = data.get("result", "UNOBSERVED")
            if result == "UNOBSERVED":
                unobserved += 1
                continue
            observed += 1
            end_returns.append(data.get("end_return", 0) or 0)
            max_upsides.append(data.get("max_upside", 0) or 0)
            max_drawdowns.append(data.get("max_drawdown", 0) or 0)
            if result == "SUCCESS":
                success += 1
                if data.get("days_to_target") is not None:
                    days_to_target.append(data["days_to_target"])
            elif result == "FAILED":
                failed += 1
                if data.get("days_to_stop") is not None:
                    days_to_stop.append(data["days_to_stop"])
            elif result == "UNRESOLVED":
                unresolved += 1
        horizon_stats[h] = {
            "observed": observed,
            "unobserved": unobserved,
            "success": success,
            "failed": failed,
            "unresolved": unresolved,
            "success_rate": round(success / observed * 100, 2) if observed else 0,
            "failed_rate": round(failed / observed * 100, 2) if observed else 0,
            "avg_end_return": round(_st.mean(end_returns), 6) if end_returns else 0,
            "median_end_return": round(_st.median(end_returns), 6) if end_returns else 0,
            "avg_max_upside": round(_st.mean(max_upsides), 6) if max_upsides else 0,
            "avg_max_drawdown": round(_st.mean(max_drawdowns), 6) if max_drawdowns else 0,
            "avg_days_to_target": round(_st.mean(days_to_target), 1) if days_to_target else None,
            "avg_days_to_stop": round(_st.mean(days_to_stop), 1) if days_to_stop else None,
        }

    entered_opps = [opp for opp in opps if opp.get("entry_price") and opp["entry_price"] > 0]
    realized_returns = [opp.get("realized_return") or 0 for opp in entered_opps]
    wins = [value for value in realized_returns if value > 0]
    losses = [value for value in realized_returns if value < 0]
    avg_win = _st.mean(wins) if wins else 0
    avg_loss = _st.mean(losses) if losses else 0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    holding_days = [opp.get("holding_days") or 0 for opp in entered_opps if opp.get("holding_days")]
    target = sum(1 for opp in opps if opp.get("exit_reason") == "TARGET")
    stop = sum(1 for opp in opps if opp.get("exit_reason") == "STOP")
    unresolved = sum(1 for opp in opps if opp.get("exit_reason") == "UNRESOLVED")
    positive = sum(1 for value in realized_returns if value > 0)

    funnel_columns = [
        "evaluation_days",
        "liquidity_filtered_days",
        "trend_filtered_days",
        "setup_failed_days",
        "volume_failed_days",
        "second_breakout_failed_days",
        "risk_failed_days",
        "trade_quality_failed_days",
        "score_failed_days",
        "invalid_data_days",
        "evaluation_error_days",
        "raw_signals_count",
        "opportunities_count",
    ]
    funnel_row = conn.execute(
        "SELECT " + ", ".join(f"COALESCE(SUM({column}), 0)" for column in funnel_columns)
        + " FROM strategy3_backtest_task_stocks WHERE task_id=?",
        (task_id,),
    ).fetchone()
    funnel = dict(zip(funnel_columns, funnel_row))

    groups = {
        "by_total_score_band": _strategy3_group_by(opps, lambda row: _strategy3_score_band(row.get("max_score"))),
        "by_trend_score_band": _strategy3_group_by(opps, lambda row: _strategy3_score_band(row.get("trend_score"))),
        "by_pullback": _strategy3_group_by(opps, lambda row: _strategy3_pullback_bucket(row.get("pullback_pct") or 0)),
        "by_volume_stability_score_band": _strategy3_group_by(opps, lambda row: _strategy3_score_band(row.get("volume_stability_score"))),
        "by_second_breakout_score_band": _strategy3_group_by(opps, lambda row: _strategy3_score_band(row.get("second_breakout_score"))),
        "by_risk_ratio": _strategy3_group_by(opps, lambda row: _strategy3_risk_bucket(row.get("risk_ratio") or 0)),
        "by_rr1": _strategy3_group_by(opps, lambda row: _strategy3_rr_bucket(row.get("rr1") or 0)),
        "by_month": _strategy3_group_by(opps, lambda row: (row.get("first_detected_date") or "")[:7] or "UNKNOWN"),
        "by_trade_state": _strategy3_group_by(opps, lambda row: row.get("trade_state") or "UNKNOWN"),
        "by_market_index": _strategy3_group_by(opps, lambda row: _strategy3_snapshot_value(row, "market_index_symbol") or "UNKNOWN"),
        "by_market_return_20": _strategy3_group_by(opps, lambda row: _strategy3_market_return_bucket(_strategy3_snapshot_value(row, "market_return_20"))),
        "by_market_return_60": _strategy3_group_by(opps, lambda row: _strategy3_market_return_bucket(_strategy3_snapshot_value(row, "market_return_60"))),
        "by_market_ma_state": _strategy3_group_by(opps, _strategy3_market_ma_state),
    }

    return {
        "horizon_stats": horizon_stats,
        "execution_stats": {
            "opportunities": len(opps),
            "entered": len(entered_opps),
            "target": target,
            "stop": stop,
            "unresolved": unresolved,
            "not_entered": len(opps) - len(entered_opps),
            "target_hit_rate": round(target / len(entered_opps) * 100, 2) if entered_opps else 0,
            "stop_hit_rate": round(stop / len(entered_opps) * 100, 2) if entered_opps else 0,
            "avg_realized_return": round(_st.mean(realized_returns), 6) if realized_returns else 0,
            "median_realized_return": round(_st.median(realized_returns), 6) if realized_returns else 0,
            "avg_win": round(avg_win, 6),
            "avg_loss": round(avg_loss, 6),
            "payoff_ratio": round(avg_win / abs(avg_loss), 4) if avg_loss else 0,
            "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else 0,
            "expectancy": round(_st.mean(realized_returns), 6) if realized_returns else 0,
            "max_consecutive_losses": _strategy3_max_consecutive_losses(entered_opps),
            "positive_rate": round(positive / len(entered_opps) * 100, 2) if entered_opps else 0,
            "avg_holding_days": round(_st.mean(holding_days), 1) if holding_days else 0,
        },
        "funnel": funnel,
        "groups": groups,
        "marketDataMode": _strategy3_market_data_mode(opps),
    }


def _upsert_strategy3_backtest_task_stock_conn(conn, task_id: str, code: str, values: dict):
    existing = conn.execute(
        "SELECT 1 FROM strategy3_backtest_task_stocks WHERE task_id=? AND code=?",
        (task_id, code),
    ).fetchone()
    if existing:
        if not values:
            return
        sets = ", ".join(f"{key}=?" for key in values)
        conn.execute(
            f"UPDATE strategy3_backtest_task_stocks SET {sets} WHERE task_id=? AND code=?",
            list(values.values()) + [task_id, code],
        )
        return
    cols = ["task_id", "code"] + list(values.keys())
    placeholders = ", ".join("?" for _ in cols)
    conn.execute(
        f"INSERT INTO strategy3_backtest_task_stocks ({', '.join(cols)}) VALUES ({placeholders})",
        [task_id, code] + list(values.values()),
    )


def _strategy3_signal_row(signal, code: str, name: str) -> dict:
    if hasattr(signal, "evaluation_date"):
        return {
            "code": getattr(signal, "code", code) or code,
            "name": getattr(signal, "name", name) or name,
            "evaluation_date": signal.evaluation_date,
            "evaluation_index": signal.evaluation_index,
            "total_score": signal.total_score,
            "level": signal.level,
            "current_close": signal.current_close,
            "trend_score": signal.trend_score,
            "pullback_score": signal.pullback_score,
            "volume_stability_score": signal.volume_stability_score,
            "second_breakout_score": signal.second_breakout_score,
            "risk_reward_score": signal.risk_reward_score,
            "trade_state": signal.trade_state,
            "trade_state_label": signal.trade_state_label,
            "trade_quality_score": signal.trade_quality_score,
            "volume_dry_score": signal.volume_dry_score,
            "price_stability_score": signal.price_stability_score,
            "cannot_fall_score": signal.cannot_fall_score,
            "balance_powerless_score": signal.balance_powerless_score,
            "support_price": signal.support_price,
            "stop_loss": signal.stop_loss,
            "target_price": signal.target_price,
            "risk_ratio": signal.risk_ratio,
            "rr1": signal.rr1,
            "pullback_pct": signal.pullback_pct,
            "volume_ratio_5_20": signal.volume_ratio_5_20,
            "evaluation_snapshot": _json_text(signal.evaluation_snapshot),
        }
    return {
        "code": signal.get("code", code),
        "name": signal.get("name", name),
        "evaluation_date": signal.get("evaluation_date", ""),
        "evaluation_index": signal.get("evaluation_index", 0),
        "total_score": signal.get("total_score", 0),
        "level": signal.get("level", ""),
        "current_close": signal.get("current_close", 0),
        "trend_score": signal.get("trend_score", 0),
        "pullback_score": signal.get("pullback_score", 0),
        "volume_stability_score": signal.get("volume_stability_score", 0),
        "second_breakout_score": signal.get("second_breakout_score", 0),
        "risk_reward_score": signal.get("risk_reward_score", 0),
        "trade_state": signal.get("trade_state", ""),
        "trade_state_label": signal.get("trade_state_label", ""),
        "trade_quality_score": signal.get("trade_quality_score", 0),
        "volume_dry_score": signal.get("volume_dry_score", 0),
        "price_stability_score": signal.get("price_stability_score", 0),
        "cannot_fall_score": signal.get("cannot_fall_score", 0),
        "balance_powerless_score": signal.get("balance_powerless_score", 0),
        "support_price": signal.get("support_price", 0),
        "stop_loss": signal.get("stop_loss", 0),
        "target_price": signal.get("target_price", 0),
        "risk_ratio": signal.get("risk_ratio", 0),
        "rr1": signal.get("rr1", 0),
        "pullback_pct": signal.get("pullback_pct", 0),
        "volume_ratio_5_20": signal.get("volume_ratio_5_20", 0),
        "evaluation_snapshot": _json_text(signal.get("evaluation_snapshot", {})),
    }


def _strategy3_eval_result_counters(eval_results: dict) -> dict:
    counter = {
        "trend_filtered_days": 0,
        "setup_failed_days": 0,
        "volume_failed_days": 0,
        "second_breakout_failed_days": 0,
        "risk_failed_days": 0,
        "trade_quality_failed_days": 0,
        "score_failed_days": 0,
        "invalid_data_days": 0,
    }
    mapping = {
        "TREND_REJECTED": "trend_filtered_days",
        "SETUP_REJECTED": "setup_failed_days",
        "VOLUME_REJECTED": "volume_failed_days",
        "SECOND_BREAKOUT_REJECTED": "second_breakout_failed_days",
        "RISK_REJECTED": "risk_failed_days",
        "TRADE_QUALITY_REJECTED": "trade_quality_failed_days",
        "SCORE_BELOW_THRESHOLD": "score_failed_days",
        "INSUFFICIENT_DATA": "invalid_data_days",
        "INVALID_DATA": "invalid_data_days",
        "EVALUATION_ERROR": "invalid_data_days",
    }
    for reason in eval_results.values():
        key = mapping.get(reason)
        if key:
            counter[key] += 1
    return counter


def _json_text(value) -> str:
    if value is None:
        return "{}"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}


def _strategy3_snapshot(row: dict) -> dict:
    return _json_loads(row.get("evaluation_snapshot"))


def _strategy3_snapshot_value(row: dict, key: str):
    return _strategy3_snapshot(row).get(key)


def _strategy3_group_by(rows: list[dict], key_fn) -> dict:
    import statistics as _st
    groups = {}
    for row in rows:
        groups.setdefault(key_fn(row), []).append(row)
    result = {}
    for key, items in sorted(groups.items()):
        entered = [row for row in items if row.get("entry_price") and row["entry_price"] > 0]
        returns = [row.get("realized_return") or 0 for row in entered]
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value < 0]
        avg_win = _st.mean(wins) if wins else 0
        avg_loss = _st.mean(losses) if losses else 0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        target = sum(1 for row in items if row.get("exit_reason") == "TARGET")
        stop = sum(1 for row in items if row.get("exit_reason") == "STOP")
        result[key] = {
            "opportunities": len(items),
            "entered": len(entered),
            "target": target,
            "stop": stop,
            "not_entered": len(items) - len(entered),
            "target_hit_rate": round(target / len(entered) * 100, 2) if entered else 0,
            "stop_hit_rate": round(stop / len(entered) * 100, 2) if entered else 0,
            "average_realized_return": round(_st.mean(returns), 6) if returns else 0,
            "median_realized_return": round(_st.median(returns), 6) if returns else 0,
            "avg_win": round(avg_win, 6),
            "avg_loss": round(avg_loss, 6),
            "payoff_ratio": round(avg_win / abs(avg_loss), 4) if avg_loss else 0,
            "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else 0,
            "expectancy": round(_st.mean(returns), 6) if returns else 0,
        }
    return result


def _strategy3_max_consecutive_losses(rows: list[dict]) -> int:
    max_streak = 0
    streak = 0
    for row in sorted(rows, key=lambda item: (item.get("first_detected_date") or "", item.get("code") or "")):
        if (row.get("realized_return") or 0) < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def _strategy3_market_return_bucket(value) -> str:
    try:
        numeric = float(value)
    except Exception:
        return "UNKNOWN"
    if numeric < 0:
        return "negative"
    if numeric < 0.03:
        return "0-3%"
    if numeric <= 0.05:
        return "3-5%"
    return ">5%"


def _strategy3_market_ma_state(row: dict) -> str:
    snapshot = _strategy3_snapshot(row)
    if "market_above_ma20" not in snapshot or "market_above_ma60" not in snapshot:
        return "UNKNOWN"
    above20 = bool(snapshot.get("market_above_ma20"))
    above60 = bool(snapshot.get("market_above_ma60"))
    if above20 and above60:
        return "above_ma20_above_ma60"
    if above20 and not above60:
        return "above_ma20_below_ma60"
    if not above20 and above60:
        return "below_ma20_above_ma60"
    return "below_ma20_below_ma60"


def _strategy3_market_data_mode(rows: list[dict]) -> str:
    modes = {
        _strategy3_snapshot_value(row, "market_data_mode")
        for row in rows
        if _strategy3_snapshot_value(row, "market_data_mode")
    }
    if not modes:
        return ""
    if len(modes) == 1:
        return next(iter(modes))
    return "mixed"


def _strategy3_score_band(value) -> str:
    try:
        score = int(value or 0)
    except Exception:
        score = 0
    lower = max(0, min(100, (score // 10) * 10))
    if lower == 100:
        return "100"
    return f"{lower}-{lower + 9}"


def _strategy3_risk_bucket(risk_ratio: float) -> str:
    if risk_ratio <= 0.04:
        return "<=4%"
    if risk_ratio <= 0.06:
        return "4-6%"
    if risk_ratio <= 0.08:
        return "6-8%"
    return ">8%"


def _strategy3_rr_bucket(rr1: float) -> str:
    if rr1 < 1.5:
        return "<1.5"
    if rr1 < 2.0:
        return "1.5-2"
    if rr1 < 3.0:
        return "2-3"
    return ">=3"


def _strategy3_pullback_bucket(pullback_pct: float) -> str:
    if pullback_pct < 0.10:
        return "<10%"
    if pullback_pct < 0.15:
        return "10-15%"
    if pullback_pct <= 0.22:
        return "15-22%"
    if pullback_pct <= 0.30:
        return "22-30%"
    return ">30%"


def summarize_strategy2_backtest_for_comparison(task_id: str) -> dict:
    """Return compact execution metrics for baseline/experiment comparison."""
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*), "
        "SUM(CASE WHEN COALESCE(entry_price,0)>0 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN exit_reason='TARGET' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN exit_reason='STOP' THEN 1 ELSE 0 END), "
        "AVG(CASE WHEN COALESCE(entry_price,0)>0 THEN COALESCE(realized_return,0) END) "
        "FROM strategy2_backtest_opportunities WHERE task_id=?",
        (task_id,),
    ).fetchone()
    opportunities, entered, target, stop, avg_return = row
    opportunities = opportunities or 0
    entered = entered or 0
    target = target or 0
    stop = stop or 0
    return {
        "opportunities": opportunities,
        "entered": entered,
        "target": target,
        "stop": stop,
        "successRate": round(target / entered, 6) if entered else 0.0,
        "stopRate": round(stop / entered, 6) if entered else 0.0,
        "averageRealizedReturn": round(avg_return or 0.0, 6),
    }


def compare_strategy2_backtest_tasks(experiment_task_id: str, baseline_task_id: str) -> dict:
    """Compare two completed Strategy2 backtest tasks and explain incompatibility."""
    baseline = get_strategy2_backtest_task(baseline_task_id)
    experiment = get_strategy2_backtest_task(experiment_task_id)
    if not baseline or not experiment:
        return {
            "comparable": False,
            "baselineTaskId": baseline_task_id,
            "experimentTaskId": experiment_task_id,
            "reasons": ["task_not_found"],
        }

    checks = [
        "requested_start_date",
        "requested_end_date",
        "requested_codes",
        "max_stocks",
        "execution_model",
        "backtest_engine_version",
        "strategy_engine_version",
        "data_revision_version",
        "data_revision_id",
    ]
    reasons = [key for key in checks if (baseline.get(key) or "") != (experiment.get(key) or "")]
    if baseline.get("credibility_status") != "TRUSTED_BASELINE":
        reasons.append("baseline_credibility_status")
    if experiment.get("credibility_status") != "EXPERIMENTAL":
        reasons.append("experiment_credibility_status")

    base_summary = summarize_strategy2_backtest_for_comparison(baseline_task_id)
    exp_summary = summarize_strategy2_backtest_for_comparison(experiment_task_id)
    delta = {
        key: round(exp_summary.get(key, 0) - base_summary.get(key, 0), 6)
        for key in {
            "opportunities", "entered", "target", "stop",
            "successRate", "stopRate", "averageRealizedReturn",
        }
    }
    return {
        "comparable": len(reasons) == 0,
        "baselineTaskId": baseline_task_id,
        "experimentTaskId": experiment_task_id,
        "reasons": reasons,
        "baseline": base_summary,
        "experiment": exp_summary,
        "delta": delta,
    }


def save_strategy2_backtest_insufficient_stocks(task_id: str, stocks: list[dict]):
    if not stocks:
        return
    conn = get_conn()
    for s in stocks:
        conn.execute(
            """INSERT INTO strategy2_backtest_insufficient_stocks
               (task_id, code, name, reason_code, available_days, required_days,
                earliest_date, latest_date, actual_start_date, actual_end_date, detail)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (task_id, s["code"], s.get("name", ""), s["reason_code"],
             s.get("available_days", 0), s.get("required_days", 0),
             s.get("earliest_date", ""), s.get("latest_date", ""),
             s.get("actual_start_date", ""), s.get("actual_end_date", ""),
             s.get("detail", "")),
        )
    conn.commit()


def get_strategy2_backtest_insufficient_stocks(task_id: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM strategy2_backtest_insufficient_stocks "
        "WHERE task_id=? ORDER BY reason_code, code",
        (task_id,),
    ).fetchall()
    cols = [d[1] for d in conn.execute(
        "PRAGMA table_info(strategy2_backtest_insufficient_stocks)"
    )]
    return [dict(zip(cols, r)) for r in rows]


# ====== Strategy1 Trusted Backtest ======

STRATEGY1_DATA_REVISION_VERSION = "daily-ohlc-v1"


def _ensure_strategy1_backtest_tables(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS strategy1_backtest_tasks (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            credibility_status TEXT,
            requested_start_date TEXT,
            requested_end_date TEXT,
            actual_evaluation_start_date TEXT,
            actual_evaluation_end_date TEXT,
            observation_data_end_date TEXT,
            scope_type TEXT,
            requested_codes TEXT,
            max_stocks INTEGER,
            config_snapshot TEXT NOT NULL,
            experiment_snapshot TEXT,
            baseline_task_id TEXT,
            comparison_summary_json TEXT,
            strategy_engine_version TEXT,
            backtest_engine_version TEXT,
            data_revision_version TEXT,
            data_revision_id TEXT,
            execution_model TEXT,
            total_stocks INTEGER DEFAULT 0,
            processed_stocks INTEGER DEFAULT 0,
            failed_stocks_count INTEGER DEFAULT 0,
            insufficient_stocks_count INTEGER DEFAULT 0,
            raw_signals_count INTEGER DEFAULT 0,
            opportunities_count INTEGER DEFAULT 0,
            summary_json TEXT,
            started_at TEXT,
            finished_at TEXT,
            elapsed_seconds REAL,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS strategy1_backtest_task_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            status TEXT NOT NULL,
            available_days INTEGER DEFAULT 0,
            required_days INTEGER DEFAULT 0,
            earliest_date TEXT,
            latest_date TEXT,
            actual_start_date TEXT,
            actual_end_date TEXT,
            raw_signals_count INTEGER DEFAULT 0,
            opportunities_count INTEGER DEFAULT 0,
            evaluation_days INTEGER DEFAULT 0,
            filtered_days INTEGER DEFAULT 0,
            error_code TEXT,
            error_detail TEXT,
            UNIQUE(task_id, code)
        );

        CREATE TABLE IF NOT EXISTS strategy1_backtest_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            evaluation_date TEXT NOT NULL,
            evaluation_index INTEGER DEFAULT 0,
            pattern_kind TEXT,
            score INTEGER DEFAULT 0,
            cup_depth_pct REAL DEFAULT 0,
            cup_duration INTEGER DEFAULT 0,
            handle_depth_pct REAL DEFAULT 0,
            handle_duration INTEGER DEFAULT 0,
            lip_deviation_pct REAL DEFAULT 0,
            is_breakout INTEGER DEFAULT 0,
            is_volume_breakout INTEGER DEFAULT 0,
            breakout_price REAL DEFAULT 0,
            current_close REAL DEFAULT 0,
            volume_dry_score INTEGER DEFAULT 0,
            price_stable_score INTEGER DEFAULT 0,
            pattern_score_20 INTEGER DEFAULT 0,
            verdict_key TEXT,
            risk_percent REAL DEFAULT 0,
            rr1 REAL DEFAULT 0,
            entry_zone_low REAL DEFAULT 0,
            entry_zone_high REAL DEFAULT 0,
            stop_loss REAL DEFAULT 0,
            target_1 REAL DEFAULT 0,
            target_2 REAL DEFAULT 0,
            baseline_passed INTEGER DEFAULT 1,
            experiment_passed INTEGER DEFAULT 1,
            experiment_filter_reason TEXT,
            evaluation_snapshot TEXT,
            UNIQUE(task_id, code, evaluation_date)
        );

        CREATE TABLE IF NOT EXISTS strategy1_backtest_opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            first_detected_date TEXT NOT NULL,
            last_detected_date TEXT,
            pattern_kind TEXT,
            first_score INTEGER DEFAULT 0,
            max_score INTEGER DEFAULT 0,
            signal_count INTEGER DEFAULT 0,
            entry_date TEXT,
            entry_price REAL DEFAULT 0,
            stop_loss REAL DEFAULT 0,
            exit_date TEXT,
            exit_price REAL DEFAULT 0,
            exit_reason TEXT,
            realized_return REAL,
            mark_to_market_end_return REAL,
            holding_days INTEGER DEFAULT 0,
            available_forward_days INTEGER DEFAULT 0,
            horizon_3 TEXT,
            horizon_5 TEXT,
            horizon_10 TEXT,
            horizon_20 TEXT,
            market_context_json TEXT,
            evaluation_snapshot TEXT,
            UNIQUE(task_id, code, first_detected_date)
        );

        CREATE TABLE IF NOT EXISTS strategy1_backtest_insufficient_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            reason_code TEXT,
            available_days INTEGER DEFAULT 0,
            required_days INTEGER DEFAULT 0,
            earliest_date TEXT,
            latest_date TEXT,
            detail TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s1_bt_task_status ON strategy1_backtest_tasks(status, started_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s1_bt_signal_task ON strategy1_backtest_signals(task_id, code, evaluation_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s1_bt_opp_task ON strategy1_backtest_opportunities(task_id, first_detected_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s1_bt_stock_task ON strategy1_backtest_task_stocks(task_id, status)")
    _ensure_column(conn, "strategy1_backtest_opportunities", "volume_dry_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy1_backtest_opportunities", "price_stable_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy1_backtest_opportunities", "verdict_key", "TEXT")
    _ensure_column(conn, "strategy1_backtest_opportunities", "quality_tags", "TEXT")
    _ensure_column(conn, "strategy1_backtest_opportunities", "quality_layer", "TEXT")
    _ensure_column(conn, "strategy1_backtest_opportunities", "short_term_exit_note", "TEXT")


def create_strategy1_backtest_task(task_id: str, payload: dict, config_snapshot: str):
    conn = get_conn()
    experiment = payload.get("experiment_snapshot")
    if experiment is None:
        experiment = payload.get("experiment")
    experiment_json = (
        experiment if isinstance(experiment, str)
        else json.dumps(experiment, ensure_ascii=False) if experiment is not None else None
    )
    credibility_status = "EXPERIMENTAL" if _strategy1_experiment_enabled(experiment) else "INCOMPLETE"
    execution_model = "NEXT_OPEN"
    if isinstance(experiment, dict):
        execution_model = experiment.get("execution_model") or experiment.get("executionModel") or execution_model

    conn.execute(
        """INSERT INTO strategy1_backtest_tasks
           (id, status, credibility_status, requested_start_date, requested_end_date,
            scope_type, requested_codes, max_stocks, config_snapshot,
            experiment_snapshot, baseline_task_id, execution_model,
            data_revision_version, started_at)
           VALUES (?, 'running', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            task_id,
            credibility_status,
            payload.get("startDate", ""),
            payload.get("endDate", ""),
            "market" if not payload.get("codes") else "single",
            ",".join(payload.get("codes") or []),
            payload.get("maxStocks"),
            config_snapshot,
            experiment_json,
            payload.get("baselineTaskId"),
            execution_model,
            STRATEGY1_DATA_REVISION_VERSION,
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()


def mark_running_strategy1_backtests_interrupted() -> list[str]:
    """Mark Strategy1 backtests left running by a previous process interrupted."""
    conn = get_conn()
    task_ids = [
        row[0] for row in conn.execute(
            "SELECT id FROM strategy1_backtest_tasks WHERE LOWER(status)='running'"
        ).fetchall()
    ]
    if not task_ids:
        return []
    try:
        conn.execute("BEGIN IMMEDIATE")
        for task_id in task_ids:
            conn.execute(
                "UPDATE strategy1_backtest_tasks "
                "SET status='INTERRUPTED', credibility_status='INCOMPLETE', "
                "error='Interrupted by server restart' WHERE id=?",
                (task_id,),
            )
            conn.execute(
                "UPDATE strategy1_backtest_task_stocks SET status='PENDING' "
                "WHERE task_id=? AND status='RUNNING'",
                (task_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return task_ids


def update_strategy1_backtest_task(task_id: str, **kwargs):
    if not kwargs:
        return
    conn = get_conn()
    sets = ", ".join(f"{key}=?" for key in kwargs)
    conn.execute(f"UPDATE strategy1_backtest_tasks SET {sets} WHERE id=?", list(kwargs.values()) + [task_id])
    conn.commit()


def get_strategy1_backtest_task(task_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM strategy1_backtest_tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        return None
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy1_backtest_tasks)")]
    return dict(zip(cols, row))


def get_strategy1_backtest_tasks(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[dict], int]:
    conn = get_conn()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    where = ""
    params = []
    if status:
        where = " WHERE LOWER(status)=LOWER(?)"
        params.append(status)
    total = conn.execute("SELECT COUNT(*) FROM strategy1_backtest_tasks" + where, params).fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM strategy1_backtest_tasks" + where
        + " ORDER BY started_at DESC LIMIT ? OFFSET ?",
        params + [page_size, (page - 1) * page_size],
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy1_backtest_tasks)")]
    return [dict(zip(cols, row)) for row in rows], total


def save_strategy1_backtest_signal(task_id: str, signal):
    conn = get_conn()
    snapshot_json = json.dumps(getattr(signal, "evaluation_snapshot", None) or {}, ensure_ascii=False)
    conn.execute(
        """INSERT INTO strategy1_backtest_signals
           (task_id, code, name, evaluation_date, evaluation_index, pattern_kind,
            score, cup_depth_pct, cup_duration, handle_depth_pct, handle_duration,
            lip_deviation_pct, is_breakout, is_volume_breakout, breakout_price,
            current_close, volume_dry_score, price_stable_score, pattern_score_20,
            verdict_key, risk_percent, rr1, entry_zone_low, entry_zone_high,
            stop_loss, target_1, target_2, baseline_passed, experiment_passed,
            experiment_filter_reason, evaluation_snapshot)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(task_id, code, evaluation_date) DO UPDATE SET
            score=excluded.score,
            experiment_passed=excluded.experiment_passed,
            experiment_filter_reason=excluded.experiment_filter_reason,
            evaluation_snapshot=excluded.evaluation_snapshot""",
        (
            task_id,
            signal.code,
            signal.name,
            signal.evaluation_date,
            signal.evaluation_index,
            signal.pattern_kind,
            signal.score,
            signal.cup_depth_pct,
            signal.cup_duration,
            signal.handle_depth_pct,
            signal.handle_duration,
            signal.lip_deviation_pct,
            1 if signal.is_breakout else 0,
            1 if signal.is_volume_breakout else 0,
            signal.breakout_price,
            signal.current_close,
            signal.volume_dry_score,
            signal.price_stable_score,
            signal.pattern_score_20,
            signal.verdict_key,
            signal.risk_percent,
            signal.rr1,
            signal.entry_zone_low,
            signal.entry_zone_high,
            signal.stop_loss,
            signal.target_1,
            signal.target_2,
            1 if signal.baseline_passed else 0,
            1 if signal.experiment_passed else 0,
            signal.experiment_filter_reason,
            snapshot_json,
        ),
    )
    conn.commit()


def replace_strategy1_stock_backtest_result(task_id: str, code: str, name: str, result: dict):
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM strategy1_backtest_opportunities WHERE task_id=? AND code=?", (task_id, code))
        conn.execute("DELETE FROM strategy1_backtest_signals WHERE task_id=? AND code=?", (task_id, code))

        for signal in result.get("signals") or []:
            _insert_strategy1_signal(conn, task_id, signal)
        for opportunity in result.get("opportunities") or []:
            _insert_strategy1_opportunity(conn, task_id, opportunity)

        stock_values = {
            "task_id": task_id,
            "code": code,
            "name": name,
            "status": result.get("status", "COMPLETED"),
            "available_days": result.get("available_days", 0),
            "required_days": result.get("required_days", 0),
            "earliest_date": result.get("earliest_date", ""),
            "latest_date": result.get("latest_date", ""),
            "actual_start_date": result.get("actual_start_date", result.get("actual_eval_start_date", "")),
            "actual_end_date": result.get("actual_end_date", result.get("actual_eval_end_date", "")),
            "raw_signals_count": result.get("raw_signals_count", 0),
            "opportunities_count": result.get("opportunities_count", 0),
            "evaluation_days": result.get("evaluation_days", result.get("eval_days", 0)),
            "filtered_days": result.get("filtered_days", 0),
            "error_code": result.get("error_code", ""),
            "error_detail": result.get("error_detail", ""),
        }
        columns = list(stock_values)
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{column}=excluded.{column}" for column in columns if column not in {"task_id", "code"})
        conn.execute(
            f"""INSERT INTO strategy1_backtest_task_stocks ({', '.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(task_id, code) DO UPDATE SET {updates}""",
            [stock_values[column] for column in columns],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_strategy1_backtest_opportunities(
    task_id: str,
    code: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    conn = get_conn()
    params = [task_id]
    where = "WHERE task_id=?"
    if code:
        where += " AND code=?"
        params.append(code)
    rows = conn.execute(
        "SELECT * FROM strategy1_backtest_opportunities "
        + where
        + " ORDER BY first_detected_date LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy1_backtest_opportunities)")]
    result = [dict(zip(cols, row)) for row in rows]
    for item in result:
        raw_tags = item.get("quality_tags")
        if isinstance(raw_tags, str) and raw_tags:
            try:
                parsed = json.loads(raw_tags)
                item["quality_tags"] = parsed if isinstance(parsed, list) else []
            except Exception:
                item["quality_tags"] = []
        elif not raw_tags:
            item["quality_tags"] = []
    return result


def get_strategy1_backtest_signals(
    task_id: str,
    code: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    conn = get_conn()
    params = [task_id]
    where = "WHERE task_id=?"
    if code:
        where += " AND code=?"
        params.append(code)
    rows = conn.execute(
        "SELECT * FROM strategy1_backtest_signals "
        + where
        + " ORDER BY evaluation_index LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy1_backtest_signals)")]
    return [dict(zip(cols, row)) for row in rows]


def get_strategy1_backtest_task_stocks(task_id: str, status: str | None = None) -> list[dict]:
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM strategy1_backtest_task_stocks WHERE task_id=? AND status=? ORDER BY code",
            (task_id, status),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM strategy1_backtest_task_stocks WHERE task_id=? ORDER BY code",
            (task_id,),
        ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy1_backtest_task_stocks)")]
    return [dict(zip(cols, row)) for row in rows]


def build_strategy1_backtest_summary(task_id: str) -> dict:
    import statistics as _st

    conn = get_conn()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy1_backtest_opportunities)")]
    rows = conn.execute(
        "SELECT * FROM strategy1_backtest_opportunities WHERE task_id=?",
        (task_id,),
    ).fetchall()
    opportunities = [dict(zip(cols, row)) for row in rows]
    entered = [row for row in opportunities if (row.get("entry_price") or 0) > 0]
    realized = [row.get("realized_return") or 0 for row in entered]
    target_count = sum(1 for row in opportunities if row.get("exit_reason") == "TARGET")
    stop_count = sum(1 for row in opportunities if row.get("exit_reason") == "STOP")
    raw_signals_count = conn.execute(
        "SELECT COUNT(*) FROM strategy1_backtest_signals WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]

    def _group_by(field: str) -> dict:
        grouped = {}
        for row in opportunities:
            key = row.get(field) or "UNKNOWN"
            grouped.setdefault(key, []).append(row)
        return {
            key: {
                "count": len(items),
                "entered": sum(1 for item in items if (item.get("entry_price") or 0) > 0),
                "target": sum(1 for item in items if item.get("exit_reason") == "TARGET"),
                "stop": sum(1 for item in items if item.get("exit_reason") == "STOP"),
            }
            for key, items in sorted(grouped.items())
        }

    def _group_by_quality_tag() -> dict:
        grouped = {}
        for row in opportunities:
            raw_tags = row.get("quality_tags")
            tags = []
            if isinstance(raw_tags, str) and raw_tags:
                try:
                    parsed = json.loads(raw_tags)
                    tags = parsed if isinstance(parsed, list) else []
                except Exception:
                    tags = []
            elif isinstance(raw_tags, list):
                tags = raw_tags
            if not tags:
                tags = ["UNTAGGED"]
            for tag in tags:
                grouped.setdefault(tag, []).append(row)
        return {
            key: {
                "count": len(items),
                "entered": sum(1 for item in items if (item.get("entry_price") or 0) > 0),
                "target": sum(1 for item in items if item.get("exit_reason") == "TARGET"),
                "stop": sum(1 for item in items if item.get("exit_reason") == "STOP"),
            }
            for key, items in sorted(grouped.items())
        }

    return {
        "total_opportunities": len(opportunities),
        "raw_signals_count": raw_signals_count,
        "entered_count": len(entered),
        "target_count": target_count,
        "stop_count": stop_count,
        "target_rate": round(target_count / len(entered), 6) if entered else 0.0,
        "stop_rate": round(stop_count / len(entered), 6) if entered else 0.0,
        "average_realized_return": round(_st.mean(realized), 6) if realized else 0.0,
        "median_realized_return": round(_st.median(realized), 6) if realized else 0.0,
        "by_pattern_kind": _group_by("pattern_kind"),
        "by_quality_tag": _group_by_quality_tag(),
    }


def validate_strategy1_backtest_integrity(task_id: str) -> tuple[bool, list[str]]:
    """Validate whether a Strategy1 backtest task can be trusted as baseline."""
    conn = get_conn()
    errors: list[str] = []
    task = get_strategy1_backtest_task(task_id)
    if not task:
        return False, ["task_not_found"]

    if str(task.get("status", "")).lower() != "completed":
        errors.append(f"task status is {task.get('status')}, expected completed")
    if not task.get("data_revision_id"):
        errors.append("missing data_revision_id")
    if task.get("data_revision_version") != STRATEGY1_DATA_REVISION_VERSION:
        errors.append(f"invalid data_revision_version: {task.get('data_revision_version')}")
    if not task.get("strategy_engine_version"):
        errors.append("missing strategy_engine_version")
    if not task.get("backtest_engine_version"):
        errors.append("missing backtest_engine_version")

    total = int(task.get("total_stocks") or 0)
    processed = int(task.get("processed_stocks") or 0)
    stocks_count = conn.execute(
        "SELECT COUNT(*) FROM strategy1_backtest_task_stocks WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]
    if stocks_count != total:
        errors.append(f"task_stocks count mismatch: {stocks_count} != {total}")
    if processed != total:
        errors.append(f"processed {processed} != total {total}")

    pending = conn.execute(
        "SELECT COUNT(*) FROM strategy1_backtest_task_stocks "
        "WHERE task_id=? AND status IN ('PENDING','RUNNING')",
        (task_id,),
    ).fetchone()[0]
    if pending:
        errors.append(f"{pending} stocks still PENDING/RUNNING")

    signal_count = conn.execute(
        "SELECT COUNT(*) FROM strategy1_backtest_signals WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]
    stock_signal_count = conn.execute(
        "SELECT COALESCE(SUM(raw_signals_count),0) FROM strategy1_backtest_task_stocks WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]
    if signal_count != stock_signal_count:
        errors.append(f"signal delta: {signal_count} vs {stock_signal_count}")

    opp_count = conn.execute(
        "SELECT COUNT(*) FROM strategy1_backtest_opportunities WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]
    stock_opp_count = conn.execute(
        "SELECT COALESCE(SUM(opportunities_count),0) FROM strategy1_backtest_task_stocks WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]
    if opp_count != stock_opp_count:
        errors.append(f"opportunity delta: {opp_count} vs {stock_opp_count}")

    if int(task.get("failed_stocks_count") or 0) > 0:
        errors.append(f"failed_stocks_count={task.get('failed_stocks_count')} > 0")
    if not task.get("observation_data_end_date"):
        errors.append("missing observation_data_end_date")
    if not task.get("summary_json"):
        errors.append("missing summary_json")
    else:
        try:
            summary = json.loads(task["summary_json"])
            for key in ["total_opportunities", "raw_signals_count", "entered_count"]:
                if key not in summary:
                    errors.append(f"missing summary key {key}")
        except Exception:
            errors.append("invalid summary_json")

    return len(errors) == 0, errors


def compare_strategy1_backtest_tasks(experiment_task_id: str, baseline_task_id: str) -> dict:
    baseline = get_strategy1_backtest_task(baseline_task_id)
    experiment = get_strategy1_backtest_task(experiment_task_id)
    if not baseline or not experiment:
        return {
            "comparable": False,
            "baselineTaskId": baseline_task_id,
            "experimentTaskId": experiment_task_id,
            "reasons": ["TASK_NOT_FOUND"],
        }

    checks = [
        ("requested_start_date", "DATE_RANGE_MISMATCH"),
        ("requested_end_date", "DATE_RANGE_MISMATCH"),
        ("requested_codes", "STOCK_SCOPE_MISMATCH"),
        ("max_stocks", "STOCK_SCOPE_MISMATCH"),
        ("execution_model", "EXECUTION_MODEL_MISMATCH"),
        ("strategy_engine_version", "STRATEGY_VERSION_MISMATCH"),
        ("data_revision_version", "DATA_REVISION_MISMATCH"),
        ("data_revision_id", "DATA_REVISION_MISMATCH"),
    ]
    reasons = []
    for field, reason in checks:
        if (baseline.get(field) or "") != (experiment.get(field) or "") and reason not in reasons:
            reasons.append(reason)
    if baseline.get("credibility_status") != "TRUSTED_BASELINE":
        reasons.append("BASELINE_NOT_TRUSTED")
    if experiment.get("credibility_status") != "EXPERIMENTAL":
        reasons.append("EXPERIMENT_NOT_MARKED")

    baseline_summary = _strategy1_summary_for_comparison(baseline_task_id, baseline)
    experiment_summary = _strategy1_summary_for_comparison(experiment_task_id, experiment)
    delta = {
        key: round((experiment_summary.get(key) or 0) - (baseline_summary.get(key) or 0), 6)
        for key in {"opportunities", "entered", "target", "stop", "targetRate", "stopRate", "averageRealizedReturn"}
    }
    return {
        "comparable": not reasons,
        "baselineTaskId": baseline_task_id,
        "experimentTaskId": experiment_task_id,
        "reasons": reasons,
        "baseline": baseline_summary,
        "experiment": experiment_summary,
        "delta": delta,
    }


def _insert_strategy1_signal(conn: sqlite3.Connection, task_id: str, signal):
    snapshot_json = json.dumps(getattr(signal, "evaluation_snapshot", None) or {}, ensure_ascii=False)
    conn.execute(
        """INSERT INTO strategy1_backtest_signals
           (task_id, code, name, evaluation_date, evaluation_index, pattern_kind,
            score, current_close, volume_dry_score, price_stable_score,
            pattern_score_20, verdict_key, risk_percent, rr1, stop_loss,
            baseline_passed, experiment_passed, experiment_filter_reason,
            evaluation_snapshot)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            task_id,
            signal.code,
            signal.name,
            signal.evaluation_date,
            signal.evaluation_index,
            signal.pattern_kind,
            signal.score,
            signal.current_close,
            signal.volume_dry_score,
            signal.price_stable_score,
            signal.pattern_score_20,
            signal.verdict_key,
            signal.risk_percent,
            signal.rr1,
            signal.stop_loss,
            1 if signal.baseline_passed else 0,
            1 if signal.experiment_passed else 0,
            signal.experiment_filter_reason,
            snapshot_json,
        ),
    )


def _insert_strategy1_opportunity(conn: sqlite3.Connection, task_id: str, opportunity):
    horizons = getattr(opportunity, "horizons", {}) or {}

    def _horizon_json(days: str) -> str:
        hp = horizons.get(days) or horizons.get(int(days))
        return json.dumps(hp.to_dict() if hasattr(hp, "to_dict") else {}, ensure_ascii=False)

    conn.execute(
        """INSERT INTO strategy1_backtest_opportunities
           (task_id, code, name, first_detected_date, last_detected_date,
            pattern_kind, first_score, max_score, signal_count, entry_date,
            entry_price, stop_loss, exit_date, exit_price, exit_reason,
            realized_return, mark_to_market_end_return, holding_days,
            available_forward_days, horizon_3, horizon_5, horizon_10,
            horizon_20, market_context_json, evaluation_snapshot,
            volume_dry_score, price_stable_score, verdict_key, quality_tags,
            quality_layer, short_term_exit_note)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            task_id,
            opportunity.code,
            opportunity.name,
            opportunity.first_detected_date,
            opportunity.last_detected_date,
            opportunity.pattern_kind,
            opportunity.first_score,
            opportunity.max_score,
            opportunity.signal_count,
            opportunity.entry_date,
            opportunity.entry_price,
            opportunity.stop_loss,
            opportunity.exit_date,
            opportunity.exit_price,
            opportunity.exit_reason,
            opportunity.realized_return,
            opportunity.mark_to_market_end_return,
            opportunity.holding_days,
            opportunity.available_forward_days,
            _horizon_json("3"),
            _horizon_json("5"),
            _horizon_json("10"),
            _horizon_json("20"),
            json.dumps(opportunity.market_context or {}, ensure_ascii=False),
            json.dumps(opportunity.evaluation_snapshot or {}, ensure_ascii=False),
            getattr(opportunity, "volume_dry_score", 0),
            getattr(opportunity, "price_stable_score", 0),
            getattr(opportunity, "verdict_key", ""),
            json.dumps(getattr(opportunity, "quality_tags", []) or [], ensure_ascii=False),
            getattr(opportunity, "quality_layer", "normal"),
            getattr(opportunity, "short_term_exit_note", ""),
        ),
    )


def _strategy1_summary_for_comparison(task_id: str, task: dict) -> dict:
    raw = task.get("summary_json")
    if raw:
        try:
            summary = json.loads(raw)
            return {
                "opportunities": summary.get("total_opportunities", summary.get("opportunities", 0)),
                "entered": summary.get("entered_count", summary.get("entered", 0)),
                "target": summary.get("target_count", summary.get("target", 0)),
                "stop": summary.get("stop_count", summary.get("stop", 0)),
                "targetRate": summary.get("target_rate", summary.get("targetRate", 0)),
                "stopRate": summary.get("stop_rate", summary.get("stopRate", 0)),
                "averageRealizedReturn": summary.get(
                    "average_realized_return",
                    summary.get("averageRealizedReturn", 0),
                ),
            }
        except Exception:
            pass
    summary = build_strategy1_backtest_summary(task_id)
    return {
        "opportunities": summary["total_opportunities"],
        "entered": summary["entered_count"],
        "target": summary["target_count"],
        "stop": summary["stop_count"],
        "targetRate": summary["target_rate"],
        "stopRate": summary["stop_rate"],
        "averageRealizedReturn": summary["average_realized_return"],
    }


def _strategy1_experiment_enabled(experiment) -> bool:
    if isinstance(experiment, str):
        try:
            experiment = json.loads(experiment)
        except Exception:
            return False
    return bool(isinstance(experiment, dict) and experiment.get("enabled"))
