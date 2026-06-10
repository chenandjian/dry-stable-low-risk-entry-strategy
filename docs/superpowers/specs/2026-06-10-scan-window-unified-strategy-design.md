# 开发方案文档：扫描策略窗口与统一策略入口优化

Date: 2026-06-10

## 1. 需求背景

当前系统已经存在两个不同概念，但扫描流程尚未彻底分离：

- `liquidity.min_listing_days`：日线数据拉取天数，同时用于上市天数检查和流动性过滤。
- `data.backtest_window_days`：回测时每个判断时点传入策略引擎的分析窗口。

扫描流程目前会将拉取并合并后的完整日线数据直接传入策略引擎。若日线拉取天数从 250 日提高到 500 日，扫描策略实际观察范围也会随之扩大，导致策略结果受到拉取范围和历史缓存长度影响。

此外，更新后的代码虽然已引入 `CupHandleStrategyEngine.evaluate_at()`，但部分调用方仍在策略引擎外重复判断评分、决策状态和突破状态；批量历史回测、CLI 单股分析和候选详情分析也存在窗口或调用入口不一致的问题。因此，目前还不能保证扫描与回测真正使用同一份策略代码并产生一致结果。

本次优化需要同时解决：

- 日线拉取窗口与扫描策略计算窗口分离。
- 扫描、重新分析、单股回测、批量回测、CLI 分析和候选详情统一使用一个策略判断入口。
- 相同配置、相同判断日期、相同股票和市场数据下，扫描与回测得到一致策略结论。

### 当前问题

- 调大 `min_listing_days` 会间接扩大扫描策略计算范围。
- SQLite 缓存历史不断增长时，扫描结果可能发生非预期变化。
- 扫描在 `evaluation.passed` 之外再次实现候选判断。
- 批量历史回测没有按照 `backtest_window_days` 截取固定窗口。
- 批量历史回测存在额外 `min_score` 候选门槛。
- CLI 单股分析和候选详情分析绕过统一策略引擎。

### 用户痛点

- 无法独立控制“拉多少日线”和“策略分析多少日线”。
- 扫描结果与回测结果可能不一致，降低回测可信度。
- 策略规则散落在多个调用方，后续修改容易遗漏。

### 业务目标

- 拉取足够长的历史数据支持流动性过滤和数据完整性检查。
- 使用固定扫描窗口保证策略结果稳定、可复现。
- 确保线上扫描和历史回测验证的是同一套策略。

### 预期效果

当配置为：

```yaml
liquidity:
  min_listing_days: 500

data:
  scan_window_days: 200
  backtest_window_days: 200
```

系统拉取最近 500 个交易日，使用完整数据执行上市天数检查和流动性过滤，但扫描策略只分析最新 200 个交易日。回测在每个历史判断时点同样只分析该时点以前最近 200 个交易日。

---

## 2. 需求目标

### 2.1 必须实现

- 新增配置项 `data.scan_window_days`，默认值为 `250`。
- `liquidity.min_listing_days` 继续作为扫描日线拉取天数。
- 上市天数检查和流动性过滤使用拉取后的完整日线数据。
- 扫描策略计算只使用最新 `scan_window_days` 个交易日。
- 扫描数据不足 `scan_window_days` 时跳过策略计算并记录明确原因。
- `scan_all()` 与 `reanalyze_task()` 使用相同扫描窗口规则。
- 单股回测与批量历史回测统一使用 `backtest_window_days`。
- 所有业务入口统一调用 `CupHandleStrategyEngine.evaluate_at()`。
- 将候选资格判断完整收敛到统一策略引擎。
- 调用方只允许准备数据窗口、调用策略引擎和处理结果，不允许重复实现策略规则。
- 增加扫描与回测一致性测试。

### 2.2 可选增强

- 在扫描日志中记录实际拉取数据长度和实际策略窗口长度。
- 在扫描任务详情中展示本次使用的 `scan_window_days`。
- 后续持久化任务级配置快照，用于配置变更后的历史结果精确复算。

### 2.3 不做范围

