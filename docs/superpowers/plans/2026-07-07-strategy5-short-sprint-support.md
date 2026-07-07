# 策略5短线强势冲刺股盘整支撑实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 新增独立策略5“短线强势冲刺股 · 盘整支撑策略”，完整接入后端扫描、数据库、API、前端结果页和配置页。

**架构：** 策略5新增独立 `strategy5/` 包，唯一判断入口为 `ShortSprintSupportEngine.evaluate_at()`。扫描器复用 `scanner.stock_pool`、`scanner.daily_data_service.fetch_with_retry()`、`daily_ohlc` 和 `task_stocks`，候选独立写入 `strategy5_candidates`，不修改策略1-4判断链路。

**技术栈：** Python 3、SQLite、FastAPI、Vue 3、Vitest、pytest。

---

## 文件结构

- 创建：`strategy5/__init__.py`，包导出与版本边界。
- 创建：`strategy5/models.py`，`Strategy5Indicators`、`Strategy5Evaluation` 等数据结构。
- 创建：`strategy5/validation.py`，默认配置与参数校验。
- 创建：`strategy5/indicators.py`，均线、涨幅、振幅、成交额、斜率、标签计算。
- 创建：`strategy5/filters.py`，F1-F11 硬过滤和稳定失败码。
- 创建：`strategy5/support.py`，MA5/MA10/MA20/MA50 支撑状态与 `support_score`。
- 创建：`strategy5/scorer.py`，技术35、资金30、趋势20、支撑15四维评分。
- 创建：`strategy5/engine.py`，唯一策略入口 `ShortSprintSupportEngine.evaluate_at()`。
- 创建：`strategy5/scanner.py`，全市场扫描、失败处理、候选持久化。
- 创建：`strategy5/backtester.py`，只读本地 DB 的最小验证/回测能力。
- 修改：`scanner/db.py`，新增 `strategy5_candidates` 表和 CRUD。
- 修改：`server.py`，新增策略5扫描、状态、任务、候选 API。
- 修改：`config.yaml`，新增 `strategy5` 显式配置段。
- 修改：`web/src/composables/useApi.js`，新增策略5 API 方法。
- 修改：`web/src/router/index.js`、`web/src/components/TopNav.vue`，新增策略5结果页入口。
- 修改：`web/src/pages/ScannerConsole.vue`，新增策略5启动入口和发现展示。
- 修改：`web/src/pages/TaskCenter.vue`，新增策略5任务识别和跳转。
- 修改：`web/src/pages/StrategyConfig.vue`，新增策略5配置项。
- 创建：`web/src/pages/Strategy5Results.vue`，策略5候选分层结果页。
- 创建：`tests/test_strategy5_validation.py`，配置校验测试。
- 创建：`tests/test_strategy5_core_rules.py`，F1-F11、支撑、分类、评分单元测试。
- 创建：`tests/test_strategy5_db_api.py`，候选表/API/策略隔离测试。
- 创建：`tests/test_strategy5_scanner.py`，扫描器数据链路和失败列表测试。
- 创建：`web/src/pages/__tests__/Strategy5Results.test.js`，前端候选展示测试。
- 创建：`docs/reviews/2026-07-07-strategy5-acceptance-report.md`，验收报告。

---

## 任务 1：策略5配置解析

**文件：**
- 创建：`tests/test_strategy5_validation.py`
- 创建：`strategy5/validation.py`
- 创建：`strategy5/__init__.py`

- [ ] **步骤 1：编写失败测试**

```python
import pytest

from strategy5.validation import resolve_strategy5_config


def test_strategy5_default_config_matches_design():
    cfg = resolve_strategy5_config({})
    assert cfg["enabled"] is True
    assert cfg["kline_days"] == 1100
    assert cfg["minimum_kline_days"] == 260
    assert cfg["minimum_trading_days"] == 500
    assert cfg["min_avg_amount_60d_yi"] == 20
    assert cfg["min_avg_amount_30d_yi"] == 15
    assert cfg["min_avg_amount_10d_yi"] == 10
    assert cfg["key_candidate_min_support_score"] == 8


def test_strategy5_rejects_invalid_ranges():
    with pytest.raises(ValueError, match="kline_days"):
        resolve_strategy5_config({"strategy5": {"kline_days": 200}})
    with pytest.raises(ValueError, match="near_120d_high_ratio"):
        resolve_strategy5_config({"strategy5": {"near_120d_high_ratio": 1.2}})
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy5_validation.py -q`
预期：`ModuleNotFoundError: No module named 'strategy5'`。

