# 策略3支撑区 V2 设计

## 目标

将策略3「强势回踩二次启动」的支撑判断从单点价格升级为支撑区间，统一服务风险收益、缩量企稳和前端解释，减少把盘中假跌破误判为结构失败的问题。

## 范围

本次只修改策略3：

- `strategy3/indicators.py`
- `strategy3/risk.py`
- `strategy3/volume_stability.py`
- `strategy3/models.py`
- `strategy3/validation.py`
- `strategy3/scanner.py`
- `scanner/db.py`
- `web/src/pages/Strategy3Results.vue`
- 策略3相关测试

不修改策略1、策略2，不引入通用 `analyzer/support/` 模块，不实现成交量分布支撑。

## 核心设计

策略3新增三层支撑：

| 层级 | 用途 | 默认来源 |
| --- | --- | --- |
| 短线支撑 `short_support` | 判断短线强度 | 5日最低收盘、5日最低价、MA20 |
| 关键支撑 `key_support` | 判断缩量企稳和低风险入场是否有效 | 10日最低收盘、10日最低价、平台低点、MA20/MA60 |
| 强支撑 `strong_support` | 判断结构是否明显损坏 | 20日最低收盘、20日最低价、MA60 |

每个支撑输出：

- `price`
- `zone_low`
- `zone_high`
- `sources`

支撑区间半径：

```text
zone_radius = max(price * support_zone_pct, ATR14 * support_zone_atr_ratio)
```

默认：

- `support_zone_pct = 0.01`
- `support_zone_atr_ratio = 0.30`

## 状态定义

| 状态 | 含义 | 策略影响 |
| --- | --- | --- |
| `VALID` | 当前收盘在关键支撑区上沿之上，且近期无收盘跌破 | 可正常入选 |
| `TESTING` | 当前收盘位于关键支撑区内，且近期无收盘跌破 | 可正常入选，但解释为正在测试 |
| `WEAKENING` | 最近出现收盘跌破关键支撑区，但当前已收回 | 排除，避免把已破位后反抽当成低风险 |
| `BROKEN` | 当前收盘跌破关键支撑区下沿 | 排除 |
| `FAILED` | 出现有效跌破 | 排除 |

有效跌破满足任一条件：

1. 连续 `support_effective_break_days` 天收盘低于 `key_support_zone_low`；
2. 单日收盘低于 `key_support_zone_low` 且成交量 `>= V20 * support_big_down_volume_ratio`；
3. 单日跌幅 `<= support_big_down_return` 且收盘低于 `key_support_zone_low`。

默认：

- `support_effective_break_days = 2`
- `support_big_down_return = -0.04`
- `support_big_down_volume_ratio = 1.30`

## 策略语义

1. 盘中最低价跌破支撑区但收盘收回，不视为失败。
2. 最近出现收盘跌破后再收回，标记 `WEAKENING` 并排除，保证策略3偏高质量。
3. `key_support` 用于判断缩量企稳和结构有效性，不直接等同于战术止损支撑。
4. 战术风险优先选择离当前价最近且仍有效的支撑区，例如 `short_support`、MA20、MA60；`key_support` 作为较深层的有效性支撑和兜底支撑。
5. `strong_support` 保留结构性风险视角，前端展示但不单独改变通过条件。
6. 原有 `support_price`、`stop_loss`、`risk_ratio`、`rr1` 字段继续兼容，映射到战术支撑口径。
7. `short_support` 使用评估日前 5 天，`key_support` 和 `strong_support` 使用最近 5 天之前的历史窗口，避免破位验证日把支撑价格同步拖低。

## 数据与前端

候选表新增字段：

- `short_support`
- `short_support_zone_low`
- `short_support_zone_high`
- `key_support`
- `key_support_zone_low`
- `key_support_zone_high`
- `strong_support`
- `strong_support_zone_low`
- `strong_support_zone_high`
- `support_status`
- `break_status`
- `nearest_support_distance`
- `support_sources`

前端策略3结果页在展开详情中显示：

- 支撑状态和跌破状态；
- 短线/关键/强支撑区；
- 当前价格距离关键支撑；
- 支撑来源。

## 验收标准

1. 健康策略3样本仍可通过。
2. 支撑字段包含区间而不是只有单点。
3. 盘中跌破但收盘收回不会触发支撑失败。
4. 连续两天收盘跌破关键支撑会被排除。
5. 放量或大阴线跌破关键支撑会被排除。
6. 候选持久化、API、前端能展示新增字段。
7. 策略3不导入策略1/策略2决策模块。
