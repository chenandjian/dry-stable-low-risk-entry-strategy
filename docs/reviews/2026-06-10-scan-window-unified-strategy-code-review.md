# 扫描窗口与统一策略入口代码审查报告

## 1. 检查范围

本次审查对照以下设计文档检查提交 `c2c6e9c`：

```text
docs/superpowers/specs/2026-06-10-scan-window-unified-strategy-design.md
```

基线与提交：

```text
base: f32c132
head: c2c6e9c
branch: worktree-multi-source-daily-kline
```

重点检查范围：

* `scan_window_days`、`backtest_window_days` 和 `min_listing_days` 的职责分离。
* 全市场扫描、任务重新分析、CLI 单股分析、单股回测、批量回测和候选详情的统一策略入口。
* 扫描与回测在相同配置、窗口、股票数据和市场数据下的一致性。
* 非法配置、数据不足、历史市场数据和未来数据边界。
* 配置页面和候选详情页面是否完成设计要求。
* 新增测试是否真实覆盖业务调用路径。

---

## 2. 总体结论

提交已经完成以下核心基础工作：

* 新增 `data.scan_window_days`。
* 新增共享 `select_strategy_window()`。
* 将突破排除规则收敛到 `CupHandleStrategyEngine`。
* 扫描和重新分析在调用策略前截取扫描窗口。
* CLI 单股分析和候选详情后端改用 `evaluate_at()`。
* 离线全量测试和前端构建通过。

但是，当前实现尚未达到设计文档要求的“扫描与回测真正一致”和“一次性完成全部 Phase”标准。

主要阻塞问题是：

1. 批量回测没有按 `backtest_window_days + 60` 请求数据，默认 CLI 回测很可能整批跳过。
2. 批量回测恰好拿到 `窗口 + 60` 日时一次策略判断都不会执行。
3. 单股回测没有传入历史市场指数数据，无法与扫描和批量回测得到一致结论。
4. 非法窗口配置仍可被保存和启动，`0` 值会被静默替换为 `250`。
5. 单股回测缺少固定 250 日兼容默认值，且前置数据范围未随回测窗口增长。
6. 拉取窗口仍受设计明确禁止的 `daily_kline_days` 控制，CLI 分析计算拉取天数后没有传给数据源。
7. 候选详情前端未展示后端新增的当前配置分析与提示。
8. 部分调用方仍重复实现候选资格判断，新增“一致性测试”没有覆盖真实扫描与回测路径。

因此，本提交当前不建议直接作为设计完成版本交付。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| BUG-001 | 批量回测未请求足够数据，默认回测可能全部跳过 | 高 | 批量回测正确性 | 是 |
| BUG-002 | 批量回测 `窗口 + 60` 边界被循环排除 | 高 | 回测完整性 | 是 |
| BUG-003 | 单股回测未传入历史市场指数数据 | 高 | 扫描/回测一致性 | 是 |
| BUG-004 | 后端窗口配置校验不完整，非法值可保存和启动 | 高 | 配置、扫描稳定性 | 是 |
| BUG-005 | 单股回测默认窗口和前置数据范围不符合设计 | 高 | 单股回测完整性 | 是 |
| BUG-006 | 拉取窗口仍受 `daily_kline_days` 控制，CLI 未按拉取配置请求数据 | 中 | 扫描/CLI 一致性 | 是 |
| BUG-007 | 候选详情前端未展示当前配置重算结果和提示 | 中 | 前端语义、用户判断 | 是 |
| BUG-008 | 调用方仍存在策略候选资格旁路判断 | 中 | 长期一致性 | 是 |
| BUG-009 | `--min-score` 报告过滤未在报告中明确标记 | 中 | 回测报告可解释性 | 是 |
| BUG-010 | 新增一致性测试未覆盖真实扫描和回测调用路径 | 中 | 回归保护 | 是 |

---

## 4. 详细问题分析

### BUG-001：批量回测未请求足够数据，默认回测可能全部跳过

#### 问题现象

`run_backtest()` 要求股票数据长度至少为：

```text
backtest_window_days + 60
```

但调用数据源时仍执行：

```python
data = fetch_fn(code)
```

没有向支持 `days` 参数的数据源传入所需长度。

CLI 使用的 `fetch_sina_daily` 默认只返回 250 日。默认 `backtest_window_days=250` 时，回测要求至少 310 日，因此股票会在策略判断前全部跳过。

#### 涉及模块

* `scanner/backtester.py:166-188`
* `main.py:236-242`
* `scanner/sina_source.py`

