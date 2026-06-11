# 开发方案文档：策略2价格路径与120日趋势过滤 V2

## 1. 需求背景

### 1.1 当前问题

上一版下降趋势证据包含：

```text
RETURN_60 = 当前收盘价 / 60日前收盘价 - 1
```

该指标只比较两个日期，忽略60日内部价格路径。股票可能在期间大幅上涨后持续下跌，最终价格恰好接近60日前价格，导致 `RETURN_60` 看似接近平盘。

### 1.2 实际漏选案例：002468

`002468` 在 `2026-06-11` 的关键数据：

```text
60日前收盘价 = 14.03
当前收盘价 = 13.91
RETURN_60 = -0.86%

60日最高收盘价 = 17.93
当前价较60日最高点回撤 = -22.42%
最近20日均价较此前20日均价变化 = -10.86%
60日最大回撤约 = -23.98%
```

端点收益接近平盘，但实际价格路径是冲高后持续下降。仅使用 `RETURN_60` 不合理。

### 1.3 业务目标

- 移除下降趋势判断对60日起止收益的依赖。
- 使用价格路径、价格中枢、均线方向和120日长期结构综合判断。
- 同时识别 `002468` 和 `601607` 等明显下降趋势股票。
- 避免因单次历史高点或普通上涨回调误杀股票。

---

## 2. 需求目标

### 2.1 必须实现

- 使用本方案完全替代上一版下降趋势证据评分规则。
- 删除 `RETURN_60 < -5%` 下降证据。
- 增加60日高点回撤、20日价格中枢下移和60日线性趋势证据。
- 增加120日长期趋势确认。
- 只有同时满足必要条件、短中期证据、长期证据和总分条件时才过滤。
- 趋势过滤继续位于策略2评分、风险计算和一票否决之前。
- 将 `002468` 和 `601607` 加入离线回归测试。
- 增加反误杀测试。
- 数据库、API和前端展示完整趋势证据。

### 2.2 不做范围

- 不使用 `RETURN_60` 或 `RETURN_120` 端点收益作为下降证据。
- 不修改策略2原有100分评分。
- 不修改策略2风险和一票否决规则。
- 不修改策略1。
- 不引入MACD、RSI等额外指标。
- 不开放趋势阈值配置。
- 不重构无关模块。

---

## 3. 默认假设

1. 当前策略2趋势模块已存在于 `strategy2/trend.py`。
2. 默认策略2计算窗口为120个交易日。
3. 趋势判断必须使用完整120日数据。
4. 日线数据按日期升序排列并已完成合法性校验。
5. 本文档优先级高于此前的趋势过滤开发文档和下降趋势证据评分文档。
6. 当前worktree存在其他未提交修改，开发时不得覆盖或回退。

---

## 4. 最终下降趋势判定规则

### 4.1 核心判定

```text
DOWNTREND =
    necessary_conditions_met
    AND short_mid_score >= 4
    AND long_score >= 1
    AND total_evidence_score >= 6
```

其中：

```text
necessary_conditions_met =
    current_close < MA20
    AND MA20 < MA60

total_evidence_score = short_mid_score + long_score
```

说明：

- 必要条件用于确认当前价格仍处于短中期均线压制下。
- 短中期证据用于识别最近60日真实下降路径。
- 长期证据用于确认下降并非普通短期回调。
- 四组条件缺少任意一组，均返回 `UPTREND_OR_SIDEWAYS`。

### 4.2 短中期证据：8项

| 编号 | 证据 | 条件 | 稳定代码 |
|---|---|---|---|
| S1 | 当前价低于MA20 | `current_close < MA20` | `CLOSE_BELOW_MA20` |
| S2 | MA20低于MA60 | `MA20 < MA60` | `MA20_BELOW_MA60` |
| S3 | MA20向下 | `MA20_SLOPE_5 < 0` | `MA20_SLOPE_NEGATIVE` |
| S4 | MA60向下 | `MA60_SLOPE_10 < 0` | `MA60_SLOPE_NEGATIVE` |
| S5 | 当前价远离60日高点 | `DRAWDOWN_FROM_HIGH_60 <= -12%` | `DRAWDOWN_FROM_HIGH60_AT_LEAST_12_PERCENT` |
| S6 | 最近20日价格中枢下移 | `CENTER_SHIFT_20 <= -5%` | `LATEST20_CENTER_BELOW_PREVIOUS20_BY_5_PERCENT` |
| S7 | 位于60日区间底部 | `PRICE_POSITION_60 <= 30%` | `PRICE_POSITION60_BOTTOM_30_PERCENT` |
| S8 | 60日线性趋势向下 | `LINEAR_TREND_60 <= -3%` | `LINEAR_TREND60_BELOW_MINUS_3_PERCENT` |

每项命中计1分，`short_mid_score` 满分8分。

### 4.3 长期证据：3项

