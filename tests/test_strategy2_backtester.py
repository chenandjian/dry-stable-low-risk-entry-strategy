# tests/test_strategy2_backtester.py
"""策略2回测 Phase 1 可信度修复测试。"""
import pytest
from strategy2.backtest_models import (
    HorizonPerformance, BacktestOpportunity, BacktestSignal,
    BacktestSummary, InsufficientStock,
)
from strategy2.backtester import (
    calculate_horizon_performance,
    merge_consecutive_signals,
    aggregate_backtest_summary,
)


def _make_future(highs, lows, closes):
    return [{"date": f"f-{i+1}", "high": h, "low": l, "close": c, "open": c}
            for i, (h, l, c) in enumerate(zip(highs, lows, closes))]


# ═══ calculate_horizon_performance (existing, unchanged) ═══

def test_success_target_hit_before_stop():
    future = _make_future([10.3, 10.2, 10.6], [9.8, 9.7, 9.9], [10.1, 10.0, 10.3])
    r = calculate_horizon_performance(future, 10.0, 9.5, 3)
    assert r.result == "SUCCESS"

def test_failed_stop_hit_before_target():
    future = _make_future([10.2, 10.1], [9.8, 9.4], [10.0, 9.6])
    r = calculate_horizon_performance(future, 10.0, 9.5, 2)
    assert r.result == "FAILED"

def test_unresolved_neither_hit():
    future = _make_future([10.3, 10.2, 10.1], [9.8, 9.7, 9.6], [10.1, 10.0, 9.9])
    r = calculate_horizon_performance(future, 10.0, 9.5, 3)
    assert r.result == "UNRESOLVED"

def test_unobserved_insufficient_future_data():
    r = calculate_horizon_performance(_make_future([10.3], [9.8], [10.1]), 10.0, 9.5, 20)
    assert r.result == "UNOBSERVED"

def test_same_day_target_and_stop_is_failed():
    r = calculate_horizon_performance(_make_future([10.6], [9.4], [10.0]), 10.0, 9.5, 1)
    assert r.result == "FAILED"

def test_empty_future_is_unobserved():
    assert calculate_horizon_performance([], 10.0, 9.5, 5).result == "UNOBSERVED"


# ═══ merge_consecutive_signals (REWRITTEN Phase 1) ═══

def _sig(date, idx, score=70, close=10.0):
    return BacktestSignal(code="000001", name="test", evaluation_date=date,
                          evaluation_index=idx, score=score, current_close=close,
                          stop_loss=9.5, risk_ratio=0.03)

# Eval results per index: "PASSED" = hit, other = missed
P = "PASSED"
L = "LIQUIDITY_FILTERED"
D = "DOWNTREND_FILTERED"
S = "SCORE_BELOW_THRESHOLD"
R = "RISK_RATIO_TOO_HIGH"
I = "INSUFFICIENT_DATA"
E = "EVALUATION_ERROR"


def test_consecutive_signals_merge_when_adjacent():
    """相邻命中 → 一个机会。"""
    hits = [_sig("2025-01-02", 10), _sig("2025-01-03", 11)]
    eval_results = {10: P, 11: P}
    opps = merge_consecutive_signals(hits, eval_results)
    assert len(opps) == 1

def test_9_missed_days_same_opportunity():
    """命中后连续9个未命中日再命中 → 仍属同一机会。"""
    # idx 10: hit, 11-19: 9 missed, 20: hit again
    hits = [_sig("2025-01-02", 10), _sig("2025-01-15", 20)]
    eval_results = {
        10: P, 11: L, 12: L, 13: S, 14: R, 15: D, 16: L, 17: S, 18: R, 19: L,
        20: P,
    }
    opps = merge_consecutive_signals(hits, eval_results)
    assert len(opps) == 1

def test_10_missed_days_new_opportunity():
    """命中后连续10个未命中日再命中 → 新机会。"""
    hits = [_sig("2025-01-02", 10), _sig("2025-01-16", 21)]
    eval_results = {
        10: P, 11: L, 12: L, 13: S, 14: R, 15: D, 16: L, 17: S, 18: R, 19: L, 20: L,
        21: P,
    }
    opps = merge_consecutive_signals(hits, eval_results)
    assert len(opps) == 2, f"Expected 2 opportunities, got {len(opps)}"

def test_months_apart_split():
    """相隔数月 → 必定拆分（中间大量未命中日）。"""
    hits = [_sig("2025-01-02", 10), _sig("2025-06-01", 100)]
    # 89 gaps filled with liquidity filtered (counts as missed)
    eval_results = {10: P}
    for i in range(11, 100):
        eval_results[i] = L
    eval_results[100] = P
    opps = merge_consecutive_signals(hits, eval_results)
    assert len(opps) == 2