#### 证据

直接复现实验：

```text
配置 backtest_window_days=400
数据源函数默认 days=250
run_backtest() 实际调用记录：[("600000", 250)]
```

#### 触发条件

* 使用 CLI 批量回测。
* 使用默认返回 250 日的新浪数据源。
* `backtest_window_days >= 191`。

#### 影响

批量回测可能显示“测试了股票但未发现任何形态”，实际原因不是策略未命中，而是每只股票都因数据不足被静默跳过。

#### 修复建议

1. 在 `run_backtest()` 中计算：

```python
required_days = backtest_window_days + min_forward_days
```

2. 新增或复用兼容调用 helper：

```python
def _call_fetch_fn(fetch_fn, code: str, days: int):
    try:
        return fetch_fn(code, days=days)
    except TypeError:
        return fetch_fn(code)
```

更稳妥的实现应使用 `inspect.signature()` 判断是否支持 `days`，避免吞掉数据源函数内部真实 `TypeError`。

3. 对不支持 `days` 的注入函数保持兼容。
4. 数据不足时记录股票代码、需要天数和实际天数，不能静默跳过。

#### 验证方式

增加测试，传入支持 `days` 的 fake fetch：

```python
assert requested_days == [backtest_window_days + 60]
```

另增加默认 CLI 数据源调用测试，确认不会使用数据源默认 250 日。

---

### BUG-002：批量回测 `窗口 + 60` 边界被循环排除

#### 问题现象

当前代码：

```python
for i in range(backtest_window_days, n - min_forward_days):
```

当数据长度恰好为 `backtest_window_days + 60` 时：

```python
range(250, 250)
```

循环为空，一次策略判断都不会执行。

#### 涉及模块

* `scanner/backtester.py:188-201`

#### 证据

直接复现实验：

```text
数据长度：310
backtest_window_days：250
min_forward_days：60
evaluate_at 调用次数：0
```

#### 影响

即使 BUG-001 按设计精确拉取 `窗口 + 60` 日，批量回测仍然不会产生任何判断点。

#### 修复建议

将循环上界改为包含最后一个具备完整 60 日未来数据的判断点：

```python
for i in range(backtest_window_days, n - min_forward_days + 1):
```

同时确认：

```python
history_data = data[:i]
future_data = data[i:]
len(future_data) >= 60
```

#### 验证方式

增加边界测试：

* 数据长度 `window + 59`：不调用策略。
* 数据长度 `window + 60`：调用策略一次。
* 数据长度 `window + 61`：调用策略两次。

---

### BUG-003：单股回测未传入历史市场指数数据

#### 问题现象

批量回测按判断日期截取市场指数：

```python
market_window = [r for r in market_data_full if r["date"] <= detect_date]
evaluation = engine.evaluate_at(..., market_data=market_window)
```

单股回测调用：

```python
evaluation = engine.evaluate_at(eval_window, code=code, name=name)
```

没有传入 `market_data`。指定柄诊断同样没有传入市场数据。

#### 涉及模块

* `scanner/single_stock_backtest.py:370-409`
* `scanner/backtester.py:205-211`

#### 触发条件

市场环境分析参与干稳决策时。

#### 影响

相同股票、相同日期、相同窗口和相同配置下：

* 扫描可能使用市场指数。
* 批量回测使用截至判断日的市场指数。
* 单股回测完全不使用市场指数。

三条路径可能产生不同 `verdict_key`、风险提示、仓位建议和最终 `evaluation.passed`，违背本次设计的核心目标。

#### 修复建议

1. 为 `run_single_stock_cuphandle_backtest()` 增加可注入参数：

```python
market_data: list[dict] | None = None
```

2. 未注入时按配置的 `market_environment.index_symbol` 获取一次完整市场数据。
3. 每个判断日期使用：

```python
market_window = [r for r in market_data_full if r["date"] <= row["date"]]
```

4. 指定柄诊断使用截至 `handle_end_date` 的市场数据。
5. 测试必须断言未来市场数据没有传入策略引擎。

#### 验证方式

增加单股回测测试，注入包含判断日之后数据的市场指数，断言每次 `evaluate_at()` 收到的最大市场日期不晚于判断日期。

---

### BUG-004：后端窗口配置校验不完整，非法值可保存和启动

#### 问题现象

设计要求三个窗口字段必须是正整数且不低于 30，并要求：

```text
scan_window_days <= min_listing_days
```

当前问题：

