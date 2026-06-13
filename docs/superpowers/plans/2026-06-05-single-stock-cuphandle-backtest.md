# Single Stock Cup-Handle Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-stock cup-handle backtest feature that reuses the live scan cup-handle strategy, returns auto-detected handle regions, diagnoses a user-specified handle region with rule-level explanations, saves JSON output, and displays results on a Vue page with K-line markers.

**Architecture:** Add a shared `CupHandleStrategyEngine` that wraps existing detector/scorer/analyzer modules instead of duplicating strategy decisions. Add a focused single-stock backtest module that handles data coverage, fresh-first fetch, sliding-window evaluation, specified-handle diagnosis, dedupe, and JSON output. Expose it through `POST /api/stock/{code}/backtest/cup-handle`, then add a Vue workbench page that consumes the API and renders form, summary, diagnostics, result list, score breakdown, and chart markers.

**Tech Stack:** Python 3.10+, FastAPI, SQLite via `scanner/db.py`, existing Sina/Tencent data sources, pytest, Vue 3 `<script setup>`, Vite, `lightweight-charts`.

---

## File Structure

### Backend files

- Create: `scanner/strategy_engine.py`
  - Defines `RuleDiagnostic`, `StrategyEvaluation`, `HandleDiagnosis`, `CupHandleStrategyEngine`, `build_pattern_config()`, `compute_config_hash()`, and serialization helpers.
  - Owns strategy orchestration and rule diagnostics.

- Create: `scanner/single_stock_backtest.py`
  - Defines `run_single_stock_cuphandle_backtest()`.
  - Owns input validation, data coverage checks, conditional fresh-first fetch, sliding-window evaluation, dedupe, specified-handle diagnosis, and JSON writing.

- Modify: `scanner/engine.py`
  - Replace duplicated cup-handle config construction and found-cup scoring/analyzer orchestration with `CupHandleStrategyEngine.evaluate_at()` for the cup-handle path.
  - Keep existing VCP-only fallback behavior in `engine.py`.
  - Keep `_fetch_with_retry()` available for single-stock backtest reuse.

- Modify: `server.py`
  - Add `POST /api/stock/{code}/backtest/cup-handle`.
  - Keep existing dict-response style and simple `JSONResponse` errors.

### Frontend files

- Modify: `web/src/composables/useApi.js`
  - Add `runCupHandleBacktest(code, payload)`.

- Modify: `web/src/router/index.js`
  - Add `/backtest/cup-handle` and `/backtest/cup-handle/:code` routes.

- Modify: `web/src/components/TopNav.vue`
  - Add “单股回测” route link.

- Modify: `web/src/pages/StockDetail.vue`
  - Add “用该股票回测” action that navigates to `/backtest/cup-handle/{code}`.

- Create: `web/src/pages/SingleStockBacktest.vue`
  - Implements the analysis workbench layout.

### Test files

- Create: `tests/test_cuphandle_strategy_engine.py`
- Create: `tests/test_single_stock_backtest.py`
- Create: `tests/test_single_stock_backtest_api.py`

---

## Shared Test Helpers

Use local helpers inside test files rather than adding a global test utility module in this first pass. Keep synthetic OHLC data deterministic.

Representative helper to copy into tests that need a clean cup-handle fixture:

```python
def make_ohlc_from_closes(closes, start_month=1):
    rows = []
    for i, close in enumerate(closes):
        rows.append({
            "date": f"2025-{(start_month + i // 20):02d}-{(i % 20) + 1:02d}",
            "open": round(close * 0.99, 2),
            "high": round(close * 1.02, 2),
            "low": round(close * 0.98, 2),
            "close": round(close, 2),
            "volume": 10_000_000 + i * 10_000,
            "turnover": round(close * (10_000_000 + i * 10_000), 2),
        })
    return rows


def build_cup_handle_closes(
    pre_days=40,
    down_days=35,
    bottom_days=20,
    up_days=35,
    handle_days=12,
    post_days=8,
    left_high=65.0,
    cup_low=52.0,
    right_high=62.0,
    handle_low=58.0,
    breakout=64.0,
):
    import math
    closes = []
    for i in range(pre_days):
        t = i / max(pre_days - 1, 1)
        closes.append(50 + (left_high - 50) * t)
    for i in range(down_days):
        t = i / max(down_days - 1, 1)
        closes.append(left_high - (left_high - cup_low) * math.sin(t * math.pi / 2))
    for i in range(bottom_days):
        closes.append(cup_low + 0.7 + ((i % 3) - 1) * 0.2)
    for i in range(up_days):
        t = i / max(up_days - 1, 1)
        closes.append(cup_low + (right_high - cup_low) * math.sin(t * math.pi / 2))
    for i in range(handle_days):
        t = i / max(handle_days - 1, 1)
        closes.append(right_high - (right_high - handle_low) * t)
    for i in range(post_days):
        closes.append(breakout + i * 0.2)
    return closes


def base_config():
    return {
        "cup": {
            "min_duration": 35,
            "max_duration": 180,
            "min_depth": 0.12,
            "max_depth": 0.45,
            "max_lip_deviation": 0.12,
            "min_bottom_roundness": 0.10,
        },
        "handle": {
            "min_duration": 5,
            "max_duration": 30,
            "max_depth": 0.18,
            "max_vs_right_rally": 0.50,
        },
        "breakout": {
            "buffer_pct": 0.02,
            "volume_multiplier": 1.5,
        },
        "scoring": {
            "strong_threshold": 80,
            "medium_threshold": 70,
        },
        "data": {
            "database_path": "unused-in-unit-tests.db",
        },
    }
```

---

### Task 1: Add Strategy Engine Core

**Files:**
- Create: `scanner/strategy_engine.py`
- Test: `tests/test_cuphandle_strategy_engine.py`

- [ ] **Step 1: Write failing tests for config hashing and pattern config construction**

Create `tests/test_cuphandle_strategy_engine.py` with:

```python
from scanner.strategy_engine import build_pattern_config, compute_config_hash, CupHandleStrategyEngine


def base_config():
    return {
        "cup": {"min_duration": 35, "max_duration": 180},
        "handle": {"min_duration": 5, "max_duration": 30, "max_depth": 0.18},
        "breakout": {"buffer_pct": 0.02, "volume_multiplier": 1.5},
        "scoring": {"medium_threshold": 70},
    }


def test_build_pattern_config_prefixes_handle_keys():
    cfg = build_pattern_config(base_config())
    assert cfg["min_duration"] == 35
    assert cfg["max_duration"] == 180
    assert cfg["handle_min_duration"] == 5
    assert cfg["handle_max_duration"] == 30
    assert cfg["handle_max_depth"] == 0.18
    assert cfg["buffer_pct"] == 0.02
    assert cfg["volume_multiplier"] == 1.5


def test_config_hash_is_stable_for_key_order():
    config_a = {"b": 2, "a": {"x": 1, "y": 2}}
    config_b = {"a": {"y": 2, "x": 1}, "b": 2}
    assert compute_config_hash(config_a) == compute_config_hash(config_b)
    assert compute_config_hash(config_a).startswith("sha256:")
    assert len(compute_config_hash(config_a)) == len("sha256:") + 64


def test_engine_exposes_strategy_version_and_hash():
    engine = CupHandleStrategyEngine(base_config())
    assert engine.strategy_version == "cuphandle-v1"
    assert engine.config_hash.startswith("sha256:")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_cuphandle_strategy_engine.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scanner.strategy_engine'`.

- [ ] **Step 3: Implement minimal strategy engine scaffolding**

Create `scanner/strategy_engine.py`:

```python
# scanner/strategy_engine.py
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from analyzer.dry_stable import analyze_dry_stable
from scanner.pattern_detector import CupHandleResult, detect_cup_handle
from scanner.scorer import score_cup_handle_advanced


@dataclass
class RuleDiagnostic:
    ruleName: str
    requiredValue: str
    actualValue: str
    severity: str
    explanation: str

    def to_dict(self) -> dict:
        return {
            "ruleName": self.ruleName,
            "requiredValue": self.requiredValue,
            "actualValue": self.actualValue,
            "severity": self.severity,
            "explanation": self.explanation,
        }


@dataclass
class StrategyEvaluation:
    passed: bool
    result: CupHandleResult
    dry_stable: dict | None
    strategy_version: str
    config_hash: str
    passed_rules: list[RuleDiagnostic] = field(default_factory=list)
    failed_rules: list[RuleDiagnostic] = field(default_factory=list)

    def to_dict(self) -> dict:
        return serialize_evaluation(self)


@dataclass
class HandleDiagnosis:
    start_date: str
    end_date: str
    passed: bool
    matched_pattern_id: str | None
    passed_rules: list[RuleDiagnostic] = field(default_factory=list)
    failed_rules: list[RuleDiagnostic] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "startDate": self.start_date,
            "endDate": self.end_date,
            "passed": self.passed,
            "matchedPatternId": self.matched_pattern_id,
            "passedRules": [r.to_dict() for r in self.passed_rules],
            "failedRules": [r.to_dict() for r in self.failed_rules],
        }


def build_pattern_config(config: dict) -> dict:
    cup_cfg = config.get("cup", {})
    handle_cfg = config.get("handle", {})
    breakout_cfg = config.get("breakout", {})
    handle_prefixed = {f"handle_{key}": value for key, value in handle_cfg.items()}
    return {**cup_cfg, **handle_prefixed, **breakout_cfg}


def compute_config_hash(config: dict) -> str:
    canonical = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class CupHandleStrategyEngine:
    strategy_version = "cuphandle-v1"

    def __init__(self, config: dict):
        self.config = config
        self.pattern_cfg = build_pattern_config(config)
        self.scoring_cfg = config.get("scoring", {})
        self.config_hash = compute_config_hash(config)

    def evaluate_at(
        self,
        data_until_date: list[dict],
        *,
        code: str = "",
        name: str = "",
        market_data: list[dict] | None = None,
    ) -> StrategyEvaluation:
        result = detect_cup_handle(data_until_date, self.pattern_cfg)
        if not result.found:
            failed = diagnose_cup_handle(data_until_date, self.pattern_cfg).failed_rules
            return StrategyEvaluation(
                passed=False,
                result=CupHandleResult(found=False, code=code, name=name),
                dry_stable=None,
                strategy_version=self.strategy_version,
                config_hash=self.config_hash,
                failed_rules=failed,
            )

        result.code = code
        result.name = name
        result.score = score_cup_handle_advanced(result, data_until_date, self.scoring_cfg)
        dry_stable = analyze_dry_stable(result, data_until_date, market_data=market_data)
        passed_rules, failed_rules = self._candidate_rules(result, dry_stable)
        return StrategyEvaluation(
            passed=not failed_rules,
            result=result,
            dry_stable=dry_stable,
            strategy_version=self.strategy_version,
            config_hash=self.config_hash,
            passed_rules=passed_rules,
            failed_rules=failed_rules,
        )

    def diagnose_handle(
        self,
        data_until_handle_end: list[dict],
        handle_start_date: str,
        handle_end_date: str,
        *,
        code: str = "",
        name: str = "",
        market_data: list[dict] | None = None,
    ) -> HandleDiagnosis:
        evaluation = self.evaluate_at(
            data_until_handle_end,
            code=code,
            name=name,
            market_data=market_data,
        )
        passed_rules = list(evaluation.passed_rules)
        failed_rules = list(evaluation.failed_rules)
        matched_pattern_id = None

        if evaluation.result.found:
            actual_start = _handle_start_date(data_until_handle_end, evaluation.result)
            actual_end = data_until_handle_end[-1]["date"] if data_until_handle_end else ""
            if actual_start == handle_start_date and actual_end == handle_end_date:
                passed_rules.append(RuleDiagnostic(
                    "指定柄区间匹配",
                    "用户输入柄区间应与策略识别柄区间一致",
                    f"{actual_start} ~ {actual_end}",
                    "info",
                    "你标注的柄区间与当前杯柄策略识别出的柄部区间一致。",
                ))
                matched_pattern_id = _pattern_id(code, actual_start, actual_end, evaluation.result.handle_low_date)
            else:
                failed_rules.append(RuleDiagnostic(
                    "指定柄区间匹配",
                    "用户输入柄区间应与策略识别柄区间一致",
                    f"策略识别柄区间为 {actual_start} ~ {actual_end}",
                    "high",
                    "你标注的区间没有被当前策略识别为完整杯柄结构中的柄部，因此不能进入策略结果。",
                ))
        else:
            failed_rules.append(RuleDiagnostic(
                "完整杯柄结构",
                "必须识别到左杯口、杯底、右杯口和有效柄部",
                "未识别到完整杯柄结构",
                "high",
                "截至指定柄结束日，当前策略没有识别到完整杯柄结构。",
            ))

        return HandleDiagnosis(
            start_date=handle_start_date,
            end_date=handle_end_date,
            passed=evaluation.passed and not failed_rules,
            matched_pattern_id=matched_pattern_id,
            passed_rules=passed_rules,
            failed_rules=failed_rules,
        )

    def _candidate_rules(self, result: CupHandleResult, dry_stable: dict | None) -> tuple[list[RuleDiagnostic], list[RuleDiagnostic]]:
        passed: list[RuleDiagnostic] = []
        failed: list[RuleDiagnostic] = []
        threshold = self.scoring_cfg.get("medium_threshold", 70) - 10
        if result.score >= threshold:
            passed.append(RuleDiagnostic("形态评分门槛", f">= {threshold}", str(result.score), "info", "形态评分达到当前策略候选门槛。"))
        else:
            failed.append(RuleDiagnostic("形态评分门槛", f">= {threshold}", str(result.score), "medium", "形态评分低于当前策略候选门槛。"))

        verdict = dry_stable.get("decision", {}).get("verdict") if dry_stable else "无干稳分析"
        if verdict != "不建议买入":
            passed.append(RuleDiagnostic("最终策略结论", "不能为 不建议买入", verdict, "info", "干稳低吸决策未阻断该杯柄结果。"))
        else:
            failed.append(RuleDiagnostic("最终策略结论", "不能为 不建议买入", verdict, "high", "干稳低吸决策认为该结构暂不适合买入。"))
        return passed, failed


def diagnose_cup_handle(data: list[dict], pattern_cfg: dict, specified_handle: dict | None = None):
    passed_rules: list[RuleDiagnostic] = []
    failed_rules: list[RuleDiagnostic] = []
    min_len = 120
    actual_len = len(data)
    if actual_len >= min_len:
        passed_rules.append(RuleDiagnostic("数据长度", f">= {min_len} 根K线", f"{actual_len} 根K线", "info", "K线数量满足杯柄检测的最低要求。"))
    else:
        failed_rules.append(RuleDiagnostic("数据长度", f">= {min_len} 根K线", f"{actual_len} 根K线", "high", "K线数量不足，无法可靠识别杯柄结构。"))
    return type("RuleDiagnostics", (), {"passed_rules": passed_rules, "failed_rules": failed_rules})()


def serialize_evaluation(evaluation: StrategyEvaluation) -> dict:
    result = evaluation.result
    pattern = _serialize_pattern(result, []) if result.found else None
    return {
        "passed": evaluation.passed,
        "strategyVersion": evaluation.strategy_version,
        "configHash": evaluation.config_hash,
        "score": result.score,
        "pattern": pattern,
        "dryStable": evaluation.dry_stable,
        "passedRules": [r.to_dict() for r in evaluation.passed_rules],
        "failedRules": [r.to_dict() for r in evaluation.failed_rules],
    }


def _serialize_pattern(result: CupHandleResult, data: list[dict]) -> dict:
    return {
        "leftHighDate": result.left_high_date,
        "cupLowDate": result.cup_low_date,
        "rightHighDate": result.right_high_date,
        "handleStartDate": _handle_start_date(data, result) if data else "",
        "handleEndDate": data[-1]["date"] if data else "",
        "handleLowDate": result.handle_low_date,
        "cupDepthPct": result.cup_depth_pct,
        "cupDuration": result.cup_duration,
        "handleDepthPct": result.handle_depth_pct,
        "handleDuration": result.handle_duration,
        "lipDeviationPct": result.lip_deviation_pct,
        "isBreakout": result.is_breakout,
        "isVolumeBreakout": result.is_volume_breakout,
        "volMultiplier": result.vol_multiplier,
    }


def serialize_pattern_for_backtest(result: CupHandleResult, data: list[dict]) -> dict:
    return _serialize_pattern(result, data)


def _handle_start_date(data: list[dict], result: CupHandleResult) -> str:
    idx = result.right_high_idx + 1
    if 0 <= idx < len(data):
        return data[idx]["date"]
    return ""


def _pattern_id(code: str, handle_start: str, handle_end: str, handle_low: str) -> str:
    return f"{code}-{handle_start}-{handle_end}-{handle_low}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/test_cuphandle_strategy_engine.py -v
```

Expected: PASS for the three tests added in Step 1.

- [ ] **Step 5: Checkpoint**

Run:

```bash
git status --short
git diff -- scanner/strategy_engine.py tests/test_cuphandle_strategy_engine.py
```

Expected: only the new strategy engine and its test are relevant. If committing, first show status/diff and ask user confirmation per project Git Safety Rules.

---

### Task 2: Add Strategy Evaluation and Diagnosis Tests

**Files:**
- Modify: `tests/test_cuphandle_strategy_engine.py`
- Modify: `scanner/strategy_engine.py`

- [ ] **Step 1: Extend tests for valid cup-handle evaluation and VCP exclusion**

Append to `tests/test_cuphandle_strategy_engine.py`:

```python
def make_ohlc_from_closes(closes):
    rows = []
    for i, close in enumerate(closes):
        rows.append({
            "date": f"2025-{(i // 20) + 1:02d}-{(i % 20) + 1:02d}",
            "open": round(close * 0.99, 2),
            "high": round(close * 1.02, 2),
            "low": round(close * 0.98, 2),
            "close": round(close, 2),
            "volume": 10_000_000 + i * 10_000,
            "turnover": round(close * (10_000_000 + i * 10_000), 2),
        })
    return rows


def build_cup_handle_closes():
    import math
    closes = []
    for i in range(40):
        closes.append(50 + (65 - 50) * (i / 39))
    for i in range(35):
        closes.append(65 - (65 - 52) * math.sin((i / 34) * math.pi / 2))
    for i in range(20):
        closes.append(52.7 + ((i % 3) - 1) * 0.2)
    for i in range(35):
        closes.append(52 + (62 - 52) * math.sin((i / 34) * math.pi / 2))
    for i in range(12):
        closes.append(62 - (62 - 58) * (i / 11))
    for i in range(8):
        closes.append(64 + i * 0.2)
    return closes


def full_config():
    cfg = base_config()
    cfg["cup"].update({
        "min_depth": 0.12,
        "max_depth": 0.45,
        "max_lip_deviation": 0.12,
        "min_bottom_roundness": 0.10,
    })
    cfg["handle"].update({
        "max_vs_right_rally": 0.50,
    })
    return cfg


def test_evaluate_at_returns_passed_for_valid_cup_handle():
    data = make_ohlc_from_closes(build_cup_handle_closes())
    engine = CupHandleStrategyEngine(full_config())

    evaluation = engine.evaluate_at(data, code="600000", name="浦发银行")

    assert evaluation.result.found is True
    assert evaluation.result.code == "600000"
    assert evaluation.result.name == "浦发银行"
    assert evaluation.result.score > 0
    assert evaluation.dry_stable is not None
    assert all(rule.ruleName != "VCP" for rule in evaluation.passed_rules + evaluation.failed_rules)


def test_evaluate_at_does_not_promote_vcp_only_result():
    flat_data = make_ohlc_from_closes([10 + (i % 5) * 0.1 for i in range(180)])
    engine = CupHandleStrategyEngine(full_config())

    evaluation = engine.evaluate_at(flat_data, code="600001")

    assert evaluation.passed is False
    assert evaluation.result.found is False
    assert evaluation.dry_stable is None
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
python -m pytest tests/test_cuphandle_strategy_engine.py::test_evaluate_at_returns_passed_for_valid_cup_handle tests/test_cuphandle_strategy_engine.py::test_evaluate_at_does_not_promote_vcp_only_result -v
```

Expected before implementation refinement: the first test may fail if candidate gating is too strict or serialization does not include expected values.

- [ ] **Step 3: Refine `evaluate_at()` candidate gating**

In `scanner/strategy_engine.py`, ensure `evaluate_at()` uses the same candidate threshold as live scan for cup-handle results:

```python
threshold = self.scoring_cfg.get("medium_threshold", 70) - 10
passed = result.score >= threshold and dry_stable["decision"]["verdict"] != "不建议买入"
```

Set `StrategyEvaluation.passed` from that boolean while keeping `failed_rules` as the explanation source.

- [ ] **Step 4: Add specified handle diagnosis tests**

Append:

```python
def test_diagnose_handle_returns_passed_and_failed_rule_arrays():
    data = make_ohlc_from_closes(build_cup_handle_closes())
    engine = CupHandleStrategyEngine(full_config())
    evaluation = engine.evaluate_at(data, code="600000")
    actual_start = data[evaluation.result.right_high_idx + 1]["date"]
    actual_end = data[-1]["date"]

    diagnosis = engine.diagnose_handle(data, actual_start, actual_end, code="600000")

    body = diagnosis.to_dict()
    assert "passedRules" in body
    assert "failedRules" in body
    assert any(rule["ruleName"] == "指定柄区间匹配" for rule in body["passedRules"])


def test_diagnose_handle_reports_mismatched_user_range():
    data = make_ohlc_from_closes(build_cup_handle_closes())
    engine = CupHandleStrategyEngine(full_config())

    diagnosis = engine.diagnose_handle(data, "2025-01-01", data[-1]["date"], code="600000")

    failed = diagnosis.to_dict()["failedRules"]
    assert any(rule["ruleName"] == "指定柄区间匹配" for rule in failed)
    match_rule = next(rule for rule in failed if rule["ruleName"] == "指定柄区间匹配")
    assert match_rule["severity"] == "high"
    assert match_rule["requiredValue"]
    assert match_rule["actualValue"]
    assert match_rule["explanation"]
```

- [ ] **Step 5: Run strategy engine tests**

Run:

```bash
python -m pytest tests/test_cuphandle_strategy_engine.py -v
```

Expected: PASS.

- [ ] **Step 6: Checkpoint**

Run:

```bash
git diff -- scanner/strategy_engine.py tests/test_cuphandle_strategy_engine.py
```

Expected: strategy evaluation and diagnosis are covered before backtest orchestration begins.

---

### Task 3: Add Single-Stock Backtest Data Coverage and Fetch Logic

**Files:**
- Create: `scanner/single_stock_backtest.py`
- Test: `tests/test_single_stock_backtest.py`

- [ ] **Step 1: Write failing tests for cache coverage and fresh fetch behavior**

Create `tests/test_single_stock_backtest.py`:

```python
from scanner import db
from scanner.single_stock_backtest import ensure_backtest_data, DataCoverageError


def rows_for_dates(code_dates):
    rows = []
    for i, date in enumerate(code_dates):
        close = 10 + i * 0.1
        rows.append({
            "date": date,
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": 1_000_000 + i,
            "turnover": close * (1_000_000 + i),
        })
    return rows


def test_ensure_backtest_data_uses_cache_when_coverage_is_complete(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    dates = [f"2025-01-{day:02d}" for day in range(1, 21)]
    db.save_ohlc("600000", rows_for_dates(dates))
    calls = []

    def fake_fetch(*args, **kwargs):
        calls.append(args)
        raise AssertionError("fresh fetch should not be called")

    data, coverage = ensure_backtest_data(
        "600000",
        required_start_date="2025-01-01",
        required_end_date="2025-01-20",
        fetch_fn=fake_fetch,
    )

    assert calls == []
    assert len(data) == 20
    assert coverage["source"] == "cache"
    assert coverage["availableRange"] == {"startDate": "2025-01-01", "endDate": "2025-01-20"}


def test_ensure_backtest_data_fetches_when_cache_is_short(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    db.save_ohlc("600000", rows_for_dates(["2025-01-10", "2025-01-11"]))

    def fake_fetch(code):
        assert code == "600000"
        return rows_for_dates([f"2025-01-{day:02d}" for day in range(1, 21)])

    data, coverage = ensure_backtest_data(
        "600000",
        required_start_date="2025-01-01",
        required_end_date="2025-01-20",
        fetch_fn=fake_fetch,
    )

    assert len(data) == 20
    assert coverage["source"] == "fresh_merged"
    assert db.get_ohlc("600000")[0]["date"] == "2025-01-01"


def test_ensure_backtest_data_raises_when_fresh_data_still_incomplete(tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))

    def fake_fetch(code):
        return rows_for_dates(["2025-01-10", "2025-01-11"])

    try:
        ensure_backtest_data(
            "600000",
            required_start_date="2025-01-01",
            required_end_date="2025-01-20",
            fetch_fn=fake_fetch,
        )
    except DataCoverageError as exc:
        payload = exc.to_dict()
    else:
        raise AssertionError("DataCoverageError was not raised")

    assert payload["error"] == "Insufficient data coverage"
    assert payload["requiredRange"] == {"startDate": "2025-01-01", "endDate": "2025-01-20"}
    assert payload["availableRange"] == {"startDate": "2025-01-10", "endDate": "2025-01-11"}
    assert payload["missingRanges"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_single_stock_backtest.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scanner.single_stock_backtest'`.

- [ ] **Step 3: Implement coverage helpers and fresh merge**

Create `scanner/single_stock_backtest.py`:

```python
# scanner/single_stock_backtest.py
from __future__ import annotations

import datetime as _dt
import json
import os
import time
from typing import Callable

import scanner.db as db
from scanner.engine import _merge_data
from scanner.sina_source import fetch_sina_daily
from scanner.tencent_source import fetch_tencent_daily
from scanner.strategy_engine import CupHandleStrategyEngine, serialize_pattern_for_backtest


class DataCoverageError(Exception):
    def __init__(self, code: str, required_start: str, required_end: str, available_range: dict | None):
        self.code = code
        self.required_start = required_start
        self.required_end = required_end
        self.available_range = available_range or {"startDate": None, "endDate": None}
        super().__init__("Insufficient data coverage")

    def to_dict(self) -> dict:
        return {
            "error": "Insufficient data coverage",
            "message": "K线数据无法完整覆盖策略所需区间，已停止回测。",
            "code": self.code,
            "requiredRange": {"startDate": self.required_start, "endDate": self.required_end},
            "availableRange": self.available_range,
            "missingRanges": _missing_ranges(self.required_start, self.required_end, self.available_range),
        }


def _range_for(data: list[dict] | None) -> dict | None:
    if not data:
        return None
    ordered = sorted(data, key=lambda row: row["date"])
    return {"startDate": ordered[0]["date"], "endDate": ordered[-1]["date"]}


def _covers(data: list[dict] | None, start_date: str, end_date: str) -> bool:
    rng = _range_for(data)
    if not rng:
        return False
    return rng["startDate"] <= start_date and rng["endDate"] >= end_date


def _missing_ranges(start_date: str, end_date: str, available_range: dict | None) -> list[dict]:
    if not available_range or not available_range.get("startDate"):
        return [{"startDate": start_date, "endDate": end_date}]
    missing = []
    if available_range["startDate"] > start_date:
        missing.append({"startDate": start_date, "endDate": _prev_date(available_range["startDate"])})
    if available_range["endDate"] < end_date:
        missing.append({"startDate": _next_date(available_range["endDate"]), "endDate": end_date})
    return missing


def _prev_date(date_str: str) -> str:
    d = _dt.date.fromisoformat(date_str)
    return (d - _dt.timedelta(days=1)).isoformat()


def _next_date(date_str: str) -> str:
    d = _dt.date.fromisoformat(date_str)
    return (d + _dt.timedelta(days=1)).isoformat()


def default_fresh_fetch(code: str) -> list[dict] | None:
    data = fetch_sina_daily(code)
    if data:
        return data
    return fetch_tencent_daily(code)


def ensure_backtest_data(
    code: str,
    *,
    required_start_date: str,
    required_end_date: str,
    fetch_fn: Callable[[str], list[dict] | None] = default_fresh_fetch,
) -> tuple[list[dict], dict]:
    cached = db.get_ohlc(code) or []
    if _covers(cached, required_start_date, required_end_date):
        return cached, {
            "requiredRange": {"startDate": required_start_date, "endDate": required_end_date},
            "availableRange": _range_for(cached),
            "source": "cache",
        }

    fresh = fetch_fn(code) or []
    merged = _merge_data(cached, fresh)
    if merged:
        db.save_ohlc(code, merged)

    if not _covers(merged, required_start_date, required_end_date):
        raise DataCoverageError(code, required_start_date, required_end_date, _range_for(merged))

    return merged, {
        "requiredRange": {"startDate": required_start_date, "endDate": required_end_date},
        "availableRange": _range_for(merged),
        "source": "fresh_merged",
    }
```

- [ ] **Step 4: Run coverage tests**

Run:

```bash
python -m pytest tests/test_single_stock_backtest.py -v
```

Expected: PASS for the three coverage tests.

- [ ] **Step 5: Checkpoint**

Run:

```bash
git diff -- scanner/single_stock_backtest.py tests/test_single_stock_backtest.py
```

Expected: data coverage/fetch behavior is implemented without endpoint or frontend changes.

---

### Task 4: Add Sliding-Window Backtest and JSON Output

**Files:**
- Modify: `scanner/single_stock_backtest.py`
- Modify: `tests/test_single_stock_backtest.py`

- [ ] **Step 1: Add tests for sliding-window no-future-data and JSON output**

Append to `tests/test_single_stock_backtest.py`:

```python
def test_run_backtest_uses_only_data_up_to_detection_day(monkeypatch, tmp_path):
    from scanner.single_stock_backtest import run_single_stock_cuphandle_backtest

    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    config = {
        "data": {"database_path": str(db_path)},
        "cup": {"max_duration": 60},
        "handle": {"max_duration": 20},
        "breakout": {},
        "scoring": {"medium_threshold": 70},
        "output": {"output_dir": str(tmp_path / "output_data")},
    }
    dates = [f"2025-01-{day:02d}" for day in range(1, 21)]
    data = rows_for_dates(dates)
    db.save_ohlc("600000", data)
    seen_lengths = []

    class FakeEvaluation:
        def __init__(self, date):
            self.passed = date in {"2025-01-10", "2025-01-11"}
            self.result = type("R", (), {
                "found": self.passed,
                "score": 80,
                "handle_low_date": "2025-01-09",
                "right_high_idx": 7,
                "handle_low_idx": 8,
                "left_high_date": "2025-01-03",
                "cup_low_date": "2025-01-05",
                "right_high_date": "2025-01-08",
                "cup_depth_pct": 20,
                "cup_duration": 5,
                "handle_depth_pct": 7,
                "handle_duration": 2,
                "lip_deviation_pct": 2,
                "is_breakout": False,
                "is_volume_breakout": False,
                "vol_multiplier": 1.0,
            })()
            self.dry_stable = {
                "key_prices": {"entry_zone_low": 10, "entry_zone_high": 11, "pivot": 12, "stop_loss": 9, "target_1": 14, "target_2": 16},
                "risk_reward": {"rr1": 2.0},
                "volume_dry": {"score": 8, "level": "良好"},
                "price_stable": {"score": 7, "level": "良好"},
                "pattern_score": {"score": 16, "type": "cup_handle", "key_pattern_type": "cup_handle"},
                "decision": {"verdict": "可低吸", "summary": "测试通过"},
            }
            self.passed_rules = []
            self.failed_rules = []

    class FakeEngine:
        strategy_version = "cuphandle-v1"
        config_hash = "sha256:" + "1" * 64
        def __init__(self, config):
            pass
        def evaluate_at(self, window, **kwargs):
            seen_lengths.append(len(window))
            return FakeEvaluation(window[-1]["date"])
        def diagnose_handle(self, *args, **kwargs):
            return None

    monkeypatch.setattr("scanner.single_stock_backtest.CupHandleStrategyEngine", FakeEngine)

    result = run_single_stock_cuphandle_backtest(
        "600000",
        "2025-01-01",
        "2025-01-20",
        config,
        context_days=0,
    )

    assert result["summary"]["totalPatterns"] == 1
    assert result["patterns"][0]["firstDetectedDate"] == "2025-01-10"
    assert result["patterns"][0]["detectedDate"] == "2025-01-10" or result["patterns"][0]["detectedDate"] == "2025-01-11"
    assert max(seen_lengths) <= 20
    assert result["outputFile"].endswith(".json")


def test_run_backtest_writes_json_file(monkeypatch, tmp_path):
    from scanner.single_stock_backtest import run_single_stock_cuphandle_backtest

    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    data = rows_for_dates([f"2025-01-{day:02d}" for day in range(1, 21)])
    db.save_ohlc("600000", data)
    config = {"data": {"database_path": str(db_path)}, "output": {"output_dir": str(tmp_path / "output_data")}, "cup": {}, "handle": {}, "breakout": {}, "scoring": {}}

    result = run_single_stock_cuphandle_backtest("600000", "2025-01-01", "2025-01-20", config, context_days=0)

    import json
    from pathlib import Path
    path = Path(result["outputFile"])
    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["code"] == "600000"
    assert saved["strategyVersion"] == result["strategyVersion"]
```

- [ ] **Step 2: Run tests to verify missing function failure**

Run:

```bash
python -m pytest tests/test_single_stock_backtest.py::test_run_backtest_uses_only_data_up_to_detection_day tests/test_single_stock_backtest.py::test_run_backtest_writes_json_file -v
```

Expected: FAIL with `ImportError` or missing `run_single_stock_cuphandle_backtest`.

- [ ] **Step 3: Implement backtest orchestration**

Append to `scanner/single_stock_backtest.py`:

```python
def run_single_stock_cuphandle_backtest(
    code: str,
    start_date: str,
    end_date: str,
    config: dict,
    handle_start_date: str | None = None,
    handle_end_date: str | None = None,
    context_days: int | None = None,
    fetch_fn: Callable[[str], list[dict] | None] = default_fresh_fetch,
) -> dict:
    _validate_request(start_date, end_date, handle_start_date, handle_end_date)
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)
    context_days = context_days if context_days is not None else _context_days(config)

    cached = db.get_ohlc(code) or []
    required_start = _required_start_from_cached(cached, start_date, context_days)
    required_end = end_date
    data, coverage = ensure_backtest_data(
        code,
        required_start_date=required_start,
        required_end_date=required_end,
        fetch_fn=fetch_fn,
    )
    data = [row for row in data if required_start <= row["date"] <= required_end]

    engine = CupHandleStrategyEngine(config)
    patterns = _run_windows(code, data, start_date, end_date, engine)
    specified = None
    if handle_start_date and handle_end_date:
        handle_window = [row for row in data if row["date"] <= handle_end_date]
        diagnosis = engine.diagnose_handle(handle_window, handle_start_date, handle_end_date, code=code)
        specified = diagnosis.to_dict() if diagnosis else None

    response = {
        "code": code,
        "name": "",
        "strategyVersion": engine.strategy_version,
        "configHash": engine.config_hash,
        "request": {
            "startDate": start_date,
            "endDate": end_date,
            "specifiedHandle": ({"startDate": handle_start_date, "endDate": handle_end_date} if handle_start_date and handle_end_date else None),
        },
        "dataCoverage": {
            "requestedRange": {"startDate": start_date, "endDate": end_date},
            **coverage,
        },
        "summary": {
            "totalPatterns": len(patterns),
            "bestScore": max((p["score"] for p in patterns), default=0),
            "firstDetectedDate": patterns[0]["firstDetectedDate"] if patterns else None,
            "hasSpecifiedDiagnosis": specified is not None,
            "specifiedPassed": specified.get("passed") if specified else None,
        },
        "patterns": patterns,
        "specifiedDiagnosis": specified,
        "ohlc": [row for row in data if start_date <= row["date"] <= end_date],
        "outputFile": "",
    }
    response["outputFile"] = _write_backtest_json(response, config)
    return response


def _validate_request(start_date: str, end_date: str, handle_start: str | None, handle_end: str | None):
    _dt.date.fromisoformat(start_date)
    _dt.date.fromisoformat(end_date)
    if start_date > end_date:
        raise ValueError("回测开始日期不能晚于回测结束日期。")
    if (handle_start and not handle_end) or (handle_end and not handle_start):
        raise ValueError("指定柄开始日期和结束日期必须同时填写。")
    if handle_start and handle_end:
        _dt.date.fromisoformat(handle_start)
        _dt.date.fromisoformat(handle_end)
        if handle_start > handle_end:
            raise ValueError("指定柄开始日期不能晚于指定柄结束日期。")
        if handle_start < start_date or handle_end > end_date:
            raise ValueError("指定柄区间必须落在回测区间内。")


def _context_days(config: dict) -> int:
    cup_max = config.get("cup", {}).get("max_duration", 180)
    handle_max = config.get("handle", {}).get("max_duration", 30)
    return max(cup_max + handle_max + 30, 180)


def _required_start_from_cached(cached: list[dict], start_date: str, context_days: int) -> str:
    ordered = sorted(cached, key=lambda row: row["date"])
    dates = [row["date"] for row in ordered if row["date"] <= start_date]
    if len(dates) > context_days:
        return dates[-context_days - 1]
    if ordered:
        return ordered[0]["date"]
    return start_date


def _run_windows(code: str, data: list[dict], start_date: str, end_date: str, engine: CupHandleStrategyEngine) -> list[dict]:
    by_key: dict[tuple[str, str, str], dict] = {}
    for idx, row in enumerate(data):
        current_date = row["date"]
        if current_date < start_date or current_date > end_date:
            continue
        window = data[:idx + 1]
        evaluation = engine.evaluate_at(window, code=code)
        if not evaluation.passed or not evaluation.result.found:
            continue
        pattern = _pattern_payload(code, current_date, evaluation, window)
        key = (
            pattern["pattern"]["handleStartDate"],
            pattern["pattern"]["handleEndDate"],
            pattern["pattern"]["handleLowDate"],
        )
        existing = by_key.get(key)
        if existing is None:
            pattern["firstDetectedDate"] = current_date
            by_key[key] = pattern
        elif pattern["score"] > existing["score"]:
            pattern["firstDetectedDate"] = existing["firstDetectedDate"]
            by_key[key] = pattern
    return sorted(by_key.values(), key=lambda item: item["detectedDate"])


def _pattern_payload(code: str, detected_date: str, evaluation, window: list[dict]) -> dict:
    result = evaluation.result
    pattern = serialize_pattern_for_backtest(result, window)
    pattern_id = f"{code}-{pattern['handleStartDate']}-{pattern['handleEndDate']}-{pattern['handleLowDate']}"
    dry = evaluation.dry_stable or {}
    keys = dry.get("key_prices", {})
    rr = dry.get("risk_reward", {})
    return {
        "id": pattern_id,
        "detectedDate": detected_date,
        "firstDetectedDate": detected_date,
        "score": result.score,
        "rating": "强候选" if result.score >= 80 else "中等候选" if result.score >= 70 else "弱候选",
        "pattern": pattern,
        "tradePlan": {
            "entryZoneLow": keys.get("entry_zone_low"),
            "entryZoneHigh": keys.get("entry_zone_high"),
            "pivot": keys.get("pivot"),
            "stopLoss": keys.get("stop_loss"),
            "target1": keys.get("target_1"),
            "target2": keys.get("target_2"),
            "riskReward1": rr.get("rr1"),
        },
        "scoreBreakdown": {
            "volumeDry": dry.get("volume_dry"),
            "priceStable": dry.get("price_stable"),
            "patternScore": dry.get("pattern_score"),
        },
        "decision": dry.get("decision"),
        "passedRules": [rule.to_dict() for rule in evaluation.passed_rules],
        "failedRules": [rule.to_dict() for rule in evaluation.failed_rules],
    }


def _write_backtest_json(response: dict, config: dict) -> str:
    output_dir = config.get("output", {}).get("output_dir", "./output_data")
    backtest_dir = os.path.join(output_dir, "backtests")
    os.makedirs(backtest_dir, exist_ok=True)
    start = response["request"]["startDate"].replace("-", "")
    end = response["request"]["endDate"].replace("-", "")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(backtest_dir, f"{response['code']}_cuphandle_{start}_{end}_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(response, f, ensure_ascii=False, indent=2)
    return path
```

- [ ] **Step 4: Run backtest tests**

Run:

```bash
python -m pytest tests/test_single_stock_backtest.py -v
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run:

```bash
git diff -- scanner/single_stock_backtest.py tests/test_single_stock_backtest.py
```

Expected: sliding-window and JSON behavior are implemented and tested.

---

### Task 5: Add FastAPI Endpoint

**Files:**
- Modify: `server.py`
- Test: `tests/test_single_stock_backtest_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_single_stock_backtest_api.py`:

```python
from fastapi.testclient import TestClient

import server
from scanner import db


def test_cup_handle_backtest_endpoint_returns_success(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

    def fake_run(code, start_date, end_date, config, handle_start_date=None, handle_end_date=None):
        assert code == "600000"
        assert start_date == "2025-01-01"
        assert end_date == "2025-01-20"
        return {
            "code": code,
            "strategyVersion": "cuphandle-v1",
            "configHash": "sha256:" + "1" * 64,
            "patterns": [],
            "specifiedDiagnosis": None,
            "dataCoverage": {},
            "ohlc": [],
        }

    monkeypatch.setattr(server, "run_single_stock_cuphandle_backtest", fake_run, raising=False)
    client = TestClient(server.app)

    res = client.post("/api/stock/600000/backtest/cup-handle", json={"startDate": "2025-01-01", "endDate": "2025-01-20"})

    assert res.status_code == 200
    body = res.json()
    assert body["code"] == "600000"
    assert body["strategyVersion"] == "cuphandle-v1"
    assert body["configHash"].startswith("sha256:")


def test_cup_handle_backtest_endpoint_returns_validation_error(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})
    client = TestClient(server.app)

    res = client.post("/api/stock/600000/backtest/cup-handle", json={"startDate": "2025-02-01", "endDate": "2025-01-01"})

    assert res.status_code == 400
    assert res.json()["error"] == "Invalid request"


def test_cup_handle_backtest_endpoint_returns_data_coverage_error(monkeypatch, tmp_path):
    from scanner.single_stock_backtest import DataCoverageError

    db_path = tmp_path / "cuphandle.db"
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

    def fake_run(*args, **kwargs):
        raise DataCoverageError("600000", "2025-01-01", "2025-01-20", {"startDate": "2025-01-10", "endDate": "2025-01-11"})

    monkeypatch.setattr(server, "run_single_stock_cuphandle_backtest", fake_run, raising=False)
    client = TestClient(server.app)

    res = client.post("/api/stock/600000/backtest/cup-handle", json={"startDate": "2025-01-01", "endDate": "2025-01-20"})

    assert res.status_code == 422
    body = res.json()
    assert body["error"] == "Insufficient data coverage"
    assert body["missingRanges"]
```

- [ ] **Step 2: Run API tests to verify they fail**

Run:

```bash
python -m pytest tests/test_single_stock_backtest_api.py -v
```

Expected: FAIL with 404 for missing endpoint or import monkeypatch failure.

- [ ] **Step 3: Add server import**

At the top of `server.py`, add:

```python
from scanner.single_stock_backtest import (
    DataCoverageError,
    run_single_stock_cuphandle_backtest,
)
```

- [ ] **Step 4: Add endpoint near `/api/stock/{code}/ohlc`**

In `server.py`, before `@app.get("/api/stock/{code}/ohlc")`, add:

```python
@app.post("/api/stock/{code}/backtest/cup-handle")
async def backtest_cup_handle(code: str, payload: dict):
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)
    try:
        specified = payload.get("specifiedHandle") or {}
        result = run_single_stock_cuphandle_backtest(
            code,
            payload.get("startDate", ""),
            payload.get("endDate", ""),
            config,
            handle_start_date=specified.get("startDate"),
            handle_end_date=specified.get("endDate"),
        )
        return result
    except ValueError as exc:
        return JSONResponse(
            {"error": "Invalid request", "message": str(exc)},
            status_code=400,
        )
    except DataCoverageError as exc:
        return JSONResponse(exc.to_dict(), status_code=422)
    except Exception as exc:
        logger.exception("Single stock cup-handle backtest failed")
        return JSONResponse(
            {"error": "Backtest failed", "message": str(exc)},
            status_code=500,
        )