def test_liquidity_filtered_counts_as_missed():
    """流动性过滤未通过 → 计入冷却期。"""
    hits = [_sig("2025-01-02", 10), _sig("2025-01-16", 21)]
    eval_results = {10: P}
    for i in range(11, 21):
        eval_results[i] = L  # all liquidity filtered
    eval_results[21] = P
    opps = merge_consecutive_signals(hits, eval_results)
    assert len(opps) == 2  # 10 gaps → new opp

def test_invalid_data_does_not_count_as_missed():
    """数据异常日 → 不计入冷却期。"""
    hits = [_sig("2025-01-02", 10), _sig("2025-01-16", 21)]
    eval_results = {10: P}
    for i in range(11, 16):
        eval_results[i] = L   # 5 liquidity filtered (counted)
    for i in range(16, 21):
        eval_results[i] = I   # 5 insufficient (NOT counted)
    eval_results[21] = P
    # Only 5 counted missed days → same opportunity
    opps = merge_consecutive_signals(hits, eval_results)
    assert len(opps) == 1

def test_different_codes_separate():
    """不同股票独立处理。"""
    hits = [
        _sig("2025-01-02", 10),
        BacktestSignal(code="000002", name="b", evaluation_date="2025-01-02",
                       evaluation_index=10, score=70, current_close=10.0, stop_loss=9.5),
    ]
    opps = merge_consecutive_signals(hits, {10: P})
    assert len(opps) == 2
    assert {o.code for o in opps} == {"000001", "000002"}

def test_signal_count_accurate():
    """每个机会的记录数准确。"""
    hits = [_sig("2025-01-02", 10), _sig("2025-01-03", 11), _sig("2025-01-06", 12)]
    eval_results = {10: P, 11: P, 12: P}
    opps = merge_consecutive_signals(hits, eval_results)
    assert len(opps) == 1
    assert opps[0].consecutive_hit_days == 3
    assert opps[0].first_score == 70


# ═══ aggregate_backtest_summary ═══

def test_summary_counts():
    s = aggregate_backtest_summary([BacktestOpportunity(code="a")])
    assert s.total_opportunities == 1

def test_empty_no_crash():
    assert aggregate_backtest_summary([]).total_opportunities == 0


# ═══ DB round-trip tests (Batch A) ═══

def test_signal_save_roundtrip(tmp_path):
    """新数据库保存原始信号 → 查询一致。"""
    import scanner.db as db, os
    p = str(tmp_path / "test.db")
    db.init_db(p)
    signal = type('s',(),{'code':'000001','name':'t','evaluation_date':'2025-01-01','evaluation_index':0,'score':70,'level':'','current_close':10.0,'stop_loss':9.5,'risk_ratio':0.03,'volume_dry_score':20,'price_stable_score':50,'trend_type':'','trend_evidence_score':3,'evaluation_snapshot':{'k':'v'}})()
    db.save_strategy2_backtest_signal('t1', signal)
    rows = db.get_conn().execute("SELECT * FROM strategy2_backtest_signals WHERE task_id='t1'").fetchall()
    assert len(rows) == 1
    # 幂等：重复保存不增加
    db.save_strategy2_backtest_signal('t1', signal)
    assert db.get_conn().execute("SELECT COUNT(*) FROM strategy2_backtest_signals WHERE task_id='t1'").fetchone()[0] == 1

def test_opportunity_save_with_execution_fields(tmp_path):
    """保存带执行字段的机会 → round-trip 一致。"""
    import scanner.db as db, os
    p = str(tmp_path / "test.db")
    db.init_db(p)
    opp = {'code':'t','name':'','first_detected_date':'2025-01-01','last_detected_date':'2025-01-02','consecutive_hit_days':2,'first_score':70,'max_score':75,'level':'重点观察','entry_close':10.0,'stop_loss':9.5,'risk_ratio':0.03,'trend_type':'UPTREND_OR_SIDEWAYS','trend_evidence_score':4,'evaluation_snapshot':'{}','horizon_3':'{}','horizon_5':'{}','horizon_10':'{}','horizon_20':'{}','signal_count':2,'execution_model':'NEXT_OPEN','entry_date':'2025-01-03','entry_price':10.1,'exit_date':'2025-01-05','exit_price':10.5,'exit_reason':'TARGET','realized_return':0.0396,'mark_to_market_end_return':0.04,'holding_days':2,'available_forward_days':20}
    db.save_strategy2_backtest_opportunity('t2', opp)
    rows = db.get_strategy2_backtest_opportunities('t2')
    assert len(rows) == 1
    r = rows[0]
    assert r['execution_model'] == 'NEXT_OPEN'
    assert r['entry_price'] == 10.1
    assert r['exit_reason'] == 'TARGET'
    assert r['exit_date'] == '2025-01-05'
    assert r['signal_count'] == 2
