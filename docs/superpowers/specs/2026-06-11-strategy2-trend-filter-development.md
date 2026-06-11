# 开发方案文档：策略2走势趋势过滤增量开发

## 1. 需求背景

### 当前问题

策略2「极致量干价稳」已经能够独立扫描全市场股票，并根据量干、价稳、关键支撑和风险比筛选候选。

但当前策略2没有判断股票所处的中期走势趋势。处于明确下降趋势中的股票，也可能因为短期缩量和波动收窄获得较高分数，形成“下跌中继被误认为低风险整理”的风险。

### 用户痛点

- 下降趋势股票可能因短期缩量进入候选。
- 用户希望策略2只关注上涨趋势或横盘整理股票。
- 趋势过滤结果需要可解释，不能只显示笼统的“不符合条件”。

### 业务目标

在不修改策略2原有100分评分体系的前提下，新增独立的走势趋势前置过滤：

- 明确下降趋势股票强制排除。
- 上涨趋势或横盘股票继续执行现有策略2评分。
- 保留趋势指标和过滤原因，方便核查。

### 预期效果

策略2候选结果中不再出现符合已定义下降趋势条件的股票。候选详情可以查看趋势类型、MA20、MA60、MA20斜率和20日涨跌幅。

---

## 2. 需求目标

### 2.1 必须实现

- 新增策略2独立趋势判断模块。
- 趋势判断作为评分前置强制过滤，不参与原有100分评分。
- 同时满足四个下降条件时，将股票判定为 `DOWNTREND`。
- `DOWNTREND` 股票强制排除，记录 `DOWNTREND_FILTERED`。
- 未同时满足四个条件时，统一归类为 `UPTREND_OR_SIDEWAYS`，继续执行现有策略2逻辑。
- 趋势判断只能使用评估日及之前的数据。
- 策略2候选表持久化趋势类型和趋势指标。
- 策略2候选 API 和结果页展示趋势信息。
- 策略2重新评估任务必须执行相同趋势过滤。
- 新增完整单元测试、引擎测试、扫描测试、数据库测试、接口测试和前端测试。

### 2.2 可选增强

- 策略2结果页支持按趋势指标排序。
- 任务详情页展示被下降趋势过滤的股票及趋势指标。

可选增强不作为本期验收阻塞项。

### 2.3 不做范围

- 不修改策略2原有量干50分、价稳50分评分规则。
- 不将趋势判断设计为加分项或扣分项。
- 不开放趋势阈值配置，本期使用固定规则。
- 不细分上涨趋势和横盘趋势。
- 不修改策略1任何逻辑。
- 不修改全局流动性过滤规则。
- 不修改策略2现有一票否决和风险比规则。
- 不开发策略2回测。
- 不重构无关模块。

---

## 3. 默认假设

1. 策略2现有实现位于 `strategy2/`。
2. 策略2唯一评估入口为 `ExtremeDryStableStrategyEngine.evaluate_at()`。
3. 策略2扫描与重新评估均通过该唯一评估入口执行。
4. `strategy2.strategy_window_days` 和 `strategy2.minimum_required_days` 默认均能提供至少60个交易日数据。
5. 日线数据已经按日期升序排列，并经过现有结构和值校验。
6. 趋势阈值首期固定在代码中，不增加配置页参数。
7. SQLite 数据库采用现有兼容式迁移方式新增字段。
8. 当前 worktree 中可能存在其他未提交开发修改，执行时不得覆盖或回退这些修改。

---

## 4. 产品设计方案

### 4.1 用户使用流程

1. 用户启动策略2扫描。
2. 系统获取股票数据并执行现有流动性过滤。
3. 策略2引擎计算趋势指标。
4. 系统判断股票是否处于下降趋势。
5. 下降趋势股票被过滤，不进入量干价稳评分。
6. 上涨或横盘股票继续执行现有评分、否决和风险判断。
7. 入选候选在策略2结果页展示趋势类型和趋势指标。

### 4.2 页面展示要求

策略2候选结果及详情至少展示：

