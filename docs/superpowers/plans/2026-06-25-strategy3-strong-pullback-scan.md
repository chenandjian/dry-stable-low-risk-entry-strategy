# 策略3强势回踩二次启动正式扫描实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 实现策略3「强势回踩二次启动」的正式扫描闭环：独立策略引擎、独立候选表、独立 API、扫描控制台入口、配置区和结果页。

**架构：** 新增 `strategy3/` 包，按策略2模式拆分为配置校验、指标、趋势、回踩、缩量企稳、二次转强、风险收益、评分和引擎。后端复用 `scan_tasks/task_stocks`、股票池、日线拉取、新鲜度判断、流动性过滤和全局互斥；候选写入 `strategy3_candidates`，不混入策略1/2。前端按策略2结果页模式新增 `/strategy3/results`，扫描控制台三策略互斥。

**技术栈：** Python 3.10+、dataclasses、SQLite、FastAPI、pytest、Vue 3、Vitest。

---

## 文件结构

创建：

- `strategy3/__init__.py`：策略3包声明。
- `strategy3/models.py`：`Strategy3Indicators`、`Strategy3Score`、`Strategy3Risk`、`Strategy3Evaluation` 等 dataclass。
- `strategy3/validation.py`：配置解析、OHLC 结构/数值校验。
- `strategy3/indicators.py`：MA、收益率、波动、成交量、相对强度等基础指标。
- `strategy3/trend.py`：强势趋势过滤与趋势分。
- `strategy3/pullback.py`：健康回踩过滤与回踩分。
- `strategy3/volume_stability.py`：缩量企稳过滤与缩量分。
- `strategy3/second_breakout.py`：二次转强过滤与转强分。
- `strategy3/risk.py`：支撑位、止损、目标、风险比和 RR1。
- `strategy3/scorer.py`：五模块总分、候选等级、最终状态原因。
- `strategy3/engine.py`：唯一策略入口 `StrongPullbackSecondBreakoutEngine.evaluate_at()`。
- `strategy3/scanner.py`：全市场扫描、失败重试、重新评估。
- `tests/test_strategy3_validation.py`：策略3配置和数据校验测试。
- `tests/test_strategy3_engine.py`：策略3核心规则和引擎测试。
- `tests/test_strategy3_independence.py`：导入隔离测试。
- `tests/test_strategy3_db_api.py`：候选表、API、跨策略隔离测试。
- `web/src/pages/Strategy3Results.vue`：策略3结果页。
- `web/src/pages/__tests__/Strategy3Results.test.js`：结果页测试。

修改：

- `config.yaml`：新增 `strategy3` 配置段。
- `scanner/db.py`：新增 `strategy3_candidates` 表和 CRUD；初始化时迁移。
- `server.py`：新增策略3 API；中断恢复和运行状态支持策略3。
- `web/src/composables/useApi.js`：新增策略3 API 方法。
- `web/src/router/index.js`：新增 `/strategy3/results` 路由。
- `web/src/pages/ScannerConsole.vue`：新增策略3启动按钮、运行状态、实时发现字段。
- `web/src/pages/StrategyConfig.vue`：新增策略3配置分区。
- `web/src/pages/TaskCenter.vue`：策略3任务的查看结果和导出入口。
- `tests/test_strategy2_independence.py` 或新增隔离测试：确认策略3不导入策略1/2判断模块。

不在本计划中实现：

- 策略3回测。回测涉及信号/机会/入场/退出/完整性校验，使用第二份计划实现。
- 策略3与策略1/2横向对比页。
- CSV 导出增强。首期可沿用候选 JSON API。

---

### 任务 1：策略3配置与模型

**文件：**
- 创建：`strategy3/__init__.py`
- 创建：`strategy3/models.py`
- 创建：`strategy3/validation.py`
- 测试：`tests/test_strategy3_validation.py`
- 修改：`config.yaml`

- [ ] **步骤 1：编写失败的配置测试**