- 不修改杯柄、VCP、成交量、价稳、风险收益等具体计算公式。
- 不修改现有候选评分阈值和决策状态定义。
- 不重构数据源链和数据库缓存结构。
- 不新增数据库表或字段。
- 不修改前端整体风格。
- 不把流动性过滤改为使用扫描策略窗口。
- 不允许回测复制一套独立策略实现。

---

## 3. 默认假设

1. 实施目标代码以已包含 `scanner/strategy_engine.py` 和 `scanner/single_stock_backtest.py` 的更新版本为基础。
2. `liquidity.min_listing_days` 是扫描日线拉取天数，不新增 `daily_kline_days` 作为第二个拉取配置。
3. `scan_window_days` 和 `backtest_window_days` 都表示交易日数量。
4. 策略窗口包含判断时点当天。
5. 日线数据按日期升序排列。
6. 扫描与回测的一致性要求建立在相同配置、相同 OHLC、相同市场指数数据和相同判断日期基础上。
7. 缓存可以保留超过 `min_listing_days` 的历史数据，但策略调用前必须按配置截取窗口。
8. 为兼容旧配置，缺少 `scan_window_days` 时回退到 `min_listing_days`；缺少 `backtest_window_days` 时同样回退到 `min_listing_days`。

---

## 4. 产品设计方案

### 4.1 用户使用流程

1. 用户进入策略配置页面。
2. 用户设置“日线拉取天数”，例如 500 日。
3. 用户设置“扫描分析天数”，例如 200 日。
4. 用户设置“回测分析天数”，例如 200 日。
5. 用户保存配置并启动扫描。
6. 系统拉取 500 日数据并执行上市天数检查和流动性过滤。
7. 流动性过滤通过后，系统截取最新 200 日执行统一策略判断。
8. 用户执行回测时，系统在每个历史判断日期截取此前最新 200 日并调用同一策略入口。

### 4.2 页面展示要求

策略配置页“基础参数”区域展示：

- 日线拉取天数：绑定 `liquidity.min_listing_days`。
- 扫描分析天数：绑定 `data.scan_window_days`。
- 回测分析天数：绑定 `data.backtest_window_days`。

字段说明必须明确：

- 日线拉取天数用于拉取、上市天数检查和流动性过滤。
- 扫描分析天数仅用于扫描策略计算。
- 回测分析天数仅用于回测每个判断时点的策略计算。

### 4.3 交互规则

- 三个字段必须为正整数且不低于 30。
- `scan_window_days` 不得大于 `min_listing_days`。
- `backtest_window_days` 可以大于 `min_listing_days`，因为回测可能根据用户日期范围拉取更长历史；但回测数据不足时不得静默缩短策略窗口。
- 保存配置后，下次扫描和回测生效。
- 运行中的扫描任务继续使用启动时已加载的配置对象。
- 若扫描数据不足 `scan_window_days`，该股票跳过策略计算并显示明确原因。

---

## 5. 技术架构方案

### 5.1 总体架构

涉及模块：

- `config.yaml`：新增扫描分析窗口配置。
- `web/src/pages/StrategyConfig.vue`：新增扫描分析天数输入和校验。
- `scanner/strategy_engine.py`：唯一策略判断入口和共享窗口辅助函数。
- `scanner/engine.py`：扫描、任务重新分析的数据准备与策略调用。
- `scanner/single_stock_backtest.py`：单股回测窗口准备。
- `scanner/backtester.py`：批量历史回测窗口准备。
- `main.py`：CLI 单股分析统一接入策略引擎。
- `server.py`：候选详情重新分析统一接入策略引擎。
- 测试模块：验证窗口分离和策略一致性。

### 5.2 数据流设计

扫描数据流：

1. 从 `liquidity.min_listing_days` 读取日线拉取天数。
2. 数据源拉取指定交易日数量。
3. fresh 数据与 SQLite 缓存合并并保存。
4. 使用完整可用数据执行上市天数检查。
5. 使用完整可用数据执行流动性过滤。
6. 检查数据长度是否满足 `scan_window_days`。
7. 截取最新 `scan_window_days` 日。
8. 调用 `CupHandleStrategyEngine.evaluate_at()`。
9. 仅根据 `evaluation.passed` 决定是否进入候选结果。

