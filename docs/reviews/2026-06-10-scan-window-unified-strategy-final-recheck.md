# 扫描窗口与统一策略入口最终复查报告

## 1. 检查范围

本次复查以 `f32c132` 为基线，重点检查以下提交：

* `c2c6e9c feat: unified strategy window and single evaluation entry point`
* `7da4c2a fix: address code review findings BUG-001 through BUG-010`
* `d1f9203 fix: address recheck findings RECHECK-001 through RECHECK-004`

检查范围包括：

* `main.py` CLI 单股分析入口
* `server.py` 扫描启动、配置保存和候选详情接口
* `scanner/engine.py` 全市场扫描窗口准备
* `scanner/strategy_engine.py` 统一窗口解析与唯一策略入口
* `scanner/backtester.py` 批量历史回测
* 新增的扫描与回测一致性测试
* `docs/superpowers/specs/2026-06-10-scan-window-unified-strategy-design.md`

本次只生成审查与修复文档，不修改业务代码。

---

## 2. 总体结论

`d1f9203` 已正确修复上一轮发现的严格窗口类型校验、CLI 窗口变量顺序和候选详情直接读取窗口配置等问题。

但是，本次复查仍发现两个会直接破坏用户功能的高严重度回归：

1. `server.py` 使用了 `resolve_strategy_windows()`，却没有导入该函数。启动扫描、保存配置和读取带 OHLC 的候选详情时都会触发 `NameError`。
2. CLI 单股分析在新浪和腾讯均获取失败时，不再提前返回，而是把 `None` 传给 `select_strategy_window()`，触发 `TypeError`。

此外，设计文档要求的“相同判断日期下真实扫描与回测结果完全一致”测试仍未完成。当前新增测试使用两个伪策略引擎，并且比较的是不同日期窗口，只能证明两条路径调用了 `evaluate_at()`，不能保护策略结果一致性。

因此，当前提交不建议作为本功能最终完成版本。按照本文方案修复后，应能一次性完成本轮收尾。

---

## 3. 上一轮问题复查结论

| 编号 | 复查状态 | 结论 |
| --- | --- | --- |
| RECHECK-001 | 部分修复并引入新回归 | CLI 已在拉取前解析窗口，但删除了双源失败提前返回 |
| RECHECK-002 | 主体已修复 | resolver 已严格拒绝 `0`、浮点数、字符串和布尔值；候选详情已改用 resolver，但遗漏导入 |
| RECHECK-003 | 部分修复 | 测试经过真实 `scan_all()` 和 `run_backtest()`，但没有使用真实策略结果，也没有对齐判断日期 |
| RECHECK-004 | 原文档已修复，新文档再次出现 | `git diff --check 7da4c2a..d1f9203` 报告新复查文档末尾多余空行 |

---

## 4. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| FINAL-001 | `server.py` 缺少 `resolve_strategy_windows` 导入，三个 API 会触发 `NameError` | 高 | 扫描启动、配置保存、候选详情 | 是 |
| FINAL-002 | CLI 双数据源失败时把 `None` 传入窗口截取函数 | 高 | CLI 单股分析、异常处理 | 是 |
| FINAL-003 | 扫描与回测一致性测试未比较同一判断日期的真实策略结果 | 中 | 策略可信度、长期回归保护 | 是 |
| FINAL-004 | 扫描引擎仍直接读取 `min_listing_days`，没有完全使用 resolver 结果 | 低 | 单一事实来源、后续维护 | 是 |
| FINAL-005 | 新复查文档末尾存在多余空行 | 低 | 提交质量检查 | 否，但应顺手修复 |

---

## 5. 详细问题分析与修复方案

### FINAL-001：`server.py` 缺少统一窗口解析器导入

#### 问题现象

以下接口执行到窗口校验或候选重算时会抛出：

```text
NameError: name 'resolve_strategy_windows' is not defined
```

受影响入口：

* `GET /api/scan/start`
* `PUT /api/config`
* `GET /api/candidates/{code}`，且候选存在 OHLC 数据

#### 代码证据

`server.py:19` 当前只导入：

```python
from scanner.strategy_engine import CupHandleStrategyEngine, select_strategy_window
```

