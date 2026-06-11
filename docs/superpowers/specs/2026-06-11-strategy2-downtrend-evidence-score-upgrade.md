# 开发方案文档：策略2下降趋势证据评分升级

## 1. 需求背景

### 1.1 当前问题

策略2当前使用四项条件全部满足才过滤下降趋势：

```text
current_close < MA20
MA20 < MA60
MA20_SLOPE_5 < 0
RETURN_20 < -5%
```

该规则过度依赖最近20日跌幅。长期下降趋势股票在短期反弹或跌势放缓后，可能仅因 `RETURN_20` 未低于 `-5%` 而被错误归类为 `UPTREND_OR_SIDEWAYS`。

### 1.2 实际漏选案例：601607 上海医药

评估日 `2026-06-11` 的已保存趋势数据：

```text
current_close = 16.24
MA20 = 16.38
MA60 = 16.80
MA20_SLOPE_5 = -1.33%
RETURN_20 = -3.85%
```

旧规则前三项命中，但因20日跌幅未低于 `-5%`，该股票仍进入候选。

进一步检查中长期走势：

```text
MA20 < MA60 < MA120
MA60_SLOPE_10 ≈ -0.88%
RETURN_60 ≈ -6.07%
RETURN_120 ≈ -8.15%
PRICE_POSITION_60 ≈ 16%
```

该股票具有明确的中长期下降证据，应被策略2过滤。

### 1.3 业务目标

将下降趋势判断升级为多时间尺度证据评分，降低单一短期指标造成的漏判，同时保留明确的空头排列作为必要条件，避免正常上涨回调被过度过滤。

---

## 2. 需求目标

### 2.1 必须实现

- 将旧“四项全部满足”规则替换为下降趋势证据评分制。
- 使用短期、中期和长期趋势证据综合判断。
- `MA20 < MA60` 必须作为下降趋势过滤的必要条件。
- 下降趋势证据分达到5分时强制过滤。
- 下降趋势过滤仍在策略2评分、风险和一票否决之前执行。
- 趋势证据分不参与策略2原有100分评分。
- 持久化并展示新增趋势指标、证据分和命中证据。
- 正常扫描和重新评估使用完全一致的规则。
- 将 `601607` 加入真实数据回归验证，确保不会再次进入候选。

### 2.2 可选增强

- 策略2结果页支持查看候选未命中的下降趋势证据。
- 任务详情页支持按 `DOWNTREND_FILTERED` 筛选股票。

### 2.3 不做范围

- 不修改策略2量干50分、价稳50分评分。
- 不修改策略2一票否决规则和风险比规则。
- 不修改策略1。
- 不开放趋势阈值配置，本期固定为代码规则。
- 不引入MACD、RSI、布林带等额外技术指标。
- 不重构无关模块。

---

## 3. 默认假设

1. 当前策略2趋势模块已经存在于 `strategy2/trend.py`。
2. 当前策略2趋势结果模型为 `Strategy2Trend`。
3. 策略2默认计算窗口为120个交易日。
4. 趋势计算只使用评估日及之前的数据。
5. 日线数据已按日期升序排列，并经过现有校验。
6. SQLite 变更使用兼容式新增字段，不重建现有表。
7. 当前 worktree 存在其他未提交修改，开发时不得覆盖或回退。

---

## 4. 产品设计方案

### 4.1 用户可见结果

策略2继续只收录未被确认处于下降趋势的股票。

候选详情增加展示：

- 趋势类型
- 下降趋势证据分
- 命中的下降趋势证据
- MA20、MA60、MA120
- MA20最近5日斜率
- MA60最近10日斜率
- 60日涨跌幅
- 近60日价格区间位置

### 4.2 用户使用流程

1. 用户启动策略2扫描。
2. 系统执行数据获取和流动性过滤。
3. 策略2计算多时间尺度趋势指标。
4. 系统计算下降趋势证据分。
5. 满足必要条件且证据分达到5分时，股票被强制过滤。
6. 其他股票继续执行现有策略2判断。