- 趋势类型：`上涨或横盘`
- MA20
- MA60
- MA20最近5日变化率
- 最近20日涨跌幅

由于下降趋势股票不会成为候选，候选页面不应出现 `DOWNTREND`。

### 4.3 交互规则

- 趋势过滤无需用户单独开启或关闭。
- 趋势阈值本期不允许在前端修改。
- 策略2重新评估历史任务时，应使用当前代码中的趋势规则重新筛选结果。
- 原本是候选、重新评估后被判定为下降趋势的股票，应从候选表移除。

---

## 5. 技术架构方案

### 5.1 总体架构

```text
日线数据
  → 数据校验
  → 策略窗口截取
  → 策略2基础指标计算
  → 走势趋势前置过滤
      ├─ DOWNTREND：返回 DOWNTREND_FILTERED
      └─ UPTREND_OR_SIDEWAYS：继续
  → 风险计算
  → 一票否决
  → 量干价稳评分
  → 最终入选判断
```

### 5.2 新增模块

新增：

```text
strategy2/trend.py
```

职责：

- 计算 MA20、MA60、MA20斜率和20日涨跌幅。
- 判断趋势类型。
- 返回结构化 `Strategy2Trend`。
- 不负责评分、风险计算、数据库写入或日志。

### 5.3 需要修改的现有模块

- `strategy2/models.py`：新增 `Strategy2Trend`，并在 `Strategy2Evaluation` 中增加 `trend`。
- `strategy2/engine.py`：在基础指标计算后执行趋势过滤。
- `strategy2/scanner.py`：候选发现结构中增加趋势字段；下降趋势任务记录可审计信息。
- `scanner/db.py`：为 `strategy2_candidates` 兼容式新增趋势字段。
- `server.py`：候选列表和详情返回趋势字段。
- `web/src/pages/Strategy2Results.vue`：展示趋势类型和指标。
- `tests/test_strategy2_independence.py`：将 `strategy2.trend` 加入允许的策略2模块。

### 5.4 数据流设计

1. `ExtremeDryStableStrategyEngine.evaluate_at()` 完成现有数据校验和策略窗口截取。
2. 调用现有 `compute_indicators()`。
3. 调用新增 `evaluate_trend(strategy_data)`。
4. 若返回 `DOWNTREND`，立即返回未通过的 `Strategy2Evaluation`。
5. 下降趋势评估结果必须包含 `trend`，状态原因为 `DOWNTREND_FILTERED`。
6. 若返回 `UPTREND_OR_SIDEWAYS`，继续执行现有风险、否决、评分和入选逻辑。
7. 候选发现结构增加趋势字段。
8. 候选趋势信息写入数据库并由 API 返回前端。

---

## 6. 走势趋势规则

### 6.1 指标定义

所有计算均基于评估日 `T` 及之前、按日期升序排列的收盘价。

```text
MA20_T = T日及之前最近20个交易日收盘价的简单平均值
MA60_T = T日及之前最近60个交易日收盘价的简单平均值

MA20_T_MINUS_5 =
    以T-5交易日为结束日，向前最近20个交易日收盘价的简单平均值

MA20_SLOPE_5 = MA20_T / MA20_T_MINUS_5 - 1

RETURN_20 = CLOSE_T / CLOSE_T_MINUS_20 - 1
```

Python下标口径：

```text
CLOSE_T = closes[-1]
CLOSE_T_MINUS_20 = closes[-21]
MA20_T = mean(closes[-20:])
MA20_T_MINUS_5 = mean(closes[-25:-5])
```

禁止使用：

- `closes[-20]` 作为20日前收盘价。
- `mean(closes[-20:-5])` 计算五日前MA20，因为该切片只有15个交易日。
- 评估日之后的数据。

### 6.2 下降趋势判定

仅当以下四项同时成立时，判定为下降趋势：

```text
current_close < MA20
MA20 < MA60
MA20_SLOPE_5 < 0
RETURN_20 < -0.05
```

返回：

```text
trend_type = DOWNTREND
status_reason = DOWNTREND_FILTERED
```

