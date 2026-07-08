# 策略5量干判断设计文档

## 1. 背景与目标

策略5当前定位是“短线强势冲刺后的盘整支撑机会”，核心入口是 `strategy5/engine.py::ShortSprintSupportEngine.evaluate_at()`。当前策略5已经具备：

- 短线强度识别：`ret_20d`、`ret_10d`、`ret_5d`、`single_day_surge`、`ret_50d`。
- 新高或近高确认：`new_120d_high`、`near_120d_high`。
- 均线支撑识别：MA5 / MA10 / MA20 / MA50。
- 放量下跌风险识别：`VOLUME_UP_DECLINE` / `CONSOLIDATION_VOLUME_UP_DECLINE`。

但策略5目前没有真正的“量干评分”。它更多是在判断“成交额是否足够活跃”和“是否存在放量下跌”，还没有系统判断冲刺后的卖压是否枯竭。

本设计目标：

1. 基于策略1-4已有经验，为策略5新增专用量干判断体系。
2. 不新建独立策略，不影响策略1、策略2、策略3、策略4。
3. 保持策略5扫描入口、API、旧字段兼容。
4. 量干只作为策略5质量增强层，不替代短线强度、新高、支撑、风控规则。
5. 识别“强势后的健康缩量”，排除“弱势阴跌缩量、放量破位、死盘缩量”。

---

## 2. 策略1-4经验总结

### 2.1 策略1经验：量干不是越低越好，必须有封顶规则

策略1的 `analyzer/volume_dry.py` 使用 0-12 分量干评分，核心经验是：

- 最近成交量低于 MA20 / MA50 可以加分。
- 成交量阶段性递减可以加分。
- 下跌日没有放量可以加分。
- 极低成交量可以加分。
- 但以下情况必须封顶或降级：
  - 放量大阴线。
  - 缩量但价格重心持续下移。
  - 股价处于近60日低位。
  - 放量滞涨。

对策略5的启发：

策略5不能只看 `V5/V20` 是否低。强势股冲刺后，缩量必须同时满足“价格不破、支撑有效、下跌量缩、没有放量滞涨”。否则低量可能只是无人接盘。

### 2.2 策略2经验：量干指标要简单、稳定、可解释

策略2的量干评分满分 50，核心指标是：

- `V5 / V20 <= 0.60`
- `V5 / V20 <= 0.50`
- `V3 < V5 < V10 < V20`
- 最近5日成交量处于近60日最低20%
- `return_5 >= -3%`

对策略5的启发：

策略5应复用这些稳定指标作为基础量干判断，因为它们可解释、易测试、边界清楚。但策略5是强势冲刺策略，阈值不能机械照搬：强势股缩量不一定要求极致到 0.50，重点是“冲刺后量能下降但价格仍守住短均线或支撑”。

### 2.3 策略3经验：量干必须和价稳、跌不动、支撑、盈亏比联动

策略3已经形成比较完整的交易质量过滤层：

- 量干评分：`volume_ratio_5_20`、成交量递减、量能分位、下跌日量能。
- 价稳评分：`range_5`、`close_range_5`、ATR 收缩、日涨跌收敛。
- 跌不动评分：不创新低、支撑有效、阴线实体缩小、下跌幅度收敛、下影线承接。
- 回避信号：放量破位、连续新低、阴线实体扩大、支撑失效。
- 最终交易状态还要结合支撑距离、止损空间、目标空间、盈亏比。

对策略5的启发：

策略5的量干不能孤立决定入选。最佳做法是新增“策略5量干质量层”，输出量干分、触发原因和风险提示，再由候选分类逻辑决定：

- 高质量量干：可以增强 `KEY_CANDIDATE`。
- 普通量干：最多 `WATCH_CANDIDATE`。
- 失败量干：即使短线强度达标，也应拒绝或降级。

### 2.4 策略4经验：强势题材/龙头回调里，连续放量阴线要强排除

策略4回调逻辑中，`CONSECUTIVE_HEAVY_BEAR_DAYS` 用于识别回调中的连续放量阴线。

对策略5的启发：

策略5也是强势股策略，最怕“强势后派发”。因此量干判断必须把以下情况作为强风险：