### 4.3 交互规则

- 趋势证据评分无需用户配置。
- 被过滤股票记录 `DOWNTREND_FILTERED`。
- 候选结果中不应出现 `DOWNTREND`。
- 重新评估历史任务时，旧候选若满足新下降趋势规则，必须从候选表移除。

---

## 5. 新下降趋势规则

### 5.1 核心判定

```text
DOWNTREND =
    MA20 < MA60
    AND downtrend_evidence_score >= 5
```

其中：

- `MA20 < MA60` 是必要条件。
- 证据分满分7分。
- 达到5分时判定为下降趋势。
- 未满足必要条件或证据分低于5分时，返回 `UPTREND_OR_SIDEWAYS`。

### 5.2 下降趋势证据

| 证据 | 条件 | 分值 | 稳定代码 |
|---|---|---:|---|
| 当前价低于MA20 | `current_close < MA20` | 1 | `CLOSE_BELOW_MA20` |
| 短中期均线空头 | `MA20 < MA60` | 1 | `MA20_BELOW_MA60` |
| 中长期均线空头 | `MA60 < MA120` | 1 | `MA60_BELOW_MA120` |
| MA20向下 | `MA20_SLOPE_5 < 0` | 1 | `MA20_SLOPE_NEGATIVE` |
| MA60向下 | `MA60_SLOPE_10 < 0` | 1 | `MA60_SLOPE_NEGATIVE` |
| 中期跌幅明显 | `RETURN_60 < -5%` | 1 | `RETURN60_BELOW_MINUS_5_PERCENT` |
| 位于60日区间底部 | `PRICE_POSITION_60 <= 30%` | 1 | `PRICE_POSITION60_BOTTOM_30_PERCENT` |

### 5.3 精确指标定义

```text
MA20 = mean(closes[-20:])
MA60 = mean(closes[-60:])
MA120 = mean(closes[-120:])

MA20_T_MINUS_5 = mean(closes[-25:-5])
MA20_SLOPE_5 = MA20 / MA20_T_MINUS_5 - 1

MA60_T_MINUS_10 = mean(closes[-70:-10])
MA60_SLOPE_10 = MA60 / MA60_T_MINUS_10 - 1

RETURN_60 = closes[-1] / closes[-61] - 1

MIN_CLOSE_60 = min(closes[-60:])
MAX_CLOSE_60 = max(closes[-60:])
PRICE_POSITION_60 =
    (closes[-1] - MIN_CLOSE_60) / (MAX_CLOSE_60 - MIN_CLOSE_60)
```

若 `MAX_CLOSE_60 == MIN_CLOSE_60`：

```text
PRICE_POSITION_60 = 0.5
```

将完全横盘视为中性位置，不命中区间底部证据。

### 5.4 数据不足行为

- 少于60日：沿用 `INSUFFICIENT_STRATEGY_DATA`。
- 60至69日：无法计算 `MA60_SLOPE_10`，该证据不加分。
- 60至119日：无法计算 `MA120`，该证据不加分。
- 数据不足的证据不得默认命中，也不得抛异常。
- 证据阈值仍固定为5分，不按可用证据数量动态降低。
- 默认120日策略窗口下，全部7项证据均可计算。

### 5.5 严格边界

- `MA20 == MA60`：不满足必要条件，也不获得对应证据分。
- `MA60 == MA120`：不获得对应证据分。
- `MA20_SLOPE_5 == 0`：不获得对应证据分。
- `MA60_SLOPE_10 == 0`：不获得对应证据分。
- `RETURN_60 == -5%`：不获得对应证据分。
- `PRICE_POSITION_60 == 30%`：获得区间底部证据分。
- `downtrend_evidence_score == 5`：判定为下降趋势。

### 5.6 601607验收结果

使用 `2026-06-11` 日线数据时，`601607` 预计命中：

