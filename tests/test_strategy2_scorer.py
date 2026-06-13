# tests/test_strategy2_scorer.py
"""策略2评分测试 — 量干50分、价稳50分、等级。"""
import pytest
from strategy2.models import Strategy2Indicators
from strategy2.scorer import score_volume_dry, score_price_stable, compute_total_score


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


class TestScoreVolumeDry:
    def test_max_score_50(self):
        ind = _ind(
            volume_ratio_5_20=0.40,
            v3=500_000, v5=600_000, v10=700_000, v20=800_000,
            volume_percentile=10.0,
            return_5=0.01,
        )
        score, reasons = score_volume_dry(ind)
        assert score == 50
        assert len(reasons) == 5

    def test_min_score_0(self):
        ind = _ind(
            volume_ratio_5_20=1.5,
            v3=1_500_000, v5=1_200_000, v10=1_000_000, v20=800_000,
            volume_percentile=80.0,
            return_5=-0.08,
        )
        score, reasons = score_volume_dry(ind)
        assert score == 0
        assert len(reasons) == 0

    def test_ratio_0_60_boundary(self):
        ind = _ind(volume_ratio_5_20=0.60)
        score, reasons = score_volume_dry(ind)
        assert score >= 10
        assert any("V5/V20 <= 0.60" in r for r in reasons)

    def test_ratio_0_50_boundary(self):
        ind = _ind(volume_ratio_5_20=0.50)
        score, reasons = score_volume_dry(ind)
        assert score >= 20
        assert sum(1 for r in reasons if "V5/V20" in r) == 2

    def test_ratio_0_49(self):
        ind = _ind(volume_ratio_5_20=0.49)
        score, reasons = score_volume_dry(ind)
        assert score >= 20

    def test_ratio_0_61(self):
        ind = _ind(volume_ratio_5_20=0.61, v3=2_000_000, v5=1_500_000, v10=1_200_000, v20=1_000_000,
                   volume_percentile=90.0, return_5=-0.08)
        score, reasons = score_volume_dry(ind)
        assert score == 0  # nothing triggers — ratio > 0.60, V3 > V5 (not increasing), pct > 20, return < -3%

    def test_v3_v5_v10_v20_decreasing(self):
        ind = _ind(
            volume_ratio_5_20=1.0, v3=500_000, v5=600_000, v10=700_000, v20=800_000,
            volume_percentile=90.0, return_5=-0.08,
        )
        score, reasons = score_volume_dry(ind)
        assert score == 10
        assert any("V3 < V5 < V10 < V20" in r for r in reasons)

    def test_v3_v5_v10_v20_not_strictly_increasing(self):
        ind = _ind(
            volume_ratio_5_20=1.0, v3=1_000_000, v5=900_000, v10=800_000, v20=700_000,
            volume_percentile=90.0, return_5=-0.08,
        )
        score, reasons = score_volume_dry(ind)
        assert score == 0  # V3 > V5 — not strictly increasing
        assert not any("V3 < V5 < V10 < V20" in r for r in reasons)

    def test_volume_percentile_below_20(self):
        ind = _ind(volume_ratio_5_20=1.0, volume_percentile=15.0,
                   v3=2_000_000, v5=1_500_000, v10=1_200_000, v20=1_000_000,
                   return_5=-0.08)
        score, reasons = score_volume_dry(ind)
        assert score == 10
        assert any("20%" in r for r in reasons)

    def test_volume_percentile_boundary(self):
        ind = _ind(volume_ratio_5_20=1.0, volume_percentile=20.0,
                   v3=2_000_000, v5=1_500_000, v10=1_200_000, v20=1_000_000,
                   return_5=-0.08)
        score, reasons = score_volume_dry(ind)
        assert score == 10  # <= 20.0 → +10

    def test_return_5_boundary(self):
        ind = _ind(volume_ratio_5_20=1.0, return_5=-0.03,
                   v3=2_000_000, v5=1_500_000, v10=1_200_000, v20=1_000_000,
                   volume_percentile=90.0)
        score, reasons = score_volume_dry(ind)
        assert score == 10
        assert any("return_5 >= -3%" in r for r in reasons)