| 编号 | 证据 | 条件 | 稳定代码 |
|---|---|---|---|
| L1 | 中长期均线空头 | `MA60 < MA120` | `MA60_BELOW_MA120` |
| L2 | 当前价远离120日高点 | `DRAWDOWN_FROM_HIGH_120 <= -18%` | `DRAWDOWN_FROM_HIGH120_AT_LEAST_18_PERCENT` |
| L3 | 最近40日长期中枢下移 | `CENTER_SHIFT_40 <= -6%` | `LATEST40_CENTER_BELOW_PREVIOUS40_BY_6_PERCENT` |

每项命中计1分，`long_score` 满分3分。

### 4.4 总证据分

```text
total_evidence_score = short_mid_score + long_score
```

总分满分11分。

必要条件中的S1和S2仍各计入一次短中期证据分，不得重复计分。

---

## 5. 精确指标定义

所有指标只使用评估日 `T` 及之前的收盘价。

### 5.1 均线与斜率

```text
MA20 = mean(closes[-20:])
MA60 = mean(closes[-60:])
MA120 = mean(closes[-120:])

MA20_T_MINUS_5 = mean(closes[-25:-5])
MA20_SLOPE_5 = MA20 / MA20_T_MINUS_5 - 1

MA60_T_MINUS_10 = mean(closes[-70:-10])
MA60_SLOPE_10 = MA60 / MA60_T_MINUS_10 - 1
```

### 5.2 高点回撤

```text
MAX_CLOSE_60 = max(closes[-60:])
DRAWDOWN_FROM_HIGH_60 = current_close / MAX_CLOSE_60 - 1

MAX_CLOSE_120 = max(closes[-120:])
DRAWDOWN_FROM_HIGH_120 = current_close / MAX_CLOSE_120 - 1
```

使用最高收盘价，不使用盘中最高价，避免单日异常影线过度影响。

### 5.3 价格中枢变化

```text
LATEST_20_CENTER = mean(closes[-20:])
PREVIOUS_20_CENTER = mean(closes[-40:-20])
CENTER_SHIFT_20 = LATEST_20_CENTER / PREVIOUS_20_CENTER - 1

LATEST_40_CENTER = mean(closes[-40:])
PREVIOUS_40_CENTER = mean(closes[-80:-40])
CENTER_SHIFT_40 = LATEST_40_CENTER / PREVIOUS_40_CENTER - 1
```

价格中枢变化用于识别一段时间内整体价格平台是否下移，不使用两个单日端点。

### 5.4 60日价格区间位置

```text
MIN_CLOSE_60 = min(closes[-60:])
MAX_CLOSE_60 = max(closes[-60:])

PRICE_POSITION_60 =
    (current_close - MIN_CLOSE_60)
    / (MAX_CLOSE_60 - MIN_CLOSE_60)
```

若 `MAX_CLOSE_60 == MIN_CLOSE_60`：

```text
PRICE_POSITION_60 = 0.5
```

### 5.5 60日线性趋势

对最近60日收盘价执行普通最小二乘线性回归：

```text
x = [0, 1, 2, ..., 59]
y = closes[-60:]
SLOPE_60 = OLS_SLOPE(x, y)

LINEAR_TREND_60 =
    SLOPE_60 * 59 / mean(closes[-60:])
```

`LINEAR_TREND_60` 表示拟合趋势线在60日窗口内的标准化总变化比例。

不得使用简单起止收益替代。

---

## 6. 数据不足与异常行为

- 少于120个有效交易日：返回 `INSUFFICIENT_TREND_DATA`，不得默认判定为上涨或横盘。
- 趋势计算数据不足时，该股票不进入候选。
- 分母小于等于0或指标非有限数时，返回 `INVALID_MARKET_DATA`。
- 不允许按可用证据数量动态降低阈值。
- 不允许跳过长期证据后继续按短中期规则入选。

原因：本方案明确要求120日长期确认。数据不足时无法证明股票不是长期下降趋势，应采用保守排除。

---

## 7. 严格边界

- `current_close == MA20`：必要条件不成立。
- `MA20 == MA60`：必要条件不成立。
- `short_mid_score == 4`：满足短中期分数要求。
- `long_score == 1`：满足长期分数要求。
- `total_evidence_score == 6`：满足总分要求。
- `DRAWDOWN_FROM_HIGH_60 == -12%`：命中。
- `CENTER_SHIFT_20 == -5%`：命中。
- `PRICE_POSITION_60 == 30%`：命中。
- `LINEAR_TREND_60 == -3%`：命中。
- `DRAWDOWN_FROM_HIGH_120 == -18%`：命中。
- `CENTER_SHIFT_40 == -6%`：命中。
- 其他斜率条件保持严格小于0。

---

## 8. 样本验收

### 8.1 002468

截至 `2026-06-11`：