- [ ] **步骤 3：实现最少配置代码**

实现 `DEFAULT_STRATEGY5_CONFIG`、`resolve_strategy5_config()` 和数值范围校验；支持从完整项目配置的 `strategy5` 段或裸配置解析。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_strategy5_validation.py -q`
预期：全部通过。

---

## 任务 2：指标、硬过滤、支撑状态、评分核心

**文件：**
- 创建：`tests/test_strategy5_core_rules.py`
- 创建：`strategy5/models.py`
- 创建：`strategy5/indicators.py`
- 创建：`strategy5/filters.py`
- 创建：`strategy5/support.py`
- 创建：`strategy5/scorer.py`
- 创建：`strategy5/engine.py`

- [ ] **步骤 1：编写失败测试**

覆盖以下行为：

```python
from strategy5.engine import ShortSprintSupportEngine
from strategy5.support import evaluate_support_status


def row(i, close=10.0, high=None, low=None, volume=1000, turnover=30):
    return {
        "date": f"2026-01-{(i % 28) + 1:02d}",
        "open": close * 0.99,
        "high": high if high is not None else close * 1.01,
        "low": low if low is not None else close * 0.99,
        "close": close,
        "volume": volume,
        "turnover": turnover,
    }


def build_strong_data(length=1100):
    data = []
    for i in range(length):
        close = 10 + i * 0.02
        data.append(row(i, close=close, turnover=30, volume=1000 + i))
    for j in range(20):
        data[-20 + j]["close"] *= 1 + j * 0.006
        data[-20 + j]["high"] = data[-20 + j]["close"] * 1.01
        data[-20 + j]["low"] = data[-20 + j]["close"] * 0.99
    return data


def test_engine_outputs_key_candidate_with_strength_high_support_and_scores():
    data = build_strong_data()
    result = ShortSprintSupportEngine({}).evaluate_at(data, code="000001", name="平安银行")
    assert result.passed is True
    assert result.candidate_type in {"KEY_CANDIDATE", "WATCH_CANDIDATE"}
    assert result.indicators.strength_trigger
    assert result.indicators.high_trigger
    assert result.support.support_status.startswith("SPRINT_")
    assert 0 <= result.score.total_score <= 100


def test_volume_up_decline_is_rejected_with_stable_reason():
    data = build_strong_data()
    data[-1]["close"] = data[-2]["close"] * 0.92
    data[-1]["volume"] = data[-20]["volume"] * 3
    result = ShortSprintSupportEngine({}).evaluate_at(data, code="000001", name="平安银行")
    assert result.passed is False
    assert "CONSOLIDATION_VOLUME_UP_DECLINE" in result.reject_reasons


def test_support_status_priority_prefers_ma5_before_ma10():
    support = evaluate_support_status(close=100, ma5=99, ma10=98, ma20=96, ma50=92)
    assert support.support_status == "SPRINT_MA5_SUPPORT"
    assert support.main_support_ma == "MA5"
    assert support.support_score >= 8
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy5_core_rules.py -q`
预期：导入失败或属性不存在。

- [ ] **步骤 3：实现最少核心代码**

实现时间升序数据输入、字段适配 `turnover/amount`、MA5/10/20/50/100/120/250、F1-F11、`strength_trigger`、`high_trigger`、风险标签、支撑状态、三级分类和四维评分。

- [ ] **步骤 4：运行核心测试通过**

运行：`python -m pytest tests/test_strategy5_validation.py tests/test_strategy5_core_rules.py -q`
预期：全部通过。

---

## 任务 3：数据库表和 CRUD

**文件：**
- 修改：`scanner/db.py`
- 创建：`tests/test_strategy5_db_api.py`

- [ ] **步骤 1：编写失败测试**

```python
import scanner.db as db