但文件内在以下位置调用了未导入函数：

* `server.py:182`
* `server.py:635`
* `server.py:750`

直接调用候选详情已复现：

```text
File "server.py", line 635, in get_candidate
    windows = resolve_strategy_windows(cfg)
NameError: name 'resolve_strategy_windows' is not defined
```

#### 触发条件

* 用户启动一次扫描。
* 用户在配置页保存任意配置。
* 用户打开一个已保存 OHLC 数据的候选详情。

#### 影响

这是服务端关键入口的确定性运行时错误。现有测试全部通过仍未发现它，说明接口级覆盖不足。

#### 修复代码

修改 `server.py` 顶部导入：

```python
from scanner.strategy_engine import (
    CupHandleStrategyEngine,
    resolve_strategy_windows,
    select_strategy_window,
)
```

候选详情还应显式处理手工修改或旧配置产生的非法窗口，避免导入修复后由 `ValueError` 变成无说明的 HTTP 500：

```python
try:
    windows = resolve_strategy_windows(cfg)
except ValueError as exc:
    return JSONResponse(
        {"error": f"Invalid window config: {exc}"},
        status_code=400,
    )
```

#### 必须新增的测试

至少覆盖三个真实接口：

```python
def test_start_scan_resolves_window_without_name_error(client, monkeypatch):
    # 固定合法配置，隔离股票池和后台线程。
    response = client.get("/api/scan/start")
    assert response.status_code != 500
    assert "resolve_strategy_windows" not in response.text


def test_update_config_validates_window_without_name_error(client):
    response = client.put(
        "/api/config",
        json={"data": {"scan_window_days": 200}},
    )
    assert response.status_code == 200


def test_candidate_detail_with_ohlc_uses_resolver(client, monkeypatch):
    # mock db.get_candidate() 和 db.get_ohlc() 返回有效数据。
    response = client.get("/api/candidates/600000")
    assert response.status_code == 200
    assert "current_analysis" in response.json()
```

再增加非法配置候选详情测试：

```python
def test_candidate_detail_invalid_window_returns_400(client, monkeypatch):
    monkeypatch.setattr(
        server,
        "load_config",
        lambda: {
            "data": {"scan_window_days": 0},
            "liquidity": {"min_listing_days": 250},
        },
    )
    # mock 候选和 OHLC 存在。
    response = client.get("/api/candidates/600000")
    assert response.status_code == 400
    assert "Invalid window config" in response.json()["error"]
```

---

### FINAL-002：CLI 双数据源失败时触发 `TypeError`

#### 问题现象

执行 CLI 单股分析时，如果新浪和腾讯均返回 `None`，程序不会记录“无法获取数据”并正常退出，而会崩溃：

```text
TypeError: object of type 'NoneType' has no len()
```

#### 代码证据

`d1f9203` 从 `main.py::cmd_analyze()` 删除了原有保护：

```python
if data is None:
    logger.error(f"Cannot fetch data for {code}")
    return
```

当前代码在双源失败后直接执行：

```python
strategy_data = select_strategy_window(data, scan_window_days)
```

`select_strategy_window()` 内部执行 `len(data)`，因此 `data=None` 必然崩溃。

#### 触发条件

* 新浪请求失败或解析失败。
* 腾讯请求也失败或解析失败。

#### 影响

数据源短时异常会把正常的业务失败升级为 CLI 未处理异常，用户无法获得清晰错误信息。

#### 修复代码

在腾讯回退之后、窗口截取之前恢复提前返回：

```python
data = fetch_sina_daily(code, days=kline_days)
if data is None:
    logger.info("Sina failed, trying Tencent...")
    data = fetch_tencent_daily(code, days=kline_days)

if data is None:
    logger.error("Cannot fetch data for %s", code)
    return

logger.info("Got %s days of data", len(data))

strategy_data = select_strategy_window(data, scan_window_days)
```

不要通过让 `select_strategy_window()` 接受 `None` 来修复。该函数的职责是截取有效序列；数据源失败应由调用入口显式处理。

#### 必须新增的测试