```python
import pytest

from strategy3.validation import resolve_strategy3_config


def test_resolve_strategy3_config_defaults():
    cfg = resolve_strategy3_config({"liquidity": {"min_listing_days": 350}})
    assert cfg["strategy_window_days"] == 250
    assert cfg["minimum_required_days"] == 180
    assert cfg["candidate_min_score"] == 75
    assert cfg["core_min_score"] == 85
    assert cfg["max_risk_ratio"] == 0.08
    assert cfg["min_relative_strength_60"] == 0.05


def test_rejects_window_larger_than_listing_days():
    with pytest.raises(ValueError, match="strategy_window_days"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 200},
            "strategy3": {"strategy_window_days": 250},
        })


def test_rejects_invalid_score_order():
    with pytest.raises(ValueError, match="core_min_score"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"candidate_min_score": 90, "core_min_score": 80},
        })
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy3_validation.py -q`

预期：FAIL，报错包含 `ModuleNotFoundError: No module named 'strategy3'`。

- [ ] **步骤 3：实现模型和配置解析**

实现要点：

```python
# strategy3/models.py
from dataclasses import dataclass, field


@dataclass
class Strategy3Indicators:
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma60: float = 0.0
    ma120: float = 0.0
    return_3: float = 0.0
    return_20: float = 0.0
    return_60: float = 0.0
    return_120: float = 0.0
    high_120: float = 0.0
    drawdown_from_high_120: float = 0.0
    relative_strength_60: float = 0.0
    ma60_slope_20: float = 0.0
    recent_high: float = 0.0
    pullback_pct: float = 0.0
    range_5: float = 0.0
    close_range_5: float = 0.0
    volume_ratio_5_20: float = 0.0


@dataclass
class Strategy3Score:
    trend_score: int = 0
    pullback_score: int = 0
    volume_stability_score: int = 0
    second_breakout_score: int = 0
    risk_reward_score: int = 0
    total_score: int = 0
    level: str = ""
    score_reasons: list[str] = field(default_factory=list)


@dataclass
class Strategy3Risk:
    support_price: float = 0.0
    stop_loss: float = 0.0
    target_1: float = 0.0
    risk_ratio: float = 0.0
    rr1: float = 0.0


@dataclass
class Strategy3Evaluation:
    passed: bool
    code: str = ""
    name: str = ""
    evaluation_date: str = ""
    indicators: Strategy3Indicators = field(default_factory=Strategy3Indicators)
    risk: Strategy3Risk = field(default_factory=Strategy3Risk)
    trend_score: int = 0
    pullback_score: int = 0
    volume_stability_score: int = 0
    second_breakout_score: int = 0
    risk_reward_score: int = 0
    total_score: int = 0
    level: str = ""
    current_close: float = 0.0
    score_reasons: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)
    status_reason: str | None = None
```

```python
# strategy3/validation.py
DEFAULT_STRATEGY3_CONFIG = {
    "enabled": True,
    "strategy_window_days": 250,
    "minimum_required_days": 180,
    "pullback_lookback_days": 60,
    "support_lookback_days": 20,
    "candidate_min_score": 75,
    "core_min_score": 85,
    "max_risk_ratio": 0.08,
    "max_pullback_from_high": 0.30,
    "min_pullback_from_high": 0.08,
    "max_recent_range_5": 0.12,
    "max_recent_surge_3": 0.10,
    "min_relative_strength_60": 0.05,
    "volume_shrink_ratio": 0.85,
}


def resolve_strategy3_config(config: dict) -> dict:
    raw = dict(DEFAULT_STRATEGY3_CONFIG)
    raw.update((config or {}).get("strategy3", config or {}) if "strategy3" in (config or {}) else (config or {}))
    liquidity = (config or {}).get("liquidity", {})
    min_listing_days = int(liquidity.get("min_listing_days", 350))
    _validate_int_range(raw, "minimum_required_days", 120, 1000)
    _validate_int_range(raw, "strategy_window_days", raw["minimum_required_days"], min_listing_days)
    _validate_int_range(raw, "pullback_lookback_days", 40, 120)
    _validate_int_range(raw, "support_lookback_days", 10, 40)
    _validate_number_range(raw, "candidate_min_score", 0, 100)
    _validate_number_range(raw, "core_min_score", 0, 100)
    if raw["core_min_score"] < raw["candidate_min_score"]:
        raise ValueError("core_min_score must be >= candidate_min_score")
    _validate_number_range(raw, "max_risk_ratio", 0.01, 0.5)
    _validate_number_range(raw, "min_pullback_from_high", 0.0, 0.5)
    _validate_number_range(raw, "max_pullback_from_high", raw["min_pullback_from_high"], 0.8)
    _validate_number_range(raw, "max_recent_range_5", 0.01, 0.5)
    _validate_number_range(raw, "max_recent_surge_3", 0.01, 0.5)
    _validate_number_range(raw, "min_relative_strength_60", -0.5, 0.5)
    _validate_number_range(raw, "volume_shrink_ratio", 0.1, 2.0)
    return raw
```