def test_strategy5_candidate_table_is_independent(tmp_path):
    db_path = tmp_path / "s5.db"
    db.init_db(str(db_path))
    db.create_scan_task("s5-test", "2026-07-07 10:00:00", strategy_type="STRATEGY_5_SHORT_SPRINT_SUPPORT")
    db.upsert_strategy5_candidate("s5-test", {
        "code": "000001",
        "name": "平安银行",
        "evaluation_date": "2026-07-03",
        "candidate_type": "KEY_CANDIDATE",
        "classification": "highlight",
        "total_score": 88,
        "support_status": "SPRINT_MA5_SUPPORT",
    })
    rows = db.get_strategy5_candidates("s5-test")
    assert rows[0]["code"] == "000001"
    assert rows[0]["candidate_type"] == "KEY_CANDIDATE"
    assert db.get_strategy3_candidates(task_id="s5-test") == []
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy5_db_api.py::test_strategy5_candidate_table_is_independent -q`
预期：`AttributeError: module 'scanner.db' has no attribute 'upsert_strategy5_candidate'`。

- [ ] **步骤 3：实现 DB 表和 CRUD**

新增 `_ensure_strategy5_candidates_table()`，在 `init_db()` 调用；新增 `upsert_strategy5_candidate()`、`get_strategy5_candidates()`、`get_strategy5_candidate()`，JSON 字段使用现有 `_json_any()` 和反序列化风格。

- [ ] **步骤 4：运行 DB 测试通过**

运行：`python -m pytest tests/test_strategy5_db_api.py -q`
预期：全部通过。

---

## 任务 4：扫描器和最小回测能力

**文件：**
- 创建：`strategy5/scanner.py`
- 创建：`strategy5/backtester.py`
- 创建：`tests/test_strategy5_scanner.py`

- [ ] **步骤 1：编写失败测试**

```python
from scanner.daily_data_service import FetchResult
from strategy5.scanner import scan_strategy5_all, STRATEGY5_TYPE


def test_strategy5_scan_uses_fetch_with_retry_and_marks_failures(tmp_path, monkeypatch):
    import scanner.db as db
    db_path = tmp_path / "s5scan.db"
    config = {"data": {"database_path": str(db_path), "daily_sources": ["baidu", "sina", "tencent"], "worker_count": 1}}
    stocks = [{"code": "000001", "name": "平安银行", "market": "SZ"}]

    def fake_fetch(*args, **kwargs):
        return FetchResult(data=None, primary_source="baidu", fallback_source="tencent", primary_error="boom")

    result = scan_strategy5_all(config, task_id="s5-scan", stocks=stocks, fetch_daily_fn=fake_fetch, worker_count=1)
    assert result["task_id"] == "s5-scan"
    assert result["stats"]["failed"] == 1
    assert db.get_task_strategy_type("s5-scan") == STRATEGY5_TYPE
    assert db.get_failed_task_stocks("s5-scan")[0]["code"] == "000001"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy5_scanner.py -q`
预期：`ModuleNotFoundError` 或扫描入口不存在。

- [ ] **步骤 3：实现扫描器**

以策略3为模板：使用 `get_a_stock_pool()`、`fetch_with_retry()`、`build_cache_freshness_context()`、`resolve_effective_worker_count()`、`task_stocks` 状态、三源失败入失败列表；候选写入 `strategy5_candidates`。

- [ ] **步骤 4：实现只读本地最小回测/验证**

`strategy5/backtester.py` 提供 `run_strategy5_local_backtest(config, evaluation_dates=None, limit=None)`，从 `daily_ohlc` 截断到 `evaluation_date` 评估，不调用行情源。

- [ ] **步骤 5：运行扫描测试通过**

运行：`python -m pytest tests/test_strategy5_scanner.py tests/test_strategy5_core_rules.py -q`
预期：全部通过。

---

## 任务 5：后端 API 接入

**文件：**
- 修改：`server.py`
- 扩展：`tests/test_strategy5_db_api.py`

- [ ] **步骤 1：编写失败测试**

在现有 FastAPI 测试风格中断言：

```python
def test_strategy5_tasks_and_candidates_api_rejects_cross_strategy(client, tmp_path):
    import scanner.db as db
    db.init_db(str(tmp_path / "api.db"))
    db.create_scan_task("s1-task", "2026-07-07 10:00:00", strategy_type="STRATEGY_1_CUP_HANDLE")
    res = client.get("/api/strategy5/tasks/s1-task/candidates")
    assert res.status_code == 409
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy5_db_api.py -q`
预期：策略5 API 404。

- [ ] **步骤 3：实现 API**

新增 `STRATEGY5_TYPE` 导入，新增：
- `POST /api/strategy5/scans`
- `GET /api/strategy5/scans/status`
- `GET /api/strategy5/tasks`
- `GET /api/strategy5/tasks/{task_id}/candidates`
- `GET /api/strategy5/tasks/{task_id}/candidates/{code}`

- [ ] **步骤 4：运行 API 测试通过**

运行：`python -m pytest tests/test_strategy5_db_api.py -q`
预期：全部通过。

---

## 任务 6：前端接入

**文件：**
- 修改：`web/src/composables/useApi.js`
- 修改：`web/src/router/index.js`
- 修改：`web/src/components/TopNav.vue`
- 修改：`web/src/pages/ScannerConsole.vue`
- 修改：`web/src/pages/TaskCenter.vue`
- 修改：`web/src/pages/StrategyConfig.vue`
- 创建：`web/src/pages/Strategy5Results.vue`
- 创建：`web/src/pages/__tests__/Strategy5Results.test.js`

- [ ] **步骤 1：编写失败测试**

测试 `Strategy5Results.vue` 加载候选并显示分层字段：

```javascript
import { mount } from '@vue/test-utils'
import Strategy5Results from '../Strategy5Results.vue'

