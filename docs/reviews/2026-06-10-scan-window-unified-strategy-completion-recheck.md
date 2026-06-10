# 扫描窗口与统一策略入口完成复查报告

## 1. 检查范围

本次复查重点检查提交：

* `3bef48e fix: address final recheck FINAL-001 through FINAL-005`
* 父提交：`d1f9203`
* 功能基线：`f32c132`

检查范围：

* `main.py` CLI 单股分析
* `server.py` 扫描启动、配置保存、候选详情
* `scanner/engine.py` 扫描和重新分析
* `scanner/backtester.py` 批量回测
* `scanner/single_stock_backtest.py` 单股回测
* `scanner/strategy_engine.py` 统一策略入口与共享窗口函数
* `tests/test_backtester.py` 新增真实路径一致性测试
* `docs/superpowers/specs/2026-06-10-scan-window-unified-strategy-design.md`

本次只修改审查文档和操作日志，不修改业务代码。

---

## 2. 总体结论

`3bef48e` 已正确修复：

* `server.py` 缺少 `resolve_strategy_windows` 导入的问题。
* CLI 双数据源失败时的 `TypeError`。
* 扫描引擎再次直接读取 `min_listing_days` 的问题。
* 上一轮复查文档末尾多余空行。
* 一致性测试不使用真实策略引擎、判断日期不一致的问题。

但是，当前仍存在一个影响策略正确性的高严重度问题：

> 扫描、重新分析、CLI 分析和候选详情会把完整市场指数数据传给策略引擎。对于停牌、数据缺日或缓存滞后的股票，策略会使用股票判断日期之后的大盘数据，造成未来数据泄漏，并导致扫描和回测在相同股票窗口下得到不同结论。

新增一致性测试没有发现该问题，因为测试在进入真实扫描路径前，已经手工把扫描市场数据截断到判断日期。这验证了“调用方提供相同数据时策略结果相同”，但没有验证真实扫描调用方会正确准备数据。

另外，设计文档明确要求一致性测试分别覆盖完整杯柄、VCP-only、突破排除和策略拒绝。当前只覆盖平滑上涨后被拒绝的一种场景。

因此，本功能还需要最后一轮小范围修复。

---

## 3. FINAL-001 至 FINAL-005 复查结果

| 编号 | 状态 | 证据 |
| --- | --- | --- |
| FINAL-001 | 已修复 | `server.py` 已导入 resolver，候选详情非法配置返回 400 |
| FINAL-002 | 已修复 | CLI 双源失败后记录错误并提前返回，新增三条来源路径测试 |
| FINAL-003 | 部分修复 | 已使用真实策略、相同判断日期和八个核心字段，但只覆盖拒绝场景，且预先截断扫描市场数据 |
| FINAL-004 | 已修复 | 扫描上市天数检查使用已解析的 `kline_days` |
| FINAL-005 | 已修复 | `git diff --check d1f9203..3bef48e` 通过 |

---

## 4. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| COMPLETION-001 | 扫描等实时入口未按股票判断日期截断市场数据，存在未来数据泄漏 | 高 | 扫描结果、重算结果、CLI、候选详情、回测一致性 | 是 |
| COMPLETION-002 | 一致性测试仍未覆盖完整杯柄、VCP-only 和突破排除场景 | 中 | 策略回归保护、设计验收 | 是 |
| COMPLETION-003 | FINAL-001 的三个关键 API 修复没有入口级回归测试 | 中 | API 稳定性、名称错误防回归 | 是 |

---

## 5. 详细问题分析

### COMPLETION-001：实时与重算入口存在市场数据未来泄漏

#### 问题现象

批量回测和单股回测会按股票判断日期截断市场指数数据：

```python
market_window = [r for r in market_data_full if r["date"] <= detect_date]
```

但是以下入口直接传入完整市场数据：

* `scanner/engine.py::scan_all()`
* `scanner/engine.py::re_evaluate_task()`
* `main.py::cmd_analyze()`
* `server.py::get_candidate()`

#### 代码证据

全市场扫描：

```python
market_data = fetch_market_index_daily(...)

evaluation = strategy_engine.evaluate_at(
    strategy_data,
    code=code,
    name=stock.get("name", ""),
    market_data=market_data,
)
```

重新分析：

```python
evaluation = strategy_engine.evaluate_at(
    strategy_data, code=code, name=name, market_data=market_data,
)
```

CLI：

```python
evaluation = engine.evaluate_at(
    strategy_data, code=code, name="", market_data=market_data,
)
```

候选详情：

