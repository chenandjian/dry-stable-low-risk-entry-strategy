# 开发方案文档：策略2 Phase 2 回测实验与策略优化评估

## 1. 需求背景

### 1.1 当前问题

策略2 Phase 1 已完成回测可信度修复，当前系统已经具备：

- 本地数据库短线回测。
- 原始信号与合并机会追溯。
- 下一交易日开盘执行模型。
- 任务状态、版本、可信度和分页展示。
- 可信基线所需的版本标识与完整性校验。

但 Phase 1 的目标是“让回测可信”，不是“直接修改策略”。接下来需要在可信回测基础上验证策略2是否可以通过参数和交易执行规则提升短线表现。

当前仍存在几个产品和策略层面的痛点：

- 旧任务曾显示量干分较高的机会表现更好，但旧任务存在合并错误，不能直接作为调参依据。
- 总分、量干分、价稳分之间的关系尚未验证，不能只凭总分决定候选质量。
- 策略2当前发现的是“量干价稳观察机会”，并不等同于当日立即买入信号。
- 部分机会可能属于趋势延续，部分可能属于下跌后的反弹修复，两类机会混合统计会掩盖真实差异。
- 市场环境会显著影响短线胜率，现有页面缺少市场阶段分组对比。
- 用户需要在不影响正式扫描的前提下，对多个优化方向做可重复实验。

### 1.2 用户痛点

- 不知道策略2是否应该提高量干门槛。
- 不知道 5 日、10 日短线退出哪个更适合当前策略。
- 不知道是否需要等待突破、站上均线等启动确认。
- 不知道“趋势延续”和“反转修复”哪类机会更值得跟踪。
- 不希望实验代码污染正式扫描逻辑。
- 不希望 AI 根据单次旧回测结果直接改正式配置。

### 1.3 业务目标

Phase 2 的核心目标是建设“策略2回测实验层”，让用户能够在同一数据范围、同一策略引擎、同一执行模型下，对不同实验参数进行公平对比。

本期必须强调：

- Phase 2 是实验评估，不是正式策略升级。
- 实验关闭时，结果必须等同 Phase 1 可信基线。
- 实验任务不得自动改写 `config.yaml` 中的正式策略参数。
- 实验结论必须基于新的 `TRUSTED_BASELINE` 任务，而不是修复前旧任务。

### 1.4 预期效果

- 用户可以创建基线任务和实验任务。
- 用户可以选择量干分门槛、分层评分门槛、时间退出、启动确认等实验条件。
- 系统保存实验快照，历史任务不受后续配置修改影响。
- 前端明确标识实验任务，不把实验结果误认为正式扫描结果。
- 用户可以查看实验任务相对基线的机会数、入场数、胜率、收益、止损率、超额收益变化。
- 系统按月份、机会类型、市场环境、分数分层展示实验统计。
- AI 开发工具可以按本文档实施，不需要再次猜测业务边界。

---

## 2. 需求目标

### 2.1 必须实现

- 新增策略2回测实验配置，不直接修改正式策略2扫描逻辑。
- 回测启动接口支持 `experiment` 参数。
- 回测任务保存 `experiment_snapshot`。
- 实验关闭时，回测结果必须与 Phase 1 基线完全一致。
- 支持最低量干分实验：`minimum_volume_dry_score`。
- 支持分层评分门槛实验：
  - `minimum_total_score`
  - `minimum_volume_dry_score`
  - `minimum_price_stable_score`
- 支持时间退出实验：`time_exit_days`。
- 支持启动确认实验：
  - `NONE`
  - `BREAK_RECENT_5D_HIGH`
  - `CLOSE_ABOVE_MA20`
  - `BREAK_HIGH_WITH_MODERATE_VOLUME`
- 支持机会类型标签：
  - `CONTINUATION`
  - `REVERSAL`
  - `NEUTRAL`
- 支持市场环境统计，不作为硬过滤。
- 支持实验任务与基线任务对比。
- 前端展示实验模式、实验参数、实验徽标和“不影响正式扫描”的提示。
- 所有实验任务必须可追溯、可复现、可比较。

### 2.2 可选增强

- 参数网格批量实验。
- 多实验任务排行榜。
- 实验结果导出 CSV。
- 行业、板块和市值分组。
- 手续费、印花税、滑点配置。
- 组合资金曲线和最大回撤。

可选增强不作为本期验收阻塞项。

### 2.3 不做范围

- 不修改策略2正式扫描候选规则。
- 不直接提高正式 `config.yaml` 中策略2门槛。
- 不复制 `ExtremeDryStableStrategyEngine.evaluate_at()` 的策略判断逻辑。
- 不新增第二份策略2正式代码。
- 不修改策略1。
- 不请求百度、新浪、腾讯、yfinance、AKShare 或任何外部数据源。
- 不把实验任务标记为 `TRUSTED_BASELINE`。
- 不基于修复前旧任务自动得出正式策略结论。
- 不在本期实现自动交易、资金管理或仓位系统。

说明：

- Phase 2 本身只建设实验能力。
- 用户已授权后续在实验结果充分时调整策略2正式规则，但该动作必须作为“实验结果驱动的正式策略升级”单独执行。
- 正式策略升级前必须先产出策略升级建议，升级后必须交付“优化后的策略文档”，明确所有最终参数名和参数值。

---

## 3. 默认假设

1. Phase 1 代码已经通过功能验收，但正式实验结论仍需要新的全市场可信基线任务。
2. 新可信基线任务应满足：
   - `status = completed`
   - `credibility_status = TRUSTED_BASELINE`
   - `backtest_engine_version = phase1-v3`
   - `strategy_engine_version = strategy2-v2`
   - `data_revision_version = daily-ohlc-v2`
