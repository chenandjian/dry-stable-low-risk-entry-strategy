# 扫描窗口与统一策略入口修复复查报告

## 1. 检查范围

本次复查检查修复提交：

```text
base: c2c6e9c
head: 7da4c2a
branch: worktree-multi-source-daily-kline
```

复查依据：

```text
docs/reviews/2026-06-10-scan-window-unified-strategy-code-review.md
docs/superpowers/specs/2026-06-10-scan-window-unified-strategy-design.md
```

重点逐项复核上一轮 `BUG-001` 至 `BUG-010`，并检查修复提交是否引入新回归。

---

## 2. 总体结论

修复提交已经完成大部分核心问题：

* 批量回测会请求 `backtest_window_days + 60` 日数据。
* 批量回测 `窗口 + 60` 边界会执行一次判断。
* 单股回测会按判断日期截断并传入市场指数数据。
* 扫描与重新分析使用统一窗口解析，并移除候选旁路条件。
* 单股回测缺配置时使用固定 250 日窗口。
* `daily_kline_days` 不再覆盖扫描拉取天数。
* 候选详情页面展示当前配置重新分析结果。
* `--min-score` 默认值和报告过滤元数据已改进。

但是当前仍有一个高严重度功能回归和两个必须补齐的一致性问题：

1. CLI 单股分析 `main.py analyze` 必然触发 `UnboundLocalError`，功能完全不可用。
2. 统一窗口解析仍会静默接受 `min_listing_days=0`，且候选详情仍绕过统一解析。
3. `BUG-010` 所要求的真实扫描与回测业务路径一致性测试仍未实现。

因此本轮暂不能判定修复完成。

---

## 3. 原问题修复状态

| 原编号 | 复查结论 | 说明 |
| --- | --- | --- |
| BUG-001 | 已修复 | 批量回测通过 `_call_backtest_fetch()` 请求 `backtest_window_days + 60` |
| BUG-002 | 已修复 | 循环上界已增加 `+1`，边界测试通过 |
| BUG-003 | 已修复 | 单股回测和指定柄诊断均传入截至判断日期的市场数据 |
| BUG-004 | 部分修复 | 增加统一 resolver 和 API 校验，但 `min_listing_days=0` 仍被吞掉 |
| BUG-005 | 已修复 | 单股回测固定默认 250，并扩展前置自然日范围 |
| BUG-006 | 部分修复 | 扫描拉取来源已统一，但 CLI 分析因变量顺序错误完全不可用 |
| BUG-007 | 已修复 | 详情页展示 `analysis_notice` 和 `current_analysis` |
| BUG-008 | 已修复 | 扫描、重新分析、单股回测仅依据 `evaluation.passed` |
| BUG-009 | 已修复 | `--min-score` 默认 `None`，报告包含 `report_filter` |
| BUG-010 | 未修复 | 新测试仍未经过真实 `scan_all()` 与回测业务路径 |

---

## 4. 剩余问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| RECHECK-001 | CLI 单股分析在拉取数据前使用未赋值的 `kline_days` | 高 | CLI `analyze` 功能 | 是 |
| RECHECK-002 | 统一窗口校验仍会吞掉非法值，候选详情绕过 resolver | 中 | 配置正确性、入口一致性 | 是 |
| RECHECK-003 | “真实路径一致性测试”仍未经过真实业务路径 | 中 | 回归保护、设计验收 | 是 |
| RECHECK-004 | 提交级 `git diff --check` 未通过 | 低 | 交付质量 | 是 |

---

## 5. 详细问题分析

### RECHECK-001：CLI 单股分析在拉取数据前使用未赋值的 `kline_days`

#### 问题现象

`main.py::cmd_analyze()` 当前执行顺序：

```python
data = fetch_sina_daily(code, days=kline_days)
...
windows = resolve_strategy_windows(config)
kline_days = windows.min_listing_days
```

`kline_days` 在赋值前被使用，因此任何 CLI 单股分析都会立即失败。

#### 涉及模块

* `main.py:81-97`

#### 直接复现

执行 `cmd_analyze()` 得到：

```text
UnboundLocalError: cannot access local variable 'kline_days'
where it is not associated with a value
```

#### 影响

```bash
python main.py analyze 600000
```

完全不可用，无法进入数据源请求、策略窗口截取或统一策略引擎。

#### 根本原因

修复 BUG-006 时只把数据源调用改为传入 `kline_days`，但没有把窗口解析代码移动到拉取数据之前。

#### 修复方案

在导入完成后、任何数据源调用前解析窗口：

```python
from scanner.strategy_engine import (
    CupHandleStrategyEngine,
    resolve_strategy_windows,
    select_strategy_window,
)

windows = resolve_strategy_windows(config)
kline_days = windows.min_listing_days
scan_window_days = windows.scan_window_days

data = fetch_sina_daily(code, days=kline_days)
if data is None:
    data = fetch_tencent_daily(code, days=kline_days)
```

