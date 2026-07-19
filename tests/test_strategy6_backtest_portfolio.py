from strategy6.backtest.portfolio import allocate_candidates, simulate_portfolio


def _candidate(code, candidate_type, score, entry=10.0, stop=9.5):
    return {
        "code": code,
        "candidate_type": candidate_type,
        "total_score": score,
        "entry_price": entry,
        "stop_loss_price": stop,
    }


def test_candidate_allocation_uses_production_tier_then_score_and_cash_limit():
    candidates = [
        _candidate("A", "WATCH_CANDIDATE", 99),
        _candidate("B", "KEY_CANDIDATE", 80),
        _candidate("C", "READY_CANDIDATE", 75),
    ]
    result = allocate_candidates(
        candidates, equity=100_000, cash=25_000, mode="EQUAL_WEIGHT",
        max_positions=2, max_position_pct=0.2, risk_per_trade=0.01,
    )
    assert [item["code"] for item in result.allocations] == ["C"]
    assert result.rejected[0]["reason"] == "INSUFFICIENT_CASH"


def test_fixed_risk_position_uses_stop_distance_and_board_lot():
    result = allocate_candidates(
        [_candidate("A", "READY_CANDIDATE", 90, entry=10, stop=9)],
        equity=100_000, cash=100_000, mode="FIXED_RISK",
        max_positions=10, max_position_pct=0.2, risk_per_trade=0.01,
    )
    allocation = result.allocations[0]
    assert allocation["shares"] == 1000
    assert allocation["notional"] == 10_000


def test_portfolio_replay_enforces_cash_concurrency_and_same_stock_overlap():
    trades = [
        {"code": "A", "candidate_type": "READY_CANDIDATE", "total_score": 80, "entry_date": "2025-01-02", "exit_date": "2025-01-10", "entry_price": 10, "stop_loss_price": 9, "net_profit": 100, "net_return": 0.1},
        {"code": "B", "candidate_type": "WATCH_CANDIDATE", "total_score": 99, "entry_date": "2025-01-02", "exit_date": "2025-01-05", "entry_price": 10, "stop_loss_price": 9, "net_profit": 100, "net_return": 0.1},
        {"code": "A", "candidate_type": "READY_CANDIDATE", "total_score": 90, "entry_date": "2025-01-03", "exit_date": "2025-01-06", "entry_price": 10, "stop_loss_price": 9, "net_profit": 100, "net_return": 0.1},
    ]
    result = simulate_portfolio(
        trades, initial_equity=20_000, mode="EQUAL_WEIGHT", risk_per_trade=0.01,
        max_position_pct=1.0, max_concurrent_positions=1,
    )
    assert [item["code"] for item in result["accepted_trades"]] == ["A"]
    assert result["rejected_count"] == 2
    assert result["max_concurrent_positions"] == 1