同时在 `config.yaml` 增加设计文档中的 `strategy3` 默认配置段。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_strategy3_validation.py -q`

预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add strategy3/__init__.py strategy3/models.py strategy3/validation.py tests/test_strategy3_validation.py config.yaml
git commit -m "feat: add strategy3 config and models"
```

---

### 任务 2：指标、规则评分和唯一引擎

**文件：**
- 创建：`strategy3/indicators.py`
- 创建：`strategy3/trend.py`
- 创建：`strategy3/pullback.py`
- 创建：`strategy3/volume_stability.py`
- 创建：`strategy3/second_breakout.py`
- 创建：`strategy3/risk.py`
- 创建：`strategy3/scorer.py`
- 创建：`strategy3/engine.py`
- 测试：`tests/test_strategy3_engine.py`

- [ ] **步骤 1：编写失败的引擎测试**

```python
from strategy3.engine import StrongPullbackSecondBreakoutEngine


def make_bars(days=220, start=10.0):
    rows = []
    price = start
    for i in range(days):
        if i < 150:
            price *= 1.003
        elif i < 190:
            price *= 0.997
        else:
            price *= 1.002
        rows.append({
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "open": round(price * 0.99, 2),
            "high": round(price * 1.01, 2),
            "low": round(price * 0.98, 2),
            "close": round(price, 2),
            "volume": 1000000 if i < 180 else 700000,
            "turnover": price * 1000000,
        })
    return rows


def test_engine_passes_healthy_strong_pullback():
    engine = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}})
    result = engine.evaluate_at(make_bars(), code="000001", name="样本")
    assert result.passed is True
    assert result.total_score >= 75
    assert result.level in {"观察候选", "核心候选"}
    assert result.risk.stop_loss > 0
    assert result.risk.rr1 >= 1.5


def test_engine_rejects_deep_drawdown():
    data = make_bars()
    data[-1]["close"] = data[-1]["close"] * 0.55
    engine = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}})
    result = engine.evaluate_at(data, code="000002")
    assert result.passed is False
    assert "DEEP_DRAWDOWN_FROM_HIGH" in result.reject_reasons or result.status_reason == "PULLBACK_TOO_DEEP"


def test_engine_rejects_recent_overheated():
    data = make_bars()
    data[-1]["close"] = data[-4]["close"] * 1.12
    data[-1]["high"] = data[-1]["close"] * 1.01
    engine = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}})
    result = engine.evaluate_at(data, code="000003")
    assert result.passed is False
    assert result.status_reason == "RECENT_OVERHEATED"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy3_engine.py -q`

预期：FAIL，报错包含 `ModuleNotFoundError` 或 `ImportError`。

- [ ] **步骤 3：实现指标与规则模块**

实现口径：

- `compute_indicators(data, config, market_data=None)`：只使用评估日及之前数据；`recent_high` 固定取 `high`；`relative_strength_60` 在无 `market_data` 时使用 `return_60` 作为相对强度的保守替代，并在 `score_reasons` 中记录 `NO_MARKET_DATA_RELATIVE_STRENGTH_FALLBACK`。
- `trend.evaluate_trend(indicators, config)`：返回 `(reject_reasons, trend_score, score_reasons)`，模块封顶 25。
- `pullback.evaluate_pullback(indicators, data, config)`：返回回踩硬过滤和 25 分评分。
- `volume_stability.evaluate_volume_stability(indicators, data, config)`：返回缩量企稳硬过滤和 20 分评分。
- `second_breakout.evaluate_second_breakout(indicators, data, config)`：返回二次转强硬过滤和 15 分评分。
- `risk.compute_strategy3_risk(data, indicators, config)`：计算 `support_price`、`stop_loss`、`target_1`、`risk_ratio`、`rr1`。
- `scorer.build_strategy3_score(...)`：合并五模块分数，封顶总分 100，并按 `core_min_score/candidate_min_score` 生成等级。