- 最近5-10日出现连续放量阴线。
- 冲高后成交量没有收缩，反而高位放大。
- 放量下跌跌破 MA10 / MA20 / 主支撑。

---

## 3. 策略5量干定义

策略5中的“量干”不应定义为单纯成交量低，而应定义为：

> 强势冲刺后，成交量相对前期明显收缩，下跌日量能不足，价格仍维持在关键均线或支撑附近，波动逐步收敛，说明短线获利盘和卖压正在衰减。

它必须同时回答四个问题：

1. 量是否真的缩了？
2. 缩量时价格有没有守住？
3. 下跌日是否没有明显放量？
4. 这是健康盘整，还是弱势阴跌 / 高位派发 / 死盘？

---

## 4. 建议新增指标

建议在 `Strategy5Indicators` 中新增以下字段，只追加字段，不删除旧字段。

### 4.1 基础成交量指标

| 字段 | 说明 |
|---|---|
| `v3` | 最近3日平均成交量 |
| `v5` | 最近5日平均成交量 |
| `v10` | 最近10日平均成交量 |
| `v20` | 最近20日平均成交量，当前已有 |
| `v50` | 最近50日平均成交量 |
| `volume_ratio_5_20` | `v5 / v20` |
| `volume_ratio_5_50` | `v5 / v50` |
| `volume_percentile_60` | `v5` 在近60日成交量中的分位，越低越干 |

### 4.2 下跌量能指标

| 字段 | 说明 |
|---|---|
| `down_volume_ratio_5` | 最近5日阴线成交量 / 最近5日总成交量 |
| `down_day_avg_volume_ratio_20` | 最近5日下跌日平均成交量 / `v20` |
| `has_big_down_volume` | 最近5日是否存在放量大跌 |
| `consecutive_heavy_bear_days` | 最近回调段是否存在连续放量阴线 |

### 4.3 价格配合指标

| 字段 | 说明 |
|---|---|
| `close_range_5` | 最近5日收盘价波动 |
| `atr_ratio_5_20` | ATR5 / ATR20，判断波动是否收缩 |
| `direction_efficiency_5` | 5日净涨跌幅 / 5日绝对波动合计，判断涨跌是否无力 |
| `no_new_low_5` | 最近5日是否没有创新低 |
| `bear_body_shrink` | 近期阴线实体是否缩小 |
| `down_return_contracting` | 下跌幅度是否收敛 |

### 4.4 支撑联动指标

| 字段 | 说明 |
|---|---|
| `dry_support_price` | 量干判断使用的支撑价，优先 MA10 / MA20 / 当前主支撑 |
| `dry_support_distance` | 当前价距离量干支撑的比例 |
| `dry_support_valid` | 最近5日是否守住量干支撑 |

---

## 5. 策略5量干评分设计

建议新增 `strategy5/volume_dry.py`，提供：

```python
def evaluate_strategy5_volume_dry(ind: Strategy5Indicators, config: dict) -> Strategy5VolumeDry:
    ...
```

新增数据结构：

```python
@dataclass
class Strategy5VolumeDry:
    volume_dry_score: int = 0
    volume_dry_level: str = ""
    volume_dry_reasons: list[str] = field(default_factory=list)
    volume_dry_warnings: list[str] = field(default_factory=list)
    volume_dry_rejects: list[str] = field(default_factory=list)
```

### 5.1 总分

建议满分 20 分，分为五个维度：

| 维度 | 分值 | 含义 |
|---|---:|---|
| 成交量收缩 | 6 | 量是否明显下降 |
| 缩量序列 | 4 | 是否逐步缩量 |
| 下跌无量 | 4 | 卖压是否衰减 |
| 价格守住 | 4 | 缩量时价格是否稳住 |
| 波动收敛 | 2 | 是否进入蓄力状态 |

### 5.2 成交量收缩，最高 6 分

规则：

- `volume_ratio_5_20 <= 0.75`：+2
- `volume_ratio_5_20 <= 0.65`：额外 +2
- `volume_ratio_5_50 <= 0.70`：+1
- `volume_percentile_60 <= 0.25`：+1

解释：

策略5是强势股，不宜一开始就要求 `V5/V20 <= 0.50`。过严会漏掉刚从冲刺转入盘整的票。建议用 `0.75 / 0.65` 做分层，`0.50` 只作为“极致量干”的额外标签。