* `PUT /api/config` 深度合并后直接写文件，没有后端校验。
* `scan_all()` 只检查 `scan_window_days > min_listing_days`。
* `0` 会被 `or 250` 静默替换为默认值。
* `20` 可以启动扫描。
* 字符串或浮点值会在比较或切片时产生非业务化异常。
* `/api/scan/start` 在后台线程内部才可能失败，不会在创建任务前明确拒绝请求。
* `re_evaluate_task()`、候选详情、CLI 分析和回测入口没有统一校验。

#### 涉及模块

* `scanner/engine.py:98-110`
* `server.py:168-209`
* `server.py:727-743`
* `scanner/strategy_engine.py:323-336`
* `web/src/pages/StrategyConfig.vue:336-348`

#### 证据

直接调用 `scan_all()`：

```text
scan_window_days=0：被接受
scan_window_days=20, min_listing_days=20：被接受
```

`select_strategy_window()`：

```text
window_days=2.5 -> TypeError: slice indices must be integers
window_days="50" -> TypeError: '<=' not supported ...
```

#### 影响

非法配置可能被永久写入 `config.yaml`，随后在后台扫描、详情接口或回测中以不同方式失败，用户无法获得明确配置错误。

#### 修复建议

新增一个无副作用的统一配置解析与校验函数，例如：

```python
@dataclass(frozen=True)
class StrategyWindows:
    min_listing_days: int
    scan_window_days: int
    backtest_window_days: int

def resolve_strategy_windows(config: dict) -> StrategyWindows:
    ...
```

统一规则：

* 缺失值使用固定默认值 250。
* 明确拒绝 `bool`、字符串、浮点数、`None` 之外的非法类型。
* 三个值必须是整数且 `>= 30`。
* `scan_window_days <= min_listing_days`。
* 不使用 `value or 250`，避免吞掉 `0`。

调用位置：

* `PUT /api/config` 写文件之前。
* `/api/scan/start` 创建任务和线程之前。
* `scan_all()` 和 `re_evaluate_task()` 作为内部防线。
* CLI 分析、批量回测、单股回测、候选详情。

接口非法时返回 HTTP 400 和明确字段错误，不要创建扫描任务。

#### 验证方式

增加参数化测试覆盖：

```text
缺失 -> 250
0 / -1 / 29 -> 拒绝
30 -> 接受
浮点 / 字符串 / bool -> 拒绝
scan > min_listing -> 拒绝
backtest > min_listing -> 接受
```

增加 API 测试，确认非法配置不会改写配置文件、不会创建扫描任务。

---

### BUG-005：单股回测默认窗口和前置数据范围不符合设计

#### 问题现象

当前单股回测缺少 `backtest_window_days` 时回退到：

```python
kline_days = daily_kline_days or min_listing_days
backtest_window = backtest_window_days or kline_days
```

这违反“旧配置固定回退 250，不得跟随 min_listing_days”的明确要求。

同时 `_derive_context_days()` 只根据杯体和柄部最大周期计算：

```python
max(120, cup_max + handle_max)
```

默认结果是 210 个自然日，通常不足 250 个交易日。即使 `backtest_window_days` 改为 500，前置上下文仍是 210 个自然日。

#### 涉及模块

* `scanner/single_stock_backtest.py:188-191`
* `scanner/single_stock_backtest.py:350-368`

#### 证据

直接实验：

```text
backtest_window_days=250 -> context_days=210
backtest_window_days=500 -> context_days=210
```

#### 影响

* 旧配置的单股回测窗口会随拉取配置变化。
* 用户指定回测开始日期后的早期交易日会被静默跳过，因为没有足够前置交易日。
* 增大回测窗口后，实际可评估区间进一步缩短，结果却没有明确提示。

#### 修复建议

1. 使用统一窗口解析函数，缺失 `backtest_window_days` 固定为 250。
2. 前置数据需求必须覆盖至少 `backtest_window_days` 个交易日。
3. 因接口使用日期范围拉取，可采用保守自然日换算：

```python
context_calendar_days = max(
    cup_max + handle_max,
    ceil(backtest_window_days * 1.6) + buffer_days,
)
```

或者先拉取较长范围，再验证开始日期前实际交易日数量，不足则继续补拉。
4. 在结果 `dataCoverage` 中明确实际最早可评估日期和因窗口不足跳过的判断日数量。

#### 验证方式

* 缺失 `backtest_window_days` 且 `min_listing_days=500` 时，策略窗口仍为 250。
* 配置 500 日窗口时，首个策略调用收到 500 日，而不是因 210 日上下文不足被长期跳过。
* 数据不足时不调用策略，并在结果中明确报告。

