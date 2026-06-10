# tests/test_strategy2_bug_fixes.py
"""回归测试 — 覆盖 BUG-S2-001 至 BUG-S2-011 的所有修复验证。"""
import pytest
import json

from strategy2.validation import (
    resolve_strategy2_config,
    validate_ohlc_data,
    recent_daily_changes,
)
from strategy2.models import Strategy2Evaluation
from strategy2.engine import ExtremeDryStableStrategyEngine
from strategy2.indicators import compute_indicators


# ── helpers ──────────────────────────────────────────────────────────────────

def _flat_data(days: int, close: float = 10.0, volume: float = 1_000_000) -> list[dict]:
    from datetime import datetime, timedelta
    base = datetime(2026, 6, 10)
    return [
        {"date": (base - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d"),
         "open": close, "high": close, "low": close,
         "close": close, "volume": volume, "turnover": close * volume}
        for i in range(days)
    ]


def _s2_cfg(**overrides) -> dict:
    cfg = {
        "strategy_window_days": 120, "minimum_required_days": 60,
        "candidate_min_score": 70, "max_risk_ratio": 0.05,
        "support_lookback_days": 10, "buy_zone_max_premium": 0.03,
        "stop_loss_buffer": 0.03,
    }
    cfg.update(overrides)
    return cfg


# ═══════════════════════════════════════════════════════════════════════════════
# BUG-S2-005: 行情校验不完整
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateOHLCData:
    def test_valid_data_passes(self):
        data = _flat_data(120)
        assert validate_ohlc_data(data) is None

    def test_missing_high_field(self):
        data = _flat_data(120)
        del data[0]["high"]
        assert validate_ohlc_data(data) == "INVALID_MARKET_DATA"

    def test_missing_open_field(self):
        data = _flat_data(120)
        del data[-1]["open"]
        assert validate_ohlc_data(data) == "INVALID_MARKET_DATA"

    def test_string_close(self):
        data = _flat_data(120)
        data[0]["close"] = "10.5"
        assert validate_ohlc_data(data) == "INVALID_MARKET_DATA"

    def test_nan_value(self):
        import math
        data = _flat_data(120)
        data[50]["close"] = float('nan')
        assert validate_ohlc_data(data) == "INVALID_MARKET_DATA"

    def test_inf_value(self):
        data = _flat_data(120)
        data[50]["volume"] = float('inf')
        assert validate_ohlc_data(data) == "INVALID_MARKET_DATA"

    def test_negative_volume(self):
        data = _flat_data(120)
        data[50]["volume"] = -100
        assert validate_ohlc_data(data) == "INVALID_MARKET_DATA"

    def test_high_less_than_low(self):
        data = _flat_data(120)
        data[10]["high"] = 5.0
        data[10]["low"] = 10.0
        data[10]["open"] = 8.0
        data[10]["close"] = 8.0
        assert validate_ohlc_data(data) == "INVALID_MARKET_DATA"

    def test_high_less_than_close(self):
        data = _flat_data(120)
        data[10]["high"] = 5.0
        data[10]["close"] = 10.0
        data[10]["low"] = 4.0
        data[10]["open"] = 7.0
        assert validate_ohlc_data(data) == "INVALID_MARKET_DATA"

    def test_reverse_order_dates(self):
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        data = [
            {"date": (base - timedelta(days=119 - i)).strftime("%Y-%m-%d"),
             "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1_000_000}
            for i in range(120)
        ]
        # Swap first two dates to create reverse order
        data[0], data[1] = data[1], data[0]
        assert validate_ohlc_data(data) == "INVALID_MARKET_DATA"

    def test_duplicate_dates(self):
        data = _flat_data(120)
        data[5]["date"] = data[4]["date"]
        assert validate_ohlc_data(data) == "INVALID_MARKET_DATA"

    def test_bool_value_rejected(self):
        data = _flat_data(120)
        data[50]["close"] = True
        assert validate_ohlc_data(data) == "INVALID_MARKET_DATA"

    def test_empty_list(self):
        assert validate_ohlc_data([]) == "INVALID_MARKET_DATA"

    def test_none_data(self):
        assert validate_ohlc_data(None) == "INVALID_MARKET_DATA"


# ═══════════════════════════════════════════════════════════════════════════════
# BUG-S2-003: 最近5日跌幅（共享函数）
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecentDailyChanges:
    def test_returns_5_changes_for_6_rows(self):
        data = _flat_data(6)
        changes = recent_daily_changes(data, days=5)
        assert len(changes) == 5  # 6 rows needed → 5 changes

    def test_insufficient_data(self):
        data = _flat_data(4)
        changes = recent_daily_changes(data, days=5)
        assert changes == []

    def test_first_day_detected(self):
        """BUG-S2-003: data[-5] relative to data[-6] must be detected."""
        data = _flat_data(120)
        # Make day -5 (index 115 in 120 rows) drop 5% from data[-6]
        data[115]["close"] = 9.5  # prev close was 10.0 → -5%
        data[115]["volume"] = 3_000_000
        changes = recent_daily_changes(data, days=5)
        # The first change should be data[-5] vs data[-6]
        assert changes[0]["row"]["date"] == data[115]["date"]
        assert changes[0]["change"] == pytest.approx(-0.05)

    def test_all_five_days_detected(self):
        """Each of the last 5 days should be present."""
        data = _flat_data(120)
        # Set a different close for each of the last 6 days
        for i, offset in enumerate([-5, -4, -3, -2, -1]):
            data[-(6 - i)]["close"] = 10.0 + i * 0.5  # day-6=10.0, day-5=10.5, etc.
        changes = recent_daily_changes(data, days=5)
        assert len(changes) == 5
        # Each change should be computable
        for ch in changes:
            assert isinstance(ch["change"], float)


# ═══════════════════════════════════════════════════════════════════════════════
# BUG-S2-002: strategy_window_days 未实际截取
# BUG-S2-004: V20=0 零成交量
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategyWindowTruncation:
    def test_window_truncation_excludes_bad_outside_data(self):
        """BUG-S2-002: Prefix data outside strategy window must not affect evaluation.

        The first 10 rows have high close=99 (different from recent 120), but they
        are outside strategy_window_days. OHLC validation passes since close>0.
        If truncation works, engine only sees the last 120 rows (close=10).
        """
        engine = ExtremeDryStableStrategyEngine(_s2_cfg(strategy_window_days=120, minimum_required_days=60))
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        data = []
        for i in range(130):
            date = (base - timedelta(days=129 - i)).strftime("%Y-%m-%d")
            c = 99.0 if i < 10 else 10.0
            data.append({"date": date, "open": c, "high": c, "low": c, "close": c, "volume": 1_000_000, "turnover": c * 1_000_000})
        ev = engine.evaluate_at(data, code="000001", name="test")
        # Window truncation means only last 120 rows used — close=10.0, not 99.0
        assert ev.indicators.return_5 == pytest.approx(0.0)  # flat 10.0 data
        assert ev.status_reason != "INVALID_MARKET_DATA"

    def test_same_recent_window_same_result(self):
        """BUG-S2-002: Same recent 120 rows, different prefix → same result."""
        engine = ExtremeDryStableStrategyEngine(_s2_cfg(strategy_window_days=120, minimum_required_days=60))
        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        # Build base 120 rows of valid data
        recent = [
            {"date": (base - timedelta(days=119 - i)).strftime("%Y-%m-%d"),
             "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0, "volume": 1_000_000, "turnover": 10_000_000}
            for i in range(120)
        ]
        # Set different prefixes
        from datetime import timedelta
        prefix_a = [{"date": (base - timedelta(days=139 - i)).strftime("%Y-%m-%d"),
                     "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 100, "turnover": 100}
                    for i in range(20)]
        prefix_b = [{"date": (base - timedelta(days=139 - i)).strftime("%Y-%m-%d"),
                     "open": 99.0, "high": 99.0, "low": 99.0, "close": 99.0, "volume": 99_000_000, "turnover": 99_000_000}
                    for i in range(20)]
        ev_a = engine.evaluate_at(prefix_a + recent, code="000001", name="test")
        ev_b = engine.evaluate_at(prefix_b + recent, code="000001", name="test")
        assert ev_a.total_score == ev_b.total_score
        assert ev_a.passed == ev_b.passed
        assert ev_a.status_reason == ev_b.status_reason

    def test_data_shorter_than_window_uses_all(self):
        """BUG-S2-002: Input 80 days, window 120, min 60 → uses all 80 days, not rejected."""
        engine = ExtremeDryStableStrategyEngine(_s2_cfg(strategy_window_days=120, minimum_required_days=60))
        data = _flat_data(80)
        ev = engine.evaluate_at(data, code="000001", name="test")
        assert ev.status_reason != "INSUFFICIENT_STRATEGY_DATA"
        # Support lookback (10) must work with available data
        assert ev.risk.key_support is not None

    def test_zero_volume_rejected(self):
        """BUG-S2-004: All-zero volume data must not become a candidate."""
        engine = ExtremeDryStableStrategyEngine(_s2_cfg())
        data = _flat_data(120, volume=0)
        ev = engine.evaluate_at(data, code="000001", name="test")
        assert ev.passed is False
        assert ev.status_reason == "INVALID_MARKET_DATA"

    def test_v20_zero_rejected(self):
        """BUG-S2-004: V20=0 must return INVALID_MARKET_DATA."""
        engine = ExtremeDryStableStrategyEngine(_s2_cfg())
        data = _flat_data(120, volume=0)
        ind = compute_indicators(data)
        assert ind.v20 == 0.0
        ev = engine.evaluate_at(data, code="000001", name="test")
        assert ev.passed is False
        assert ev.status_reason == "INVALID_MARKET_DATA"


# ═══════════════════════════════════════════════════════════════════════════════
# BUG-S2-006: 后端策略2配置校验
# ═══════════════════════════════════════════════════════════════════════════════

class TestResolveStrategy2Config:
    def test_valid_config_returns_normalized(self):
        cfg = resolve_strategy2_config({
            "strategy2": {"strategy_window_days": 120, "minimum_required_days": 60},
            "liquidity": {"min_listing_days": 350},
        })
        assert cfg["strategy_window_days"] == 120
        assert cfg["minimum_required_days"] == 60

    def test_window_greater_than_min_listing_rejected(self):
        with pytest.raises(ValueError, match="min_listing_days"):
            resolve_strategy2_config({
                "strategy2": {"strategy_window_days": 500, "minimum_required_days": 60},
                "liquidity": {"min_listing_days": 350},
            })

    def test_window_less_than_min_required_rejected(self):
        with pytest.raises(ValueError, match="must be >="):
            resolve_strategy2_config({
                "strategy2": {"strategy_window_days": 50, "minimum_required_days": 60},
                "liquidity": {"min_listing_days": 350},
            })

    def test_string_window_rejected(self):
        with pytest.raises(ValueError, match="must be an integer"):
            resolve_strategy2_config({
                "strategy2": {"strategy_window_days": "120"},
                "liquidity": {"min_listing_days": 350},
            })

    def test_bool_value_rejected(self):
        with pytest.raises(ValueError, match="must be an integer"):
            resolve_strategy2_config({
                "strategy2": {"strategy_window_days": True, "minimum_required_days": 60},
                "liquidity": {"min_listing_days": 350},
            })

    def test_float_days_rejected(self):
        with pytest.raises(ValueError, match="must be an integer"):
            resolve_strategy2_config({
                "strategy2": {"strategy_window_days": 120.5, "minimum_required_days": 60},
                "liquidity": {"min_listing_days": 350},
            })

    def test_support_lookback_not_less_than_window(self):
        with pytest.raises(ValueError, match="support_lookback_days"):
            resolve_strategy2_config({
                "strategy2": {"strategy_window_days": 120, "minimum_required_days": 60, "support_lookback_days": 120},
                "liquidity": {"min_listing_days": 350},
            })

    def test_missing_strategy2_section_uses_defaults(self):
        cfg = resolve_strategy2_config({"liquidity": {"min_listing_days": 350}})
        assert cfg["strategy_window_days"] == 120

    def test_min_required_below_60_rejected(self):
        with pytest.raises(ValueError, match="minimum_required_days"):
            resolve_strategy2_config({
                "strategy2": {"minimum_required_days": 30},
                "liquidity": {"min_listing_days": 350},
            })

    def test_max_risk_ratio_zero_rejected(self):
        with pytest.raises(ValueError, match="max_risk_ratio"):
            resolve_strategy2_config({
                "strategy2": {"max_risk_ratio": 0},
                "liquidity": {"min_listing_days": 350},
            })


# ═══════════════════════════════════════════════════════════════════════════════
# BUG-S2-003: 引擎使用 shared recent_daily_changes + 否决/评分正确
# ═══════════════════════════════════════════════════════════════════════════════

class TestEngineRecent5DayFix:
    @staticmethod
    def _make_drop_data(drop_idx: int, close: float, vol: float = 5_000_000):
        """Create data with a drop at a specific index, with valid OHLC."""
        data = _flat_data(120)
        drop_c = close
        data[drop_idx]["close"] = drop_c
        data[drop_idx]["low"] = drop_c  # low <= close must hold
        data[drop_idx]["volume"] = vol
        return data

    def test_big_drop_on_first_day_detected_in_rejection(self):
        """BUG-S2-003: Drop on data[-5] must be detected by rejection."""
        engine = ExtremeDryStableStrategyEngine(_s2_cfg())
        data = self._make_drop_data(115, 9.55)  # -4.5%
        ev = engine.evaluate_at(data, code="000001", name="test")
        assert "REJECT_HEAVY_VOLUME_DROP" in ev.reject_reasons

    def test_big_drop_on_last_day_detected(self):
        """Drop on data[-1] (most recent day) should be detected."""
        engine = ExtremeDryStableStrategyEngine(_s2_cfg())
        data = self._make_drop_data(119, 9.55)  # -4.5% on last day
        ev = engine.evaluate_at(data, code="000001", name="test")
        assert "REJECT_HEAVY_VOLUME_DROP" in ev.reject_reasons

    def test_no_big_drop_score_deducted_correctly(self):
        """A small -2% drop should NOT trigger big-drop rejection."""
        engine = ExtremeDryStableStrategyEngine(_s2_cfg())
        data = self._make_drop_data(115, 9.8)  # -2%
        ev = engine.evaluate_at(data, code="000001", name="test")
        assert "REJECT_HEAVY_VOLUME_DROP" not in ev.reject_reasons

    def test_exactly_minus_4_pct_heavy_volume_rejected(self):
        """Exactly -4% with vol > V20 → REJECT_HEAVY_VOLUME_DROP."""
        engine = ExtremeDryStableStrategyEngine(_s2_cfg())
        data = self._make_drop_data(117, 9.6)  # -4% day -3
        ev = engine.evaluate_at(data, code="000001", name="test")
        assert "REJECT_HEAVY_VOLUME_DROP" in ev.reject_reasons


# ═══════════════════════════════════════════════════════════════════════════════
# BUG-S2-001: 中断恢复按 strategy_type 分派
# ═══════════════════════════════════════════════════════════════════════════════

class TestInterruptedTaskDispatch:
    def test_get_interrupted_task_returns_strategy_type(self, monkeypatch, tmp_path):
        import scanner.db as db
        db_path = str(tmp_path / "test.db")
        db.init_db(db_path)
        # Create a strategy2 interrupted task
        db.create_scan_task("s2-interrupted", "2026-06-10 09:00:00", total_stocks=1,
                            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        db.save_task_stocks("s2-interrupted", [{"code": "000001", "name": "test", "market": ""}])
        # Mark it as failed without finished_at
        conn = db.get_conn()
        conn.execute("UPDATE scan_tasks SET status='failed', finished_at=NULL WHERE id='s2-interrupted'")
        conn.commit()

        interrupted = db.get_interrupted_task()
        assert interrupted is not None
        assert interrupted["id"] == "s2-interrupted"
        assert interrupted["strategy_type"] == "STRATEGY_2_EXTREME_DRY_STABLE"

    def test_get_interrupted_task_null_strategy_defaults_to_s1(self, monkeypatch, tmp_path):
        import scanner.db as db
        db_path = str(tmp_path / "test2.db")
        db.init_db(db_path)
        db.create_scan_task("old-task", "2026-06-10 09:00:00", total_stocks=1)
        db.save_task_stocks("old-task", [{"code": "000001", "name": "test", "market": ""}])
        conn = db.get_conn()
        conn.execute("UPDATE scan_tasks SET status='failed', finished_at=NULL WHERE id='old-task'")
        conn.commit()

        interrupted = db.get_interrupted_task()
        assert interrupted["strategy_type"] == "STRATEGY_1_CUP_HANDLE"  # NULL → default


# ═══════════════════════════════════════════════════════════════════════════════
# BUG-S2-007: 任务类型隔离
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaskIsolation:
    def test_get_candidates_default_filters_strategy_type(self, tmp_path):
        """策略1默认候选不应受策略2任务影响。"""
        import scanner.db as db
        db_path = str(tmp_path / "test3.db")
        db.init_db(db_path)
        # Create strategy1 task with candidate
        db.create_scan_task("s1-task", "2026-06-10 09:00:00", strategy_type="STRATEGY_1_CUP_HANDLE")
        conn = db.get_conn()
        conn.execute("UPDATE scan_tasks SET status='completed', finished_at='2026-06-10 10:00:00' WHERE id='s1-task'")
        db.upsert_candidate("s1-task", {"code": "000001", "name": "S1候选", "score": 85})
        conn.commit()
        # Create later strategy2 task
        db.create_scan_task("s2-task", "2026-06-10 11:00:00", strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        conn.execute("UPDATE scan_tasks SET status='completed', finished_at='2026-06-10 12:00:00' WHERE id='s2-task'")
        conn.commit()

        # get_candidates() without task_id should return strategy1 candidates only
        candidates = db.get_candidates()
        assert len(candidates) == 1
        assert candidates[0]["code"] == "000001"

    def test_get_running_task_id_returns_strategy_type(self, tmp_path):
        import scanner.db as db
        db_path = str(tmp_path / "test4.db")
        db.init_db(db_path)
        db.create_scan_task("s2-running", "2026-06-10 09:00:00", strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        task = db.get_running_task()
        assert task is not None
        assert task["strategy_type"] == "STRATEGY_2_EXTREME_DRY_STABLE"


# ═══════════════════════════════════════════════════════════════════════════════
# BUG-S2-008: 缓存新鲜度回退
# ═══════════════════════════════════════════════════════════════════════════════

class TestCacheFreshness:
    def test_fetch_result_from_cache_flag_exists(self):
        from scanner.daily_data_service import FetchResult
        fr = FetchResult(data=[], primary_source="sina", fallback_source="sina", from_cache=True)
        assert fr.from_cache is True

    def test_fetch_result_default_from_cache_false(self):
        from scanner.daily_data_service import FetchResult
        fr = FetchResult(data=[], primary_source="sina", fallback_source="sina")
        assert fr.from_cache is False


# ═══════════════════════════════════════════════════════════════════════════════
# BUG-S2-011: JSON 反序列化 + 排序
# ═══════════════════════════════════════════════════════════════════════════════

class TestJsonDeserialization:
    def test_get_strategy2_candidates_deserializes_arrays(self, tmp_path):
        import scanner.db as db
        db_path = str(tmp_path / "test5.db")
        db.init_db(db_path)
        db.create_scan_task("json-test", "2026-06-10 09:00:00",
                            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        conn = db.get_conn()
        conn.execute("UPDATE scan_tasks SET status='completed', finished_at='2026-06-10 10:00:00' WHERE id='json-test'")
        conn.commit()

        db.upsert_strategy2_candidate("json-test", {
            "code": "000001", "name": "test", "evaluation_date": "2026-06-10",
            "total_score": 80, "level": "重点观察",
            "volume_dry_score": 40, "price_stable_score": 40,
            "current_close": 10.0,
            "key_support": 9.5, "buy_zone_low": 9.5, "buy_zone_high": 9.79,
            "stop_loss": 9.22, "risk_ratio": 0.04, "risk_level": "风险可接受",
            "score_reasons": ["V5/V20 <= 0.60: +10", "range_5 <= 3%: +10"],
            "reject_reasons": [],
        })

        candidates = db.get_strategy2_candidates(task_id="json-test")
        assert len(candidates) == 1
        c = candidates[0]
        # JSON fields should be lists, not strings
        assert isinstance(c["score_reasons"], list), f"Expected list, got {type(c['score_reasons'])}: {c['score_reasons']!r}"
        assert isinstance(c["reject_reasons"], list), f"Expected list, got {type(c['reject_reasons'])}: {c['reject_reasons']!r}"
        assert len(c["score_reasons"]) == 2