3. Phase 2 实验任务的可信度状态建议使用 `EXPERIMENTAL`，不使用 `TRUSTED_BASELINE`。
4. 实验任务必须复用策略2唯一判断入口 `ExtremeDryStableStrategyEngine.evaluate_at()`。
5. 实验过滤只允许作用于策略引擎返回结果之后，或交易执行层，不允许提前改变策略引擎内部判断。
6. 当前策略2至少 250 日数据即可判断，最多使用 350 日，Phase 2 不改变该窗口规则。
7. 回测仍只读取本地 `stock_pool` 和 `daily_ohlc`。
8. 实验对比必须使用相同股票范围、相同请求区间、相同数据版本、相同执行模型。
9. 如果没有可比基线任务，系统可以创建实验任务，但页面必须提示“暂无可信基线对比”。
10. 所有实验参数必须保存到任务快照；历史任务查看时不能读取当前实时配置解释旧结果。

---

## 4. 产品设计方案

### 4.1 用户使用流程

1. 用户进入“策略2回测”页面。
2. 用户先运行或选择一个可信基线任务。
3. 用户打开“实验模式”开关。
4. 页面显示“实验不会影响正式扫描”的提示。
5. 用户选择实验参数：
   - 最低量干分。
   - 最低总分。
   - 最低价稳分。
   - 时间退出天数。
   - 启动确认方式。
   - 启动确认最大等待天数。
6. 用户选择对比基线任务。
7. 系统校验实验任务与基线任务是否可比较。
8. 用户启动实验回测。
9. 前端展示实验任务进度。
10. 完成后展示实验结果与基线对比：
    - 原始命中数变化。
    - 实际入场数变化。
    - 机会数变化。
    - 胜率变化。
    - 止损率变化。
    - 平均收益变化。
    - 超额收益变化。
    - 月份和机会类型分组差异。

### 4.2 页面展示要求

#### 实验模式入口

- 开关：`启用策略实验`
- 徽标：`EXPERIMENTAL`
- 提示文案：

```text
实验任务仅用于回测评估，不会修改策略2正式扫描规则。
实验结果需要与可信基线对比后再讨论是否升级为正式参数。
```

#### 实验参数区

- 最低总分：默认空，表示沿用基线。
- 最低量干分：默认空，推荐候选值 40、50。
- 最低价稳分：默认空。
- 时间退出：默认关闭，候选值 5、10。
- 启动确认：
  - 不启用。
  - 突破近 5 日高点。
  - 收盘站上 MA20。
  - 温和放量突破。
- 最大等待天数：默认 5。

#### 基线对比区

- 基线任务 ID。
- 基线可信度。
- 基线数据版本。
- 基线策略版本。
- 基线股票范围。
- 基线请求日期。
- 是否可比较。
- 不可比较原因。

#### 实验汇总区

- 基线机会数。
- 实验保留机会数。
- 实验过滤机会数。
- 实际入场机会数。
- 未确认入场机会数。
- 时间退出次数。
- 目标达成次数。
- 止损次数。
- 5日、10日核心统计。
- 平均实际收益。
- 中位实际收益。
- 跑赢本地市场比例。

#### 分组统计区

- 按月份。
- 按机会类型。
- 按量干分段。
- 按价稳分段。
- 按总分段。
- 按市场环境。
- 按启动确认结果。

### 4.3 交互规则

- 实验模式关闭时，不显示高级实验参数。
- 实验模式关闭时，提交 payload 中 `experiment.enabled=false`。
- 实验模式开启时，必须显示 `EXPERIMENTAL` 标识。
- 选择基线任务后，前端调用后端校验接口或对比接口获取可比性。
- 若基线任务不是 `TRUSTED_BASELINE`，允许继续但必须给出黄色警告。
- 若数据版本、股票范围、日期范围或执行模型不一致，对比接口必须返回不可比较原因。
- 实验任务完成后，不得在页面上显示“可信基线”字样。
- 用户刷新页面后，实验参数和对比结果必须从任务快照恢复。

---

## 5. 技术架构方案

### 5.1 总体架构

```text
前端策略2回测页
  -> 创建回测任务 API，携带 experiment 配置
  -> strategy2/backtest_service.py 冻结 config_snapshot + experiment_snapshot
  -> strategy2/backtester.py 继续调用唯一策略引擎
  -> strategy2/backtest_experiments.py 应用实验过滤、启动确认、时间退出、机会分类
  -> scanner/db.py 持久化实验任务、机会字段、汇总和对比信息
  -> API 返回实验汇总、分组统计和基线对比
  -> 前端展示实验结果，不影响正式扫描
```

### 5.2 模块边界

#### `strategy2/backtester.py`

职责：

- 读取本地历史日线。
- 构造历史判断窗口。
- 调用策略2唯一引擎。
- 生成原始信号和基线机会。
- 将可扩展的实验配置传入实验模块。

不允许：

- 复制策略2评分逻辑。
- 在该模块内堆叠大量实验判断。

#### `strategy2/backtest_experiments.py`

新增模块，职责：

- 解析实验配置。
- 校验实验参数。
- 对策略2评估结果应用实验过滤。
- 给机会打类型标签。
- 执行启动确认。
- 执行时间退出。
- 生成实验漏斗统计。

该模块是 Phase 2 的主要新增边界，避免把实验逻辑散落在回测服务和 API 层。

#### `strategy2/backtest_service.py`

职责：

- 创建、恢复、取消、重试回测任务。
- 冻结 `experiment_snapshot`。
- 标记任务可信度状态。
- 生成最终汇总。
- 触发实验对比统计。

#### `scanner/db.py`

职责：

- 兼容式新增实验相关字段。
- 保存实验快照。
- 保存实验过滤计数。
- 保存机会类型、入场确认和时间退出信息。
- 提供基线对比查询需要的聚合数据。

#### `server.py`

职责：

- 接收实验配置。
- 返回参数校验错误。
- 提供对比接口。
- 不承载复杂实验算法。

#### `web/src/pages/Strategy2Backtest.vue`

职责：

- 展示实验配置表单。
- 展示实验标识和风险提示。
- 展示基线可比性。
- 展示实验结果和对比统计。