回测数据流：

1. 获取覆盖回测区间和前置历史的数据。
2. 对每个历史判断日期只取该日期及以前的数据。
3. 截取此前最新 `backtest_window_days` 日。
4. 截取截至该判断日期的市场指数数据。
5. 调用同一个 `CupHandleStrategyEngine.evaluate_at()`。
6. 仅根据 `evaluation.passed` 判断该日是否产生策略候选。
7. 策略判断完成后，回测模块再计算未来收益，不得将未来数据传入策略引擎。

### 5.3 统一策略入口设计

唯一策略入口：

```python
evaluation = CupHandleStrategyEngine(config).evaluate_at(
    strategy_data,
    code=code,
    name=name,
    market_data=market_data_until_date,
)
```

`evaluate_at()` 必须统一负责：

- 杯柄识别。
- VCP-only 判断。
- 高级评分。
- 干稳低吸分析。
- 候选评分门槛。
- 主导形态类型校验。
- `verdict_key` 候选状态校验。
- 突破状态排除规则。
- 最终候选结论 `evaluation.passed`。

调用方不得再实现以下判断：

```python
result.score >= threshold
verdict_key in CANDIDATE_KEYS
verdict not in REJECT_KEYS
not result.is_breakout
```

### 5.4 共享窗口设计

在 `scanner/strategy_engine.py` 提供无业务副作用的共享函数：

```python
def select_strategy_window(data: list[dict], window_days: int) -> list[dict]:
    if window_days <= 0:
        raise ValueError("window_days must be a positive integer")
    return data[-window_days:]
```

该函数只负责窗口截取，不读取场景配置。扫描和回测调用方分别传入自己的窗口天数。

### 5.5 状态设计

不新增扫描任务状态。数据不足时沿用 `skipped`：

```text
status = skipped
status_reason = 策略计算数据不足：需要 200 日，实际 150 日
```

状态优先级：

1. 数据源全部失败：`failed`。
2. 数据长度不足 `min_listing_days`：`skipped / 上市天数不足`。
3. 流动性过滤未通过：`skipped / 流动性过滤未通过`。
4. 数据不足 `scan_window_days`：`skipped / 策略计算数据不足`。
5. 策略通过：`candidate`。
6. 策略未通过：`scanned`。

---

## 6. 数据库设计方案

### 6.1 新增表

无。

### 6.2 修改表

无。

### 6.3 索引设计

无新增索引。

### 6.4 数据兼容方案

- 继续使用现有 `daily_ohlc` 缓存结构。
- 缓存可以保留超过拉取和策略窗口的历史数据。
- 旧扫描任务无需迁移。
- 重新分析旧任务时使用当前配置的 `scan_window_days`。
- 本次不持久化任务配置快照，因此配置变化后重新分析结果可能变化；该限制必须在文档中明确。

---

## 7. 接口设计方案

### 7.1 新增接口

无。

### 7.2 修改接口

现有配置接口保持路径不变：

```http
GET /api/config
PUT /api/config
```

配置响应和更新请求增加：

```json
{
  "data": {
    "scan_window_days": 200,
    "backtest_window_days": 200
  },
  "liquidity": {
    "min_listing_days": 500
  }
}
```

### 7.3 接口兼容要求

- 旧配置不存在 `scan_window_days` 时，后端回退到 `min_listing_days`。
- 旧配置不存在 `backtest_window_days` 时，后端回退到 `min_listing_days`。
- 不修改扫描启动、扫描状态、候选列表和回测接口的 URL。
- 不改变现有候选响应结构。

---

## 8. 可以实施的代码方案

### 8.1 后端代码方案

#### `config.yaml`

在 `data` 段新增：

```yaml
data:
  scan_window_days: 250
  backtest_window_days: 250
```

保留：

```yaml
liquidity:
  min_listing_days: 250
```

不得新增第二个日线拉取天数字段。

#### `scanner/strategy_engine.py`

需要实现：