```python
def test_cmd_analyze_returns_cleanly_when_all_sources_fail(monkeypatch, caplog):
    monkeypatch.setattr(sina_source, "fetch_sina_daily", lambda code, days=None: None)
    monkeypatch.setattr(tencent_source, "fetch_tencent_daily", lambda code, days=None: None)

    main.cmd_analyze(Args())

    assert "Cannot fetch data" in caplog.text
```

同时修正现有测试的错误注释和断言。当前测试写着“Both sources should receive”，但新浪成功时腾讯不会被调用。应拆分为：

1. 新浪成功：只断言新浪收到 `min_listing_days`。
2. 新浪失败、腾讯成功：断言两个来源都收到 `min_listing_days`。
3. 两者均失败：断言正常返回且记录错误。

---

### FINAL-003：真实路径一致性测试仍未满足设计要求

#### 问题现象

新增测试名称为：

```python
test_scan_backtest_real_paths_call_strategy_engine_consistently
```

但它不能证明扫描与回测策略结果一致。

#### 代码证据

当前测试存在四个关键缺口：

1. 扫描路径使用自定义 `RecordingEngine`，回测路径使用另一个 `RecordingBTEngine`，没有运行真实 `CupHandleStrategyEngine`。
2. 两个伪引擎都固定返回 `passed=False`，没有验证任何真实规则或策略字段。
3. 扫描使用 `ohlc[-scan_window:]`，即最后 100 日。
4. 回测第一次判断使用 `ohlc[:backtest_window]`，即最前 100 日。

因此，两条路径比较的不是同一判断日期。

测试最终只断言：

```python
assert scan_call["window_len"] == scan_window
assert bt_call["window_len"] == backtest_window
```

并且市场数据被固定为空，只能证明调用长度，不能证明无未来数据截断正确。

设计文档 `10.3 集成测试` 明确要求相同判断日期，并比较：

* `evaluation.passed`
* `result.score`
* `result.pattern_kind`
* `dry_stable.decision.verdict_key`
* `dry_stable.pattern_score.key_pattern_type`
* `dry_stable.key_prices.stop_loss`
* `dry_stable.key_prices.entry_zone_low`
* `dry_stable.key_prices.entry_zone_high`

#### 影响

后续任何入口只要传错日期窗口、传错市场窗口，或真实策略规则在扫描和回测间漂移，当前测试仍可能通过。

#### 修复原则

保留真实 `scan_all()` 和 `run_backtest()` 业务路径，但仅替换外部数据源、线程和持久化依赖。策略引擎必须执行真实逻辑。

为捕获真实结果，可以用“调用真实父类后记录结果”的轻量包装器，而不是返回伪结果：

```python
from scanner.strategy_engine import CupHandleStrategyEngine as RealStrategyEngine


def evaluation_core(evaluation):
    dry = evaluation.dry_stable or {}
    return {
        "passed": evaluation.passed,
        "score": evaluation.result.score,
        "pattern_kind": evaluation.result.pattern_kind,
        "verdict_key": dry.get("decision", {}).get("verdict_key"),
        "key_pattern_type": dry.get("pattern_score", {}).get("key_pattern_type"),
        "stop_loss": dry.get("key_prices", {}).get("stop_loss"),
        "entry_zone_low": dry.get("key_prices", {}).get("entry_zone_low"),
        "entry_zone_high": dry.get("key_prices", {}).get("entry_zone_high"),
    }
```

扫描和回测分别使用捕获包装器：

```python
scan_calls = []
backtest_calls = []


class ScanCapturingEngine(RealStrategyEngine):
    def evaluate_at(self, data, code="", name="", market_data=None):
        evaluation = super().evaluate_at(data, code, name, market_data)
        scan_calls.append({
            "stock_dates": [row["date"] for row in data],
            "market_dates": [row["date"] for row in (market_data or [])],
            "core": evaluation_core(evaluation),
        })
        return evaluation


class BacktestCapturingEngine(RealStrategyEngine):
    def evaluate_at(self, data, code="", name="", market_data=None):
        evaluation = super().evaluate_at(data, code, name, market_data)
        backtest_calls.append({
            "stock_dates": [row["date"] for row in data],
            "market_dates": [row["date"] for row in (market_data or [])],
            "core": evaluation_core(evaluation),
        })
        return evaluation
```