### 6.3 上涨或横盘判定

四个下降趋势条件未同时成立时，统一返回：

```text
trend_type = UPTREND_OR_SIDEWAYS
```

该分类表示股票未被确认处于下降趋势，不代表必须满足严格上涨趋势。

### 6.4 执行顺序

趋势过滤必须：

- 在现有全局流动性过滤之后执行。
- 在策略2量干价稳评分之前执行。
- 在风险计算和一票否决之前执行，减少无效计算。
- 对正常扫描和重新评估使用同一入口。

### 6.5 边界行为

- 有效数据少于60日：沿用现有 `INSUFFICIENT_STRATEGY_DATA`，不执行趋势判断。
- MA20或MA60无法计算：返回 `INSUFFICIENT_STRATEGY_DATA`。
- MA20五日前值小于等于0：返回 `INVALID_MARKET_DATA`。
- 恰好满足 `RETURN_20 = -5%`：不判定为下降趋势，因为规则为严格小于 `-5%`。
- 恰好满足 `current_close = MA20`：不判定为下降趋势。
- 恰好满足 `MA20 = MA60`：不判定为下降趋势。
- 恰好满足 `MA20_SLOPE_5 = 0`：不判定为下降趋势。

---

## 7. 数据模型与数据库方案

### 7.1 新增数据模型

在 `strategy2/models.py` 新增：

```python
@dataclass
class Strategy2Trend:
    trend_type: str = ""
    ma20: float = 0.0
    ma60: float = 0.0
    ma20_slope: float = 0.0
    return_20: float = 0.0
    downtrend_conditions: list[str] = field(default_factory=list)
```

在 `Strategy2Evaluation` 新增：

```python
trend: Strategy2Trend = None
```

并在 `__post_init__()` 中创建默认对象。

### 7.2 修改策略2候选表

为 `strategy2_candidates` 兼容式新增字段：

```sql
ALTER TABLE strategy2_candidates ADD COLUMN trend_type TEXT;
ALTER TABLE strategy2_candidates ADD COLUMN ma20 REAL;
ALTER TABLE strategy2_candidates ADD COLUMN ma60 REAL;
ALTER TABLE strategy2_candidates ADD COLUMN ma20_slope REAL;
ALTER TABLE strategy2_candidates ADD COLUMN return_20 REAL;
```

不得删除或重建现有表。

旧候选的趋势字段允许为空。

### 7.3 下降趋势审计信息

下降趋势股票不会写入 `strategy2_candidates`。

扫描器应写入：

```text
task_stocks.status = scanned
task_stocks.status_reason = DOWNTREND_FILTERED
```

建议将以下结构序列化为JSON写入现有 `task_stocks.error_detail`，避免新增任务明细表字段：

```json
{
  "trendType": "DOWNTREND",
  "ma20": 10.25,
  "ma60": 11.10,
  "ma20Slope": -0.021,
  "return20": -0.086,
  "conditions": [
    "CLOSE_BELOW_MA20",
    "MA20_BELOW_MA60",
    "MA20_SLOPE_NEGATIVE",
    "RETURN20_BELOW_MINUS_5_PERCENT"
  ]
}
```

---

## 8. 接口与前端方案

### 8.1 接口返回字段

策略2候选列表和详情增加：

```json
{
  "trend_type": "UPTREND_OR_SIDEWAYS",
  "ma20": 10.25,
  "ma60": 9.98,
  "ma20_slope": 0.012,
  "return_20": 0.035
}
```

接口保持向后兼容，旧候选字段为空时不得报错。

### 8.2 前端展示

在 `Strategy2Results.vue` 中：

- 候选表新增“走势趋势”字段，显示“上涨或横盘”。
- 候选详情或展开区域展示 MA20、MA60、MA20斜率、20日涨跌幅。
- 百分比字段按现有页面风格格式化。
- 空值显示 `--`。
- 不增加趋势配置控件。

### 8.3 前端文案