- 新增 `select_strategy_window()`。
- 将 `not result.is_breakout` 纳入 `_candidate_rules()`。
- 保证 `evaluation.passed` 是最终候选资格唯一结论。
- 保留 `CANDIDATE_KEYS`、`REJECT_KEYS` 作为策略引擎内部规则，不允许业务调用方重复使用它们判断候选。

核心逻辑：

```text
CupHandleStrategyEngine.evaluate_at()
1. 检测杯柄；未命中时继续分析 VCP。
2. 执行高级评分和干稳低吸分析。
3. 在策略引擎内部执行所有候选准入规则。
4. 返回 StrategyEvaluation。
5. passed=True 表示该判断时点应进入候选。
```

#### `scanner/engine.py`

`scan_all()`：

```text
1. 从 liquidity.min_listing_days 读取 kline_days。
2. 数据源调用必须传入 kline_days。
3. 使用完整 data 执行上市天数检查和流动性过滤。
4. 读取 scan_window_days，缺失时回退 min_listing_days。
5. 数据不足 scan_window_days 时记录 skipped。
6. strategy_data = select_strategy_window(data, scan_window_days)。
7. 调用 strategy_engine.evaluate_at(strategy_data, ...)。
8. 仅使用 evaluation.passed 决定 candidate/scanned。
```

删除扫描层重复候选判断，不再直接使用 `CANDIDATE_KEYS` 和 `REJECT_KEYS` 判断候选。

`reanalyze_task()`：

- 从缓存读取足够覆盖 `min_listing_days` 的完整数据。
- 完整数据执行流动性过滤。
- 按 `scan_window_days` 截取策略数据。
- 仅根据 `evaluation.passed` 重建候选。

#### `scanner/single_stock_backtest.py`

- 保留逐日无未来数据的窗口构建方式。
- 使用共享 `select_strategy_window(window, backtest_window_days)`。
- 数据不足 `backtest_window_days` 时不调用策略引擎。
- 仅根据 `evaluation.passed` 记录策略结果。
- 指定柄诊断也应使用截至柄结束日的最后 `backtest_window_days` 日，避免诊断与自动回测窗口不一致。

#### `scanner/backtester.py`

- 读取 `backtest_window_days`，缺失时回退 `min_listing_days`。
- 批量回测拉取的数据量必须至少覆盖 `backtest_window_days + 最大未来收益观察天数`，不能继续依赖数据源默认 250 日。
- 每个判断时点将 `data[:i]` 截取为最后 `backtest_window_days` 日。
- 仅根据 `evaluation.passed` 记录策略结果。
- 删除 `run_backtest()` 中作为候选资格门槛的 `min_score` 参数和判断。
- 删除或废弃 CLI `--min-score` 参数，避免调用方继续改变统一策略结论。
- 如未来需要按分数筛选报告，必须在策略结果生成后新增名称明确的报告过滤功能，不得复用策略候选概念。
- 未来收益、命中率和止损统计继续由回测模块计算，不放入策略引擎。

#### `main.py`

CLI 单股分析：

- 使用 `min_listing_days` 拉取数据。
- 使用 `scan_window_days` 截取分析窗口。
- 调用 `CupHandleStrategyEngine.evaluate_at()`。
- 删除直接编排 `detect_cup_handle()`、`score_cup_handle_advanced()` 和 `analyze_dry_stable()` 的逻辑。

#### `server.py`

候选详情重新分析：

- 使用 `scan_window_days` 截取 OHLC。
- 调用 `CupHandleStrategyEngine.evaluate_at()` 获取统一分析结果。
- 不直接调用 `analyze_dry_stable()` 重新编排策略。
- 如果当前配置与扫描时配置不同，详情属于“按当前配置重新分析”；本次不新增历史配置快照。

#### 并发控制

- 保持现有数据源互斥锁和扫描线程模型不变。
- `CupHandleStrategyEngine` 在扫描开始时按现有方式创建一次，供工作线程只读调用。
- 窗口截取返回新列表，不修改共享缓存数据。

#### 缓存策略