- [ ] **步骤 4：实现唯一引擎**

引擎顺序固定：

1. 校验数据结构和排序。
2. 裁剪 `strategy_window_days`。
3. 检查 `minimum_required_days`。
4. 计算指标。
5. 执行趋势、回踩、缩量企稳、二次转强和风险收益。
6. 任一硬过滤触发时 `passed=False`，`status_reason` 取第一个稳定错误码。
7. 无硬过滤时按总分、风险比、RR1 判断核心/观察候选。

- [ ] **步骤 5：运行测试验证通过**

运行：`python -m pytest tests/test_strategy3_engine.py tests/test_strategy3_validation.py -q`

预期：PASS。

- [ ] **步骤 6：Commit**

```bash
git add strategy3 tests/test_strategy3_engine.py
git commit -m "feat: add strategy3 evaluation engine"
```

---

### 任务 3：数据库候选表和隔离测试

**文件：**
- 修改：`scanner/db.py`
- 创建：`tests/test_strategy3_independence.py`
- 创建：`tests/test_strategy3_db_api.py`

- [ ] **步骤 1：编写失败的数据库和隔离测试**

```python
import ast
from pathlib import Path

import scanner.db as db


FORBIDDEN_IMPORTS = {
    "scanner.pattern_detector",
    "scanner.strategy_engine",
    "analyzer",
    "strategy2.engine",
    "strategy2.scorer",
    "strategy2.rejection",
    "strategy2.trend",
}


def test_strategy3_does_not_import_strategy1_or_strategy2_modules():
    for path in Path("strategy3").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert not any(name == forbidden or name.startswith(forbidden + ".") for forbidden in FORBIDDEN_IMPORTS), (path, name)


def test_strategy3_candidate_table_roundtrip(tmp_path):
    db.init_db(str(tmp_path / "test.db"))
    db.create_scan_task("s3-task", "2026-06-25 15:30:00", strategy_type="STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT")
    db.upsert_strategy3_candidate("s3-task", {
        "code": "000001",
        "name": "平安银行",
        "evaluation_date": "2026-06-25",
        "total_score": 86,
        "level": "核心候选",
        "trend_score": 25,
        "pullback_score": 20,
        "volume_stability_score": 16,
        "second_breakout_score": 12,
        "risk_reward_score": 13,
        "current_close": 10.0,
        "risk_ratio": 0.04,
        "rr1": 2.2,
        "score_reasons": ["强趋势"],
        "reject_reasons": [],
    })
    rows = db.get_strategy3_candidates(task_id="s3-task")
    assert len(rows) == 1
    assert rows[0]["code"] == "000001"
    assert rows[0]["score_reasons"] == ["强趋势"]
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy3_independence.py tests/test_strategy3_db_api.py -q`

预期：FAIL，报错包含 `AttributeError: module 'scanner.db' has no attribute 'upsert_strategy3_candidate'`。

- [ ] **步骤 3：实现 `strategy3_candidates` 表和 CRUD**

在 `init_db()` 中调用 `_ensure_strategy3_candidates_table(conn)`。

新增函数：

- `_ensure_strategy3_candidates_table(conn)`
- `upsert_strategy3_candidate(task_id: str, candidate: dict)`
- `get_strategy3_candidates(task_id: str | None = None) -> list[dict]`
- `get_strategy3_candidate(code: str, task_id: str | None = None) -> dict | None`

JSON 字段序列化规则：

- 写入时 `score_reasons`、`reject_reasons` 用 `json.dumps(..., ensure_ascii=False)`。
- 读取时反序列化为 list；空值返回 `[]`。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_strategy3_independence.py tests/test_strategy3_db_api.py -q`

预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add scanner/db.py tests/test_strategy3_independence.py tests/test_strategy3_db_api.py
git commit -m "feat: add strategy3 candidate storage"
```

---

### 任务 4：策略3扫描编排

**文件：**
- 创建：`strategy3/scanner.py`
- 测试：`tests/test_strategy3_db_api.py`

- [ ] **步骤 1：补充失败的扫描测试**