### 5.3 缩量序列，最高 4 分

规则：

- `v3 < v5 < v10 < v20`：+3
- `v5 < v10 < v20`：+2
- `v5 < v20`：+1
- 最近5日中最低成交量出现在最近2日：+1

解释：

缩量序列比单日低量更可信。单日低量可能是偶然或停牌影响，连续缩量更能说明卖压衰减。

### 5.4 下跌无量，最高 4 分

规则：

- `down_day_avg_volume_ratio_20 <= 0.90`：+2
- `down_volume_ratio_5 <= 0.60`：+1
- 最近5日没有放量大跌：+1

一票否决：

- `has_big_down_volume == True`：加入 `DRY_BIG_DOWN_VOLUME`
- `consecutive_heavy_bear_days >= 2`：加入 `DRY_CONSECUTIVE_HEAVY_BEAR`

解释：

策略5最需要防的是高位派发。下跌日一旦放量，说明卖压没有枯竭，不能用“缩量”给它加分。

### 5.5 价格守住，最高 4 分

规则：

- `close >= ma10`：+1
- `close >= ma20`：+1
- `no_new_low_5 == True`：+1
- `dry_support_valid == True`：+1

解释：

策略5的量干必须服务于“冲刺后支撑”。如果价格没有守住 MA10 / MA20 或主支撑，缩量应视为风险，而不是机会。

### 5.6 波动收敛，最高 2 分

规则：

- `close_range_5 <= 0.06`：+1
- `atr_ratio_5_20 <= 0.85` 或 `direction_efficiency_5 <= 0.35`：+1

解释：

强势股冲刺后，健康盘整通常表现为涨跌幅收敛、波动下降。若量缩但振幅扩大，通常不是量干，而是分歧加大。

---

## 6. 分层规则

| 分层 | 条件 | 策略含义 |
|---|---|---|
| `EXTREME_DRY` | `score >= 17` 且无 reject | 极致量干，短线卖压明显衰减 |
| `HEALTHY_DRY` | `score >= 14` 且无 reject | 健康缩量，可增强重点候选 |
| `WATCH_DRY` | `score >= 10` 且无 reject | 有缩量迹象，但确认不足 |
| `NOT_DRY` | `score < 10` 且无 reject | 量干不足，不作为加分项 |
| `BAD_DRY` | 存在 reject | 缩量失败或放量风险，应拒绝或降级 |

建议入选联动：

- `KEY_CANDIDATE`：要求 `volume_dry_score >= 14`，或者支撑分极高且 `volume_dry_score >= 12`。
- `WATCH_CANDIDATE`：允许 `volume_dry_score >= 10`。
- 若存在 `volume_dry_rejects`，即使短线强度达标，也应进入 `REJECTED`，除非后续回测证明过严。

---

## 7. 必须排除或降级的情况

### 7.1 放量下跌

触发条件：

- 最近5日任一日 `daily_return <= -0.05` 且 `volume >= v20 * 1.3`
- 或最近5日任一日 `close < open` 且实体跌幅 `<= -0.04` 且 `volume >= v20 * 1.3`

处理：

- 加入 `DRY_BIG_DOWN_VOLUME`
- `volume_dry_level = BAD_DRY`
- 候选拒绝或至少降级为观察外。

### 7.2 连续放量阴线

触发条件：

- 最近回调段或最近5日内，连续2日阴线实体跌幅 `<= -0.03` 且成交量高于窗口均量 `1.2` 倍。

处理：

- 加入 `DRY_CONSECUTIVE_HEAVY_BEAR`
- 直接拒绝。

### 7.3 缩量阴跌

触发条件：

- `volume_ratio_5_20 <= 0.70`
- 且 `recent_5d_return < -0.05`
- 且 `no_new_low_5 == False` 或 `close < ma20`

处理：

- 加入 `DRY_SHRINKING_BEAR_DRIFT`
- 不允许 `KEY_CANDIDATE`。

### 7.4 死盘缩量

触发条件：

- `avg_turnover_10d` 接近流动性下限。
- `volume_percentile_60` 很低，但 `recent_20d_return`、`recent_50d_return` 不满足强势条件。
- 或 `strength_trigger == ""`。