- fresh 数据成功后继续与 SQLite 缓存合并。
- 流动性过滤使用合并后的完整可用数据。
- 策略计算前必须截取固定窗口，不能将缓存完整历史直接传入策略引擎。
- 所有数据源失败时继续禁止使用旧缓存生成新扫描结果。

### 8.2 前端代码方案

#### 页面状态

在 `StrategyConfig.vue` 的默认 `data` 状态中增加：

```js
data: {
  scan_window_days: 250,
  backtest_window_days: 250,
}
```

#### 核心逻辑

基础参数区域新增“扫描分析天数”输入框：

```text
字段：config.data.scan_window_days
默认：250
最小：30
步长：50
说明：扫描时传入统一策略引擎的最近交易日数量
```

保存校验：

```text
1. min_listing_days >= 30。
2. scan_window_days >= 30。
3. backtest_window_days >= 30。
4. scan_window_days <= min_listing_days。
```

不修改其他策略配置 UI。

---

## 9. 日志与异常处理方案

### 9.1 必须记录的日志

- 扫描启动时记录：
  - `min_listing_days`
  - `scan_window_days`
  - `backtest_window_days`
- 单只股票策略数据不足时记录股票代码、需要天数和实际天数。
- 配置值非法或无法转换为正整数时记录错误并停止启动扫描。
- 批量回测启动时记录实际使用的 `backtest_window_days`。

### 9.2 异常处理

- `scan_window_days <= 0`：拒绝启动扫描并返回明确配置错误。
- `scan_window_days > min_listing_days`：拒绝保存前端配置；后端仍需防御性校验。
- 单只股票数据不足 `scan_window_days`：跳过该股票，不中断扫描。
- 单只股票策略计算异常：保持现有单只失败不中断整体任务规则。
- 回测判断时点数据不足 `backtest_window_days`：跳过该判断时点，不使用缩短窗口计算。
- 市场指数数据仍需按判断日期截取，禁止未来数据泄漏。

---

## 10. 测试方案

### 10.1 单元测试

`scanner/strategy_engine.py`：

- `select_strategy_window()` 返回最后 N 日。
- 输入数据等于 N 日时原样返回。
- 输入数据少于 N 日时返回现有数据，由调用方负责不足判断。
- 非正整数窗口抛出明确错误。
- `is_breakout=True` 时 `evaluation.passed=False`。
- 评分、主导形态、决策状态和突破排除均只在策略引擎中决定。

`scanner/engine.py`：

- 数据源收到的 `days` 等于 `min_listing_days`。
- 流动性过滤收到完整拉取数据。
- 策略引擎收到的数据长度等于 `scan_window_days`。
- 策略引擎收到最新数据而不是最早数据。
- 数据不足 `scan_window_days` 时不调用策略引擎。
- 数据不足时记录正确 `status_reason`。
- `evaluation.passed=True` 时进入候选。
- `evaluation.passed=False` 时不进入候选。
- 扫描层不再额外拒绝策略引擎已通过的结果。

`reanalyze_task()`：

- 流动性过滤使用完整缓存数据。
- 策略引擎使用 `scan_window_days`。
- 重新分析与首次扫描使用相同数据窗口时结果一致。

`scanner/single_stock_backtest.py`：

- 每个判断时点只传入最后 `backtest_window_days` 日。
- 指定柄诊断使用相同回测窗口。
- 数据不足时不使用缩短窗口执行策略。

`scanner/backtester.py`：

- 批量回测使用 `backtest_window_days`。
- 批量回测拉取数据长度满足 `backtest_window_days + 60`。
- 批量回测不再通过额外 `min_score` 改变候选资格，相关参数已移除或废弃。
- 市场指数数据只包含判断日期及以前数据。

### 10.2 接口测试

- `GET /api/config` 返回 `scan_window_days`。
- `PUT /api/config` 可保存 `scan_window_days`。
- 缺少 `scan_window_days` 的旧配置仍可启动扫描。
- 非法窗口配置返回明确错误，不启动扫描。
- 扫描任务状态接口可展示“策略计算数据不足”原因。

### 10.3 集成测试