### 5.3 数据流设计

1. 前端提交回测参数和实验配置。
2. 后端校验请求参数。
3. 后端冻结当前正式配置为 `config_snapshot`。
4. 后端冻结实验参数为 `experiment_snapshot`。
5. 后端创建回测任务。
6. 回测器按 Phase 1 可信逻辑生成历史评估结果。
7. 实验模块在策略引擎通过后应用实验过滤。
8. 若实验过滤通过，进入启动确认流程。
9. 若启动确认通过，按执行模型计算入场。
10. 若配置时间退出，目标/止损未先触发时按时间退出。
11. 持久化实验机会、过滤原因和漏斗统计。
12. 任务完成后生成实验汇总。
13. 如果指定基线任务，后端生成对比摘要。
14. 前端展示实验任务和对比结果。

### 5.4 状态设计

回测任务状态沿用 Phase 1：

- `created`
- `running`
- `completed`
- `completed_with_errors`
- `interrupted`
- `failed`
- `canceled`

可信度状态扩展：

- `TRUSTED_BASELINE`
  - 仅实验关闭、完整性通过、版本匹配的基线任务可使用。
- `EXPERIMENTAL`
  - 实验开启的任务必须使用。
- `LEGACY_UNTRUSTED`
  - 旧任务或版本不可信任务。
- `INCOMPLETE`
  - 运行中、中断或失败任务。

实验机会状态：

- `BASELINE_PASSED`
  - 策略2原始判断通过。
- `EXPERIMENT_FILTERED`
  - 策略2通过，但被实验门槛过滤。
- `ENTRY_CONFIRMED`
  - 通过启动确认并进入执行模拟。
- `NO_ENTRY_CONFIRMATION`
  - 等待期内未触发启动确认。
- `ENTERED`
  - 已产生模拟入场。
- `UNOBSERVED_ENTRY`
  - 无法观察到入场日。

---

## 6. 数据库设计方案

### 6.1 修改回测任务表

在 `strategy2_backtest_tasks` 兼容式新增字段：

```sql
ALTER TABLE strategy2_backtest_tasks ADD COLUMN experiment_snapshot TEXT;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN baseline_task_id TEXT;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN comparison_summary_json TEXT;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN experiment_filtered_days INTEGER DEFAULT 0;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN experiment_volume_filtered_days INTEGER DEFAULT 0;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN experiment_score_filtered_days INTEGER DEFAULT 0;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN entry_confirmation_failed_count INTEGER DEFAULT 0;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN time_exit_count INTEGER DEFAULT 0;
```

说明：

- `experiment_snapshot` 保存完整实验参数 JSON。
- `baseline_task_id` 保存用户选择的对比基线。
- `comparison_summary_json` 保存完成后生成的对比摘要。
- 计数字段用于任务列表快速展示，完整漏斗仍放入 `summary_json`。

### 6.2 修改原始信号表

在 `strategy2_backtest_signals` 兼容式新增字段：

```sql
ALTER TABLE strategy2_backtest_signals ADD COLUMN baseline_passed INTEGER DEFAULT 1;
ALTER TABLE strategy2_backtest_signals ADD COLUMN experiment_passed INTEGER DEFAULT 1;
ALTER TABLE strategy2_backtest_signals ADD COLUMN experiment_filter_reason TEXT;
ALTER TABLE strategy2_backtest_signals ADD COLUMN opportunity_type TEXT;
```

说明：

- 策略引擎原始通过时保存信号。
- 如果实验过滤掉该信号，`experiment_passed=0` 并记录原因。
- 这样可以保留完整实验漏斗，不丢失“基线本来命中但实验过滤”的证据。

### 6.3 修改机会表

在 `strategy2_backtest_opportunities` 兼容式新增字段：

```sql
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN opportunity_type TEXT;
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN entry_confirmation_type TEXT;
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN entry_confirmation_date TEXT;
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN entry_confirmation_price REAL;
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN entry_confirmation_status TEXT;
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN time_exit_days INTEGER;
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN market_context_json TEXT;
```

说明：

- `opportunity_type` 用于趋势延续、反转修复、中性分组。
- `entry_confirmation_*` 记录启动确认结果。
- `time_exit_days` 记录该机会使用的时间退出配置。
- `market_context_json` 保存信号日市场环境快照。

### 6.4 索引设计

```sql
CREATE INDEX IF NOT EXISTS idx_s2_bt_task_baseline
ON strategy2_backtest_tasks(baseline_task_id);

CREATE INDEX IF NOT EXISTS idx_s2_bt_signal_experiment
ON strategy2_backtest_signals(task_id, experiment_passed, experiment_filter_reason);

CREATE INDEX IF NOT EXISTS idx_s2_bt_opp_type
ON strategy2_backtest_opportunities(task_id, opportunity_type);
```

### 6.5 数据兼容方案

- 所有新增字段必须通过 `_ensure_column()` 兼容式添加。
- 旧任务 `experiment_snapshot` 为空时视为 `{"enabled": false}`。
- 旧机会 `opportunity_type` 为空时前端显示 `UNKNOWN`，不报错。
- 旧任务不得自动升级为实验任务。
- 旧任务若缺少版本信息，仍按 Phase 1 规则标记为 `LEGACY_UNTRUSTED`。

---

## 7. 接口设计方案

### 7.1 修改接口：创建策略2回测任务

```http
POST /api/strategy2/backtests
```

请求示例：

```json
{
  "startDate": "2025-08-01",
  "endDate": "2026-05-01",
  "codes": [],
  "maxStocks": null,
  "executionModel": "NEXT_OPEN",
  "baselineTaskId": "s2bt-20260613-100000-a1b2c3",
  "experiment": {
    "enabled": true,
    "minimumTotalScore": null,
    "minimumVolumeDryScore": 40,
    "minimumPriceStableScore": null,
    "timeExitDays": 5,
    "entryConfirmation": {
      "type": "BREAK_RECENT_5D_HIGH",
      "maxWaitDays": 5,
      "moderateVolumeMaxRatio": 1.8
    },
    "marketContext": {
      "enabled": true
    }
  }
}
```