```text
CLOSE_BELOW_MA20
MA20_BELOW_MA60
MA60_BELOW_MA120
MA20_SLOPE_NEGATIVE
MA60_SLOPE_NEGATIVE
RETURN60_BELOW_MINUS_5_PERCENT
PRICE_POSITION60_BOTTOM_30_PERCENT
```

预期：

```text
downtrend_evidence_score = 7
trend_type = DOWNTREND
status_reason = DOWNTREND_FILTERED
passed = false
```

---

## 6. 技术架构方案

### 6.1 修改模块

- `strategy2/trend.py`
- `strategy2/models.py`
- `strategy2/engine.py`
- `strategy2/scanner.py`
- `scanner/db.py`
- `server.py`
- `web/src/pages/Strategy2Results.vue`
- `tests/test_strategy2_trend.py`
- 相关策略2扫描、数据库、接口和前端测试

### 6.2 模型扩展

将 `Strategy2Trend` 扩展为：

```python
@dataclass
class Strategy2Trend:
    trend_type: str = ""
    evidence_score: int = 0
    ma20: float = 0.0
    ma60: float = 0.0
    ma120: float | None = None
    ma20_slope: float = 0.0
    ma60_slope: float | None = None
    return_20: float = 0.0
    return_60: float = 0.0
    price_position_60: float = 0.5
    downtrend_conditions: list[str] = field(default_factory=list)
```

保留现有 `return_20` 字段用于兼容和展示，但新下降趋势判定不再依赖它。

### 6.3 趋势模块核心逻辑

```text
evaluate_trend(data)
1. 校验至少60日数据。
2. 计算全部可用趋势指标。
3. 对七项下降证据逐项判断并记录稳定代码。
4. evidence_score = 命中证据数量。
5. necessary_condition = MA20 < MA60。
6. necessary_condition 且 evidence_score >= 5 时返回DOWNTREND。
7. 其他情况返回UPTREND_OR_SIDEWAYS。
```

### 6.4 执行顺序

保持现有顺序：

```text
数据校验
→ 策略窗口截取
→ 基础指标计算
→ 新下降趋势证据评分
→ DOWNTREND直接返回
→ 风险计算
→ 一票否决
→ 量干价稳评分
```

---

## 7. 数据库与接口设计

### 7.1 策略2候选表兼容式新增字段

```sql
ALTER TABLE strategy2_candidates ADD COLUMN trend_evidence_score INTEGER DEFAULT 0;
ALTER TABLE strategy2_candidates ADD COLUMN ma120 REAL;
ALTER TABLE strategy2_candidates ADD COLUMN ma60_slope REAL;
ALTER TABLE strategy2_candidates ADD COLUMN return_60 REAL;
ALTER TABLE strategy2_candidates ADD COLUMN price_position_60 REAL;
ALTER TABLE strategy2_candidates ADD COLUMN downtrend_conditions TEXT;
```

`downtrend_conditions` 使用JSON数组字符串存储。

不得删除、重建或破坏现有表。

### 7.2 API新增字段

策略2候选列表和详情增加：

```json
{
  "trend_evidence_score": 3,
  "ma120": 18.21,
  "ma60_slope": 0.004,
  "return_60": 0.025,
  "price_position_60": 0.72,
  "downtrend_conditions": [
    "CLOSE_BELOW_MA20",
    "MA20_SLOPE_NEGATIVE"
  ]
}
```

旧候选缺少新字段时，API必须正常返回默认值或空值。

### 7.3 下降趋势审计

下降趋势股票不写入候选表。

`task_stocks` 应记录：

```text
status = scanned
status_reason = DOWNTREND_FILTERED
```

`error_detail` 中保存趋势指标、证据分和命中证据，便于定位过滤原因。

---

## 8. 前端设计

策略2结果页增加：

- 下降趋势证据分，例如 `3 / 7`。
- MA120。
- MA60最近10日斜率。
- 60日涨跌幅。
- 近60日价格区间位置。
- 命中的下降趋势证据列表。

