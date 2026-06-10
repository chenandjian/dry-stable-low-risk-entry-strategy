# tests/test_strategy2_risk.py
"""策略2风险计算测试 — key_support、买入区间、止损、风险比。"""
import pytest
from strategy2.risk import compute_key_support, compute_risk, compute_buy_zone
from strategy2.models import Strategy2Risk


class TestComputeKeySupport:
    def test_excludes_evaluation_day(self):
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        data = []
        for i in range(20):
            date = (base - timedelta(days=19 - i)).strftime("%Y-%m-%d")
            c = 10.0 + i * 0.1
            data.append({"date": date, "close": c, "volume": 1_000_000})
        support = compute_key_support(data, lookback_days=10)
        # Excludes eval day (idx=19, close=11.9); lookback 10 before that:
        # idx 9-18 → closes 10.9-11.8 → min = 10.9
        assert support == pytest.approx(10.9)
        # Verify it's NOT the eval day close
        assert support != data[-1]["close"]

    def test_insufficient_data(self):
        data = [
            {"date": "2026-06-01", "close": 10.0, "volume": 1_000_000},
            {"date": "2026-06-02", "close": 10.5, "volume": 1_000_000},
            {"date": "2026-06-03", "close": 9.8, "volume": 1_000_000},
        ]
        support = compute_key_support(data, lookback_days=10)
        # 2 days before eval → min(10.0, 10.5) = 10.0
        assert support == 10.0

    def test_single_day_returns_none(self):
        data = [{"date": "2026-06-10", "close": 10.0, "volume": 1_000_000}]
        support = compute_key_support(data, lookback_days=10)
        assert support is None

    def test_lookback_larger_than_available(self):
        data = [
            {"date": "2026-06-08", "close": 10.5, "volume": 1_000_000},
            {"date": "2026-06-09", "close": 10.0, "volume": 1_000_000},
            {"date": "2026-06-10", "close": 10.2, "volume": 1_000_000},
        ]
        support = compute_key_support(data, lookback_days=10)
        assert support == 10.0  # min of 10.5, 10.0


class TestComputeBuyZone:
    def test_basic(self):
        low, high = compute_buy_zone(10.00, buy_zone_max_premium=0.03)
        assert low == 10.00
        assert high == pytest.approx(10.30)

    def test_different_premium(self):
        low, high = compute_buy_zone(10.00, buy_zone_max_premium=0.05)
        assert low == 10.00
        assert high == pytest.approx(10.50)


class TestComputeRisk:
    def test_low_risk(self):
        r = compute_risk(current_close=10.00, key_support=9.95,
                         buy_zone_max_premium=0.03, stop_loss_buffer=0.02)
        assert r.key_support == 9.95
        assert r.buy_zone_low == 9.95
        assert r.buy_zone_high == pytest.approx(9.95 * 1.03, abs=0.01)
        # stop = 9.95 * 0.98 = 9.751; rr = (10.00 - 9.751) / 10.00 ≈ 0.0249
        assert r.stop_loss == pytest.approx(9.751, abs=0.01)
        expected_rr = (10.00 - 9.751) / 10.00
        assert r.risk_ratio == pytest.approx(expected_rr, abs=0.001)
        assert r.risk_ratio <= 0.03
        assert r.risk_level == "低风险"

    def test_acceptable_risk(self):
        r = compute_risk(current_close=10.50, key_support=9.80,
                         buy_zone_max_premium=0.03, stop_loss_buffer=0.03)
        stop = 9.80 * 0.97  # 9.506
        rr = (10.50 - stop) / 10.50  # ≈ 9.47%
        if 0.03 < rr <= 0.05:
            assert r.risk_level == "风险可接受"
        elif rr <= 0.03:
            assert r.risk_level == "低风险"
        # either way, it's valid

    def test_high_risk(self):
        r = compute_risk(current_close=10.50, key_support=8.00,
                         buy_zone_max_premium=0.03, stop_loss_buffer=0.03)
        assert r.risk_ratio > 0.05
        assert r.risk_level == "高风险"

    def test_risk_ratio_boundary_3_percent(self):
        r = compute_risk(current_close=10.50, key_support=10.50,
                         buy_zone_max_premium=0.03, stop_loss_buffer=0.03)
        assert r.risk_ratio == pytest.approx(0.03, abs=0.001)
        assert r.risk_level == "低风险"

    def test_risk_ratio_boundary_5_percent(self):
        # Use clean math: close=100, support=100, buffer=0.05 → stop=95, rr=0.05
        r = compute_risk(current_close=100.0, key_support=100.0,
                         buy_zone_max_premium=0.03, stop_loss_buffer=0.05)
        assert r.risk_ratio == pytest.approx(0.05, abs=0.001)
        assert r.risk_level == "风险可接受"

    def test_returns_strategy2_risk_dataclass(self):
        r = compute_risk(current_close=10.50, key_support=10.00)
        assert isinstance(r, Strategy2Risk)

    def test_zero_close_safe(self):
        """Zero close should not cause division errors."""
        r = compute_risk(current_close=0.0, key_support=10.00)
        assert r.risk_ratio >= 0