```text
UPTREND_OR_SIDEWAYS → 上涨或横盘
DOWNTREND → 下降趋势
DOWNTREND_FILTERED → 下降趋势过滤
```

---

## 9. 可以实施的代码方案

### 9.1 任务一：新增趋势模型和纯计算模块

修改模块：

- `strategy2/models.py`
- 新增 `strategy2/trend.py`
- 新增 `tests/test_strategy2_trend.py`

实现逻辑：

```text
evaluate_trend(data)
1. 校验至少60日数据。
2. 提取收盘价。
3. 按规定下标计算MA20、MA60、MA20_SLOPE_5、RETURN_20。
4. 逐项记录命中的下降趋势条件。
5. 四项全部命中时返回DOWNTREND，否则返回UPTREND_OR_SIDEWAYS。
```

输入：

- 已校验、按日期升序的策略窗口日线。

输出：

- `Strategy2Trend`。

不允许修改：

- 原有指标和评分规则。
- 策略1模块。

完成验证：

```bash
python -m pytest tests/test_strategy2_trend.py tests/test_strategy2_models.py -v
```

### 9.2 任务二：接入策略2唯一评估入口

修改模块：

- `strategy2/engine.py`
- `tests/test_strategy2_engine.py`

实现要求：

- 基础指标计算完成后立即执行趋势判断。
- `DOWNTREND` 立即返回，状态原因为 `DOWNTREND_FILTERED`。
- 下降趋势不得调用风险、否决和评分函数。
- 非下降趋势保持现有行为不变。
- 所有返回路径中的 `Strategy2Evaluation` 均保留合理默认趋势对象。

完成验证：

```bash
python -m pytest tests/test_strategy2_engine.py tests/test_strategy2_trend.py -v
```

### 9.3 任务三：扩展扫描、重新评估和持久化

修改模块：

- `strategy2/scanner.py`
- `scanner/db.py`
- 对应策略2扫描和数据库测试

实现要求：

- `_build_strategy2_discovery()` 增加趋势字段。
- `upsert_strategy2_candidate()` 读写趋势字段。
- 数据库初始化兼容式增加趋势字段。
- 正常扫描和重新评估必须执行相同趋势过滤。
- 下降趋势任务股票写入 `DOWNTREND_FILTERED`。
- 将下降趋势指标JSON写入 `task_stocks.error_detail`。
- 重新评估后被过滤的旧候选必须删除。

完成验证：

```bash
python -m pytest tests/test_strategy2_acceptance_fixes.py tests/test_strategy2_recheck_fixes.py tests/test_db_strategy_fields.py -v
```

### 9.4 任务四：扩展API和前端结果页

修改模块：

- `server.py`
- `web/src/pages/Strategy2Results.vue`
- 相关接口和前端测试

实现要求：

- 候选列表和详情返回趋势字段。
- 前端明确显示“上涨或横盘”及四项趋势指标。
- 旧数据趋势字段为空时正常展示。
- 不新增策略配置项。

完成验证：

```bash
python -m pytest tests/test_strategy2_recheck_fixes.py tests/test_strategy2_final_fixes.py -v
cd web && npm run build
```

### 9.5 任务五：更新独立性测试与全量回归

修改模块：

- `tests/test_strategy2_independence.py`

实现要求：

- 将 `strategy2.trend` 纳入策略2允许模块。
- 确认 `strategy2/trend.py` 不导入策略1或 `analyzer.*`。
- 运行策略2测试、全量后端测试和前端构建。

完成验证：

```bash
python -m pytest tests/test_strategy2_independence.py tests/test_strategy2_*.py -v
python -m pytest tests/ -v
cd web && npm run build
```

---

## 10. 日志与异常处理方案

### 10.1 必须记录的日志

- 下降趋势过滤日志：任务ID、股票代码、评估日、四项趋势指标。
- 趋势计算异常日志。
- 数据不足无法计算趋势的日志。
- 重新评估导致候选被下降趋势过滤的日志。

### 10.2 异常处理