```python
from strategy3.scanner import _build_strategy3_discovery, re_evaluate_strategy3_task
from strategy3.models import Strategy3Evaluation, Strategy3Indicators, Strategy3Risk


def test_build_strategy3_discovery_contains_frontend_fields():
    ev = Strategy3Evaluation(
        passed=True,
        code="000001",
        name="平安银行",
        evaluation_date="2026-06-25",
        total_score=88,
        level="核心候选",
        current_close=10.0,
        trend_score=25,
        pullback_score=20,
        volume_stability_score=18,
        second_breakout_score=12,
        risk_reward_score=13,
        indicators=Strategy3Indicators(pullback_pct=0.15, volume_ratio_5_20=0.7, range_5=0.04, close_range_5=0.03),
        risk=Strategy3Risk(support_price=9.5, stop_loss=9.31, target_1=12.0, risk_ratio=0.069, rr1=2.9),
        score_reasons=["强趋势"],
    )
    d = _build_strategy3_discovery(ev)
    assert d["total_score"] == 88
    assert d["pullback_pct"] == 0.15
    assert d["risk_ratio"] == 0.069
    assert d["rr1"] == 2.9
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy3_db_api.py -q`

预期：FAIL，报错包含 `ModuleNotFoundError: No module named 'strategy3.scanner'`。

- [ ] **步骤 3：实现扫描编排**

按 `strategy2/scanner.py` 的结构实现：

- `scan_strategy3_all(config, progress_callback=None, task_id=None, stocks=None, worker_count=4, retry_policy="normal")`
- `_build_strategy3_discovery(evaluation, fetch_result=None)`
- `re_evaluate_strategy3_task(config, task_id, progress_callback=None)`

关键行为：

- `strategy_type` 固定为 `STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT`。
- 使用 `fetch_with_retry()`、`build_cache_freshness_context()` 和 `get_reusable_task_stock_kline_context()`。
- 数据源全部失败时状态为 `failed`，`status_reason='ALL_DATA_SOURCES_FAILED'`。
- 流动性不过时状态为 `skipped`，`status_reason='LIQUIDITY_FILTER_REJECTED'`。
- 引擎未通过时状态为 `scanned`，`status_reason=evaluation.status_reason`。
- 候选持久化失败时状态为 `failed`，`status_reason='STRATEGY3_CANDIDATE_PERSIST_FAILED'`。
- discovery 字段必须覆盖结果页字段。

- [ ] **步骤 4：运行策略3专项测试**

运行：`python -m pytest tests/test_strategy3_validation.py tests/test_strategy3_engine.py tests/test_strategy3_independence.py tests/test_strategy3_db_api.py -q`

预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add strategy3/scanner.py tests/test_strategy3_db_api.py
git commit -m "feat: add strategy3 scan orchestration"
```

---

### 任务 5：后端 API 和任务隔离

**文件：**
- 修改：`server.py`
- 测试：`tests/test_strategy3_db_api.py`

- [ ] **步骤 1：编写失败的 API 测试**

```python
from fastapi.testclient import TestClient

import scanner.db as db
import server as server_mod


def test_strategy3_candidates_reject_strategy1_task(tmp_path, monkeypatch):
    db.init_db(str(tmp_path / "test.db"))
    monkeypatch.setattr(server_mod, "DB_PATH", str(tmp_path / "test.db"), raising=False)
    db.create_scan_task("s1-task", "2026-06-25 09:00:00", strategy_type="STRATEGY_1_CUP_HANDLE")
    client = TestClient(server_mod.app)
    res = client.get("/api/strategy3/candidates?task_id=s1-task")
    assert res.status_code == 400
    assert res.json()["error"] == "TASK_STRATEGY_MISMATCH"


