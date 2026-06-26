# 策略3量干到跌不动质量层 v2 设计

## 1. 背景

策略3当前定位是“强势回踩二次启动”，核心不是单独寻找量干股，而是在强趋势和健康回踩之后，确认回踩末端卖压收缩、价格企稳、二次转强。

`docs/dry-cannot-fall-strategy.md` 中“量干到跌不动”的思想可以补强策略3当前最弱的一层：`strategy3/volume_stability.py` 目前主要看 V5/V20、5日收盘区间、低点是否连续下移和阴线日均量，无法区分“缩量企稳”和“缩量阴跌”。

## 2. 目标

在不新建策略、不改变策略3五模块权重的前提下，把“量干后跌不动”的判断融入策略3的缩量企稳模块：

- 保持总分结构：趋势 25 + 回踩 25 + 缩量企稳 20 + 二次转强 15 + 风险收益 15。
- 只修改策略3相关代码和测试，不触碰策略1/策略2核心规则。
- 新增指标必须全部基于评估日及之前数据，不能使用未来数据。
- 新增否决规则只拦截明显坏形态，避免过度拟合到没有候选。
- 候选详情和数据库中保留关键诊断字段，方便前端确认“为什么是跌不动”。

## 3. 非目标

- 不复制参考文档的 100 分独立评分体系。
- 不创建 `analyzer/dry_cannot_fall.py` 等独立策略模块。
- 不把 `dry_cannot_fall_score >= 85` 作为硬入选门槛。
- 不改变策略3趋势、回踩、二次转强、风险收益模块的业务定义。
- 不改策略1/策略2扫描入口、候选表或评分规则。

## 4. 新增指标

在 `Strategy3Indicators` 和 `compute_indicators()` 中新增以下字段：

| 字段 | 含义 |
|---|---|
| `v3` | 最近3日平均成交量 |
| `return_5` | 最近5日涨跌幅 |
| `min_close_5` | 最近5日最低收盘价 |
| `min_close_10` | 最近10日最低收盘价 |
| `previous_min_close_5` | 再前5日最低收盘价，用于判断最近5日是否创新低 |
| `no_new_low` | `min_close_5 >= previous_min_close_5 * no_new_low_tolerance` |
| `support_price_10` | 评估日前最近10日最低收盘价，避免用当日价格给自己当支撑 |
| `support_test_count` | 最近10日 low 靠近支撑的次数 |
| `support_valid` | 最近收盘价和最近10日收盘未有效跌破支撑 |
| `bear_body_shrink` | 最近阴线实体相对前期阴线实体收缩 |
| `lower_shadow_count` | 最近5日明显下影线数量 |
| `down_volume_ratio_5` | 最近5日阴线成交量占比 |
| `atr_ratio_5_20` | ATR5 / ATR20 |
| `has_big_down_volume` | 最近5日是否出现放量下跌 |

## 5. 支撑口径

参考文档中“最近10日最低收盘价”如果包含评估日，会导致“当前收盘低于最近10日最低收盘价”永远无法触发。因此策略3 v2 使用更安全的口径：

- `support_price_10` 取最近5日之前的 `dry_support_lookback_days` 日最低收盘价，避免最近破位 K 线把支撑位自动下修。
- `support_test_count` 在最近 `dry_support_lookback_days` 日内统计 `low <= support_price_10 * (1 + tolerance)`。
- `support_valid` 要求当前收盘价不低于 `support_price_10 * support_break_tolerance`，且最近窗口内没有收盘价有效跌破该线。

这样可以避免未来泄漏和自引用支撑。

## 6. 缩量企稳 v2 评分

`evaluate_volume_stability()` 继续返回 20 分，但内部改为五组质量分：

| 组别 | 上限 | 规则 |
|---|---:|---|
| 量干基础 | 5 | V5/V20 达到 `volume_shrink_ratio`、明显量干、V3<V5<V10<V20 |
| 跌不动 | 6 | return_5 不明显下跌、最近5日不创新低、5日收盘区间收窄 |
| 支撑验证 | 4 | 支撑测试次数达标、支撑未有效跌破 |
| 卖压衰竭 | 3 | 阴线实体收缩、下影线承接、阴线量占比低且无放量下跌 |
| 波动收缩 | 2 | ATR5/ATR20 收缩，极致收缩再加分 |

