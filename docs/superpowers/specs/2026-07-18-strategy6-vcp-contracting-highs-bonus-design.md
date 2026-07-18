# 策略6主链VCP高点收敛加分设计

## 目标

在策略6主链VCP中新增一个独立质量加分项：完整轮次的高点逐轮持平或降低，并且低点逐轮严格抬高时，加2分。

## 固定口径

- 至少需要两个完整VCP轮次。
- 每轮高点使用完整轮次的 `peak_close`，不使用突破确认价。
- 每个后续轮次必须满足 `current_peak <= previous_peak`。
- 每个后续轮次必须同时满足 `current_low > previous_low`。
- 任一高点升高、任一低点持平或降低、证据不足、非VCP形态均不加分。
- 该奖励与已有低点平均抬高奖励独立，可以同时触发。
- 加分进入现有 `pattern_score_component`，该项仍封顶15分，策略总分仍封顶100分。
- 不修改VCP轮次资格、观察池评分、候选门槛和策略1至策略5。

## 审计

触发时在形态原因中记录 `VCP_HIGH_NOT_RISING_LOW_RISING_BONUS`，评分原因中记录 `vcp_contracting_highs_bonus=2`。