返回示例：

```json
{
  "taskId": "s2bt-20260613-120000-b7c9e2",
  "status": "created",
  "credibilityStatus": "EXPERIMENTAL",
  "baselineTaskId": "s2bt-20260613-100000-a1b2c3",
  "estimatedStocks": 4973,
  "estimatedEvaluations": 497300
}
```

参数规则：

- `experiment.enabled=false` 时必须保持基线行为。
- `minimumVolumeDryScore` 允许 `null` 或 `0-100`。
- 推荐候选值为 `40`、`50`。
- `minimumTotalScore` 允许 `null` 或 `0-100`。
- `minimumPriceStableScore` 允许 `null` 或 `0-100`。
- `timeExitDays` 允许 `null`、`5`、`10`。
- `entryConfirmation.type` 只允许枚举值。
- `entryConfirmation.maxWaitDays` 建议 `1-10`。
- `moderateVolumeMaxRatio` 必须大于 `1.0`。

### 7.2 新增接口：预览实验配置

```http
POST /api/strategy2/backtests/experiments/preview
```

用途：

- 校验实验配置。
- 返回规范化后的实验配置。
- 返回预计实验任务可信度状态。
- 返回可理解的风险提示。

返回示例：

```json
{
  "valid": true,
  "normalizedExperiment": {
    "enabled": true,
    "minimumVolumeDryScore": 40,
    "timeExitDays": 5,
    "entryConfirmation": {
      "type": "BREAK_RECENT_5D_HIGH",
      "maxWaitDays": 5,
      "moderateVolumeMaxRatio": 1.8
    }
  },
  "warnings": [
    "实验任务不会影响正式扫描规则",
    "实验结论需要与可信基线对比"
  ]
}
```

### 7.3 新增接口：基线对比

```http
GET /api/strategy2/backtests/{taskId}/comparison?baselineTaskId=s2bt-20260613-100000-a1b2c3
```

返回示例：

```json
{
  "comparable": true,
  "baselineTaskId": "s2bt-20260613-100000-a1b2c3",
  "experimentTaskId": "s2bt-20260613-120000-b7c9e2",
  "baseline": {
    "opportunities": 1200,
    "entered": 1180,
    "successRate10": 0.43,
    "stopRate10": 0.36,
    "averageRealizedReturn": 0.008
  },
  "experiment": {
    "opportunities": 720,
    "entered": 610,
    "successRate10": 0.49,
    "stopRate10": 0.31,
    "averageRealizedReturn": 0.014
  },
  "delta": {
    "opportunities": -480,
    "entered": -570,
    "successRate10": 0.06,
    "stopRate10": -0.05,
    "averageRealizedReturn": 0.006
  },
  "groups": {
    "byMonth": [],
    "byOpportunityType": [],
    "byMarketRegime": []
  }
}
```

不可比较返回：

```json
{
  "comparable": false,
  "reasons": [
    "DATA_REVISION_MISMATCH",
    "REQUESTED_DATE_RANGE_MISMATCH"
  ]
}
```

### 7.4 修改接口：查询任务详情

```http
GET /api/strategy2/backtests/{taskId}
```

新增返回字段：

```json
{
  "experimentSnapshot": {},
  "baselineTaskId": null,
  "comparisonSummary": {},
  "credibilityStatus": "EXPERIMENTAL",
  "experimentStats": {
    "baselinePassedSignals": 1000,
    "experimentPassedSignals": 720,
    "experimentFilteredSignals": 280,
    "entryConfirmationFailedCount": 110,
    "timeExitCount": 260
  }
}
```

### 7.5 接口兼容要求

- 旧前端不传 `experiment` 时，后端按 `enabled=false` 处理。
- 旧任务详情接口不能因为缺少实验字段报错。
- 实验字段必须使用 camelCase 对外返回，内部数据库可使用 snake_case。
- 参数错误返回 HTTP 422 和稳定错误码。

---

## 8. 可以实施的代码方案

### 8.1 后端代码方案

#### 8.1.1 新增模块：`strategy2/backtest_experiments.py`

建议定义：

```text
ExperimentConfig
EntryConfirmationConfig
ExperimentDecision
OpportunityType
MarketContext
```

核心函数：

```text
normalize_experiment_config(payload) -> ExperimentConfig
validate_experiment_config(config) -> list[ValidationError]
apply_experiment_filters(evaluation, config) -> ExperimentDecision
classify_opportunity_type(history_data, evaluation) -> OpportunityType
resolve_entry_confirmation(history_data, signal_index, config) -> EntryConfirmationResult
calculate_time_exit_outcome(entry_index, future_data, config, target, stop) -> ExecutionOutcome
build_market_context(all_market_data, decision_date) -> MarketContext
```

#### 8.1.2 实验配置标准化

输入：

```json
{
  "enabled": true,
  "minimumVolumeDryScore": 40
}
```

输出：

```json
{
  "enabled": true,
  "minimum_total_score": null,
  "minimum_volume_dry_score": 40,
  "minimum_price_stable_score": null,
  "time_exit_days": null,
  "entry_confirmation": {
    "type": "NONE",
    "max_wait_days": 5,
    "moderate_volume_max_ratio": 1.8
  },
  "market_context": {
    "enabled": true
  }
}
```

边界条件：

- `experiment` 缺失：等同 `enabled=false`。
- `enabled=false`：忽略其他实验参数，但可以保存原始 payload 用于审计。
- 数值越界：返回参数错误。
- 未知枚举：返回参数错误。

#### 8.1.3 实验过滤逻辑

过滤顺序：

1. 策略2引擎必须先通过。
2. 检查 `minimum_total_score`。
3. 检查 `minimum_volume_dry_score`。
4. 检查 `minimum_price_stable_score`。
5. 记录第一个过滤原因。