---

### BUG-006：拉取窗口仍受 `daily_kline_days` 控制，CLI 未按拉取配置请求数据

#### 问题现象

设计明确规定：

```text
liquidity.min_listing_days 是扫描日线拉取天数，不新增或继续使用第二个拉取配置。
```

当前扫描和重新分析仍优先读取未正式接入配置页面的 `data.daily_kline_days`：

```python
kline_days = data.daily_kline_days or liquidity.min_listing_days
```

现有测试 `test_scan_all_uses_daily_kline_days_config` 还在保护这一与设计冲突的行为。

CLI 单股分析虽然计算了 `kline_days`，但调用数据源时没有传入：

```python
data = fetch_sina_daily(code)
data = fetch_tencent_daily(code)
```

因此仍使用数据源默认 250 日。

#### 涉及模块

* `scanner/engine.py:98-101`
* `scanner/engine.py:476-489`
* `main.py:81-100`
* `tests/test_engine_fresh_fetch.py:853`

#### 影响

拉取范围仍有两个事实来源。旧隐藏参数可覆盖用户在页面设置的“日线拉取天数”，CLI 分析也可能拿不到配置要求的数据长度。

#### 修复建议

* 删除业务代码中对 `data.daily_kline_days` 的读取。
* 扫描和重新分析统一使用 `min_listing_days`。
* CLI 分析调用：

```python
fetch_sina_daily(code, days=min_listing_days)
fetch_tencent_daily(code, days=min_listing_days)
```

* 将 `test_scan_all_uses_daily_kline_days_config` 替换为：

```text
test_scan_all_fetches_min_listing_days
test_daily_kline_days_does_not_override_min_listing_days
```

---

### BUG-007：候选详情前端未展示当前配置重算结果和提示

#### 问题现象

后端已返回：

```json
{
  "analysis_notice": "...",
  "current_analysis": {}
}
```

但 `StockDetail.vue` 只把整个响应赋给 `stock`，页面没有读取或展示 `analysis_notice`、`current_analysis`。

#### 涉及模块

* `server.py:607-689`
* `web/src/pages/StockDetail.vue`

#### 影响

用户仍然看到混合语义：

* 顶层字段来自原扫描任务。
* `trade_plan` 已来自当前配置重新分析。
* 页面没有提示哪些内容是当前配置重算。

这可能让用户误以为详情页所有内容都来自原扫描时点。

#### 修复建议

在详情页增加独立“当前配置重新分析”区域：

* 显示 `analysis_notice`。
* 明确区分“原扫描结果”和“当前配置分析”。
* 展示 `current_analysis.passed`、评分、形态、干稳结论、通过规则和失败规则。
* 当前配置分析不可覆盖原扫描顶层字段。
* `trade_plan` 应明确放在当前配置分析区域，或增加标识说明它来自当前重算。

#### 验证方式

增加前端组件测试或至少 API 映射测试，确认提示和当前分析字段可见。

---

### BUG-008：调用方仍存在策略候选资格旁路判断

#### 问题现象

设计要求调用方只使用：

```python
evaluation.passed
```

当前仍存在：

```python
if evaluation.passed and dry_stable:
```

以及单股回测中的：

```python
has_pattern = ...
is_vcp = ...
if (not has_pattern and not is_vcp) or not evaluation.passed:
    continue
```

#### 涉及模块

* `scanner/engine.py:277`
* `scanner/engine.py:508`
* `scanner/single_stock_backtest.py:384-386`

#### 影响

当前这些条件大多与策略引擎返回契约重合，但它们仍是第二份候选资格规则。策略引擎未来支持新形态或调整返回结构时，调用方可能再次与引擎产生分歧。

#### 修复建议

* 扫描、重新分析、单股回测只用 `if not evaluation.passed: continue`。
* `evaluation.passed=True` 必须由策略引擎保证 `dry_stable` 和可序列化结果完整。
* 若担心契约损坏，使用明确异常或断言，不要用额外条件静默改变候选资格。

#### 验证方式

构造 `evaluation.passed=True` 的 fake evaluation，确认各调用方不会再检查形态类型、verdict 或其他候选规则。

---

### BUG-009：`--min-score` 报告过滤未在报告中明确标记

#### 问题现象

当前 `min_score` 在策略判断后过滤结果，符合“不参与候选资格”的方向，但：