处理：

- 策略5已有强度门槛时通常会排除。
- 若后续单独调用量干模块，必须输出 `DRY_LOW_LIQUIDITY_OR_NO_STRENGTH` 警告。

### 7.5 高位放量滞涨

触发条件：

- 最近5日任一日 `volume >= v20 * 1.5`
- 当日涨幅 `< 1%`
- 收盘位置低于当日振幅中位，即 `(close - low) / (high - low) < 0.5`

处理：

- 加入 `DRY_VOLUME_STALL`
- 量干分封顶 12 分。

---

## 8. 建议配置项

在 `DEFAULT_STRATEGY5_CONFIG` 中新增：

```yaml
strategy5:
  volume_dry_min_score_key: 14
  volume_dry_min_score_watch: 10
  volume_dry_ratio_5_20: 0.75
  volume_dry_strong_ratio_5_20: 0.65
  volume_dry_extreme_ratio_5_20: 0.50
  volume_dry_ratio_5_50: 0.70
  volume_dry_percentile_60: 0.25
  volume_dry_down_volume_ratio_5: 0.60
  volume_dry_down_day_avg_ratio_20: 0.90
  volume_dry_big_down_return: -0.05
  volume_dry_big_down_volume_ratio: 1.30
  volume_dry_consecutive_bear_days: 2
  volume_dry_close_range_5: 0.06
  volume_dry_atr_contract_ratio: 0.85
  volume_dry_direction_efficiency: 0.35
```

配置原则：

- 默认值要偏质量，不追求数量。
- 所有阈值必须进入 `strategy5/validation.py` 校验。
- 前端配置可以先不全部展示，只展示最重要的两个：`volume_dry_min_score_key`、`volume_dry_min_score_watch`。

---

## 9. 输出字段设计

建议在策略5候选输出中追加字段：

| 字段 | 说明 |
|---|---|
| `volume_dry_score` | 策略5量干分，0-20 |
| `volume_dry_level` | `EXTREME_DRY / HEALTHY_DRY / WATCH_DRY / NOT_DRY / BAD_DRY` |
| `volume_ratio_5_20` | V5/V20 |
| `volume_ratio_5_50` | V5/V50 |
| `volume_percentile_60` | 60日量能分位 |
| `down_volume_ratio_5` | 最近5日阴线量占比 |
| `down_day_avg_volume_ratio_20` | 下跌日量能相对 V20 |
| `close_range_5` | 收盘价5日波动 |
| `atr_ratio_5_20` | ATR收缩比 |
| `volume_dry_reasons` | 命中的量干原因 |
| `volume_dry_warnings` | 风险提示 |
| `volume_dry_rejects` | 量干拒绝原因 |

兼容要求：

- 不删除现有字段。
- `risk_tags`、`warn_tags` 可以继续保留旧含义。
- 新字段为空时前端显示 `--`，不能导致旧任务详情报错。

---

## 10. 建议代码落点

### 10.1 后端

建议修改：

- `strategy5/models.py`
  - 新增 `Strategy5VolumeDry`。
  - `Strategy5Indicators` 追加量干指标字段。
  - `Strategy5Evaluation` 增加 `volume_dry` 字段。
  - `to_candidate_dict()` 追加输出字段。

- `strategy5/indicators.py`
  - 计算 `v3/v5/v10/v50`、`volume_ratio_5_20`、`volume_ratio_5_50`、`volume_percentile_60`。
  - 计算 `down_volume_ratio_5`、`down_day_avg_volume_ratio_20`、`has_big_down_volume`。
  - 计算 `close_range_5`、`atr_ratio_5_20`、`direction_efficiency_5`、`no_new_low_5`、`bear_body_shrink`、`down_return_contracting`。

- 新增 `strategy5/volume_dry.py`
  - 实现 `evaluate_strategy5_volume_dry()`。
  - 只依赖 `Strategy5Indicators` 和 config，不依赖策略1-4模块。

- `strategy5/engine.py`
  - 在 `calculate_indicators()` 后调用量干模块。
  - 将结果传入 `Strategy5Evaluation`。