```text
current_close = 13.91
MA20 = 14.74
MA60 = 15.29
DRAWDOWN_FROM_HIGH_60 = -22.42%
CENTER_SHIFT_20 = -10.86%
PRICE_POSITION_60 = 18.46%
DRAWDOWN_FROM_HIGH_120 = -22.42%
```

预期：

```text
necessary_conditions_met = true
short_mid_score >= 4
long_score >= 1
total_evidence_score >= 6
trend_type = DOWNTREND
status_reason = DOWNTREND_FILTERED
passed = false
```

### 8.2 601607

截至 `2026-06-11`：

```text
current_close = 16.24
MA20 = 16.38
MA60 = 16.80
MA120 = 17.14
MA20_SLOPE_5 = -1.33%
MA60_SLOPE_10 = -0.88%
PRICE_POSITION_60 = 16.15%
LINEAR_TREND_60 ≈ -4.95%
```

预期：

```text
necessary_conditions_met = true
short_mid_score >= 4
long_score >= 1
total_evidence_score >= 6
trend_type = DOWNTREND
status_reason = DOWNTREND_FILTERED
passed = false
```

---

## 9. 数据模型与数据库方案

### 9.1 趋势模型

扩展 `Strategy2Trend`：

```python
@dataclass
class Strategy2Trend:
    trend_type: str = ""
    short_mid_score: int = 0
    long_score: int = 0
    total_evidence_score: int = 0
    necessary_conditions_met: bool = False
    ma20: float = 0.0
    ma60: float = 0.0
    ma120: float = 0.0
    ma20_slope: float = 0.0
    ma60_slope: float = 0.0
    drawdown_from_high_60: float = 0.0
    center_shift_20: float = 0.0
    price_position_60: float = 0.5
    linear_trend_60: float = 0.0
    drawdown_from_high_120: float = 0.0
    center_shift_40: float = 0.0
    downtrend_conditions: list[str] = field(default_factory=list)
```

旧字段 `return_20` 和 `return_60` 可保留用于接口兼容，但不得参与新趋势判断。

### 9.2 数据库兼容迁移

为 `strategy2_candidates` 兼容式新增：

```sql
short_mid_score INTEGER DEFAULT 0
long_score INTEGER DEFAULT 0
total_evidence_score INTEGER DEFAULT 0
necessary_conditions_met INTEGER DEFAULT 0
drawdown_from_high_60 REAL
center_shift_20 REAL
linear_trend_60 REAL
drawdown_from_high_120 REAL
center_shift_40 REAL
```

已有 `ma120`、`ma60_slope`、`price_position_60`、`downtrend_conditions` 字段继续复用。

不得删除或重建表。

### 9.3 API与前端

策略2候选列表和详情增加上述趋势字段。

策略2结果页展示：

- 短中期证据分，例如 `4 / 8`
- 长期证据分，例如 `1 / 3`
- 总证据分，例如 `6 / 11`
- 60日高点回撤
- 最近20日中枢变化
- 60日线性趋势
- 120日高点回撤
- 最近40日中枢变化
- 命中证据列表

不新增趋势配置控件。

---

## 10. 可以实施的代码任务

### 10.1 任务一：升级趋势模型和纯计算

修改：

- `strategy2/models.py`
- `strategy2/trend.py`
- `tests/test_strategy2_trend.py`

要求：

- 删除 `RETURN_60` 对下降判断的影响。
- 实现8项短中期证据和3项长期证据。
- 实现必要条件、分组阈值和总分阈值。
- 实现120日数据不足保守排除。
- 添加精确公式和边界测试。

### 10.2 任务二：引擎、扫描和重新评估

修改：

- `strategy2/engine.py`
- `strategy2/scanner.py`
- 对应测试

要求：

- `INSUFFICIENT_TREND_DATA` 不得进入候选。
- `DOWNTREND` 在评分、风险和否决之前返回。
- 正常扫描与重新评估使用相同规则。
- 重新评估后移除不再符合条件的旧候选。

### 10.3 任务三：数据库、API与前端

修改：

- `scanner/db.py`
- `server.py`
- `web/src/pages/Strategy2Results.vue`
- 对应测试

要求：

- 兼容式新增字段。
- 完整序列化和反序列化证据。
- 旧数据空字段正常展示。

### 10.4 任务四：样本与反误杀测试

必须新增离线固定夹具：

- `002468` 截至 `2026-06-11`
- `601607` 截至 `2026-06-11`

测试不得依赖在线数据源。

必须验证：

- 两只股票均返回 `DOWNTREND_FILTERED`。
- 两只股票均不进入候选。
- 高位横盘不因历史高点回撤单项被过滤。
- 上涨趋势中的正常回调不被过滤。
- 仅短期急跌但无长期证据时不被过滤。
- 仅长期弱势但当前价已站上MA20时不被过滤。