* `BacktestReport` 没有记录是否启用了报告过滤。
* JSON 报告没有过滤条件。
* CLI 默认始终传入 `60`。
* `run_backtest()` 只要收到非 `None` 就记录废弃警告，而 CLI 只在非默认值时记录警告，行为不一致。

#### 涉及模块

* `main.py:229-242`
* `scanner/backtester.py:124-154`
* `scanner/backtester.py:215-218`
* `scanner/backtester.py:430` 附近报告序列化

#### 影响

报告中的总形态数和统计可能已经被分数过滤，但报告消费者无法判断，容易误解为完整策略结果。

#### 修复建议

* 明确区分：

```text
strategy_passed_results
reported_results
```

* 报告增加：

```json
"report_filter": {
  "min_score": 70,
  "applied": true
}
```

* `stocks_with_patterns` 应明确表示策略命中股票数还是报告过滤后股票数，建议同时提供两个字段。
* CLI 未显式设置 `--min-score` 时传 `None`；参数默认值改为 `None`。
* 仅当用户实际设置过滤时输出废弃警告。

#### 验证方式

增加两个策略通过、评分不同的结果，断言：

* 策略通过总数不受报告过滤影响。
* 展示结果可按过滤条件减少。
* 报告明确记录过滤条件。

---

### BUG-010：新增一致性测试未覆盖真实扫描和回测调用路径

#### 问题现象

当前所谓一致性测试实际上执行：

```python
engine1.evaluate_at(data)
engine2.evaluate_at(data)
```

这只能证明同一个函数调用两次结果一致，无法验证扫描和回测调用方是否准备了相同窗口和市场数据。

另一个测试只是对 `select_strategy_window(data, 100)` 调用两次。

因此 BUG-001、BUG-002、BUG-003、BUG-005 都没有被新增测试发现。

#### 涉及模块

* `tests/test_cuphandle_strategy_engine.py:371-415`
* `tests/test_backtester.py`
* `tests/test_single_stock_backtest.py`
* `tests/test_engine_fresh_fetch.py`

#### 修复建议

实现真正的路径一致性测试：

1. 准备固定股票 OHLC 和固定市场指数数据。
2. 设置 `scan_window_days == backtest_window_days`。
3. 通过扫描数据准备路径捕获传给 `evaluate_at()` 的股票窗口和市场窗口。
4. 通过批量或单股回测路径在同一判断日期捕获窗口。
5. 断言窗口日期、市场数据日期和核心结果完全一致。
6. 分别覆盖杯柄、VCP-only、突破排除和策略拒绝。

同时新增以下行为测试：

* 流动性过滤收到完整数据，策略收到最后 N 日。
* 数据不足扫描窗口时不调用策略并写入明确原因。
* 重新分析与首次扫描窗口一致。
* 批量回测请求 `backtest_window_days + 60`。
* 单股回测使用按日期截断的市场数据。
* CLI 分析按 `min_listing_days` 拉取。
* 候选详情 UI 展示当前分析提示。

---

## 5. 建议一次性修复顺序

为避免反复修改，建议按以下顺序执行：

1. 新增统一 `resolve_strategy_windows(config)`，完成类型、默认值和关系校验。
2. 所有入口接入统一窗口解析，彻底删除 `daily_kline_days` 业务读取。
3. 修复批量回测所需数据请求和 `窗口 + 60` 循环边界。
4. 修复单股回测前置数据范围，并接入按判断日截断的市场指数数据。
5. 删除扫描、重新分析和单股回测中的候选资格旁路判断。
6. 完成 `--min-score` 报告过滤元数据和 CLI 默认值语义。
7. 完成候选详情前端当前配置分析区域。
8. 替换伪一致性测试，补齐真实路径测试和 API 校验测试。
9. 运行所有后端测试、前端构建和关键直接复现实验。

---

## 6. 给修复 AI 的执行要求

请按照以下要求一次性修复：

1. 不修改杯柄、VCP、量干、价稳、风险收益等具体公式。
2. 不修改现有候选评分阈值和决策状态定义。
3. 不新增数据库表或字段。
4. 不重构数据源互斥锁和回退链。
5. 所有窗口值必须通过一个共享解析与校验函数读取。
6. 缺失 `scan_window_days` 和 `backtest_window_days` 时固定使用 250。
7. 禁止使用 `value or 250` 处理窗口配置。
8. 扫描拉取天数只能由 `liquidity.min_listing_days` 控制。
9. 所有业务入口只能依据 `evaluation.passed` 判断候选资格。
10. 回测不得将未来股票数据或未来市场指数数据传入策略引擎。
11. 批量回测必须请求足够覆盖策略窗口和 60 日未来收益的数据。
12. 修复后必须增加真实调用路径一致性测试，不能仅调用两次同一函数。
13. 候选详情必须保留原扫描字段，并独立展示当前配置重算结果。
14. 保持现有接口 URL 和原扫描顶层字段兼容。