过滤原因：

- `MIN_TOTAL_SCORE`
- `MIN_VOLUME_DRY_SCORE`
- `MIN_PRICE_STABLE_SCORE`

要求：

- 被实验过滤的信号仍保存到 `strategy2_backtest_signals`。
- 被实验过滤的信号不进入实验机会合并。
- 被过滤信号应计入实验漏斗。
- 实验过滤日仍属于“已评估但未通过实验”的日期，不应被静默丢弃。

#### 8.1.4 机会类型分类

初始定义：

```text
CONTINUATION:
  center_shift_20 >= 0
  AND ma20 >= ma60

REVERSAL:
  return_20 < -5%
  OR drawdown_from_high_60 <= -12%

NEUTRAL:
  其他情况
```

实现要求：

- 分类函数独立，便于后续调整。
- 分类只用于统计和分组，不直接过滤机会。
- 若数据不足以计算分类，返回 `NEUTRAL` 并记录 `classification_reason=INSUFFICIENT_CONTEXT`。

#### 8.1.5 启动确认

候选类型：

```text
NONE
BREAK_RECENT_5D_HIGH
CLOSE_ABOVE_MA20
BREAK_HIGH_WITH_MODERATE_VOLUME
```

规则：

- `NONE`：沿用 Phase 1 入场模型。
- `BREAK_RECENT_5D_HIGH`：在信号日后 `max_wait_days` 内，某日收盘价突破信号日前 5 个交易日最高价。
- `CLOSE_ABOVE_MA20`：在等待期内，某日收盘价大于该日 MA20。
- `BREAK_HIGH_WITH_MODERATE_VOLUME`：满足突破近 5 日高点，且该日成交量不超过 `V20 * moderate_volume_max_ratio`。

边界条件：

- 确认只允许使用确认日及之前数据。
- 等待期不足时按实际可观察天数判断。
- 等待期内未确认：`NO_ENTRY_CONFIRMATION`。
- 确认发生后，入场日应为确认日后的下一交易日开盘。
- 如果确认日后无下一交易日，标记 `UNOBSERVED_ENTRY`。
- 若下一交易日高开超过买入区间，沿用 Phase 1 的 `NO_ENTRY_ABOVE_BUY_ZONE` 规则。

#### 8.1.6 时间退出

规则：

- `time_exit_days=null`：沿用 Phase 1 目标/止损逻辑。
- `time_exit_days=5` 或 `10`：从实际入场日开始计数。
- 若目标或止损先触发，按目标/止损退出。
- 若到达时间退出日仍未触发目标或止损，按当日收盘价退出。
- 保存：
  - `exit_reason=TIME_EXIT`
  - `exit_date`
  - `exit_price`
  - `holding_days`
  - `realized_return`

不允许：

- 时间退出覆盖更早发生的目标或止损。
- 使用信号日而不是实际入场日作为计数起点。

#### 8.1.7 市场环境统计

本期只做统计，不做硬过滤。

计算内容：

- 信号日前本地等权市场 5 日收益。
- 信号日前本地等权市场 10 日收益。
- 信号日前本地等权市场 20 日收益。
- 本地等权市场是否位于 MA20 之上。
- 信号所属月份。

实现建议：

- 从本地 `daily_ohlc` 按日期聚合等权收益。
- 可在任务级缓存日期市场上下文，避免每个机会重复扫描全表。
- 保存到 `market_context_json`。

#### 8.1.8 回测服务接入

修改 `strategy2/backtest_service.py`：

1. 创建任务时解析并冻结 `experiment_snapshot`。
2. 实验开启时设置 `credibility_status=EXPERIMENTAL`。
3. 实验关闭时保持 Phase 1 可信基线逻辑。
4. 运行任务时将实验配置传给回测器。
5. 完成任务时生成实验汇总。
6. 若存在 `baseline_task_id`，生成 `comparison_summary_json`。

#### 8.1.9 数据库接入

修改 `scanner/db.py`：

- `_ensure_strategy2_backtest_tables()` 增加兼容字段。
- `create_strategy2_backtest_task()` 保存 `experiment_snapshot` 和 `baseline_task_id`。
- `save_strategy2_backtest_signal()` 支持实验字段。
- `save_strategy2_backtest_opportunity()` 支持机会类型、确认字段、时间退出字段、市场上下文。
- `build_strategy2_backtest_summary()` 增加实验漏斗和分组统计。
- 新增对比查询或对比汇总函数。

### 8.2 前端代码方案

#### 8.2.1 页面状态

在 `Strategy2Backtest.vue` 增加：

```js
const experimentForm = reactive({
  enabled: false,
  minimumTotalScore: null,
  minimumVolumeDryScore: null,
  minimumPriceStableScore: null,
  timeExitDays: null,
  entryConfirmation: {
    type: 'NONE',
    maxWaitDays: 5,
    moderateVolumeMaxRatio: 1.8,
  },
  marketContext: {
    enabled: true,
  },
})
```

#### 8.2.2 表单展示

要求：

- 实验模式关闭时折叠高级实验配置。
- 实验模式开启时展示黄色或橙色实验提示。
- 参数输入旁展示推荐值，不自动填入。
- 时间退出用单选：关闭、5日、10日。
- 启动确认用下拉选择。
- `BREAK_HIGH_WITH_MODERATE_VOLUME` 时显示放量倍数输入。

#### 8.2.3 请求构造

创建回测任务时：

```js
payload.experiment = {
  enabled: experimentForm.enabled,
  minimumTotalScore: normalizeNullableNumber(experimentForm.minimumTotalScore),
  minimumVolumeDryScore: normalizeNullableNumber(experimentForm.minimumVolumeDryScore),
  minimumPriceStableScore: normalizeNullableNumber(experimentForm.minimumPriceStableScore),
  timeExitDays: experimentForm.timeExitDays,
  entryConfirmation: { ...experimentForm.entryConfirmation },
  marketContext: { ...experimentForm.marketContext },
}
```

