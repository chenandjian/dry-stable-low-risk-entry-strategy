# Context

优化量干+价稳+风险最小策略，从简单评分系统升级为"评分+风险控制+拒因解释"系统。目标：减少缩量阴跌/破位缩量/放量滞涨的误判，7种决策状态替代4种，输出明确的正向因素和拒绝原因。

# Implementation Plan

## Phase 1: Core Scoring Enhancements

### 1a. analyzer/volume_dry.py — 好缩量/坏缩量识别

- 新增 `_linear_regression_slope(closes)` 辅助函数
- 新增"缩量阴跌封顶"：近10日收盘线性回归斜率< -3% 且 close < MA20 → cap score at 6
- 新增"缩量位置过滤"：计算 position_60d = (close - low_60d) / (high_60d - low_60d)
  - pos < 0.3 → cap at 5 + reject_reason
  - 0.3 <= pos < 0.5 → cap at 6 + warning
- 新增"放量滞涨封顶"：近5天任一天 vol >= 1.5*MA20 且涨幅<1% 且收盘偏下 → cap at 6
- 扩展 VolumeDryResult dataclass：+raw_score, +caps, +warnings, +reject_reasons
- 所有新阈值从 config 读取（带默认值）

### 1b. analyzer/price_stable.py — 价格稳定性增强

- 新增"收盘紧致度" close_tightness_5d = max_close_5d/min_close_5d - 1
  - ≤3%: +2, ≤5%: +1 → 输出为 positive_factor
- 新增"收盘位置评分" close_position_5d_avg
  - ≥0.6: score 输出为 positive_factor
- 优化 MA20 站上规则：改为天数制（≥4天: +2, ≥3天且最后一天站上: +1）
- 新增"跌破关键支撑封顶"：close < handle_low || close < support*0.98 || close < MA50 → cap at 5
- 扩展 PriceStableResult dataclass：+raw_score, +caps, +warnings, +positive_factors
- 新阈值可配置

### 1c. analyzer/risk_reward.py — ATR 止损校验

- 新增 ATR14 计算（从 price_stable 已有 _atr 复用或新写）
- 新增 atr_stop_multiplier 校验：risk_pct >= atr14_pct * 1.2
  - 不满足 → warning "止损过近，容易被正常波动触发"
- 扩展 RiskRewardResult：+atr14_pct, +warnings

## Phase 2: Decision System Upgrade

### 2a. analyzer/decision.py — 7 决策状态

新增决策类型映射（中文标签，兼容现有前端）：
```
REJECT          → "不建议买入"  (was 不建议买入)
WAIT_VOLUME     → "等量能萎缩"  (new)
WAIT_STABLE     → "等价格企稳"  (new)
WAIT_ENTRY      → "等回调入场"  (new)
WAIT_RR         → "等盈亏比改善" (new)
WATCH_BREAKOUT  → "突破确认"    (was 突破确认)
BUY_LOW         → "可低吸"      (was 可低吸)
```

决策优先级（早停）：
1. invalid_conditions → REJECT
2. 大盘差 → REJECT
3. pattern < min → REJECT
4. vd < min → WAIT_VOLUME (not REJECT)
5. ps < min → WAIT_STABLE (not REJECT)
6. risk > max → REJECT
7. rr1 < min → WAIT_RR (not REJECT)
8. chasing → REJECT
9. all checks pass + low buy zone → BUY_LOW
10. near pivot → WATCH_BREAKOUT
11. in_low_buy_zone=False → WAIT_ENTRY
12. else → 观察

扩展 DryStableDecision dataclass：
+ positive_factors: list[str]
+ warnings: list[str]
+ reject_reasons: list[str] (consolidated from scoring modules)

### 2b. analyzer/dry_stable.py — 聚合 positive/warnings/reject

- 从 volume_dry / price_stable / risk_reward 各模块收集 warnings 和 reject_reasons
- 汇总到 decision 输出

## Phase 3: Data Cleaner

### 3a. analyzer/data_cleaner.py (新文件)

- `detect_suspended_days(data)` → 标记 volume==0 或 high==low==close
- `detect_limit_days(data)` → 标记涨跌停（含一字板）
- `clean_for_scoring(data, exclude_suspended=True, exclude_limits=True)` → 返回过滤后的数据
- 评分计算前调用 clean_for_scoring，剔除异常日
- 上市时间检查：有效交易日 < 80 → 直接 REJECT（在 liquidity 层或 dry_stable 入口）

## Phase 4: Config Expansion

config.yaml 新增段：
```yaml
volume_dry:
  bad_shrink_max_score: 6
  min_position_60d_normal: 0.5
  low_position_max_score: 6
  very_low_position_max_score: 5
  volume_stall_max_score: 6
  big_bear_max_score: 5

price_stable:
  close_tightness_strong_pct: 3
  close_tightness_normal_pct: 5
  support_break_max_score: 5

risk_reward:
  atr_stop_multiplier: 1.2
```

## Phase 5: DB Schema

candidates 表新增列（nullable，向前兼容）：
- positive_factors TEXT (JSON array)
- warnings TEXT (JSON array)
- reject_reasons TEXT (JSON array)
- raw_volume_dry_score INTEGER
- raw_price_stable_score INTEGER
- score_caps TEXT (JSON array)

db.py 的 upsert_candidate / save_candidates 新增对应字段。

## Phase 6: Frontend

- DiscoveryItem.vue：新增决策状态标签（等量能/等企稳/等回调 → 黄色系）
- SignalBadge.vue：新增状态类型
- ScannerConsole.vue / ResultsRadar.vue：statusFor/verdictType 适配新决策类型，metrics 更新
- StockDetail.vue：展示 positive_factors / warnings / reject_reasons

## Phase 7: Tests

- test_volume_dry.py：+坏缩量封顶、缩量位置封顶、放量滞涨封顶
- test_price_stable.py：+紧致度、收盘位置、支撑跌破封顶
- test_decision.py：+7种决策状态覆盖
- test_risk_reward.py：+ATR止损校验
- test_data_cleaner.py：停牌/涨跌停检测

## Verification

```bash
python -m pytest tests/ -v    # all tests must pass
npm --prefix web run build     # frontend must build
python -c "from analyzer.decision import make_dry_stable_decision; ..."  # manual smoke
```

所有新阈值默认值与当前硬编码行为一致，改动后不影响已有候选结果，除非显式修改 config.yaml。