```

- [ ] **Step 5: Run API tests**

Run:

```bash
python -m pytest tests/test_single_stock_backtest_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Run backend focused suite**

Run:

```bash
python -m pytest tests/test_cuphandle_strategy_engine.py tests/test_single_stock_backtest.py tests/test_single_stock_backtest_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Checkpoint**

Run:

```bash
git diff -- server.py tests/test_single_stock_backtest_api.py
```

Expected: endpoint added without changing existing scan endpoints.

---

### Task 6: Refactor Live Scan Cup-Handle Path to Use Strategy Engine

**Files:**
- Modify: `scanner/engine.py`
- Test: existing `tests/test_engine_fresh_fetch.py`, `tests/test_scan_task_tracking.py`, and `tests/test_server_scan_api.py`

- [ ] **Step 1: Add regression test for cup path still producing candidates**

Inspect existing `tests/test_engine_fresh_fetch.py`. Add a focused test only if no existing test asserts a cup-handle candidate survives. Use monkeypatches to avoid network and stock-pool dependencies.

Test shape:

```python
def test_scan_all_uses_strategy_engine_for_cup_candidates(monkeypatch, tmp_path):
    from scanner import engine, db

    db_path = tmp_path / "cuphandle.db"
    config = {
        "data": {"database_path": str(db_path), "worker_count": 1},
        "liquidity": {"min_listing_days": 1, "min_avg_turnover": 0, "min_avg_volume": 0},
        "cup": {}, "handle": {}, "breakout": {}, "scoring": {"medium_threshold": 70},
    }
    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda: [])
    monkeypatch.setattr(engine, "passes_liquidity_filter", lambda data, cfg: True)
    monkeypatch.setattr(engine, "_fetch_with_retry", lambda *a, **k: engine.FetchResult(
        data=[{"date": f"2025-01-{i:02d}", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1_000_000, "turnover": 10_000_000} for i in range(1, 30)],
        primary_source="sina",
        fallback_source="tencent",
    ))

    class FakeEvaluation:
        passed = True
        dry_stable = {
            "decision": {"verdict": "可低吸", "summary": "测试"},
            "volume_dry": {"score": 8},
            "price_stable": {"score": 7},
            "pattern_score": {"score": 16, "type": "杯柄", "key_pattern_type": "cup_handle"},
            "risk_reward": {"risk_percent": 5, "rr1": 2, "position_advice": "轻仓"},
            "key_prices": {"entry_zone_low": 10, "entry_zone_high": 11, "pivot": 12, "stop_loss": 9, "target_1": 14, "target_2": 16},
            "market_environment": {"status": "一般", "position_advice": "轻仓"},
        }
        result = type("R", (), {
            "found": True, "code": "600000", "name": "浦发银行", "score": 80,
            "is_breakout": False, "is_volume_breakout": False, "breakout_price": 12,
            "cup_depth_pct": 20, "cup_duration": 60, "handle_depth_pct": 8,
            "vol_multiplier": 1.0,
        })()

    class FakeStrategyEngine:
        def __init__(self, config):
            pass
        def evaluate_at(self, data, code="", name="", market_data=None):
            FakeEvaluation.result.code = code
            FakeEvaluation.result.name = name
            return FakeEvaluation()

    monkeypatch.setattr(engine, "CupHandleStrategyEngine", FakeStrategyEngine)
    result = engine.scan_all(config, stocks=[{"code": "600000", "name": "浦发银行"}], worker_count=1)

    assert result["stats"]["candidates_found"] == 1
```

- [ ] **Step 2: Run regression test before refactor**

Run the added test:

```bash
python -m pytest tests/test_engine_fresh_fetch.py::test_scan_all_uses_strategy_engine_for_cup_candidates -v
```

Expected before import/refactor: FAIL because `engine.CupHandleStrategyEngine` does not exist.

- [ ] **Step 3: Import strategy engine in `scanner/engine.py`**

Replace direct cup imports:

```python
from scanner.pattern_detector import detect_cup_handle
from scanner.pattern_detector import CupHandleResult
from scanner.scorer import score_cup_handle_advanced
from analyzer.dry_stable import analyze_dry_stable
```

with:

```python
from scanner.pattern_detector import CupHandleResult
from analyzer.dry_stable import analyze_dry_stable
from scanner.strategy_engine import CupHandleStrategyEngine
```

Keep `CupHandleResult` and `analyze_dry_stable` for the existing VCP fallback path.

- [ ] **Step 4: Instantiate strategy engine once per scan**

Near existing config setup in `scan_all()` replace:

```python
cup_cfg = config.get("cup", {})
handle_cfg = config.get("handle", {})
breakout_cfg = config.get("breakout", {})
handle_prefixed = {f"handle_{k}": v for k, v in handle_cfg.items()}
pattern_cfg = {**cup_cfg, **handle_prefixed, **breakout_cfg}
```

with:

```python
strategy_engine = CupHandleStrategyEngine(config)
```

Keep:

```python
liquidity_cfg = config.get("liquidity", {})
scoring_cfg = config.get("scoring", {})
```

- [ ] **Step 5: Replace cup-handle detection branch**

Replace this block in `worker()`:

```python
result = detect_cup_handle(data, pattern_cfg)
if result.found:
    result.code = code
    result.name = stock.get("name", "")
    result.score = score_cup_handle_advanced(result, data, scoring_cfg)
    dry_stable = analyze_dry_stable(result, data, market_data=market_data)
else:
    result = CupHandleResult(found=False, code=code, name=stock.get("name", ""))
    dry_stable = analyze_dry_stable(result, data, market_data=market_data)
    pattern20 = dry_stable["pattern_score"]["score"]
    if dry_stable["pattern_score"].get("key_pattern_type") != "vcp" or pattern20 < 13:
        dry_stable = None
```

with:

```python
evaluation = strategy_engine.evaluate_at(
    data,
    code=code,
    name=stock.get("name", ""),
    market_data=market_data,
)
result = evaluation.result
dry_stable = evaluation.dry_stable
if not result.found:
    result = CupHandleResult(found=False, code=code, name=stock.get("name", ""))
    dry_stable = analyze_dry_stable(result, data, market_data=market_data)
    pattern20 = dry_stable["pattern_score"]["score"]
    if dry_stable["pattern_score"].get("key_pattern_type") != "vcp" or pattern20 < 13:
        dry_stable = None
```

This keeps VCP fallback exactly in `engine.py` while sharing the cup-handle path.

- [ ] **Step 6: Run scan regression tests**

Run:

```bash
python -m pytest tests/test_engine_fresh_fetch.py tests/test_scan_task_tracking.py tests/test_server_scan_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Run broader backend suite**

Run:

```bash
python -m pytest tests/ -v
```

Expected: PASS. If network-dependent tests fail due environment, capture exact failing test names and output; do not claim full suite passes.

- [ ] **Step 8: Checkpoint**

Run:

```bash
git diff -- scanner/engine.py tests/test_engine_fresh_fetch.py
```

Expected: live scan cup-handle orchestration now uses the shared engine; VCP-only fallback remains local to `engine.py`.

---

### Task 7: Add Frontend API, Route, and Navigation

**Files:**
- Modify: `web/src/composables/useApi.js`
- Modify: `web/src/router/index.js`
- Modify: `web/src/components/TopNav.vue`
- Modify: `web/src/pages/StockDetail.vue`

- [ ] **Step 1: Add API method**

In `web/src/composables/useApi.js`, add before `return`:

```js
async function runCupHandleBacktest(code, payload) {
  const res = await fetch(`${API_BASE}/stock/${code}/backtest/cup-handle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await res.json()
  return { ...body, ok: res.ok, statusCode: res.status }
}
```

Update return object:

```js
return {
  startScan, getScanStatus, getCandidates, getCandidate, getScanTasks,
  getTaskStocks, retryFailedStocks, getConfig, updateConfig,
  runCupHandleBacktest,
}
```

- [ ] **Step 2: Add routes**

In `web/src/router/index.js`, add before stock detail or after config route:

```js
{ path: '/backtest/cup-handle', name: 'SingleStockBacktest', component: () => import('../pages/SingleStockBacktest.vue') },
{ path: '/backtest/cup-handle/:code', name: 'SingleStockBacktestWithCode', component: () => import('../pages/SingleStockBacktest.vue') },
```

- [ ] **Step 3: Add nav tab**

In `web/src/components/TopNav.vue`, add after “候选列表”:

```vue
<router-link to="/backtest/cup-handle" class="topnav-tab" active-class="active">单股回测</router-link>
```

- [ ] **Step 4: Add stock detail action**

In `web/src/pages/StockDetail.vue`, in the `.stock-id` area after the tags block, add:

```vue
<button class="backtest-link" @click="router.push(`/backtest/cup-handle/${stock.code}`)">
  用该股票回测