#### 8.2.4 对比展示

新增对比卡片：

- 机会数变化。
- 入场数变化。
- 10日胜率变化。
- 10日止损率变化。
- 平均实际收益变化。
- 跑赢市场比例变化。

差值展示规则：

- 正向改善用红色。
- 负向恶化用绿色或灰色，遵循 A 股红涨绿跌的现有设计。
- 不可比较时显示原因，不展示误导性差值。

#### 8.2.5 前端不允许行为

- 不把实验参数写回正式配置页。
- 不在实验任务上显示“可信基线”。
- 不隐藏实验过滤掉的数量。
- 不把 `NO_ENTRY_CONFIRMATION` 当成策略失败，应单独展示为未入场。

---

## 9. 日志与异常处理方案

### 9.1 必须记录的日志

- 创建实验任务时的实验快照。
- 实验参数标准化结果。
- 实验参数校验失败原因。
- 每个任务的实验过滤统计。
- 启动确认失败数量。
- 时间退出数量。
- 基线对比可比性校验结果。
- 对比摘要生成成功或失败。

### 9.2 异常处理

- 实验配置非法：创建任务前返回 HTTP 422。
- 基线任务不存在：返回 HTTP 404 或对比不可用。
- 基线任务不可信：允许创建实验，但前端必须警告。
- 基线不可比较：实验任务可运行，但对比接口返回 `comparable=false`。
- 市场环境统计失败：不应导致任务失败，但必须记录 `market_context_error` 并在 summary 中披露。
- 单只股票实验计算异常：沿用 Phase 1 股票级失败处理。

### 9.3 可比性校验

以下字段必须一致，否则不允许显示正式对比差值：

- `requested_start_date`
- `requested_end_date`
- `scope_type`
- `requested_codes`
- `max_stocks`
- `sampling_method`
- `sampling_seed`
- `execution_model`
- `backtest_engine_version`
- `strategy_engine_version`
- `data_revision_version`
- `data_revision_id`

若字段不一致，返回具体原因，前端显示：

```text
该实验任务与所选基线不是同一数据条件，不能直接比较。
```

---

## 10. 测试方案

### 10.1 单元测试

#### 实验配置

- `experiment` 缺失时等同关闭。
- `enabled=false` 时输出基线配置。
- 量干分越界返回错误。
- 时间退出只允许 `null/5/10`。
- 未知启动确认类型返回错误。
- `moderateVolumeMaxRatio <= 1` 返回错误。

#### 实验过滤

- 量干分低于门槛时被过滤。
- 总分低于门槛时被过滤。
- 价稳分低于门槛时被过滤。
- 多个门槛同时失败时记录第一个稳定原因。
- 实验关闭时不过滤任何基线命中。

#### 机会类型

- `center_shift_20 >= 0 AND ma20 >= ma60` 分类为 `CONTINUATION`。
- `return_20 < -5%` 分类为 `REVERSAL`。
- `drawdown_from_high_60 <= -12%` 分类为 `REVERSAL`。
- 两者都不满足分类为 `NEUTRAL`。
- 数据不足时分类为 `NEUTRAL` 并记录原因。

#### 启动确认

- `NONE` 直接沿用 Phase 1 入场。
- 突破近 5 日高点时确认成功。
- 收盘站上 MA20 时确认成功。
- 温和放量突破时确认成功。
- 放量过大时确认失败。
- 等待期内未确认时返回 `NO_ENTRY_CONFIRMATION`。
- 确认后无下一交易日时返回 `UNOBSERVED_ENTRY`。
- 确认逻辑不得使用确认日之后的数据。

#### 时间退出

- 目标先触发时 `TARGET` 优先。
- 止损先触发时 `STOP` 优先。
- 目标和止损都未触发时按时间退出。
- 时间退出收益使用退出日收盘价。
- 时间退出从实际入场日计数。
- 未来数据不足时不伪造时间退出。

### 10.2 数据库测试

- 新增字段可在旧数据库上兼容创建。
- 旧任务 `experiment_snapshot` 为空时按关闭处理。
- 实验任务保存完整快照。
- 实验信号保存 `experiment_passed=false` 和过滤原因。
- 机会保存机会类型、确认状态和市场上下文。
- 任务保存 `comparison_summary_json`。
- 索引创建重复执行不报错。

### 10.3 接口测试

- 创建基线任务不传实验参数时仍可成功。
- 创建实验任务返回 `credibilityStatus=EXPERIMENTAL`。
- 非法实验参数返回 HTTP 422。
- 实验预览接口返回标准化配置。
- 对比接口在字段一致时返回 `comparable=true`。
- 对比接口在数据版本不一致时返回 `comparable=false`。
- 查询任务详情返回实验快照和实验统计。
- 旧任务详情兼容返回。

### 10.4 集成测试

1. 构造小型本地日线数据库。
2. 创建实验关闭任务，得到基线结果。
3. 创建实验开启任务，只设置量干分门槛。
4. 验证实验机会数小于或等于基线机会数。
5. 验证被过滤信号仍在原始信号表中可追溯。
6. 创建启动确认实验任务。
7. 验证未确认机会不进入实际入场统计。
8. 创建时间退出实验任务。
9. 验证目标/止损优先于时间退出。
10. 调用对比接口验证差值。

### 10.5 前端测试

- 实验模式开关默认关闭。
- 开启实验后显示 `EXPERIMENTAL` 标识。
- 关闭实验时不提交无效实验参数。
- 量干分、时间退出、启动确认参数正确进入 payload。
- 非法输入时前端阻止或展示后端错误。
- 对比基线不可比较时显示原因。
- 实验任务详情可恢复实验参数展示。
- `NO_ENTRY_CONFIRMATION` 单独展示，不混入失败数。

### 10.6 回归测试