#### 正确的数据对齐方式

假设：

```python
window_days = 250
forward_days = 60
ohlc = fixed_fixture[: window_days + forward_days]
decision_data = ohlc[:window_days]
decision_date = decision_data[-1]["date"]
```

扫描路径的 `_fetch_with_retry()` 必须返回 `decision_data`，不能返回 `ohlc[-window_days:]`。

回测路径返回完整 `ohlc`，然后从 `backtest_calls` 中按 `last stock_date == decision_date` 选择同一判断日期的调用。

最终断言：

```python
scan_call = scan_calls[0]
backtest_call = next(
    call for call in backtest_calls
    if call["stock_dates"][-1] == decision_date
)

assert scan_call["stock_dates"] == backtest_call["stock_dates"]
assert scan_call["core"] == backtest_call["core"]
assert all(date <= decision_date for date in backtest_call["market_dates"])
```

#### 必须覆盖的场景

按照设计文档，至少参数化覆盖：

* 完整杯柄候选
* VCP-only 候选
* 突破排除
* 策略拒绝

若现有 fixture 难以稳定构造，可先使用项目中已有的策略 fixture，不应通过伪造 `evaluation` 绕过真实策略。

---

### FINAL-004：扫描引擎仍直接读取 `min_listing_days`

#### 问题现象

`scanner/engine.py` 已在扫描开始时解析：

```python
windows = resolve_strategy_windows(config)
```

但上市天数检查仍再次直接读取原始配置：

```python
min_listing = liquidity_cfg.get("min_listing_days", 250)
```

#### 影响

当前合法配置下两者通常相同，因此不会立即产生用户可见错误；但这破坏了统一 resolver 作为窗口配置单一事实来源的约束。未来 resolver 增加标准化、默认值或兼容逻辑时，该位置可能再次产生行为漂移。

#### 修复代码

直接使用已验证值：

```python
min_listing = windows.min_listing_days
if len(data) < min_listing:
    ...
```

或直接使用已经赋值的：

```python
if len(data) < kline_days:
    ...
```

推荐使用 `windows.min_listing_days`，语义最明确。

#### 验证方式

修复后搜索业务代码，除 resolver 内部外不应再直接读取三个窗口字段：

```bash
rg 'get\("min_listing_days"|get\("scan_window_days"|get\("backtest_window_days"' main.py server.py scanner analyzer
```

允许出现的位置仅限：

* `scanner/strategy_engine.py::resolve_strategy_windows()`
* 前端配置展示或序列化代码

---

### FINAL-005：新复查文档末尾多余空行

#### 证据

执行：

```bash
git diff --check 7da4c2a..d1f9203
```

返回：

```text
docs/reviews/2026-06-10-scan-window-unified-strategy-recheck.md:462: new blank line at EOF.
```

#### 修复建议

删除该文档末尾额外空白行，并在提交前执行：

```bash
git diff --check
git diff --check 7da4c2a..HEAD
```

---

## 6. 建议一次性修复顺序

1. 修复 `server.py` 缺少导入，并补三个 API 的真实调用测试。
2. 恢复 `cmd_analyze()` 双源失败提前返回，并补三条数据源路径测试。
3. 将扫描引擎上市天数检查改为使用 `windows.min_listing_days`。
4. 重写扫描与回测一致性集成测试，使其使用真实策略、相同判断日期和相同市场数据。
5. 删除复查文档末尾多余空行。
6. 运行所有验证命令，确认不存在被测试掩盖的运行时名称错误。

---

## 7. 给修复 AI 的执行要求

请严格按照以下要求修复：

1. 不要重构策略评分、杯柄识别、VCP 识别或干稳决策规则。
2. 不要修改当前 12 分制及其阈值。
3. 不要重新引入 `mootdx`；当前日线数据源范围保持 `baidu`、`sina`、`tencent`。
4. 不要修改多数据源前复权逻辑，本轮不再将其作为问题。
5. `resolve_strategy_windows()` 继续作为窗口配置唯一解析与校验入口。
6. 数据源获取失败必须由调用方明确处理，不要让窗口 helper 接受 `None`。
7. 一致性测试必须执行真实 `CupHandleStrategyEngine`，不能用固定返回值的伪策略引擎代替。
8. 一致性测试必须比较同一判断日期的完全相同股票窗口。
9. 一致性测试必须传入非空固定市场数据，并断言没有判断日期之后的数据。
10. 不要修改无关模块或前端 UI。