</button>
```

Add scoped CSS near other button styles:

```css
.backtest-link {
  margin-top: 10px;
  width: 100%;
  border: 1px solid var(--accent);
  background: rgba(79, 125, 255, 0.12);
  color: var(--accent);
  border-radius: 4px;
  padding: 8px 10px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
}
.backtest-link:hover { background: rgba(79, 125, 255, 0.2); }
```

- [ ] **Step 5: Create temporary scaffold page to make routes build**

Create `web/src/pages/SingleStockBacktest.vue` with:

```vue
<template>
  <div class="backtest-page">
    <h1>单股杯柄策略回测</h1>
  </div>
</template>

<script setup>
</script>

<style scoped>
.backtest-page { padding: 24px; color: var(--text-primary); }
</style>
```

- [ ] **Step 6: Run frontend build**

Run:

```bash
npm --prefix web run build
```

Expected: build exits 0. Vite chunk-size or CJS warnings are acceptable if exit code is 0.

- [ ] **Step 7: Checkpoint**

Run:

```bash
git diff -- web/src/composables/useApi.js web/src/router/index.js web/src/components/TopNav.vue web/src/pages/StockDetail.vue web/src/pages/SingleStockBacktest.vue
```

Expected: route/API/nav scaffolding exists before page complexity is added.

---

### Task 8: Implement SingleStockBacktest Page Workbench

**Files:**
- Modify: `web/src/pages/SingleStockBacktest.vue`

- [ ] **Step 1: Replace scaffold template with workbench layout**

Use this structure in `SingleStockBacktest.vue`:

```vue
<template>
  <div class="backtest-layout">
    <aside class="left-panel">
      <div class="panel-card">
        <div class="section-title">单股杯柄回测</div>
        <label>股票代码</label>
        <input v-model.trim="form.code" class="form-input" aria-label="股票代码" />
        <label>回测开始日期</label>
        <input v-model="form.startDate" class="form-input" type="date" />
        <label>回测结束日期</label>
        <input v-model="form.endDate" class="form-input" type="date" />
        <div class="section-title small">指定柄区域（可选）</div>
        <label>柄开始日期</label>
        <input v-model="form.handleStartDate" class="form-input" type="date" />
        <label>柄结束日期</label>
        <input v-model="form.handleEndDate" class="form-input" type="date" />
        <button class="run-btn" :disabled="loading" @click="runBacktest">
          {{ loading ? '计算中...' : '运行回测' }}
        </button>
      </div>

      <div class="panel-card diagnosis-card">
        <div class="section-title">指定柄诊断</div>
        <div v-if="!result?.specifiedDiagnosis" class="empty-text">未指定柄区域</div>
        <div v-else>
          <div class="diagnosis-status" :class="result.specifiedDiagnosis.passed ? 'pass' : 'fail'">
            {{ result.specifiedDiagnosis.passed ? '符合策略' : '不符合策略' }}
          </div>
          <div class="rule-counts">
            <span>通过 {{ result.specifiedDiagnosis.passedRules?.length || 0 }}</span>
            <span>失败 {{ result.specifiedDiagnosis.failedRules?.length || 0 }}</span>
          </div>
          <div class="rule-list">
            <div v-for="rule in result.specifiedDiagnosis.failedRules" :key="rule.ruleName + rule.actualValue" class="rule-item" :class="rule.severity">
              <div class="rule-head"><span>{{ rule.ruleName }}</span><em>{{ severityText(rule.severity) }}</em></div>
              <div class="rule-line">要求：{{ rule.requiredValue }}</div>
              <div class="rule-line">实际：{{ rule.actualValue }}</div>
              <p>{{ rule.explanation }}</p>
            </div>
          </div>
        </div>
      </div>
    </aside>

    <main class="main-panel">
      <div v-if="error" class="error-card">
        <div class="error-title">{{ error.message || error.error }}</div>
        <div v-if="error.missingRanges?.length" class="error-detail">
          缺失区间：<span v-for="r in error.missingRanges" :key="r.startDate">{{ r.startDate }} ~ {{ r.endDate }}</span>
        </div>
      </div>

      <div class="metric-grid">
        <MetricCard label="识别区域" :value="summaryValue('totalPatterns')" />
        <MetricCard label="最高评分" :value="summaryValue('bestScore')" />
        <MetricCard label="数据来源" :value="result?.dataCoverage?.source || '--'" />
        <MetricCard label="策略版本" :value="result?.strategyVersion || '--'" />
      </div>

      <section class="chart-card">
        <div class="chart-header">
          <span>K线标记</span>
          <span class="hash" :title="result?.configHash">{{ shortHash }}</span>
        </div>
        <div ref="chartRef" class="chart-body"></div>
      </section>

      <section class="results-card">
        <div class="section-title">自动识别结果</div>
        <div v-if="!result" class="empty-text">请输入参数并运行回测</div>
        <div v-else-if="!result.patterns?.length" class="empty-text">该时间段未识别到符合杯柄策略的柄区域</div>
        <table v-else class="result-table">
          <thead><tr><th>柄区间</th><th>检测日</th><th>分数</th><th>决策</th><th>柄回撤</th><th>杯深</th><th>突破</th></tr></thead>
          <tbody>
            <tr v-for="p in result.patterns" :key="p.id" :class="{ selected: p.id === selectedPatternId }" @click="selectPattern(p.id)">
              <td>{{ p.pattern.handleStartDate }} ~ {{ p.pattern.handleEndDate }}</td>
              <td>{{ p.detectedDate }}</td>
              <td class="score">{{ p.score }}</td>
              <td>{{ p.decision?.verdict || '--' }}</td>
              <td>{{ pct(p.pattern.handleDepthPct) }}</td>
              <td>{{ pct(p.pattern.cupDepthPct) }}</td>
              <td>{{ p.pattern.isBreakout ? '是' : '否' }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section v-if="selectedPattern" class="breakdown-card">
        <div class="section-title">评分拆解</div>
        <div class="breakdown-grid">
          <ScoreBar label="量干" :current="selectedPattern.scoreBreakdown?.volumeDry?.score || 0" :max="10" />
          <ScoreBar label="价稳" :current="selectedPattern.scoreBreakdown?.priceStable?.score || 0" :max="10" />
          <ScoreBar label="形态" :current="selectedPattern.scoreBreakdown?.patternScore?.score || 0" :max="20" />
        </div>
        <RiskBox>{{ selectedPattern.decision?.summary || '无决策说明' }}</RiskBox>
      </section>
    </main>
  </div>
</template>
```

- [ ] **Step 2: Add script logic**

Use:

```vue
<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { createChart, CandlestickSeries, createSeriesMarkers } from 'lightweight-charts'
import { useApi } from '../composables/useApi.js'
import MetricCard from '../components/MetricCard.vue'
import ScoreBar from '../components/ScoreBar.vue'
import RiskBox from '../components/RiskBox.vue'

const route = useRoute()
const { runCupHandleBacktest } = useApi()
const chartRef = ref(null)
const chart = ref(null)
const candleSeries = ref(null)
const result = ref(null)
const error = ref(null)
const loading = ref(false)
const selectedPatternId = ref(null)

const form = ref({
  code: route.params.code || '',
  startDate: '',
  endDate: '',
  handleStartDate: '',
  handleEndDate: '',
})

const selectedPattern = computed(() => (result.value?.patterns || []).find(p => p.id === selectedPatternId.value) || null)
const shortHash = computed(() => result.value?.configHash ? result.value.configHash.slice(0, 18) + '…' : '--')

function summaryValue(key) {
  const value = result.value?.summary?.[key]
  return value === null || value === undefined ? '--' : value
}
function pct(value) {
  return value === null || value === undefined ? '--' : `${Number(value).toFixed(1)}%`
}
function severityText(severity) {
  return { info: '提示', low: '轻微', medium: '重要', high: '严重' }[severity] || severity
}
function selectPattern(id) {
  selectedPatternId.value = id
  drawMarkers()
}

async function runBacktest() {
  error.value = null
  result.value = null
  loading.value = true
  try {
    const payload = {
      startDate: form.value.startDate,
      endDate: form.value.endDate,
    }
    if (form.value.handleStartDate && form.value.handleEndDate) {
      payload.specifiedHandle = { startDate: form.value.handleStartDate, endDate: form.value.handleEndDate }
    }
    const body = await runCupHandleBacktest(form.value.code, payload)
    if (!body.ok) {
      error.value = body
      return
    }
    result.value = body
    selectedPatternId.value = body.patterns?.[0]?.id || null
    await nextTick()
    initChart()
  } finally {
    loading.value = false
  }
}

function initChart() {
  if (!chartRef.value || !result.value?.ohlc?.length) return
  if (chart.value) chart.value.remove()
  chart.value = createChart(chartRef.value, {
    width: chartRef.value.clientWidth,
    height: 420,
    layout: { background: { color: '#0B1220' }, textColor: '#CBD5E1' },
    grid: { vertLines: { color: '#1E293B' }, horzLines: { color: '#1E293B' } },
    timeScale: { borderColor: '#334155' },
    rightPriceScale: { borderColor: '#334155' },
  })
  candleSeries.value = chart.value.addSeries(CandlestickSeries, {
    upColor: '#EF4444', downColor: '#22C55E', borderVisible: false,
    wickUpColor: '#EF4444', wickDownColor: '#22C55E',
  })
  candleSeries.value.setData(result.value.ohlc.map(row => ({
    time: row.date, open: row.open, high: row.high, low: row.low, close: row.close,
  })))
  drawMarkers()
  chart.value.timeScale().fitContent()
}

function drawMarkers() {
  if (!candleSeries.value || !result.value) return
  const markers = []
  for (const pattern of result.value.patterns || []) {
    const selected = pattern.id === selectedPatternId.value
    const color = selected ? '#FBBF24' : '#4F7DFF'
    markers.push({ time: pattern.pattern.handleStartDate, position: 'belowBar', color, shape: 'arrowUp', text: selected ? '柄开始' : '自动柄' })
    markers.push({ time: pattern.pattern.handleEndDate, position: 'aboveBar', color, shape: 'arrowDown', text: selected ? '柄结束' : '' })
    markers.push({ time: pattern.pattern.handleLowDate, position: 'belowBar', color: '#F59E0B', shape: 'circle', text: '柄低' })
    markers.push({ time: pattern.pattern.leftHighDate, position: 'aboveBar', color: '#64748B', shape: 'circle', text: '左杯口' })
    markers.push({ time: pattern.pattern.cupLowDate, position: 'belowBar', color: '#64748B', shape: 'circle', text: '杯底' })
    markers.push({ time: pattern.pattern.rightHighDate, position: 'aboveBar', color: '#64748B', shape: 'circle', text: '右杯口' })
  }
  const specified = result.value.specifiedDiagnosis
  if (specified) {
    markers.push({ time: specified.startDate, position: 'belowBar', color: '#A855F7', shape: 'arrowUp', text: '指定柄开始' })
    markers.push({ time: specified.endDate, position: 'aboveBar', color: '#A855F7', shape: 'arrowDown', text: '指定柄结束' })
  }
  createSeriesMarkers(candleSeries.value, markers.filter(m => m.time))
}

watch(() => route.params.code, code => { if (code) form.value.code = code })
onMounted(() => { if (route.params.code) form.value.code = route.params.code })
</script>
```

- [ ] **Step 3: Add scoped styles**

Add:

```vue
<style scoped>
.backtest-layout { display: grid; grid-template-columns: 320px 1fr; gap: 16px; padding: 16px; color: var(--text-primary); }
.left-panel { display: flex; flex-direction: column; gap: 14px; }
.panel-card, .chart-card, .results-card, .breakdown-card, .error-card { background: var(--bg-panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
.section-title { font-size: 14px; font-weight: 700; margin-bottom: 12px; }
.section-title.small { margin-top: 14px; color: var(--text-secondary); }
label { display: block; margin: 10px 0 5px; font-size: 12px; color: var(--text-secondary); }
.form-input { width: 100%; background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border); border-radius: 4px; padding: 8px; }
.run-btn { width: 100%; margin-top: 14px; padding: 10px; border: none; border-radius: 4px; background: var(--accent); color: #fff; font-weight: 700; cursor: pointer; }
.run-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.main-panel { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.chart-header { display: flex; justify-content: space-between; margin-bottom: 8px; color: var(--text-secondary); font-size: 12px; }
.chart-body { height: 420px; }
.result-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.result-table th, .result-table td { padding: 9px 8px; border-bottom: 1px solid var(--border); text-align: left; }
.result-table tr { cursor: pointer; }
.result-table tr.selected { background: rgba(79, 125, 255, 0.12); }
.score { color: var(--gold); font-weight: 700; }
.empty-text { color: var(--text-secondary); font-size: 13px; padding: 12px 0; }
.diagnosis-status { font-size: 18px; font-weight: 800; margin-bottom: 8px; }
.diagnosis-status.pass { color: var(--up-red); }
.diagnosis-status.fail { color: var(--down-green); }
.rule-counts { display: flex; gap: 12px; color: var(--text-secondary); font-size: 12px; margin-bottom: 10px; }
.rule-item { border-left: 3px solid var(--border); padding: 8px 10px; margin-bottom: 8px; background: var(--bg-card); }
.rule-item.high { border-left-color: var(--down-green); }
.rule-item.medium { border-left-color: var(--orange); }
.rule-item.low { border-left-color: var(--accent); }
.rule-head { display: flex; justify-content: space-between; font-weight: 700; }
.rule-head em { font-style: normal; color: var(--text-secondary); }
.rule-line { color: var(--text-secondary); font-size: 12px; margin-top: 4px; }
.rule-item p { margin: 6px 0 0; line-height: 1.5; }
.error-card { border-color: var(--down-green); }
.error-title { color: var(--down-green); font-weight: 700; }
.error-detail { margin-top: 8px; color: var(--text-secondary); }
.breakdown-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 12px; }
@media (max-width: 1100px) { .backtest-layout { grid-template-columns: 1fr; } .metric-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
```

- [ ] **Step 4: Run frontend build**

Run:

```bash
npm --prefix web run build
```

Expected: build exits 0.

- [ ] **Step 5: Checkpoint**

Run:

```bash
git diff -- web/src/pages/SingleStockBacktest.vue
```

Expected: page implements form, diagnostics, metrics, chart markers, result list, and score breakdown.

---

### Task 9: Final Verification and Documentation Check

**Files:**
- Existing tests and docs only unless failures require targeted fixes.

- [ ] **Step 1: Run backend tests**

Run:

```bash
python -m pytest tests/ -v
```

Expected: PASS. If failures occur, record exact failures and fix only failures caused by this feature.

- [ ] **Step 2: Run frontend build**

Run:

```bash
npm --prefix web run build
```

Expected: exit code 0. Vite warnings are acceptable only if the build succeeds.

- [ ] **Step 3: Run a manual API smoke with mocked or cached data if available**

If local DB has sufficient data for a stock, start server:

```bash
python main.py serve --port 8080
```

Then in another terminal:

```bash
curl -X POST http://127.0.0.1:8080/api/stock/600036/backtest/cup-handle \
  -H "Content-Type: application/json" \
  -d '{"startDate":"2025-01-01","endDate":"2025-06-01"}'
```

Expected success shape:

```json
{
  "code": "600036",
  "strategyVersion": "cuphandle-v1",
  "configHash": "sha256:...",
  "patterns": [],
  "dataCoverage": {},
  "ohlc": []
}
```

If the API returns `Insufficient data coverage`, confirm it includes `requiredRange`, `availableRange`, and `missingRanges`; this is acceptable for local data gaps.

- [ ] **Step 4: Verify JSON output path**

After a successful API/backtest run, check:

```bash
git status --short
```

Expected: generated `output_data/backtests/*.json` is ignored by existing `.gitignore` policy or remains outside tracked changes. Do not add generated output files.

- [ ] **Step 5: Review final diff**

Run:

```bash
git diff -- scanner/strategy_engine.py scanner/single_stock_backtest.py scanner/engine.py server.py web/src/composables/useApi.js web/src/router/index.js web/src/components/TopNav.vue web/src/pages/StockDetail.vue web/src/pages/SingleStockBacktest.vue tests/test_cuphandle_strategy_engine.py tests/test_single_stock_backtest.py tests/test_single_stock_backtest_api.py
```

Expected: diff contains only feature implementation and tests.

- [ ] **Step 6: Commit checkpoint only after user confirmation**

Project rules require showing status, files, and summary before commit. Run:

```bash
git status --short
git diff --name-only
```

Summarize changes and ask user for confirmation before running any `git add` or `git commit`.

---

## Self-Review Against Spec

### Spec coverage

- Single-stock page: Task 7 and Task 8.
- Required inputs: Task 8 form.
- Optional specified handle dates: Task 8 form and Task 5 endpoint.
- Single-stock API: Task 5.
- Auto-detected handle regions: Task 4 sliding-window patterns.
- Specified handle diagnosis: Task 2 and Task 4.
- Detailed failed rules: Task 1, Task 2, Task 8.
- Reuse live scan cup-handle strategy: Task 1 and Task 6.
- Avoid VCP-only in backtest: Task 2 and Task 4.
- `strategyVersion` and `configHash`: Task 1, Task 4, Task 5.
- JSON output: Task 4.
- K-line markers: Task 8.
- Data completeness strictness: Task 3 and Task 4.

### Red-flag scan

This plan avoids unresolved red-flag terms and names exact files, commands, and code snippets. Commit steps are checkpoints because project rules require confirmation before `git add`/`git commit`.

### Type consistency

- `CupHandleStrategyEngine.evaluate_at()` returns `StrategyEvaluation` throughout.
- `diagnose_handle()` returns `HandleDiagnosis` throughout.
- Backtest response uses `patterns`, `specifiedDiagnosis`, `strategyVersion`, `configHash`, `dataCoverage`, and `ohlc` consistently across backend and frontend tasks.