评分只提升或降低模块分，不直接决定最终入选。最终仍由策略3统一入口的总分、否决原因、风险比和 RR1 决定。

## 7. 新增否决规则

只加入明显坏形态的一票否决：

| 否决码 | 条件 | 含义 |
|---|---|---|
| `SHRINKING_BEAR_DRIFT` | V5/V20 <= 0.60 且 return_5 <= -5% | 缩量但持续阴跌，不是跌不动 |
| `SUPPORT_TEST_FAILED` | 当前或近期收盘 < 支撑 * 0.98 | 支撑测试失败 |
| `DOWNSIDE_VOLATILITY_EXPANDING` | ATR5/ATR20 >= 1.20 且 return_5 < 0 | 下跌波动重新放大 |
| `DRY_HEAVY_DOWNSIDE_VOLUME` | 最近5日存在跌幅 <= -4% 且成交量 >= V20 * 1.30 | 放量下跌，疑似出逃 |

保留现有否决码：`VOLUME_NOT_STABLE`、`CLOSE_RANGE_TOO_WIDE`、`RECENT_CONTINUOUS_DROP`。

## 8. 配置

在 `DEFAULT_STRATEGY3_CONFIG` 中增加高级默认参数，允许后端配置覆盖：

```yaml
dry_volume_ratio: 0.60
dry_extreme_volume_ratio: 0.50
dry_return_5_floor: -0.03
dry_return_5_reject: -0.05
dry_support_lookback_days: 10
dry_support_min_test_count: 2
dry_support_test_tolerance: 0.02
dry_support_break_tolerance: 0.98
dry_lower_shadow_threshold: 0.40
dry_lower_shadow_min_count: 2
dry_down_volume_ratio_max: 0.60
dry_big_down_return: -0.04
dry_big_down_volume_ratio: 1.30
dry_atr_contract_ratio: 0.75
dry_atr_extreme_contract_ratio: 0.60
dry_atr_expand_reject_ratio: 1.20
dry_no_new_low_tolerance: 0.995
```

这些参数先不新增前端独立控件，避免配置页过载；若 `config.yaml` 提供这些字段，后端必须校验并生效。

## 9. 展示与持久化

策略3候选表兼容新增字段：

- `v3`、`v5`、`v10`、`v20`
- `return_5`
- `min_close_5`、`min_close_10`
- `no_new_low`
- `support_price_10`、`support_test_count`、`support_valid`
- `bear_body_shrink`
- `lower_shadow_count`
- `down_volume_ratio_5`
- `atr_ratio_5_20`
- `has_big_down_volume`

前端策略3结果详情中新增“量干跌不动质量”区域，展示 V3/V5/V10/V20、5日涨跌、是否创新低、支撑测试、阴线量占比、ATR 收缩等字段。

## 10. 验收标准

- 高质量“缩量后跌不动”样本获得更高 `volume_stability_score`，并在 `score_reasons` 中出现可解释原因。
- 缩量阴跌样本被 `SHRINKING_BEAR_DRIFT` 排除。
- 支撑有效跌破样本被 `SUPPORT_TEST_FAILED` 排除。
- ATR 下跌波动放大样本被 `DOWNSIDE_VOLATILITY_EXPANDING` 排除。
- 放量下跌样本被 `DRY_HEAVY_DOWNSIDE_VOLUME` 排除。
- 原有健康策略3样本仍可通过。
- 策略3候选 API 返回新增诊断字段。
- 前端策略3结果页能展示新增诊断字段。

## 11. 回归命令

```bash
python -m pytest tests/test_strategy3_engine.py tests/test_strategy3_validation.py tests/test_strategy3_independence.py tests/test_strategy3_db_api.py -q
python -m compileall strategy3 scanner server.py -q
npm.cmd --prefix web test -- --run Strategy3Results
npm.cmd --prefix web run build
```