```python
evaluation = engine.evaluate_at(
    strategy_data, code=code, name=c.get("name", ""),
    market_data=fetch_market_index_daily(market_idx),
)
```

#### 直接复现

构造股票最后日期为 `2026-01-30`，市场指数最后日期为 `2026-02-01`，执行真实 `scan_all()` 路径并捕获传给策略入口的数据：

```text
{'stock_last': '2026-01-30', 'market_last': '2026-02-01'}
```

这证明扫描路径会把判断日期之后的市场数据传给策略引擎。

#### 为什么会影响策略结论

`analyzer/market_env.py::assess_market_environment()` 使用市场数据最后 20、50、60 日及最后 3 日计算市场状态。

`analyzer/dry_stable.py` 将市场状态传入最终决策：

```python
decision = make_dry_stable_decision(
    ...
    market_status=market_env.status,
)
```

因此未来市场数据可能改变：

* `market_environment.status`
* `market_environment.position_advice`
* `decision.verdict`
* `decision.verdict_key`
* `evaluation.passed`

#### 触发条件

以下任一情况都会触发：

* 股票停牌，股票最后交易日早于指数最后交易日。
* 某数据源缺少股票最近一个或多个交易日。
* 本地缓存股票数据滞后，但指数请求返回最新数据。
* 使用历史缓存执行重新分析或候选详情重算。

#### 影响

* 扫描结果使用未来市场环境。
* 相同股票 OHLC 和配置下，扫描与回测结果可能不一致。
* 候选详情当前重算结果可能与原扫描日期不匹配。
* 停牌股票可能因停牌后的市场走势改变策略结论。

#### 推荐修复方案

在 `scanner/strategy_engine.py` 增加共享市场窗口函数，统一所有入口的时间边界：

```python
def select_market_window(
    market_data: list[dict] | None,
    decision_date: str,
) -> list[dict]:
    """Return market rows available on or before the stock decision date."""
    if not market_data:
        return []
    return [
        row for row in market_data
        if row.get("date") and row["date"] <= decision_date
    ]
```

该函数只负责按判断日期过滤，不修改输入列表，不静默补充未来数据。

#### 各入口精确修改

`scanner/engine.py` 导入 helper：

```python
from scanner.strategy_engine import (
    CupHandleStrategyEngine,
    resolve_strategy_windows,
    select_market_window,
    select_strategy_window,
)
```

扫描路径：

```python
decision_date = strategy_data[-1]["date"]
market_window = select_market_window(market_data, decision_date)

evaluation = strategy_engine.evaluate_at(
    strategy_data,
    code=code,
    name=stock.get("name", ""),
    market_data=market_window,
)
```

重新分析路径：

```python
decision_date = strategy_data[-1]["date"]
market_window = select_market_window(market_data, decision_date)

evaluation = strategy_engine.evaluate_at(
    strategy_data,
    code=code,
    name=name,
    market_data=market_window,
)
```

`main.py`：

```python
market_data_full = fetch_market_index_daily(market_cfg.get("index_symbol"))
market_data = select_market_window(
    market_data_full,
    strategy_data[-1]["date"],
)
```

`server.py::get_candidate()`：

```python
market_data_full = fetch_market_index_daily(market_idx)
market_data = select_market_window(
    market_data_full,
    strategy_data[-1]["date"],
)

evaluation = engine.evaluate_at(
    strategy_data,
    code=code,
    name=c.get("name", ""),
    market_data=market_data,
)
```

批量回测和单股回测也建议改为使用同一 helper，删除重复列表推导：

```python
market_window = select_market_window(market_data_full, detect_date)
```

这样所有策略入口共享完全一致的市场时间边界规则。

#### 必须新增的 helper 单元测试

```python
def test_select_market_window_excludes_future_rows():
    rows = [
        {"date": "2026-01-29"},
        {"date": "2026-01-30"},
        {"date": "2026-02-01"},
    ]

    result = select_market_window(rows, "2026-01-30")

    assert [row["date"] for row in result] == [
        "2026-01-29",
        "2026-01-30",
    ]


def test_select_market_window_handles_none():
    assert select_market_window(None, "2026-01-30") == []
```

#### 必须新增的真实路径测试

扫描测试必须把完整市场数据交给 `fetch_market_index_daily()` mock，由真实扫描代码负责截断：

```python
monkeypatch.setattr(
    engine,
    "fetch_market_index_daily",
    lambda symbol=None: list(market_full),
)

engine.scan_all(config, worker_count=1)

assert scan_calls[0]["market_dates"][-1] == decision_date
assert all(
    date <= decision_date
    for date in scan_calls[0]["market_dates"]
)
```