删除函数中后续重复导入和重复解析。

#### 必须增加的测试

新增 `tests/test_main.py` 或等价测试：

1. monkeypatch 新浪数据源并记录 `days`。
2. 配置 `min_listing_days=351`、`scan_window_days=250`。
3. 调用 `cmd_analyze()`。
4. 断言数据源收到 `days=351`。
5. 断言策略引擎收到最后 250 日。
6. 断言不会抛出 `UnboundLocalError`。
7. 覆盖新浪失败后腾讯备用源同样收到 351 日。

---

### RECHECK-002：统一窗口校验仍会吞掉非法值，候选详情绕过 resolver

#### 问题现象一：`min_listing_days=0` 被静默替换

`resolve_strategy_windows()` 当前读取：

```python
raw_min = liquidity_cfg.get("min_listing_days") or WINDOW_DEFAULT
```

因此 `0` 会被替换为 250，而不是按设计拒绝。

直接复现：

```text
输入：{"liquidity": {"min_listing_days": 0}}
输出：StrategyWindows(250, 250, 250)
```

这意味着：

* `PUT /api/config` 会接受并保存 `min_listing_days=0`。
* `/api/scan/start` 会接受该配置。
* 实际扫描却按 250 日运行。
* 配置文件值与运行行为不一致。

#### 问题现象二：整数型浮点仍被接受

当前 resolver 接受：

```text
50.0 -> 50
```

设计要求字段必须为正整数，不应隐式转换浮点值。

#### 问题现象三：候选详情仍绕过 resolver

`server.py::get_candidate()` 仍使用：

```python
scan_window_days = cfg.get("data", {}).get("scan_window_days") or 250
```

候选详情没有使用统一窗口解析函数。非法值、手工配置变更或旧配置异常时，详情入口与扫描入口的处理规则仍不一致。

#### 涉及模块

* `scanner/strategy_engine.py:39-59`
* `server.py:632-635`
* `server.py:736-754`

#### 修复方案

1. 不允许任何窗口字段使用 `or WINDOW_DEFAULT`：

```python
raw_min = liquidity_cfg.get("min_listing_days")
```

2. 严格要求 Python 整数：

```python
if type(value) is not int:
    raise ValueError(...)
```

不要接受 `bool` 或任意 `float`。

3. 候选详情使用：

```python
windows = resolve_strategy_windows(cfg)
strategy_data = select_strategy_window(ohlc, windows.scan_window_days)
```

4. 候选详情遇到非法配置时返回明确 HTTP 400，不能静默使用 250。

5. 搜索所有窗口读取，确保业务入口不再直接读取：

```text
scan_window_days
backtest_window_days
min_listing_days
```

允许配置页面显示字段，但后端业务入口统一使用 resolver。

#### 必须增加的测试

* `min_listing_days=0` 被拒绝。
* `min_listing_days=50.0` 被拒绝。
* `scan_window_days=50.0` 被拒绝。
* `backtest_window_days=50.0` 被拒绝。
* `PUT /api/config` 收到非法值时返回 400 且不写配置。
* `/api/scan/start` 非法时不创建任务。
* `/api/candidate/{code}` 使用 resolver，并在非法配置时返回明确错误。

---

### RECHECK-003：“真实路径一致性测试”仍未经过真实业务路径

#### 问题现象

新增测试名为：

```python
test_scan_vs_backtest_core_results_consistent
```

但测试实际只做了：

```python
scan_data = select_strategy_window(data, 100)
engine.evaluate_at(scan_data)
```

没有调用：

* `scanner.engine.scan_all()`
* `scanner.backtester.run_backtest()`
* `scanner.single_stock_backtest.run_single_stock_cuphandle_backtest()`

另一个“重新分析一致性”测试同样只是手工截窗后调用两次 `evaluate_at()`。

#### 影响

这类测试仍无法发现以下真实路径错误：

* CLI `kline_days` 未赋值。
* 扫描路径传错窗口或市场数据。
* 批量回测数据准备错误。
* 单股回测未传市场数据。
* 调用方重新加入候选旁路条件。

上一轮 BUG-010 的核心要求仍未满足。

#### 修复方案

至少增加一个真正经过扫描和批量回测路径的集成测试：

1. 准备固定股票历史数据：
   * 前 `N` 日为判断时点可见数据。
   * 后 60 日为回测未来收益数据。
2. 准备固定市场指数数据，包含判断日之后的数据。
3. 设置：

```text
scan_window_days == backtest_window_days == N
```

4. 扫描路径：
   * monkeypatch `_fetch_with_retry()` 返回前 `N` 日。
   * 调用真实 `scan_all()`。
   * 获取候选或捕获真实策略评价结果。