展示规则：

- 候选趋势仍显示“上涨或横盘”。
- 百分比按现有格式展示。
- 空值显示 `--`。
- 不新增趋势配置控件。

---

## 9. 可以实施的代码任务

### 9.1 任务一：升级趋势模型与纯计算

修改：

- `strategy2/models.py`
- `strategy2/trend.py`
- `tests/test_strategy2_trend.py`

要求：

- 按本文档精确公式计算新增指标。
- 用证据评分替换旧四项全满足规则。
- 保留现有字段兼容性。
- 增加60至69日、60至119日数据不足测试。
- 增加全部严格边界测试。
- 增加 `601607` 特征回归测试。

验证：

```bash
python -m pytest tests/test_strategy2_trend.py tests/test_strategy2_models.py -v
```

### 9.2 任务二：接入引擎、扫描与重新评估

修改：

- `strategy2/engine.py`
- `strategy2/scanner.py`
- 相关引擎和扫描测试

要求：

- 引擎继续在评分、风险和否决之前过滤下降趋势。
- 下降趋势评估返回完整证据数据。
- 正常扫描与重新评估使用相同趋势规则。
- 重新评估后，符合新规则的旧候选必须移除。
- `601607` 不得进入候选。

验证：

```bash
python -m pytest tests/test_strategy2_engine.py tests/test_strategy2_acceptance_fixes.py tests/test_strategy2_recheck_fixes.py -v
```

### 9.3 任务三：扩展数据库与API

修改：

- `scanner/db.py`
- `server.py`
- 相关数据库和接口测试

要求：

- 兼容式新增字段。
- 正确序列化和反序列化 `downtrend_conditions`。
- 候选列表和详情返回新增字段。
- 旧数据库和旧候选保持兼容。

验证：

```bash
python -m pytest tests/test_db_strategy_fields.py tests/test_strategy2_final_fixes.py tests/test_strategy2_recheck_fixes.py -v
```

### 9.4 任务四：扩展前端展示

修改：

- `web/src/pages/Strategy2Results.vue`
- 相关前端测试

要求：

- 展示新增趋势指标、证据分和命中证据。
- 空值兼容。
- 不增加配置项。

验证：

```bash
cd web && npm run build
```

### 9.5 任务五：全量回归

验证：

```bash
python -m pytest tests/test_strategy2_*.py -v
python -m pytest tests/ -v
cd web && npm run build
```

不得因升级趋势规则破坏策略1或策略2其他业务规则。

---

## 10. 测试方案

### 10.1 趋势单元测试

- 七项证据分别命中和不命中。
- `MA20 < MA60` 必要条件行为正确。
- 证据分4分不下降，5分下降。
- 证据分计算正确且不重复计分。
- `MA120`、`MA60_SLOPE_10`、`RETURN_60`、`PRICE_POSITION_60`计算正确。
- 60日价格区间完全相等时位置为0.5。
- 60至69日和60至119日数据行为正确。
- 所有严格边界正确。
- 不读取评估日之后的数据。

### 10.2 真实样本回归测试

使用数据库中 `601607` 截至 `2026-06-11` 的日线数据验证：

- `evidence_score >= 5`
- `trend_type == DOWNTREND`
- `status_reason == DOWNTREND_FILTERED`
- `passed == false`
- 扫描后候选表不包含 `601607`

测试不得依赖在线数据源；应使用固定测试夹具或已脱敏的必要收盘价序列。

### 10.3 反误杀测试

- `MA20 >= MA60` 时，即使其他证据达到5分，也不判定下降趋势。
- 上涨趋势中的短期回调不被过滤。
- 长期横盘且价格处于区间底部时，不因单一位置证据被过滤。
- 中期均线转平、60日跌幅不足的横盘股票不被过滤。

### 10.4 回归测试

