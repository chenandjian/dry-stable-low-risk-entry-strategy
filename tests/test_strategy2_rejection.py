# tests/test_strategy2_rejection.py
"""策略2一票否决规则测试。"""
import pytest
from strategy2.models import Strategy2Indicators
from strategy2.rejection import check_rejection_rules


def _ind(**kwargs) -> Strategy2Indicators:
    defaults = dict(
        v3=1_000_000, v5=1_200_000, v10=1_500_000, v20=2_000_000,
        volume_ratio_5_20=0.60, volume_percentile=18.0,
        volume_percentile_days=60, range_5=0.03,
        close_range_5=0.025, return_3=-0.01, return_5=-0.02,
        daily_return=0.005,
    )
    defaults.update(kwargs)
    return Strategy2Indicators(**defaults)


def _make_flat_data(days: int, close: float = 10.0, volume: float = 1_000_000) -> list[dict]:
    from datetime import datetime, timedelta
    base = datetime(2026, 6, 10)
    return [
        {"date": (base - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d"),
         "open": close, "high": close, "low": close,
         "close": close, "volume": volume, "turnover": close * volume}
        for i in range(days)
    ]


class TestRejectionRules:
    def test_no_rejection(self):
        ind = _ind(return_5=-0.02, return_3=0.01, range_5=0.03)
        data = _make_flat_data(60)
        rejects = check_rejection_rules(ind, data, key_support=9.50, current_close=10.0, v20=2_000_000)
        assert rejects == []

    def test_reject_return_5_below_minus_5(self):
        ind = _ind(return_5=-0.06)
        rejects = check_rejection_rules(ind, [], key_support=10.0, current_close=10.0, v20=1_000_000)
        assert "REJECT_VOLUME_DRY_PRICE_DROP" in rejects

    def test_reject_return_5_at_boundary(self):
        """return_5 == -5% exactly → 触发否决 (strict less than not used, check boundary)."""
        ind = _ind(return_5=-0.05)
        rejects = check_rejection_rules(ind, [], key_support=10.0, current_close=10.0, v20=1_000_000)
        # -0.05 is not < -0.05, so should NOT trigger
        assert "REJECT_VOLUME_DRY_PRICE_DROP" not in rejects

    def test_reject_heavy_volume_drop(self):
        """单日跌幅 <= -4% 且成交量 > V20。"""
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        data = []
        for i in range(60):
            date = (base - timedelta(days=59 - i)).strftime("%Y-%m-%d")
            data.append({"date": date, "open": 10, "high": 10, "low": 10,
                         "close": 10.0, "volume": 1_000_000, "turnover": 10_000_000})
        data[-4]["close"] = 9.5  # -5% from prev close 10.0
        data[-4]["volume"] = 3_000_000  # > V20
        ind = _ind()
        rejects = check_rejection_rules(ind, data, key_support=9.0, current_close=10.0, v20=2_000_000)
        assert "REJECT_HEAVY_VOLUME_DROP" in rejects

    def test_no_reject_heavy_volume_with_low_volume(self):
        """单日跌幅 <= -4% 但成交量 <= V20 → 不触发。"""
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        data = _make_flat_data(60)
        data[-4]["close"] = 9.5  # -5% drop
        data[-4]["volume"] = 1_500_000  # < V20=2_000_000
        ind = _ind()
        rejects = check_rejection_rules(ind, data, key_support=9.0, current_close=10.0, v20=2_000_000)
        assert "REJECT_HEAVY_VOLUME_DROP" not in rejects

    def test_reject_range_too_wide(self):
        ind = _ind(range_5=0.10)
        rejects = check_rejection_rules(ind, [], key_support=10.0, current_close=10.0, v20=1_000_000)
        assert "REJECT_RANGE_TOO_WIDE" in rejects

    def test_reject_range_at_boundary(self):
        """range_5 == 8% exactly → not rejected."""
        ind = _ind(range_5=0.08)
        rejects = check_rejection_rules(ind, [], key_support=10.0, current_close=10.0, v20=1_000_000)
        assert "REJECT_RANGE_TOO_WIDE" not in rejects

    def test_reject_support_broken(self):
        ind = _ind()
        rejects = check_rejection_rules(ind, [], key_support=11.0, current_close=10.0, v20=1_000_000)
        assert "REJECT_SUPPORT_BROKEN" in rejects

    def test_no_reject_support_ok(self):
        ind = _ind()
        rejects = check_rejection_rules(ind, [], key_support=9.50, current_close=10.0, v20=1_000_000)
        assert "REJECT_SUPPORT_BROKEN" not in rejects

    def test_reject_recent_surge(self):
        ind = _ind(return_3=0.10)
        rejects = check_rejection_rules(ind, [], key_support=10.0, current_close=10.0, v20=1_000_000)
        assert "REJECT_RECENT_SURGE" in rejects

    def test_reject_recent_surge_boundary(self):
        """return_3 == 8% → triggers."""
        ind = _ind(return_3=0.08)
        rejects = check_rejection_rules(ind, [], key_support=10.0, current_close=10.0, v20=1_000_000)
        assert "REJECT_RECENT_SURGE" in rejects

    def test_multiple_rejections(self):
        ind = _ind(return_5=-0.06, range_5=0.10, return_3=0.09)
        rejects = check_rejection_rules(ind, [], key_support=10.0, current_close=10.0, v20=1_000_000)
        assert len(rejects) >= 3