- 策略2正式扫描结果不变。
- 策略2配置页不被实验参数污染。
- 实验关闭时回测结果与 Phase 1 基线一致。
- 回测仍不访问任何外部数据源。
- Phase 1 的恢复、取消、失败重试、分页和可信度展示仍可用。
- 策略1不受影响。
- 后端全量测试通过。
- 前端测试和构建通过。

---

## 11. 验收标准

功能完成后必须满足：

1. 用户可以创建策略2实验回测任务。
2. 实验任务明确显示 `EXPERIMENTAL`。
3. 实验关闭时结果与可信基线一致。
4. 实验开启时不影响正式扫描和正式配置。
5. 量干分门槛实验可用。
6. 分层评分门槛实验可用。
7. 时间退出实验可用，且不覆盖更早目标/止损。
8. 启动确认实验可用，未确认机会被单独统计。
9. 机会类型标签可用于分组统计。
10. 市场环境统计可展示，不作为硬过滤。
11. 实验快照、过滤原因、确认状态和时间退出信息可追溯。
12. 基线对比接口能识别可比与不可比任务。
13. 前端能展示实验参数、实验汇总和基线差值。
14. 所有新增逻辑有单元、接口、集成和前端测试。
15. 文档中的不做范围没有被突破。
16. 如果后续根据实验结果调整正式策略，必须额外交付优化后的策略文档，且文档必须包含最终参数名、参数值、证据来源和回滚方案。

---

## 12. 实验后正式策略优化交付要求

本节不是 Phase 2 实验功能的直接开发范围，而是用户授权后的后续正式策略升级流程。

### 12.1 触发条件

只有同时满足以下条件，才允许从“实验评估”进入“正式策略调整”：

1. 已完成新的全市场可信基线任务。
2. 基线任务满足 `TRUSTED_BASELINE` 要求。
3. 至少完成一个可比较的 `EXPERIMENTAL` 任务。
4. 对比接口确认基线与实验任务可比较。
5. 实验结果在机会数、胜率、止损率、平均收益或超额收益上具备明确改善。
6. 改善不能只依赖单一月份或极少数股票。
7. 已形成策略升级建议并说明风险。

### 12.2 允许调整的正式策略内容

在满足触发条件后，允许调整：

- 策略2正式配置参数。
- 策略2正式扫描过滤门槛。
- 策略2候选展示字段和风险提示。
- 策略2配置页中与新参数相关的展示。
- 与正式策略调整对应的测试和文档。

仍然禁止：

- 修改策略1。
- 引入第二份策略2判断代码。
- 删除 Phase 2 实验能力。
- 用不可比较任务结果作为正式调整依据。
- 在没有文档说明的情况下直接修改参数。

### 12.3 必须交付的优化后策略文档

正式策略修改完成后，必须新增一份 Markdown 文档，建议路径：

```text
docs/superpowers/specs/YYYY-MM-DD-strategy2-optimized-strategy-parameters.md
```

文档标题建议：

```text
# 策略2优化后正式策略文档：极致量干价稳短线候选
```

该文档必须包含以下内容：

1. 策略版本号。
2. 生效日期。
3. 适用市场和适用周期。
4. 策略定位：短线观察、低风险候选、非自动交易。
5. 数据窗口要求：
   - 最低历史数据天数。
   - 最大策略计算窗口。
   - 流动性过滤窗口。
6. 正式入选参数表，必须写出参数名和具体数值。
7. 正式过滤规则，必须写出规则表达式和阈值。
8. 评分规则，必须写出总分、量干分、价稳分等门槛。
9. 趋势规则，必须写出上涨、横盘、下降过滤判断。
10. 风险规则，必须写出止损、买入区间、风险比上限。
11. 启动确认规则，如果升级为正式规则，必须写出确认类型和等待天数。
12. 时间退出规则，如果升级为正式规则，必须写出退出天数和优先级。
13. 机会类型处理规则：
    - `CONTINUATION`
    - `REVERSAL`
    - `NEUTRAL`
14. 参数变更前后对比表。
15. 可信基线任务 ID。
16. 实验任务 ID。
17. 核心对比结果：
    - 机会数变化。
    - 实际入场数变化。
    - 5 日与 10 日成功率变化。
    - 止损率变化。
    - 平均实际收益变化。
    - 中位实际收益变化。
    - 跑赢市场比例变化。
18. 分组表现：
    - 按月份。
    - 按机会类型。
    - 按量干分段。
    - 按价稳分段。
    - 按市场环境。
19. 不采用的实验参数及原因。
20. 已知风险和适用边界。
21. 回滚方案。
22. 后续观察指标。

### 12.4 参数表格式要求

优化后策略文档必须包含类似以下表格，不能只写描述性文字：

| 参数名 | 旧值 | 新值 | 生效位置 | 调整原因 |
|---|---:|---:|---|---|
| `minimum_total_score` | 70 | 75 | 正式扫描 | 示例：实验显示提高后止损率下降 |
| `minimum_volume_dry_score` | 无 | 40 | 正式扫描 | 示例：量干分低于40的候选收益弱 |
| `minimum_price_stable_score` | 无 | 30 | 正式扫描 | 示例：过滤波动失控候选 |
| `time_exit_days` | 无 | 5 | 交易建议 | 示例：短线收益集中在5日内 |
| `entry_confirmation.type` | `NONE` | `BREAK_RECENT_5D_HIGH` | 交易建议 | 示例：确认后失败率下降 |

注意：

- 表中的数值必须来自实际实验结论，不能沿用示例值。
- 如果某个实验参数未升级为正式规则，必须在“不采用的实验参数及原因”中说明。
- 如果只调整展示建议而不调整正式过滤，也必须明确写出。

### 12.5 回滚方案要求

优化后策略文档必须提供明确回滚方案：

```text
如果新策略连续 N 次扫描候选数低于阈值，或后续回测/实盘观察指标恶化，
则回滚到策略版本 X，恢复以下参数：
- 参数 A = 旧值
- 参数 B = 旧值
- 参数 C = 旧值
```