def test_strategy3_tasks_returns_only_strategy3(tmp_path, monkeypatch):
    db.init_db(str(tmp_path / "test.db"))
    monkeypatch.setattr(server_mod, "DB_PATH", str(tmp_path / "test.db"), raising=False)
    db.create_scan_task("s3-task", "2026-06-25 09:00:00", strategy_type="STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT")
    db.create_scan_task("s2-task", "2026-06-25 09:10:00", strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
    client = TestClient(server_mod.app)
    res = client.get("/api/strategy3/tasks")
    assert res.status_code == 200
    ids = [task["id"] for task in res.json()["tasks"]]
    assert "s3-task" in ids
    assert "s2-task" not in ids
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy3_db_api.py -q`

预期：FAIL，`/api/strategy3/...` 返回 404。

- [ ] **步骤 3：实现策略3 API**

新增端点：

- `POST /api/strategy3/scans`
- `GET /api/strategy3/scans/status`
- `GET /api/strategy3/tasks`
- `GET /api/strategy3/candidates`
- `GET /api/strategy3/candidates/{code}`
- `POST /api/strategy3/tasks/{task_id}/retry-failed`
- `POST /api/strategy3/tasks/{task_id}/re-evaluate`

同步修改：

- `_get_running_strategy_type()` 和 `_set_running()` 不需要重构，只需传入策略3类型。
- 启动策略3前使用 `_get_running_task()` 做全局互斥。
- 中断恢复识别策略3并调用 `scan_strategy3_all()`。
- 未知 `strategy_type` 仍标记失败，不默认当策略1处理。

- [ ] **步骤 4：运行 API 测试验证通过**

运行：`python -m pytest tests/test_strategy3_db_api.py tests/test_strategy2_final_fixes.py -q`

预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add server.py tests/test_strategy3_db_api.py
git commit -m "feat: add strategy3 scan api"
```

---

### 任务 6：前端 API、路由、扫描控制台、配置页和结果页

**文件：**
- 修改：`web/src/composables/useApi.js`
- 修改：`web/src/router/index.js`
- 修改：`web/src/pages/ScannerConsole.vue`
- 修改：`web/src/pages/StrategyConfig.vue`
- 修改：`web/src/pages/TaskCenter.vue`
- 创建：`web/src/pages/Strategy3Results.vue`
- 创建：`web/src/pages/__tests__/Strategy3Results.test.js`

- [ ] **步骤 1：编写失败的结果页测试**

```javascript
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import Strategy3Results from '../Strategy3Results.vue'

vi.mock('../../composables/useApi', () => ({
  useApi: () => ({
    getStrategy3Tasks: vi.fn().mockResolvedValue({ ok: true, tasks: [{ id: 's3-task', strategy_type: 'STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT' }] }),
    getStrategy3Candidates: vi.fn().mockResolvedValue({ ok: true, candidates: [{
      code: '000001',
      name: '平安银行',
      total_score: 88,
      level: '核心候选',
      pullback_pct: 0.15,
      risk_ratio: 0.05,
      rr1: 2.1,
      evaluation_date: '2026-06-25',
    }] }),
  }),
}))

describe('Strategy3Results', () => {
  it('renders strategy3 candidate fields', async () => {
    const wrapper = mount(Strategy3Results)
    await Promise.resolve()
    await Promise.resolve()
    expect(wrapper.text()).toContain('强势回踩二次启动')
    expect(wrapper.text()).toContain('000001')
    expect(wrapper.text()).toContain('核心候选')
    expect(wrapper.text()).toContain('RR1')
  })
})
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm --prefix web test -- --run web/src/pages/__tests__/Strategy3Results.test.js`

预期：FAIL，报错包含找不到 `Strategy3Results.vue` 或 API 方法。

- [ ] **步骤 3：实现前端 API 和路由**

`useApi.js` 增加：

- `startStrategy3Scan()`
- `getStrategy3ScanStatus()`
- `getStrategy3Tasks()`
- `getStrategy3Candidates(taskId)`
- `getStrategy3Candidate(code, taskId)`
- `retryStrategy3Failed(taskId)`
- `reEvaluateStrategy3Task(taskId)`

`router/index.js` 增加：

```javascript
{
  path: '/strategy3/results',
  name: 'Strategy3Results',
  component: () => import('../pages/Strategy3Results.vue'),
}
```

- [ ] **步骤 4：实现结果页**

页面要求：

- 标题明确显示 `策略3：强势回踩二次启动`。
- 任务选择器只列策略3任务。
- 表格字段包含总分、等级、五项子分、回踩幅度、风险比、RR1、支撑位、止损、第一目标、评估日期。
- 空结果显示“当前任务没有策略3候选”。
- 接口失败显示错误提示，不清空已加载数据。

- [ ] **步骤 5：修改扫描控制台和配置页**

扫描控制台：

- 三个策略启动按钮：策略1、策略2、策略3。
- 任一策略运行时三个按钮全部禁用。
- 策略3运行时实时发现展示总分、等级、回踩幅度、风险比、RR1。

配置页：

- 新增策略3配置分区。
- 文案说明策略3不是杯柄/VCP，不是极致量干价稳。
- 保存 payload 包含 `strategy3` 段。

任务中心：

- 策略3任务点击“查看结果”跳转 `/strategy3/results?task=<id>`。

- [ ] **步骤 6：运行前端测试**

运行：

```bash
npm --prefix web test -- --run web/src/pages/__tests__/Strategy3Results.test.js web/src/pages/__tests__/ScannerConsole.history-task.test.js
npm --prefix web run build
```

预期：PASS，build 成功。

- [ ] **步骤 7：Commit**

```bash
git add web/src/composables/useApi.js web/src/router/index.js web/src/pages/ScannerConsole.vue web/src/pages/StrategyConfig.vue web/src/pages/TaskCenter.vue web/src/pages/Strategy3Results.vue web/src/pages/__tests__/Strategy3Results.test.js
git commit -m "feat: add strategy3 frontend scan views"
```

---

### 任务 7：验收审核和回归门禁

**文件：**
- 创建：`docs/reviews/2026-06-25-strategy3-scan-acceptance-review.md`

- [ ] **步骤 1：运行后端专项测试**

运行：

```bash
python -m pytest tests/test_strategy3_validation.py tests/test_strategy3_engine.py tests/test_strategy3_independence.py tests/test_strategy3_db_api.py -q
```

预期：PASS。

- [ ] **步骤 2：运行策略1/策略2关键回归**

运行：

```bash
python -m pytest tests/test_strategy2_engine.py tests/test_strategy2_independence.py tests/test_strategy2_final_fixes.py tests/test_server_scan_api.py -q
```

预期：PASS。

- [ ] **步骤 3：运行编译检查**

运行：

```bash
python -m compileall scanner strategy2 strategy3 server.py -q
```

预期：退出码 0。

- [ ] **步骤 4：运行前端测试与构建**

运行：

```bash
npm --prefix web test -- --run
npm --prefix web run build
```

预期：PASS，build 成功。

- [ ] **步骤 5：以审核专家角色检查中高风险**

检查清单：

- 策略3是否导入了策略1/策略2判断模块。
- 策略3候选是否只写入 `strategy3_candidates`。
- 跨策略 task_id 是否返回 `TASK_STRATEGY_MISMATCH`。
- 数据源全部失败是否进入失败列表。
- `processed = scanned + skipped + failed + candidate` 是否仍由 DB 汇总。
- 前端历史任务上下文是否以 URL `?task=` 为准。
- 任一策略运行时三个按钮是否全部禁用。

- [ ] **步骤 6：生成验收文档**

文档结构：

```markdown
# 策略3正式扫描验收审核报告

## 1. 检查范围
## 2. 总体结论
## 3. 问题清单
## 4. 中高等级问题分析
## 5. 已运行验证
## 6. 残余风险
## 7. 回测第二计划入口
```

若没有中高等级问题，问题清单写“未发现中/高等级问题”。低等级问题只在残余风险中简述，不阻塞交付。

- [ ] **步骤 7：最终提交**

```bash
git add docs/reviews/2026-06-25-strategy3-scan-acceptance-review.md
git commit -m "docs: add strategy3 scan acceptance review"
git push -u origin codex/strategy3-strong-pullback-second-breakout
```

---

## 计划自检

- 规格覆盖：本计划覆盖策略3正式扫描、候选存储、API、前端入口、配置区、结果页、隔离和回归测试。策略3回测按规格拆为第二计划实现。
- 占位符扫描：本文没有未完成标记或空泛处理步骤。
- 类型一致性：策略类型统一使用 `STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT`；候选表统一使用 `strategy3_candidates`；引擎统一使用 `StrongPullbackSecondBreakoutEngine.evaluate_at()`。
- 风险边界：不修改策略1/策略2核心规则，不引入新数据源，不改变共享日线数据语义。