- 单只股票趋势计算失败不得中断整体扫描。
- 无效行情数据沿用 `INVALID_MARKET_DATA`。
- 数据不足沿用 `INSUFFICIENT_STRATEGY_DATA`。
- 趋势模块不得吞掉异常后将股票默认为上涨或横盘。
- API和前端必须兼容旧候选的空趋势字段。

---

## 11. 测试方案

### 11.1 单元测试

- 四项条件同时满足，返回 `DOWNTREND`。
- 缺少任意一项，返回 `UPTREND_OR_SIDEWAYS`。
- MA20、MA60计算正确。
- MA20五日斜率使用正确20日窗口。
- 20日涨跌幅使用 `closes[-21]`。
- 四个严格边界值行为正确。
- 不读取评估日之后的数据。
- 数据不足和无效数据处理正确。

### 11.2 引擎测试

- 下降趋势返回 `DOWNTREND_FILTERED`。
- 下降趋势不执行评分、风险和一票否决。
- 上涨或横盘继续执行现有完整策略。
- 原有策略2评分结果不因趋势模块发生变化。

### 11.3 数据库与扫描测试

- 新数据库创建趋势字段。
- 旧数据库自动兼容增加趋势字段。
- 候选趋势字段可正确写入和读取。
- 下降趋势不写入候选表。
- 下降趋势任务明细记录原因和指标JSON。
- 重新评估移除已转为下降趋势的旧候选。

### 11.4 接口测试

- 候选列表返回趋势字段。
- 候选详情返回趋势字段。
- 旧候选趋势字段为空时接口正常。
- 非策略2接口不受影响。

### 11.5 前端测试

- 策略2结果页展示趋势类型。
- 趋势指标格式化正确。
- 空趋势字段显示 `--`。
- 页面不出现趋势配置控件。

### 11.6 回归测试

- 策略1功能和结果不变。
- 策略2量干价稳评分规则不变。
- 策略2风险和一票否决规则不变。
- 策略2正常扫描、失败重试和重新评估可用。
- 全量后端测试通过。
- 前端构建通过。

---

## 12. 验收标准

1. 策略2能够识别并过滤已定义的下降趋势股票。
2. 策略2候选只包含 `UPTREND_OR_SIDEWAYS` 股票。
3. 趋势过滤不参与原有100分评分。
4. 下降趋势股票记录 `DOWNTREND_FILTERED`。
5. 趋势计算不存在未来数据泄漏和下标偏移。
6. 正常扫描和重新评估使用相同趋势规则。
7. 候选数据库、API和前端完整展示趋势信息。
8. 旧候选和旧数据库保持兼容。
9. 策略1和策略2原有评分逻辑不受影响。
10. 新增测试、全量后端测试和前端构建通过。

---

## 13. 给 Claude Code / Codex 的执行指令

请在当前策略2独立 worktree 中，将本文档作为增量需求执行。

执行要求：

1. 先阅读本文档和当前策略2实现，不要重新实现策略2。
2. 使用测试驱动开发，先新增失败测试，再实现功能。
3. 严格使用本文档定义的指标公式和Python下标口径。
4. 趋势判断必须是评分前置强制过滤，禁止改成评分项。
5. 不修改策略2现有量干价稳评分、一票否决和风险规则。
6. 不修改策略1逻辑。
7. 数据库仅允许兼容式新增字段。
8. 不覆盖或回退当前 worktree 中已有未提交修改。
9. 每完成一个任务立即运行对应测试。
10. 最终运行策略2测试、全量后端测试和前端构建。
11. 将执行过程、测试结果、失败和遗留问题追加到 `operations-log.md`。
12. 最终报告修改文件、核心逻辑、数据库变更、接口变更和测试结果。

---

## 14. 最终交付物

1. `strategy2/trend.py` 独立趋势模块。
2. 策略2模型和唯一评估入口变更。
3. 扫描与重新评估趋势过滤变更。
4. 数据库兼容迁移。
5. 策略2候选API和前端展示变更。
6. 趋势过滤相关测试。
7. 全量测试与前端构建结果。
8. 修改文件清单和遗留问题说明。