5. 批量回测路径：
   * fetch_fn 返回 `N + 60` 日。
   * 调用真实 `run_backtest()`。
   * 取同一判断日期结果。
6. 断言两条真实路径的核心字段一致：
   * `passed`
   * `score`
   * `pattern_kind`
   * `verdict_key`
   * `key_pattern_type`
   * `stop_loss`
   * `entry_zone_low`
   * `entry_zone_high`
7. 断言两条路径传给策略引擎的股票窗口日期完全一致。
8. 断言市场窗口不包含判断日期之后数据。

再增加单股回测真实路径测试，验证其股票窗口和市场窗口与批量回测一致。

#### 补充测试缺口

当前还缺少：

* `cmd_analyze()` 的直接测试。
* `PUT /api/config` 窗口校验 API 测试。
* 候选详情 resolver 测试。
* 单股回测市场数据截断测试。
* 候选详情 UI 行为测试。

---

### RECHECK-004：提交级 `git diff --check` 未通过

#### 问题现象

执行：

```bash
git diff --check c2c6e9c..7da4c2a
```

输出：

```text
docs/reviews/2026-06-10-scan-window-unified-strategy-code-review.md:852:
new blank line at EOF.
```

#### 修复方案

删除文档末尾多余空白行，并在最终提交前执行：

```bash
git diff --check c2c6e9c..HEAD
git diff --check
```

---

## 6. 建议一次性修复顺序

1. 先修复 `main.py::cmd_analyze()` 变量初始化顺序，并增加 CLI 测试。
2. 修复 `resolve_strategy_windows()` 对 `min_listing_days=0` 和所有浮点值的处理。
3. 将候选详情接入统一 resolver，并补齐 API 校验测试。
4. 使用真实 `scan_all()`、`run_backtest()` 和单股回测路径实现一致性集成测试。
5. 删除审查文档末尾多余空行。
6. 运行定向测试、离线全量测试、完整测试、前端构建和 diff check。

---

## 7. 给修复 AI 的执行要求

1. 不修改策略公式、评分阈值和决策状态。
2. 不修改数据源锁、重试和缓存机制。
3. 不重新引入 `daily_kline_days` 作为业务拉取配置。
4. 所有后端业务入口必须使用 `resolve_strategy_windows()`。
5. 所有窗口字段必须严格为 `int` 且不低于 30。
6. 不允许用 `or 250` 静默修复非法配置。
7. 修复 CLI 分析时确保主源和备用源都收到 `min_listing_days`。
8. 一致性测试必须经过真实业务入口，不能再次只调用 helper 或策略引擎。
9. 候选详情继续保留原扫描字段和当前配置重算字段的区分。
10. 不修改 BUG-001、BUG-002、BUG-003、BUG-005、BUG-007、BUG-008、BUG-009 已正确修复的行为。

---

## 8. 回归测试清单

修复完成后必须验证：

* CLI 单股分析正常运行。
* CLI 主数据源和备用数据源均按 `min_listing_days` 拉取。
* `min_listing_days=0`、浮点窗口和字符串窗口均被拒绝。
* 非法配置不能保存，不能启动扫描。
* 候选详情使用统一窗口解析。
* 批量回测请求 `backtest_window_days + 60`。
* `窗口 + 60` 日执行一次回测判断。
* 单股回测和指定柄诊断不使用未来市场数据。
* 扫描、重新分析、批量回测和单股回测仅依据 `evaluation.passed`。
* 真实扫描与回测路径在相同判断日期下核心结果一致。
* 候选详情显示当前配置分析区域。
* `git diff --check` 无错误。

---

## 9. 本次验证结果

```text
定向测试：
100 passed, 1 warning

离线全量测试：
200 passed, 1 warning

完整测试：
202 passed, 1 failed, 2 warnings

前端构建：
passed

compileall：
passed
```

完整测试中的失败：

```text
tests/test_akshare_hist.py::test_dongcai
```

失败原因为外部东财连接被远端关闭，不涉及本次修复逻辑。

直接复现：

```text
批量回测请求天数：310
批量回测窗口长度：250
窗口 + 60 边界执行次数：1
CLI analyze：UnboundLocalError
min_listing_days=0：被静默解析为 250
50.0 类型窗口：被接受并转换为 50
```

---

## 10. 最终交付标准

完成本轮剩余修复后，应满足：

1. CLI 单股分析可正常执行。
2. 所有窗口配置严格校验且所有后端入口处理一致。
3. 候选详情不再绕过统一窗口解析。
4. 真实扫描、批量回测和单股回测路径的一致性有自动化测试保护。
5. 离线全量测试和前端构建通过。
6. 完整测试仅允许明确的外部网络失败。
7. `git diff --check` 通过。