扫描与回测一致性测试：

1. 准备固定股票 OHLC 和固定市场指数数据。
2. 设置 `scan_window_days == backtest_window_days`。
3. 使用相同判断日期分别运行扫描策略路径和回测策略路径。
4. 断言以下字段完全一致：
   - `evaluation.passed`
   - `result.score`
   - `result.pattern_kind`
   - `dry_stable.decision.verdict_key`
   - `dry_stable.pattern_score.key_pattern_type`
   - `dry_stable.key_prices.stop_loss`
   - `dry_stable.key_prices.entry_zone_low`
   - `dry_stable.key_prices.entry_zone_high`
5. 分别覆盖完整杯柄、VCP-only、突破排除和策略拒绝场景。

### 10.4 前端测试

- 配置页显示“扫描分析天数”。
- 保存后重新加载仍显示正确值。
- `scan_window_days > min_listing_days` 时显示校验错误。
- `scan_window_days < 30` 时显示校验错误。
- 修改扫描窗口不会修改回测窗口。
- 修改回测窗口不会修改扫描窗口。

### 10.5 回归测试

必须验证：

- 日线数据源互斥锁和回退链不变。
- 流动性过滤仍使用完整拉取数据。
- 扫描恢复和失败重试使用相同窗口规则。
- 原有候选字段和前端结果展示不变。
- 回测不使用未来股票数据和未来指数数据。
- 扫描与回测不存在第二份候选准入规则。
- 全量后端测试通过。
- 前端构建通过。

验证命令：

```bash
python -m pytest tests/ -v
cd web && npm run build
```

---

## 11. 验收标准

1. `min_listing_days` 明确且唯一地控制扫描日线拉取天数。
2. 上市天数检查和流动性过滤使用完整拉取数据。
3. 扫描策略只使用最新 `scan_window_days` 日。
4. 单股与批量回测都只使用每个判断时点以前最新 `backtest_window_days` 日。
5. 所有业务入口通过 `CupHandleStrategyEngine.evaluate_at()` 执行策略判断。
6. 所有候选资格规则只存在于统一策略引擎。
7. 调用方仅根据 `evaluation.passed` 判断策略候选。
8. 相同窗口、配置、数据和判断日期下，扫描与回测核心结果完全一致。
9. 数据不足时有明确跳过原因，不静默使用缩短窗口。
10. 不破坏数据源回退、缓存、任务恢复和现有前端展示。
11. 所有新增和回归测试通过。

---

## 12. 给 Claude Code / Codex 的执行指令

请严格按照本文档执行开发。

执行要求：

1. 先确认目标分支已经包含 `scanner/strategy_engine.py` 和 `scanner/single_stock_backtest.py`；若不存在，先整合现有更新工作树中的统一策略引擎实现。
2. 先搜索所有 `detect_cup_handle()`、`score_cup_handle_advanced()`、`analyze_dry_stable()` 和 `evaluate_at()` 调用点。
3. 业务入口不得直接编排底层策略模块，只允许统一策略引擎内部调用。
4. 调用方不得重复评分门槛、决策状态、突破状态或形态类型候选判断。
5. 使用项目现有配置 API、测试框架和代码风格。
6. 不修改无关策略公式。
7. 不新增数据库 schema。
8. 每完成一个入口改造，增加对应窗口和一致性测试。
9. 对扫描和回测使用同一固定数据集做对照验证。
10. 如发现本文档与目标代码结构冲突，以“只有一个策略判断入口”和“窗口职责分离”为不可变目标，采用最小改动适配现有代码。

---

## 13. 最终交付物

开发完成后需要交付：

1. 修改文件清单。
2. `scan_window_days` 配置及兼容规则说明。
3. 日线拉取、流动性过滤、扫描策略和回测策略的数据窗口说明。
4. 已移除的重复策略判断清单。
5. 统一策略入口调用清单。
6. 扫描与回测一致性测试结果。
7. 后端全量测试结果。
8. 前端构建结果。
9. 是否存在仍绕过统一策略引擎的入口。
10. 是否存在需要后续实现的任务配置快照问题。