回滚方案必须包含：

- 回滚触发条件。
- 回滚参数清单。
- 回滚验证方式。
- 回滚后需要重新运行的测试。

---

## 13. 给 Claude Code / Codex 的执行指令

请严格按照本文档实施策略2 Phase 2 回测实验能力。

执行要求：

1. 先阅读：
   - `docs/superpowers/specs/2026-06-11-strategy2-local-database-backtest-design.md`
   - `docs/superpowers/specs/2026-06-12-strategy2-backtest-correctness-and-strategy-optimization-design.md`
   - `docs/reviews/2026-06-13-strategy2-phase1-final-acceptance-completion.md`
   - 当前 `strategy2/backtester.py`
   - 当前 `strategy2/backtest_service.py`
   - 当前 `scanner/db.py`
   - 当前 `server.py`
   - 当前 `web/src/pages/Strategy2Backtest.vue`
2. 本次只实现 Phase 2 实验层，不修改策略2正式扫描规则。
3. 使用测试驱动开发，先补实验配置、过滤、确认和时间退出的失败测试。
4. 新增 `strategy2/backtest_experiments.py` 承载实验逻辑。
5. 不复制 `ExtremeDryStableStrategyEngine.evaluate_at()` 的判断代码。
6. 实验关闭时必须与 Phase 1 基线行为一致。
7. 实验开启时任务可信度必须为 `EXPERIMENTAL`。
8. 实验参数必须保存到 `experiment_snapshot`。
9. 被实验过滤的原始信号必须可追溯，不能静默丢弃。
10. 启动确认只允许使用确认日及之前数据。
11. 时间退出不得覆盖更早触发的目标或止损。
12. 市场环境只做统计，不做硬过滤。
13. 对比接口必须校验数据版本、策略版本、日期、股票范围和执行模型。
14. 前端必须明确展示实验提示和实验徽标。
15. 不修改策略1，不请求外部数据源，不重构无关模块。
16. 每完成一个模块运行对应测试。
17. 最终运行策略2专项测试、后端全量测试、前端测试和前端构建。
18. 将开发过程、测试结果和遗留问题追加到 `operations-log.md`。
19. Phase 2 实验功能完成后，不要自动修改正式策略参数；只有在用户明确进入正式策略升级时，才按第12节交付优化后的策略文档。

---

## 14. AI 开始开发提示语

```text
请开发策略2 Phase 2“回测实验与策略优化评估”功能。

工作目录：
D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy2-extreme-dry-stable

开发依据：
docs/superpowers/specs/2026-06-13-strategy2-phase2-experiment-optimization-design.md

核心定位：
本次是策略2回测实验层，不是正式策略升级。实验参数只影响实验回测任务，不允许修改策略2正式扫描规则，不允许自动改写config.yaml正式参数。

强制要求：
1. 先阅读Phase 1回测设计、Phase 1修复验收报告和当前策略2回测代码。
2. 新增strategy2/backtest_experiments.py，集中实现实验配置解析、实验过滤、机会类型、启动确认、时间退出和市场环境统计。
3. 回测仍必须调用ExtremeDryStableStrategyEngine.evaluate_at()，禁止复制策略2核心判断逻辑。
4. experiment缺失或enabled=false时，结果必须等同Phase 1可信基线行为。
5. experiment.enabled=true时，任务credibility_status必须为EXPERIMENTAL，不得标记TRUSTED_BASELINE。
6. 保存experiment_snapshot，历史任务查看必须使用快照，不读取当前实时配置解释旧任务。
7. 支持minimum_total_score、minimum_volume_dry_score、minimum_price_stable_score实验过滤。
8. 被实验过滤的原始信号必须保存并记录experiment_filter_reason，不能静默丢弃。
9. 支持time_exit_days=null/5/10；目标或止损先触发时必须优先于时间退出。
10. 支持entry_confirmation：NONE、BREAK_RECENT_5D_HIGH、CLOSE_ABOVE_MA20、BREAK_HIGH_WITH_MODERATE_VOLUME。
11. 启动确认只能使用确认日及之前数据，未确认标记NO_ENTRY_CONFIRMATION。
12. 支持opportunity_type：CONTINUATION、REVERSAL、NEUTRAL，仅用于统计分组，不作为硬过滤。
13. 增加本地等权市场5/10/20日环境统计，只做统计，不做过滤。
14. 增加baseline comparison接口，必须校验数据版本、策略版本、日期范围、股票范围、抽样方式和执行模型一致性。
15. 前端Strategy2Backtest.vue增加实验模式开关、实验参数区、EXPERIMENTAL标识、基线对比区和实验汇总展示。
16. 不修改策略2正式扫描、不修改策略1、不访问外部数据源、不重构无关模块。
17. 使用测试驱动开发，覆盖实验配置、过滤、启动确认、时间退出、机会类型、数据库兼容、API和前端展示。
18. 最终运行策略2专项测试、后端全量测试、前端测试和前端构建，并把结果写入operations-log.md。
19. Phase 2完成后不要自动改正式策略参数；如果用户要求根据实验结果升级正式策略，必须先产出策略升级建议，并在修改完成后新增“优化后的策略文档”，写清楚所有正式参数名、参数值、证据、风险和回滚方案。

直接开始实施，不需要再次确认本文档已明确的事项。
```

---

## 15. 最终交付物

开发完成后，需要交付：

1. 修改文件清单。
2. Phase 2 实验功能说明。
3. 新增实验参数说明。
4. 数据库兼容字段说明。
5. 新增和修改接口说明。
6. 前端实验模式说明。
7. 基线对比规则说明。
8. 测试结果说明。
9. 实验关闭等同基线的验证结果。
10. 是否存在遗留问题。
11. 是否建议进入下一轮正式策略参数讨论。
12. 如果已经执行正式策略升级，还必须交付优化后的策略文档，包含所有最终参数名和具体数值。