不要再次在 mock 中预先构造 `market_for_scan`，否则测试无法验证扫描调用方本身。

还需分别验证：

* `re_evaluate_task()` 不传入未来市场数据。
* CLI 分析不传入未来市场数据。
* 候选详情重算不传入未来市场数据。

---

### COMPLETION-002：一致性测试仍未覆盖设计要求的四类场景

#### 问题现象

当前新增测试使用 `_make_ohlc_window()` 构造单调平滑上涨数据，只执行一个场景。

该数据最终通常得到：

```python
evaluation.passed is False
evaluation.result.pattern_kind == "none"
evaluation.dry_stable is None
```

因此八个核心字段虽然被比较，但大部分是 `False`、`0` 或 `None`。这只能覆盖策略拒绝场景。

#### 设计要求

设计文档 `10.3 集成测试` 要求分别覆盖：

1. 完整杯柄。
2. VCP-only。
3. 突破排除。
4. 策略拒绝。

#### 影响

当前测试不能发现以下回归：

* 杯柄候选在扫描和回测间评分不同。
* VCP-only 在某一入口未被正确识别。
* 突破状态在某一入口未被排除。
* 有效候选的止损价或入场区间在入口间不一致。

#### 推荐测试结构

提取共享执行器：

```python
def assert_scan_backtest_consistent(
    monkeypatch,
    tmp_path,
    decision_data,
    future_data,
    market_full,
    config,
    expected,
):
    # 运行真实 scan_all()。
    # 运行真实 run_backtest()。
    # 从回测调用中选择同一 decision_date。
    # 断言股票窗口、市场窗口和八个核心字段一致。
    # 断言 expected 中声明的场景保护条件。
```

参数化四类 fixture：

```python
@pytest.mark.parametrize(
    "case_name,fixture_factory,expected",
    [
        (
            "cup_handle",
            build_valid_cup_handle_fixture,
            {"pattern_kind": "cup_handle", "dry_stable_required": True},
        ),
        (
            "vcp_only",
            build_vcp_only_fixture,
            {"key_pattern_type": "vcp", "dry_stable_required": True},
        ),
        (
            "breakout_excluded",
            build_breakout_fixture,
            {"passed": False, "is_breakout": True},
        ),
        (
            "rejected",
            build_rejected_fixture,
            {"passed": False},
        ),
    ],
)
def test_scan_backtest_consistency_scenarios(...):
    ...
```

#### Fixture 复用建议

优先复用现有测试数据构造：

* `tests/test_cuphandle_strategy_engine.py::build_cup_handle_closes`
* `tests/test_cuphandle_strategy_engine.py::make_ohlc_from_closes`
* `tests/test_single_stock_backtest.py::_make_vcp_3ct_data`
* 已有突破排除测试中的 `is_breakout=True` 构造方式

若突破状态无法通过纯 OHLC 稳定产生，可以只在 fixture 层 monkeypatch `detect_cup_handle()` 产生确定的突破结果，但两条业务路径必须继续使用同一个真实 `CupHandleStrategyEngine` 和相同 patch。

#### 防止测试空转的必要断言

每个场景必须先断言 fixture 确实命中预期：

```python
assert scan_call["core"]["pattern_kind"] == expected["pattern_kind"]
assert scan_call["core"]["verdict_key"] is not None
assert scan_call["core"]["stop_loss"] is not None
```

VCP 和突破场景也应有对应的非条件断言。禁止使用“如果识别到才断言”的条件式测试。

---

### COMPLETION-003：关键 API 修复缺少入口级回归测试

#### 问题现象

`3bef48e` 修复了 `server.py` 缺少 resolver 导入的问题，但没有新增：

* 合法配置启动扫描测试。
* 合法配置保存测试。
* 带 OHLC 的候选详情测试。
* 候选详情非法窗口返回 400 测试。

现有 `test_start_scan_rejects_when_db_task_running` 会在冲突检查阶段提前返回，无法执行到窗口 resolver。

#### 影响

上轮 `NameError` 在全部测试通过时仍进入提交，已经证明当前 API 测试无法保护这些入口。没有入口级测试，未来导入调整或调用路径变化时可能再次回归。

#### 必须新增的测试

建议放入 `tests/test_server_scan_api.py`：