---

## 7. 必须新增或修改的测试

### 配置测试

* 缺少窗口配置时固定默认 250。
* `0`、负数、29、浮点、字符串、布尔值均被拒绝。
* `scan_window_days > min_listing_days` 被拒绝。
* `backtest_window_days > min_listing_days` 被允许。
* `PUT /api/config` 非法时不写文件。
* `/api/scan/start` 非法时不创建任务。

### 扫描与重新分析测试

* 数据源收到 `min_listing_days`。
* `daily_kline_days` 不覆盖拉取天数。
* 流动性过滤收到完整数据。
* 策略引擎收到最新 `scan_window_days` 日。
* 数据不足时不调用策略并写入明确原因。
* 扫描和重新分析仅依据 `evaluation.passed`。

### 批量回测测试

* 数据源收到 `backtest_window_days + 60`。
* `window + 59` 不判断，`window + 60` 判断一次。
* 每次策略窗口长度恒定为 `backtest_window_days`。
* 市场指数不包含判断日之后的数据。
* 报告过滤不改变策略通过总数，并明确记录过滤条件。

### 单股回测测试

* 缺配置时固定使用 250，而不是 `min_listing_days`。
* 前置数据覆盖配置的回测窗口。
* 数据不足时不静默缩短窗口。
* 每个判断日只收到截至当日的股票和市场数据。
* 指定柄诊断使用相同股票窗口和市场窗口。

### 一致性测试

使用相同固定数据、配置、判断日期和市场数据，通过真实扫描与回测路径断言：

* `evaluation.passed`
* `result.score`
* `result.pattern_kind`
* `verdict_key`
* `key_pattern_type`
* `stop_loss`
* `entry_zone_low`
* `entry_zone_high`

### 前端测试

* 配置页非法窗口不能保存。
* 候选详情显示 `analysis_notice`。
* 原扫描结果和 `current_analysis` 明确分区。
* 当前分析缺失时页面正常降级。

---

## 8. 本次验证结果

执行结果：

```text
python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_yfinance_hist.py
183 passed, 1 warning

cd web && npm.cmd run build
passed

git diff --check f32c132..c2c6e9c
passed
```

直接复现结果：

```text
批量回测配置 backtest_window_days=400，数据源实际收到 days=250。
批量回测数据长度恰好 250+60 时，evaluate_at 调用次数为 0。
scan_window_days=0 可启动 scan_all。
scan_window_days=20 且 min_listing_days=20 可启动 scan_all。
单股回测 backtest_window_days=250 和 500 时，自动 context_days 均为 210。
select_strategy_window(2.5) 和 select_strategy_window("50") 抛出非业务化 TypeError。
前端源码不存在 current_analysis 或 analysis_notice 展示。
```

现有测试通过不能证明设计已完成，因为关键验收路径没有被覆盖。

---

## 9. 不建议修改的内容

* 不要修改杯柄和 VCP 检测公式。
* 不要修改量干 12 分制。
* 不要修改用户主动配置的策略阈值。
* 不要重新引入 mootdx 日线数据源。
* 不要调整数据源锁、重试和缓存合并机制。
* 不要新增任务配置快照，本次仍按设计明确记录为后续限制。
* 不要删除候选详情现有顶层原扫描字段。

---

## 10. 最终交付标准

修复完成后必须满足：

1. 所有窗口配置由共享函数解析和校验。
2. 扫描只按 `min_listing_days` 拉取数据。
3. 扫描策略只使用最新 `scan_window_days` 日。
4. 单股与批量回测只使用最新 `backtest_window_days` 日。
5. 批量回测能够获取足够的策略历史和 60 日未来数据。
6. 单股与批量回测都使用截至判断日的市场指数数据。
7. 所有调用方仅依据 `evaluation.passed` 判断候选。
8. 相同数据、配置、日期和市场数据下，真实扫描与回测路径结果一致。
9. 非法配置在保存和启动扫描前被明确拒绝。
10. 候选详情页面明确区分原扫描结果与当前配置分析。
11. 后端离线全量测试通过。
12. 前端构建通过。
13. 不存在未说明的策略旁路或静默数据不足跳过。