class TestScorePriceStable:
    def test_max_score_50(self):
        ind = _ind(range_5=0.02, close_range_5=0.02)
        score, reasons = score_price_stable(ind, has_no_big_drop=True, close_above_support=True)
        assert score == 50
        assert len(reasons) == 5

    def test_min_score_0(self):
        ind = _ind(range_5=0.10, close_range_5=0.10)
        score, reasons = score_price_stable(ind, has_no_big_drop=False, close_above_support=False)
        assert score == 0
        assert len(reasons) == 0

    def test_range_5_at_5_percent(self):
        ind = _ind(range_5=0.05, close_range_5=0.10)
        score, reasons = score_price_stable(ind, has_no_big_drop=True, close_above_support=True)
        assert score == 30  # range_5<=5%: +10, no_big_drop: +10, support: +10
        assert any("range_5 <= 5%" in r for r in reasons)

    def test_range_5_at_3_percent(self):
        ind = _ind(range_5=0.03, close_range_5=0.10)
        score, reasons = score_price_stable(ind, has_no_big_drop=True, close_above_support=True)
        assert score == 40
        assert any("range_5 <= 5%" in r for r in reasons)
        assert any("range_5 <= 3%" in r for r in reasons)

    def test_close_range_5_boundary(self):
        ind = _ind(range_5=0.10, close_range_5=0.03)
        score, reasons = score_price_stable(ind, has_no_big_drop=True, close_above_support=True)
        assert score == 30
        assert any("close_range_5 <= 3%" in r for r in reasons)

    def test_no_big_drop_score(self):
        ind = _ind(range_5=0.10, close_range_5=0.10)
        score, reasons = score_price_stable(ind, has_no_big_drop=True, close_above_support=False)
        assert score == 10
        assert any("big_drop" in r.lower() or "跌幅" in r for r in reasons)

    def test_close_above_support_score(self):
        ind = _ind(range_5=0.10, close_range_5=0.10)
        score, reasons = score_price_stable(ind, has_no_big_drop=False, close_above_support=True)
        assert score == 10
        assert any("support" in r.lower() for r in reasons)


class TestComputeTotalScore:
    def test_level_70_normal(self):
        # Only V5/V20 ratio bonus + close_range bonus + no-big-drop + support → ~70
        ind = _ind(volume_ratio_5_20=0.55,  # +10
                   v3=2_000_000, v5=1_500_000, v10=1_200_000, v20=1_000_000,  # V3>V5, not increasing
                   volume_percentile=90.0,  # not low volume
                   return_5=-0.08,  # < -3% → no bonus
                   range_5=0.04,  # <= 5%: +10, but > 3% so no extra
                   close_range_5=0.04)  # > 3% → no bonus
        s = compute_total_score(ind, has_no_big_drop=True, close_above_support=True)
        # vol: ratio_0.55 → +10; price: range_5≤5% → +10, no_big_drop → +10, support → +10 = 30
        # total = 10 + 30 = 40... hmm too low
        # Let's adjust: add return_5 back
        # Actually with ratio=0.55 and others neutral: score = 10 + 30 = 40 < 70
        # This test is unrealistic. Let me make it match a real "70-79" scenario
        ind = _ind(volume_ratio_5_20=0.40,  # +20
                   v3=2_000_000, v5=1_500_000, v10=1_200_000, v20=1_000_000,  # not V3<V5<V10<V20
                   volume_percentile=12.0,  # +10
                   return_5=-0.02,  # +10
                   range_5=0.04,  # +10 (≤5%)
                   close_range_5=0.04)  # > 3%
        s = compute_total_score(ind, has_no_big_drop=True, close_above_support=True)
        # vol: 20+10+10 = 40; price: 10+10+10 = 30; total = 70
        assert s.total_score == 70
        assert s.level == "普通观察"

    def test_empty_level_below_70(self):
        ind = _ind(volume_ratio_5_20=1.5, range_5=0.10, close_range_5=0.10)
        s = compute_total_score(ind, has_no_big_drop=False, close_above_support=False)
        assert s.total_score < 70
        assert s.level == ""

    def test_level_80_key_observation(self):
        ind = _ind(volume_ratio_5_20=0.40, v3=500_000, v5=600_000, v10=700_000, v20=800_000,
                   volume_percentile=15.0, range_5=0.03, close_range_5=0.02, return_5=0.01)
        s = compute_total_score(ind, has_no_big_drop=True, close_above_support=True)
        assert s.total_score >= 80
        assert s.level in ("重点观察", "极致量干价稳", "终极状态")

    def test_total_is_sum(self):
        ind = _ind()
        s = compute_total_score(ind, has_no_big_drop=True, close_above_support=True)
        assert s.total_score == s.volume_dry_score + s.price_stable_score

    def test_score_reasons_include_all(self):
        ind = _ind(volume_ratio_5_20=0.40, volume_percentile=10.0,
                   v3=500_000, v5=600_000, v10=700_000, v20=800_000,
                   range_5=0.02, close_range_5=0.02, return_5=0.01)
        s = compute_total_score(ind, has_no_big_drop=True, close_above_support=True)
        assert len(s.score_reasons) == 10  # 5 vol + 5 price