### 10.5 验证命令

```bash
python -m pytest tests/test_strategy2_trend.py tests/test_strategy2_engine.py -v
python -m pytest tests/test_strategy2_*.py -v
python -m pytest tests/ -v
cd web && npm run build
```

---

## 11. 日志与异常处理

- 下降趋势过滤日志记录必要条件、三类分数和全部证据指标。
- `INSUFFICIENT_TREND_DATA` 记录实际数据天数。
- 指标计算异常不得默认为上涨或横盘。
- 单股趋势计算失败不得中断整体扫描。
- `task_stocks.error_detail` 保存结构化趋势证据JSON。

---

## 12. 验收标准

1. `RETURN_60` 不再参与下降趋势判断。
2. 下降趋势使用8项短中期证据和3项长期证据。
3. 必须满足当前价低于MA20且MA20低于MA60。
4. 必须满足短中期至少4分、长期至少1分、总分至少6分。
5. 少于120日数据返回 `INSUFFICIENT_TREND_DATA` 并排除。
6. `002468` 和 `601607` 离线样本均被过滤。
7. 反误杀测试通过。
8. 趋势判断不改变策略2原有100分评分、风险和否决规则。
9. 正常扫描和重新评估规则一致。
10. 数据库、API和前端完整展示趋势路径证据。
11. 策略2测试、全量后端测试和前端构建通过。

---

## 13. 给 Claude Code / Codex 的执行指令

请将本文档作为策略2趋势过滤的最终V2升级方案执行。

1. 本文档替代此前所有策略2下降趋势判定规则。
2. 先阅读当前趋势实现和测试，不要重新实现策略2。
3. 使用测试驱动开发，先写失败测试。
4. 严格按本文档公式实现价格路径和120日长期确认。
5. 禁止使用 `RETURN_60`、`RETURN_120` 端点收益作为下降证据。
6. 必须增加 `002468` 和 `601607` 离线回归测试。
7. 必须增加反误杀测试。
8. 趋势过滤继续在评分、风险和否决之前执行。
9. 不修改策略2原有评分、风险和否决规则。
10. 不修改策略1。
11. 数据库只允许兼容式新增字段。
12. 不覆盖或回退当前worktree中的已有未提交修改。
13. 每完成一个任务立即运行对应测试。
14. 最终运行策略2测试、全量后端测试和前端构建。
15. 将执行过程和测试结果追加到 `operations-log.md`。
16. 完成后提交代码并报告修改文件、核心规则、数据库/API变更和测试结果。

---

## 14. AI开发提示语

```text
请升级策略2下降趋势过滤为“价格路径 + 120日长期确认”V2。

工作目录：
D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy2-extreme-dry-stable

开发依据：
docs/superpowers/specs/2026-06-11-strategy2-path-and-120d-trend-filter-v2.md

本文档替代此前所有策略2下降趋势判定规则。

最终过滤规则：
1. 必要条件：当前价 < MA20 且 MA20 < MA60。
2. 8项短中期证据至少命中4项。
3. 3项120日长期证据至少命中1项。
4. 总证据分至少6分。

禁止使用RETURN_60或RETURN_120端点收益作为下降证据。

必须使用价格路径指标：
- 60日高点回撤
- 最近20日较此前20日的价格中枢变化
- 60日线性趋势
- 60日价格区间位置
- MA20和MA60斜率
- MA60与MA120关系
- 120日高点回撤
- 最近40日较此前40日的价格中枢变化

执行要求：
1. 先完整阅读开发文档和当前策略2实现。
2. 使用测试驱动开发，先写失败测试。
3. 将002468和601607截至2026-06-11的数据加入离线回归测试，确保两者均被DOWNTREND_FILTERED。
4. 增加高位横盘、上涨正常回调、仅短期急跌等反误杀测试。
5. 少于120日趋势数据时返回INSUFFICIENT_TREND_DATA并排除。
6. 趋势过滤必须在策略2评分、风险和一票否决之前执行。
7. 不修改策略2原有评分、风险和否决规则。
8. 不修改策略1。
9. 数据库只允许兼容式新增字段。
10. 正常扫描和重新评估必须使用同一趋势规则。
11. 不覆盖或回退当前worktree中的已有未提交修改。
12. 完成后运行策略2测试、全量后端测试和前端构建。
13. 将执行结果追加到operations-log.md并提交代码。

直接开始执行，不需要再次确认文档中已经明确的事项。
```

---

## 15. 最终交付物

1. 升级后的策略2价格路径趋势模块。
2. 120日长期确认逻辑。
3. 扩展后的趋势数据模型。
4. 正常扫描与重新评估变更。
5. 数据库兼容迁移。
6. API与前端趋势证据展示。
7. `002468`、`601607`离线回归测试。
8. 反误杀测试。
9. 全量测试和前端构建结果。
