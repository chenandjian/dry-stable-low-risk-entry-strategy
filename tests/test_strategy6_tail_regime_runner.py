import sqlite3

from strategy6.backtest.cli import build_parser
from strategy6.backtest.tail_regime_runner import (
    completed_tail_regime_codes,
    init_tail_regime_checkpoint,
    persist_tail_regime_stock_result,
)


def _stock_result(*, evaluation_date="2025-01-02", group="REGIME_ONLY"):
    return {
        "status": "COMPLETED",
        "daily_labels": [{
            "code": "000001",
            "name": "平安银行",
            "evaluation_date": evaluation_date,
            "group": group,
            "fixed_pass": False,
            "fixed_reasons": ["TAIL_VOLUME_NOT_DRY"],
            "regime_status": "CONFIRMED",
            "regime_start_date": "2024-12-25",
            "regime_days": 6,
            "regime_delta_bic": 9.5,
            "regime_reasons": ["ROBUST_BIC_CHANGE_POINT"],
            "regime_risks": [],
        }],
        "signals": [{
            "code": "000001",
            "name": "平安银行",
            "evaluation_date": evaluation_date,
            "setup_id": "setup-1",
            "candidate_type": "WATCH_CANDIDATE",
            "tail_regime_group": group,
            "research_tail_path": "REGIME",
        }],
        "orders": [{
            "order_id": "order-1",
            "code": "000001",
            "signal_date": evaluation_date,
            "status": "FILLED",
        }],
        "trades": [{
            "trade_id": "trade-1",
            "code": "000001",
            "signal_date": evaluation_date,
            "entry_date": "2025-01-03",
            "exit_date": "2025-01-10",
            "r_multiple": 2.0,
            "tail_regime_group": group,
        }],
    }


def test_tail_regime_full_command_is_available():
    args = build_parser().parse_args(["tail-regime-full"])

    assert args.command == "tail-regime-full"
    assert args.evaluation_step == 1


def test_tail_regime_checkpoint_replaces_one_stock_atomically_and_resumes(tmp_path):
    path = tmp_path / "tail-regime.sqlite3"
    conn = init_tail_regime_checkpoint(
        path,
        run_id="tail-run-1",
        metadata={"start_date": "2023-01-01", "end_date": "2025-12-31"},
    )

    persist_tail_regime_stock_result(
        conn,
        run_id="tail-run-1",
        code="000001",
        name="平安银行",
        result=_stock_result(),
    )
    persist_tail_regime_stock_result(
        conn,
        run_id="tail-run-1",
        code="000001",
        name="平安银行",
        result=_stock_result(evaluation_date="2025-01-03", group="BOTH"),
    )

    assert completed_tail_regime_codes(conn, "tail-run-1") == {"000001"}
    assert conn.execute(
        "SELECT COUNT(*) FROM tail_regime_labels WHERE run_id='tail-run-1'"
    ).fetchone()[0] == 1
    row = conn.execute(
        "SELECT evaluation_date, group_name FROM tail_regime_labels "
        "WHERE run_id='tail-run-1' AND code='000001'"
    ).fetchone()
    assert tuple(row) == ("2025-01-03", "BOTH")
    assert conn.execute(
        "SELECT COUNT(*) FROM tail_regime_signals WHERE run_id='tail-run-1'"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT status FROM tail_regime_stock_progress "
        "WHERE run_id='tail-run-1' AND code='000001'"
    ).fetchone()[0] == "COMPLETED"
    conn.close()

    reopened = sqlite3.connect(path)
    assert completed_tail_regime_codes(reopened, "tail-run-1") == {"000001"}
    reopened.close()