- 策略2原有量干价稳评分不变。
- 策略2风险和否决规则不变。
- 策略1不受影响。
- 正常扫描、失败重试、重新评估可用。
- 旧数据库可启动。
- 前端构建通过。

---

## 11. 验收标准

1. `601607` 使用 `2026-06-11` 数据时被判断为下降趋势并过滤。
2. 下降趋势采用必要条件加7项证据评分，不再依赖四项全部满足。
3. `MA20 < MA60` 是下降趋势必要条件。
4. 证据分达到5分时过滤。
5. 趋势判断不参与策略2原有100分评分。
6. 正常扫描和重新评估规则一致。
7. 新趋势指标和证据可被数据库、API和前端完整展示。
8. 旧数据库和旧候选兼容。
9. 反误杀测试通过。
10. 策略2测试、全量测试和前端构建通过。

---

## 12. 给 Claude Code / Codex 的执行指令

请将本文档作为对现有策略2趋势过滤功能的增量升级执行。

1. 先阅读当前 `strategy2/trend.py`、模型、引擎、扫描器、数据库和测试。
2. 不要重新实现策略2，只升级下降趋势判断。
3. 使用测试驱动开发，先新增失败测试。
4. 严格按本文档的公式、必要条件和7项证据评分实现。
5. 必须增加 `601607` 固定数据回归测试。
6. 不得使用在线数据源作为测试依赖。
7. 趋势过滤必须继续位于评分、风险和一票否决之前。
8. 不修改策略2原有评分、风险和否决规则。
9. 不修改策略1。
10. 数据库只允许兼容式新增字段。
11. 不覆盖或回退当前worktree中的已有未提交修改。
12. 每完成一个任务立即运行对应测试。
13. 最终运行策略2测试、全量后端测试和前端构建。
14. 将开发过程、测试结果和遗留问题追加到 `operations-log.md`。
15. 完成后提交代码，并报告文件清单、核心规则、数据库/API变更和测试结果。

---

## 13. AI开发提示语

```text
请升级策略2的下降趋势过滤功能。

工作目录：
D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy2-extreme-dry-stable

开发依据：
docs/superpowers/specs/2026-06-11-strategy2-downtrend-evidence-score-upgrade.md

当前问题：
旧趋势规则要求四项条件全部满足，导致601607等明显处于中长期下降趋势的股票，仅因20日跌幅不足-5%而进入候选。

核心新规则：
DOWNTREND = MA20 < MA60 且下降趋势证据分 >= 5。

七项下降趋势证据，每项1分：
1. 当前价 < MA20
2. MA20 < MA60
3. MA60 < MA120
4. MA20最近5日斜率 < 0
5. MA60最近10日斜率 < 0
6. 60日涨跌幅 < -5%
7. 当前价位于近60日收盘价区间底部30%

执行要求：
1. 先完整阅读开发文档和当前策略2实现。
2. 使用测试驱动开发，先写失败测试。
3. 严格使用文档定义的公式和边界。
4. 将601607截至2026-06-11的固定数据加入离线回归测试，确保其被DOWNTREND_FILTERED。
5. 趋势过滤继续在评分、风险和一票否决之前执行。
6. 不修改策略2现有评分、风险和否决规则。
7. 不修改策略1。
8. 数据库只允许兼容式新增字段。
9. 正常扫描和重新评估必须使用同一趋势规则。
10. 不覆盖或回退当前worktree中的已有未提交修改。
11. 完成后运行策略2测试、全量后端测试和前端构建。
12. 将执行结果追加到operations-log.md并提交代码。

直接开始执行，不需要再次确认文档中已经明确的事项。
```

---

## 14. 最终交付物

1. 升级后的策略2趋势证据评分模块。
2. 扩展后的趋势模型。
3. 正常扫描与重新评估变更。
4. 数据库兼容迁移。
5. API与前端趋势证据展示。
6. `601607`离线回归测试。
7. 反误杀测试。
8. 全量测试和前端构建结果。