test('renders strategy5 key and watch candidates with support fields', async () => {
  global.fetch = vi.fn(async () => ({
    ok: true,
    json: async () => ({ candidates: [
      { code: '000001', name: '平安银行', candidate_type: 'KEY_CANDIDATE', total_score: 88, support_status: 'SPRINT_MA5_SUPPORT', main_support_ma: 'MA5', support_score: 9, risk_tags: [] },
      { code: '000002', name: '万科A', candidate_type: 'WATCH_CANDIDATE', total_score: 72, support_status: 'SPRINT_MA50_TESTING', main_support_ma: 'MA50', support_score: 4, warn_tags: ['EXTREME_PULLBACK_OBSERVE'] },
    ] }),
  }))
  const wrapper = mount(Strategy5Results)
  await Promise.resolve()
  await Promise.resolve()
  expect(wrapper.text()).toContain('KEY_CANDIDATE')
  expect(wrapper.text()).toContain('SPRINT_MA5_SUPPORT')
  expect(wrapper.text()).toContain('WATCH_CANDIDATE')
})
```

- [ ] **步骤 2：运行前端测试验证失败**

运行：`npm.cmd --prefix web test -- Strategy5Results --run`
预期：组件不存在。

- [ ] **步骤 3：实现前端**

新增 API 方法、路由、导航、启动按钮、任务中心识别、配置字段和结果页；结果页展示重点/观察分组、支撑状态、主支撑均线、支撑分、四维评分、风险标签、触发原因。

- [ ] **步骤 4：运行前端测试通过**

运行：`npm.cmd --prefix web test -- Strategy5Results --run`
预期：通过。

---

## 任务 7：本地数据验证和验收报告

**文件：**
- 创建：`docs/reviews/2026-07-07-strategy5-acceptance-report.md`

- [ ] **步骤 1：运行本地 DB 最小验证**

运行：`python -m strategy5.backtester --db data/cuphandle.db --limit 300`
预期：输出评估股票数、KEY/WATCH 数、失败原因分布，且不发起外部行情请求。

- [ ] **步骤 2：运行专项和回归测试**

运行：
```bash
python -m pytest tests/test_strategy5_* -q
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py
python -m compileall scanner strategy2 strategy3 strategy4 strategy5 server.py -q
npm.cmd --prefix web test -- --run
npm.cmd --prefix web run build
```

- [ ] **步骤 3：审核专家验收**

逐项检查：
- 策略5未导入策略1/2/3/4判断模块。
- 策略5扫描只复用现有 `stock_pool + fetch_with_retry + daily_ohlc`。
- 三源失败进入 `task_stocks.failed`。
- 策略5候选独立存储。
- 前端能启动、识别任务、展示候选分层。

- [ ] **步骤 4：写验收报告**

报告必须包含修改范围、测试结果、本地 DB 验证摘要、残余风险和中高等级问题结论。

---

## 自检

- 规格覆盖：F1-F11、短线强度、新高确认、盘整过滤、风险标签、支撑状态、支撑评分、三级分类、四维评分、输出字段、DB/API/前端/本地验证均有任务覆盖。
- 策略隔离：策略5使用独立包、独立候选表、独立 `STRATEGY_5_SHORT_SPRINT_SUPPORT`。
- 数据链路：扫描器任务明确复用 `fetch_with_retry()` 和 `daily_ohlc`，禁止 westock/yfinance。
- TDD：每个新增核心模块先有失败测试再实现。
- 验证：包含专项、后端回归、编译、前端测试和构建。
