# tests/test_strategy2_models.py
"""策略2数据模型测试。"""
import pytest
from strategy2.models import (
    Strategy2Indicators,
    Strategy2Score,
    Strategy2Risk,
    Strategy2Evaluation,
    IndicatorValidation,
)


class TestIndicatorValidation:
    def test_valid(self):
        result = IndicatorValidation(valid=True, data_days=120, window_days=120)
        assert result.valid is True
        assert result.data_days == 120
        assert result.window_days == 120
        assert result.reason == ""

    def test_invalid_with_reason(self):
        result = IndicatorValidation(
            valid=False, data_days=30, window_days=120,
            reason="INSUFFICIENT_STRATEGY_DATA",
        )
        assert result.valid is False
        assert result.reason == "INSUFFICIENT_STRATEGY_DATA"


class TestStrategy2Indicators:
    def test_construction(self):
        ind = Strategy2Indicators(
            v3=1000000, v5=1200000, v10=1500000, v20=2000000,
            volume_ratio_5_20=0.60,
            volume_percentile=18.5,
            volume_percentile_days=60,
            range_5=0.03,
            close_range_5=0.025,
            return_3=-0.01,
            return_5=-0.02,
            daily_return=0.005,
        )
        assert ind.v3 == 1000000
        assert ind.v5 == 1200000
        assert ind.v10 == 1500000
        assert ind.v20 == 2000000
        assert ind.volume_ratio_5_20 == 0.60
        assert ind.volume_percentile == 18.5
        assert ind.volume_percentile_days == 60
        assert ind.range_5 == 0.03
        assert ind.close_range_5 == 0.025
        assert ind.return_3 == -0.01
        assert ind.return_5 == -0.02
        assert ind.daily_return == 0.005

    def test_defaults(self):
        ind = Strategy2Indicators()
        assert ind.v3 == 0.0
        assert ind.v5 == 0.0
        assert ind.v10 == 0.0
        assert ind.v20 == 0.0


class TestStrategy2Score:
    def test_defaults(self):
        s = Strategy2Score()
        assert s.volume_dry_score == 0
        assert s.price_stable_score == 0
        assert s.total_score == 0
        assert s.level == ""
        assert s.score_reasons == []

    def test_construction_with_reasons(self):
        s = Strategy2Score(
            volume_dry_score=30,
            price_stable_score=40,
            total_score=70,
            level="普通观察",
            score_reasons=["V5/V20 <= 0.60: +10"],
        )
        assert s.total_score == 70
        assert s.level == "普通观察"
        assert s.total_score == s.volume_dry_score + s.price_stable_score
        assert "V5/V20 <= 0.60: +10" in s.score_reasons


class TestStrategy2Risk:
    def test_construction(self):
        r = Strategy2Risk(
            key_support=10.50,
            buy_zone_low=10.50,
            buy_zone_high=10.82,
            stop_loss=10.19,
            risk_ratio=0.03,
            risk_level="低风险",
        )
        assert r.key_support == 10.50
        assert r.buy_zone_low == 10.50
        assert r.buy_zone_high == pytest.approx(10.82, abs=0.01)
        assert r.stop_loss == pytest.approx(10.19, abs=0.01)
        assert r.risk_ratio == 0.03
        assert r.risk_level == "低风险"

    def test_defaults(self):
        r = Strategy2Risk()
        assert r.key_support == 0.0
        assert r.risk_ratio == 0.0
        assert r.risk_level == ""


class TestStrategy2Evaluation:
    def test_passed_evaluation(self):
        ind = Strategy2Indicators(
            v3=500000, v5=600000, v10=700000, v20=800000,
            volume_ratio_5_20=0.55, volume_percentile=15.0,
            volume_percentile_days=60, range_5=0.04,
            close_range_5=0.03, return_3=0.01, return_5=0.02,
            daily_return=0.005,
        )
        risk = Strategy2Risk(
            key_support=10.0, buy_zone_low=10.0, buy_zone_high=10.30,
            stop_loss=9.70, risk_ratio=0.03, risk_level="低风险",
        )
        ev = Strategy2Evaluation(
            passed=True,
            code="000001",
            name="平安银行",
            evaluation_date="2026-06-10",
            indicators=ind,
            volume_dry_score=40,
            price_stable_score=40,
            total_score=80,
            level="重点观察",
            score_reasons=["V5/V20 <= 0.60: +10"],
            reject_reasons=[],
            risk=risk,
            status_reason=None,
        )
        assert ev.passed is True
        assert ev.code == "000001"
        assert ev.total_score == 80
        assert ev.level == "重点观察"
        assert ev.indicators.v5 == 600000
        assert ev.risk.risk_level == "低风险"

    def test_rejected_evaluation(self):
        ind = Strategy2Indicators(
            v3=500000, v5=600000, v10=700000, v20=800000,
            volume_ratio_5_20=0.75, volume_percentile=40.0,
            volume_percentile_days=60, range_5=0.10,
            close_range_5=0.08, return_3=0.01, return_5=-0.06,
            daily_return=0.005,
        )
        risk = Strategy2Risk(
            key_support=10.0, buy_zone_low=10.0, buy_zone_high=10.30,
            stop_loss=9.70, risk_ratio=0.06, risk_level="高风险",
        )
        ev = Strategy2Evaluation(
            passed=False,
            code="000002",
            name="万科A",
            evaluation_date="2026-06-10",
            indicators=ind,
            volume_dry_score=10,
            price_stable_score=10,
            total_score=20,
            level="",
            score_reasons=[],
            reject_reasons=["REJECT_VOLUME_DRY_PRICE_DROP", "REJECT_RANGE_TOO_WIDE"],
            risk=risk,
            status_reason="REJECT_RANGE_TOO_WIDE",
        )
        assert ev.passed is False
        assert len(ev.reject_reasons) == 2
        assert "REJECT_RANGE_TOO_WIDE" in ev.reject_reasons
        assert ev.status_reason == "REJECT_RANGE_TOO_WIDE"

    def test_default_indicators_and_risk(self):
        """__post_init__ should create default indicators and risk when None."""
        ev = Strategy2Evaluation(passed=False, status_reason="TEST")
        assert ev.indicators is not None
        assert ev.indicators.v3 == 0.0
        assert ev.risk is not None
        assert ev.risk.risk_ratio == 0.0