```python
def test_start_scan_valid_config_reaches_window_validation(monkeypatch, tmp_path):
    # mock 合法配置、股票池结果和后台线程。
    # 确保请求经过 resolve_strategy_windows()。
    response = client.get("/api/scan/start")
    assert response.status_code == 200


def test_update_config_valid_window_returns_ok(monkeypatch, tmp_path):
    # 将工作目录或配置写入目标隔离到 tmp_path。
    response = client.put(
        "/api/config",
        json={"data": {"scan_window_days": 200}},
    )
    assert response.status_code == 200


def test_candidate_detail_with_ohlc_returns_current_analysis(monkeypatch):
    # mock 候选、足量 OHLC、市场数据和真实/可控策略结果。
    response = client.get("/api/candidates/600000")
    assert response.status_code == 200
    assert response.json()["current_analysis"] is not None


def test_candidate_detail_invalid_window_returns_400(monkeypatch):
    response = client.get("/api/candidates/600000")
    assert response.status_code == 400
    assert "Invalid window config" in response.json()["error"]
```

测试必须真正执行到 resolver 和候选重算代码，不能在冲突、404 或无 OHLC 分支提前返回。

---

## 6. 建议一次性修复顺序

1. 在 `scanner/strategy_engine.py` 增加 `select_market_window()` 及单元测试。
2. 将扫描、重新分析、CLI、候选详情、批量回测和单股回测全部改为调用该 helper。
3. 修改现有一致性测试：扫描 mock 返回完整市场数据，由真实扫描代码负责截断。
4. 参数化补齐完整杯柄、VCP-only、突破排除和策略拒绝四类一致性场景。
5. 为扫描启动、配置保存和候选详情补入口级 API 测试。
6. 运行完整验证命令和 `git diff --check`。

---

## 7. 给修复 AI 的执行要求

1. 不要修改杯柄、VCP、干稳评分和最终决策规则。
2. 不要修改 12 分制或用户配置阈值。
3. 不要新增或恢复 `mootdx`。
4. 不要调整多数据源前复权逻辑。
5. 市场窗口截止日期必须来自实际传给策略引擎的股票窗口最后日期：

```python
decision_date = strategy_data[-1]["date"]
```

6. 不要使用系统当前日期作为判断日期。
7. 不要在测试 mock 中预先截断扫描市场数据。
8. 所有策略入口必须共享同一个市场窗口 helper。
9. 四类一致性场景必须有非条件断言，确保 fixture 真正命中目标场景。
10. 不要重构无关模块。

---

## 8. 回归测试清单

* 扫描股票最后日期早于指数最后日期时，不传入未来指数数据。
* 重新分析不传入股票判断日期之后的指数数据。
* CLI 分析不传入股票判断日期之后的指数数据。
* 候选详情重算不传入股票判断日期之后的指数数据。
* 批量回测和单股回测继续不使用未来市场数据。
* 空市场数据返回空列表并正常执行策略。
* 完整杯柄扫描与回测核心字段一致。
* VCP-only 扫描与回测核心字段一致。
* 突破排除扫描与回测核心字段一致。
* 策略拒绝扫描与回测核心字段一致。
* 合法配置可启动扫描。
* 合法配置可保存。
* 带 OHLC 的候选详情返回当前分析。
* 候选详情非法窗口返回明确 400。

---

## 9. 必须执行的验证命令

```bash
python -m pytest tests/test_backtester.py tests/test_cuphandle_strategy_engine.py tests/test_server_scan_api.py tests/test_engine_fresh_fetch.py tests/test_single_stock_backtest.py -v
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_yfinance_hist.py
python -m pytest tests/ -v
python -m compileall analyzer scanner main.py server.py tests
cd web && npm run build
git diff --check
```

---

## 10. 本次验证结果

### 自动化验证

```text
相关策略、回测和 API 测试：109 passed
离线全量测试：209 passed
完整测试：211 passed，1 个外部东财连接失败，2 warnings
Python compileall：通过
前端 npm run build：通过
提交级 git diff --check：通过
```

完整测试失败来自外部东财接口连接被远端关闭，与本次提交无关。

### 直接复现

真实扫描路径收到的日期：

```text
股票判断日期：2026-01-30
传入策略的市场最后日期：2026-02-01
```

因此 COMPLETION-001 已由直接运行证实。

---

## 11. 最终交付标准

满足以下全部条件后，可以判定本功能完成：

1. 所有策略入口均按股票判断日期截断市场数据。
2. 扫描路径接收完整市场数据时，能够自行排除未来日期。
3. 扫描与回测在相同判断日期下使用完全相同的股票和市场窗口。
4. 完整杯柄、VCP-only、突破排除和策略拒绝四类场景的八个核心字段全部一致。
5. 三个关键 API 修复均有真实入口测试保护。
6. 离线全量测试、编译、前端构建和 `git diff --check` 全部通过。
7. 完整测试除明确外部网络失败外无业务测试失败。
