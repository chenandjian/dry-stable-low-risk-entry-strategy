# tests/test_strategy2_indicators.py
"""策略2指标计算测试。"""
import pytest
from strategy2.indicators import (
    compute_indicators,
    compute_volume_percentile,
    validate_strategy_data,
)
from strategy2.models import IndicatorValidation


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_flat_data(days: int, close: float = 10.0, volume: float = 1_000_000) -> list[dict]:
    """Create flat price/volume data for N days, ascending by date."""
    from datetime import datetime, timedelta
    base = datetime(2026, 6, 10)
    return [
        {"date": (base - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d"),
         "open": close * 0.99, "high": close * 1.02, "low": close * 0.98,
         "close": close, "volume": volume, "turnover": close * volume}
        for i in range(days)
    ]


# ── validate_strategy_data ───────────────────────────────────────────────────

class TestValidateStrategyData:
    def test_valid_data_passes(self):
        data = _make_flat_data(120)
        result = validate_strategy_data(data, strategy_window_days=120, min_required=60)
        assert result.valid is True
        assert result.data_days == 120

    def test_empty_data_fails(self):
        result = validate_strategy_data([], strategy_window_days=120, min_required=60)
        assert result.valid is False
        assert result.reason == "INVALID_MARKET_DATA"

    def test_none_data_fails(self):
        result = validate_strategy_data(None, strategy_window_days=120, min_required=60)
        assert result.valid is False
        assert result.reason == "INVALID_MARKET_DATA"

    def test_insufficient_days_fails(self):
        data = _make_flat_data(30)
        result = validate_strategy_data(data, strategy_window_days=120, min_required=60)
        assert result.valid is False
        assert result.reason == "INSUFFICIENT_STRATEGY_DATA"

    def test_null_close_fails(self):
        data = _make_flat_data(120)
        data[-1]["close"] = None
        result = validate_strategy_data(data, strategy_window_days=120, min_required=60)
        assert result.valid is False
        assert result.reason == "INVALID_MARKET_DATA"

    def test_negative_volume_fails(self):
        data = _make_flat_data(120)
        data[0]["volume"] = -1000
        result = validate_strategy_data(data, strategy_window_days=120, min_required=60)
        assert result.valid is False
        assert result.reason == "INVALID_MARKET_DATA"

    def test_zero_close_fails(self):
        data = _make_flat_data(120)
        data[50]["close"] = 0
        result = validate_strategy_data(data, strategy_window_days=120, min_required=60)
        assert result.valid is False
        assert result.reason == "INVALID_MARKET_DATA"

    def test_non_numeric_close_fails(self):
        data = _make_flat_data(120)
        data[0]["close"] = "abc"
        result = validate_strategy_data(data, strategy_window_days=120, min_required=60)
        assert result.valid is False
        assert result.reason == "INVALID_MARKET_DATA"


# ── compute_indicators ───────────────────────────────────────────────────────

class TestComputeIndicators:
    def test_v3_v5_v10_v20_calculation(self):
        """V3/V5/V10/V20 are simple moving averages of volume."""
        data = []
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        for i in range(120):
            date = (base - timedelta(days=119 - i)).strftime("%Y-%m-%d")
            vol = 1_000_000 * (1 + i % 10)
            data.append({"date": date, "open": 10, "high": 10.2, "low": 9.8,
                         "close": 10, "volume": vol, "turnover": 10 * vol})

        ind = compute_indicators(data)
        expected_v3 = sum(d["volume"] for d in data[-3:]) / 3
        assert ind.v3 == pytest.approx(expected_v3)
        expected_v5 = sum(d["volume"] for d in data[-5:]) / 5
        assert ind.v5 == pytest.approx(expected_v5)
        expected_v10 = sum(d["volume"] for d in data[-10:]) / 10
        assert ind.v10 == pytest.approx(expected_v10)
        expected_v20 = sum(d["volume"] for d in data[-20:]) / 20
        assert ind.v20 == pytest.approx(expected_v20)

    def test_volume_ratio_5_20_equal_volumes(self):
        data = _make_flat_data(120, close=10.0, volume=1_000_000)
        ind = compute_indicators(data)
        assert ind.volume_ratio_5_20 == pytest.approx(1.0)

    def test_volume_ratio_5_20_shrinking(self):
        """V5 smaller than V20 → ratio < 1."""
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        data = []
        for i in range(120):
            date = (base - timedelta(days=119 - i)).strftime("%Y-%m-%d")
            vol = 500_000 if i >= 115 else 2_000_000
            data.append({"date": date, "open": 10, "high": 10.2, "low": 9.8,
                         "close": 10, "volume": vol, "turnover": 10 * vol})
        ind = compute_indicators(data)
        # V5 = 500k; V20 = (5×500k + 15×2M) / 20 = 1.625M → ratio ≈ 0.308
        assert ind.volume_ratio_5_20 == pytest.approx(500_000 / 1_625_000, rel=0.01)
        assert ind.volume_ratio_5_20 < 1.0

    def test_zero_v20_handled(self):
        """V20 = 0 should not cause ZeroDivisionError."""
        data = _make_flat_data(120, close=10.0, volume=0)
        ind = compute_indicators(data)
        assert ind.v20 == 0.0
        assert ind.volume_ratio_5_20 == 0.0  # safe fallback

    def test_range_5_flat_data(self):
        """Truly flat data (high=low=close) → range_5 = 0."""
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        data = []
        for i in range(120):
            date = (base - timedelta(days=119 - i)).strftime("%Y-%m-%d")
            data.append({"date": date, "open": 10.0, "high": 10.0, "low": 10.0,
                         "close": 10.0, "volume": 1_000_000, "turnover": 10_000_000})
        ind = compute_indicators(data)
        assert ind.range_5 == pytest.approx(0.0)

    def test_range_5_with_variation(self):
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        rows = []
        for i in range(120):
            date = (base - timedelta(days=119 - i)).strftime("%Y-%m-%d")
            high = 10.0 + (0.5 if i >= 115 else 0)
            low = 10.0 - (0.5 if i >= 115 else 0)
            rows.append({"date": date, "open": 10.0, "high": high, "low": low,
                         "close": 10.0, "volume": 1_000_000, "turnover": 10_000_000})
        ind = compute_indicators(rows)
        assert ind.range_5 == pytest.approx(1.0 / 9.5, rel=0.01)

    def test_close_range_5(self):
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        data = []
        for i in range(120):
            date = (base - timedelta(days=119 - i)).strftime("%Y-%m-%d")
            c = 10.0 + (0.3 if i >= 115 else 0)
            data.append({"date": date, "open": c, "high": c, "low": c,
                         "close": c, "volume": 1_000_000, "turnover": c * 1_000_000})
        ind = compute_indicators(data)
        high_close = max(d["close"] for d in data[-5:])
        low_close = min(d["close"] for d in data[-5:])
        expected = (high_close - low_close) / low_close
        assert ind.close_range_5 == pytest.approx(expected)

    def test_return_5_calculation(self):
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        data = []
        for i in range(120):
            date = (base - timedelta(days=119 - i)).strftime("%Y-%m-%d")
            c = 10.0 * (1.05 if i >= 115 else 1.0)
            data.append({"date": date, "open": c, "high": c, "low": c,
                         "close": c, "volume": 1_000_000, "turnover": c * 1_000_000})
        ind = compute_indicators(data)
        expected = data[-1]["close"] / data[-6]["close"] - 1
        assert ind.return_5 == pytest.approx(expected)

    def test_return_3_calculation(self):
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        data = []
        for i in range(120):
            date = (base - timedelta(days=119 - i)).strftime("%Y-%m-%d")
            c = 10.0 * (1.03 if i >= 117 else 1.0)
            data.append({"date": date, "open": c, "high": c, "low": c,
                         "close": c, "volume": 1_000_000, "turnover": c * 1_000_000})
        ind = compute_indicators(data)
        expected = data[-1]["close"] / data[-4]["close"] - 1
        assert ind.return_3 == pytest.approx(expected)

    def test_daily_return(self):
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        data = []
        for i in range(120):
            date = (base - timedelta(days=119 - i)).strftime("%Y-%m-%d")
            c = 10.0 + i * 0.01
            data.append({"date": date, "open": c, "high": c, "low": c,
                         "close": c, "volume": 1_000_000, "turnover": c * 1_000_000})
        ind = compute_indicators(data)
        expected = data[-1]["close"] / data[-2]["close"] - 1
        assert ind.daily_return == pytest.approx(expected)

    def test_short_data_still_computes(self):
        """Data with less than 20 days computes what it can."""
        data = _make_flat_data(5)
        ind = compute_indicators(data)
        assert ind.v3 > 0
        assert ind.v5 > 0
        # V10 and V20 use available data if less than 10/20 days
        assert ind.v10 >= 0
        assert ind.v20 >= 0

    def test_minimal_data_two_days(self):
        data = _make_flat_data(2)
        ind = compute_indicators(data)
        assert ind.v3 > 0
        assert ind.daily_return == pytest.approx(0.0)

    def test_volume_percentile_low(self):
        """When recent volume is low, percentile should be low."""
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        data = []
        for i in range(120):
            date = (base - timedelta(days=119 - i)).strftime("%Y-%m-%d")
            vol = 1_000_000 if i < 115 else 300_000  # low volume in last 5
            data.append({"date": date, "open": 10, "high": 10.2, "low": 9.8,
                         "close": 10, "volume": vol, "turnover": 10 * vol})
        ind = compute_indicators(data)
        assert ind.volume_percentile <= 10.0
        assert ind.volume_percentile_days == 60

    def test_volume_percentile_high(self):
        """When recent volume is high, percentile should be high."""
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        data = []
        for i in range(120):
            date = (base - timedelta(days=119 - i)).strftime("%Y-%m-%d")
            vol = 1_000_000 if i < 115 else 5_000_000  # high volume in last 5
            data.append({"date": date, "open": 10, "high": 10.2, "low": 9.8,
                         "close": 10, "volume": vol, "turnover": 10 * vol})
        ind = compute_indicators(data)
        assert ind.volume_percentile >= 90.0

    def test_volume_percentile_less_than_60_days(self):
        """When data has fewer than 60 days, use actual window."""
        data = _make_flat_data(30, volume=1_000_000)
        ind = compute_indicators(data)
        assert ind.volume_percentile_days <= 30


# ── compute_volume_percentile (unit) ─────────────────────────────────────────

class TestComputeVolumePercentile:
    def test_min_volume_at_bottom(self):
        vols = [1000000] * 60
        recent = [500000]  # smallest
        pct = compute_volume_percentile(vols, recent)
        assert pct < 5.0

    def test_max_volume_at_top(self):
        vols = [1000000] * 60
        recent = [5000000]  # largest
        pct = compute_volume_percentile(vols, recent)
        assert pct >= 95.0

    def test_empty_lists(self):
        pct = compute_volume_percentile([], [])
        assert pct == 50.0

    def test_empty_window(self):
        pct = compute_volume_percentile([], [1_000_000])
        assert pct == 50.0

    def test_empty_target(self):
        pct = compute_volume_percentile([1_000_000] * 5, [])
        assert pct == 50.0