---

## 8. 回归测试清单

修复后必须验证：

* `GET /api/scan/start` 不再因缺少 resolver 导入而失败。
* `PUT /api/config` 合法窗口返回成功。
* `PUT /api/config` 非法窗口返回 400。
* 带 OHLC 的候选详情可返回 `current_analysis`。
* 候选详情遇到非法手工配置时返回明确 400，而不是未处理异常。
* CLI 新浪成功时正常分析。
* CLI 新浪失败、腾讯成功时正常回退。
* CLI 新浪和腾讯均失败时记录错误并正常退出。
* 扫描拉取天数使用 `min_listing_days`。
* 扫描上市天数检查使用 resolver 解析后的值。
* 扫描策略窗口使用 `scan_window_days`。
* 回测策略窗口使用 `backtest_window_days`。
* 相同判断日期下，扫描与回测股票窗口日期完全一致。
* 相同判断日期下，扫描与回测核心策略结果完全一致。
* 回测市场数据不包含判断日期之后的数据。
* 完整杯柄、VCP-only、突破排除和策略拒绝场景均有一致性覆盖。

---

## 9. 必须执行的验证命令

```bash
python -m pytest tests/test_backtester.py tests/test_cuphandle_strategy_engine.py tests/test_server_scan_api.py -v
python -m pytest tests/ -v
python -m compileall analyzer scanner main.py server.py tests
cd web && npm run build
git diff --check
```

建议额外执行名称与直接配置读取检查：

```bash
rg "resolve_strategy_windows" server.py
rg 'get\("min_listing_days"|get\("scan_window_days"|get\("backtest_window_days"' main.py server.py scanner analyzer
rg "detect_cup_handle\(|analyze_dry_stable\(|score_cup_handle_advanced\(" main.py server.py scanner analyzer
```

最后一个命令的业务调用应只出现在 `scanner/strategy_engine.py` 内。

---

## 10. 本次复查验证结果

### 直接复现

CLI 双源失败：

```text
File "main.py", line 97, in cmd_analyze
    strategy_data = select_strategy_window(data, scan_window_days)
File "scanner/strategy_engine.py", line 395, in select_strategy_window
    if len(data) < window_days:
TypeError: object of type 'NoneType' has no len()
```

候选详情：

```text
File "server.py", line 635, in get_candidate
    windows = resolve_strategy_windows(cfg)
NameError: name 'resolve_strategy_windows' is not defined
```

### 自动化验证

```text
相关策略、回测和 API 测试：107 passed
离线全量测试：207 passed
完整测试：210 passed，3 warnings
python compileall：通过
前端 npm run build：通过
```

现有测试全部通过但两个直接复现仍失败，说明本次必须补充真实入口级回归测试，不能仅依赖当前测试总数判断完成。

### Diff 检查

```text
docs/reviews/2026-06-10-scan-window-unified-strategy-recheck.md:462:
new blank line at EOF.
```

---

## 11. 最终交付标准

满足以下全部条件后，才能判定扫描窗口与统一策略入口开发完成：

1. 三个受影响 API 均不再出现 `resolve_strategy_windows` 名称错误。
2. CLI 双数据源失败时正常退出并记录明确错误。
3. 所有窗口业务读取均通过 resolver 结果，不存在残留旁路。
4. 扫描与回测一致性测试使用真实策略引擎。
5. 一致性测试比较相同判断日期、相同股票窗口和相同市场数据。
6. 设计文档列出的八个核心策略字段完全一致。
7. 完整杯柄、VCP-only、突破排除和策略拒绝场景均被覆盖。
8. 全量测试、编译、前端构建和 `git diff --check` 全部通过。
9. 不修改本轮范围外的策略规则、数据源范围或前复权逻辑。