- `strategy5/filters.py`
  - 将量干拒绝接入 hard filter。
  - 将量干分接入 `classify_candidate()`。

- `strategy5/scorer.py`
  - 可选择将量干加入 score reasons。
  - 不建议直接大幅重构四维评分；先以候选质量过滤层接入。

- `strategy5/validation.py`
  - 新增配置项与范围校验。

### 10.2 前端

建议修改：

- `web/src/pages/Strategy5Results.vue`
  - 候选列表新增“量干分/量干等级”。
  - 详情中展示 `volume_dry_reasons`、`volume_dry_warnings`、`volume_dry_rejects`。

- `web/src/pages/StrategyConfig.vue`
  - 第一阶段只展示：
    - 重点候选量干最低分。
    - 观察候选量干最低分。
  - 其它阈值先通过 YAML 调整，避免前端配置过载。

---

## 11. 测试计划

### 11.1 单元测试

建议新增 `tests/test_strategy5_volume_dry.py`。

必须覆盖：

1. 强势冲刺后健康缩量，`volume_dry_score >= 14`。
2. `V5/V20 <= 0.65` 且 `v3 < v5 < v10 < v20` 加分。
3. 最近5日下跌日无放量，加分。
4. 价格守住 MA10 / MA20，加分。
5. 放量大跌触发 `DRY_BIG_DOWN_VOLUME`。
6. 连续放量阴线触发 `DRY_CONSECUTIVE_HEAVY_BEAR`。
7. 缩量阴跌触发 `DRY_SHRINKING_BEAR_DRIFT`。
8. 高位放量滞涨触发 warning 或封顶。
9. 全零成交量不能因为分位低而高分。
10. 数据不足时不抛异常，返回低分和稳定原因。

### 11.2 集成测试

建议扩展 `tests/test_strategy5_core_rules.py`。

必须覆盖：

1. 量干达标的强势支撑股可进入 `KEY_CANDIDATE`。
2. 量干不足但其它条件达标时，最多进入 `WATCH_CANDIDATE` 或被拒绝。
3. 量干 reject 时，短线强度达标也不能进入候选。
4. 旧字段兼容：旧任务候选没有量干字段时，API 和前端不报错。

### 11.3 回测验证

使用本地数据库，不重新拉外部数据。

建议命令：

```bash
python -m pytest tests/test_strategy5_volume_dry.py tests/test_strategy5_core_rules.py -q
python -m pytest tests/test_strategy5_backtester.py tests/test_strategy5_scanner.py tests/test_strategy5_db_api.py -q
python -m compileall strategy5 server.py -q
npm --prefix web test -- --run
npm --prefix web run build
```

如需要看效果，再运行策略5本地回测，对比新增前后：

- 候选数量。
- 重点候选数量。
- 5/10/20日胜率。
- 20日平均收益。
- 最大回撤。
- 新增量干等级分布。
- 被量干 reject 的股票列表和原因。

---

## 12. 不建议做的事情

1. 不要把策略1的 `analyzer/volume_dry.py` 直接导入策略5。
   - 原因：策略1服务杯柄/VCP低吸，策略5服务短线强势冲刺，业务语义不同。

2. 不要把策略2的 50 分量干体系完整照搬。
   - 原因：策略2追求极致量干价稳，策略5需要允许强势股冲刺后温和缩量。

3. 不要把量干作为唯一入选条件。
   - 原因：策略5仍必须先满足强势、新高/近高、支撑和风险过滤。

4. 不要为了增加候选数量放宽放量下跌规则。
   - 原因：策略5最大风险是强势后高位派发。

5. 不要删除旧输出字段。
   - 原因：旧任务、前端结果页和历史回测可能依赖旧字段。

---

## 13. 最终判断口径

策略5量干最终应服务于一句话：

> 这只强势股冲刺之后，是否已经从“资金猛烈进攻”进入“卖压衰减、价格守住、波动收敛、准备二次上攻”的状态？

如果只是低成交量，但同时出现以下任一情况，应判定为失败：

- 跌破支撑。
- 放量阴线。
- 连续新低。
- 缩量阴跌。
- 波动扩大。
- 没有短线强度。
- 流动性不足。

策略5的理想量干不是“没人交易”，而是“该卖的卖不动了，价格还站得住”。

