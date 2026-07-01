# 策略3交易质量过滤层实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:test-driven-development 开发，使用 superpowers:verification-before-completion 验证。步骤使用复选框（`- [ ]`）语法跟踪进度。

**目标：** 在当前策略3“强势回踩二次启动”基础上增强量干价稳识别和交易质量判断，筛选高胜率、高盈亏比、风险较小的交易机会。

**架构：** 保留 `StrongPullbackSecondBreakoutEngine.evaluate_at()` 作为策略3唯一判断入口，在现有趋势、回踩、量干价稳、二次转强、风险收益计算之后新增策略3专用交易质量过滤层。新增字段只追加到策略3模型、策略3候选表、策略3 API 和策略3前端，不删除旧字段，不影响策略1、策略2。

**技术栈：** Python dataclass + pytest + SQLite 兼容迁移 + FastAPI + Vue 3/Vitest。

---

## 一、现状与边界

策略3入口和调用链：

- API 入口：`server.py::start_strategy3_scan()`，路由 `POST /api/strategy3/scans`。
- 扫描编排：`strategy3/scanner.py::scan_strategy3_all()`。
- 策略判断入口：`strategy3/engine.py::StrongPullbackSecondBreakoutEngine.evaluate_at()`。
- 候选输出：`strategy3/scanner.py::_build_strategy3_discovery()`。
- 候选持久化：`scanner/db.py::upsert_strategy3_candidate()`，表 `strategy3_candidates`。
- 前端展示：`web/src/pages/Strategy3Results.vue`。
- 策略隔离测试：`tests/test_strategy3_independence.py`。

必须保留的兼容字段：

- `total_score`, `level`, `trend_score`, `pullback_score`, `volume_stability_score`, `second_breakout_score`, `risk_reward_score`
- `current_close`, `pullback_pct`, `volume_ratio_5_20`, `range_5`, `close_range_5`
- `support_price`, `stop_loss`, `target_1`, `risk_ratio`, `rr1`
- `tactical_support`, `tactical_stop_loss`, `tactical_risk_ratio`, `tactical_rr1`
- `key_support`, `support_status`, `break_status`, `nearest_support_distance`
- `score_reasons`, `reject_reasons`

隔离要求：

- 不修改策略1核心逻辑。
- 不修改策略2核心逻辑。
- 不修改与策略3无关的数据拉取逻辑。
- 不直接改公共量干/价稳模块；新增策略3专用封装。

---

## 二、目标行为

策略3新增交易状态：

- `LOW_ABSORB` / `低吸`
- `WATCH` / `观察`
- `WAIT_BREAKOUT` / `等待突破`
- `AVOID` / `回避`

策略3新增四类状态识别：

- 成交量极致萎缩
- 价格稳定
- 跌不动
- 涨跌都无力

策略3新增交易质量判断：

- 当前价是否接近战术支撑和关键支撑。
- 止损空间是否足够小。
- 上方目标空间是否足够大。
- 预估盈亏比是否达标。
- 是否出现放量破位、连续新低、阴线实体扩大、跌破支撑等失败信号。

候选过滤原则：

- `LOW_ABSORB` 必须严格，不为增加候选数量放宽风控。
- `WATCH` 和 `WAIT_BREAKOUT` 可以进入候选列表，但必须明确状态，不得伪装成低吸。
- `AVOID` 不进入 `strategy3_candidates`，但要在 `task_stocks.error_detail` 中保留诊断字段。

---

## 三、推荐字段

新增 dataclass：`Strategy3TradeQuality`。

字段：

- `trade_quality_score: int`
- `volume_dry_score: int`
- `price_stability_score: int`
- `cannot_fall_score: int`
- `balance_powerless_score: int`
- `support_distance_pct: float`
- `key_support_distance_pct: float`
- `target_price: float`
- `target_room_pct: float`
- `estimated_rr: float`
- `trade_state: str`
- `trade_state_label: str`
- `trigger_reasons: list[str]`
- `risk_warnings: list[str]`
- `invalid_conditions: list[str]`
- `reject_reasons: list[str]`

新增指标字段：

- `volume_percentile_60`
- `avg_abs_return_5`
- `new_low_count_5`
- `bear_body_expanding`
- `down_return_contracting`

兼容输出：

- `target_price` 可与旧 `target_1` 同值或更精确，但不能删除 `target_1`。
- `estimated_rr` 可与旧 `rr1` 同值或更精确，但不能删除 `rr1`。
- `support_distance_pct` 使用战术支撑距离，旧 `nearest_support_distance` 保留。

---

## 四、阈值设计

成交量极致萎缩：

- 合格缩量：`volume_ratio_5_20 <= 0.70`
- 强缩量：`volume_ratio_5_20 <= 0.60`
- 极致缩量：`volume_ratio_5_20 <= 0.50`
- 60 日量能分位：`volume_percentile_60 <= 0.20`
- 阴线量占比：`down_volume_ratio_5 <= 0.60`

价格稳定：

- `range_5 <= 0.05`
- `close_range_5 <= 0.03`
- `atr_ratio_5_20 <= 0.75`
- `max_up_5 <= 0.03`
- `max_down_5 >= -0.03`
- `range_5 < range_10 < range_20`

跌不动：

- `no_new_low is True`
- `new_low_count_5 == 0`
- `bear_body_shrink is True`
- `down_return_contracting is True`
- `support_status in {"VALID", "TESTING"}`

涨跌都无力：

- `direction_efficiency_5 <= 0.35`
- `avg_abs_return_5 <= 0.015`
- `max_up_5 <= 0.03`
- `max_down_5 >= -0.03`
- 叠加缩量和 ATR 收缩，避免死盘误判。

交易质量：

- `LOW_ABSORB`: `support_distance_pct <= 0.04`, `risk_ratio <= 0.06`, `target_room_pct >= 0.10`, `estimated_rr >= 2.0`
- `WATCH`: `risk_ratio <= 0.08`, `estimated_rr >= 1.5`，且无硬回避信号
- `WAIT_BREAKOUT`: 量缩价稳但 `support_distance_pct > 0.04`，或需要突破平台上沿确认
- `AVOID`: 放量破位、连续新低、阴线实体扩大、支撑失败、风险比过高、目标空间不足、盈亏比不合格、数据不足

---

## 五、任务清单

### 任务 1：保护旧行为并写交易质量红灯测试

**文件：**

- 修改：`tests/test_strategy3_engine.py`

- [ ] 步骤 1：新增失败测试，验证健康策略3样本仍输出旧字段，并新增 `trade_quality`。
- [ ] 步骤 2：新增失败测试，验证上涨趋势缩量企稳可被标记为 `LOW_ABSORB`。
- [ ] 步骤 3：新增失败测试，验证价格稳定但量未缩时不能是 `LOW_ABSORB`。
- [ ] 步骤 4：新增失败测试，验证极致缩量但价格不稳时进入 `AVOID` 或不通过。
- [ ] 步骤 5：新增失败测试，验证接近支撑但盈亏比不足时不是 `LOW_ABSORB`。
- [ ] 步骤 6：新增失败测试，验证盈亏比足够但未企稳时不是 `LOW_ABSORB`。
- [ ] 步骤 7：新增失败测试，验证放量破位必须 `AVOID`。

运行：

```bash
python -m pytest tests/test_strategy3_engine.py -q
```

预期：

- 失败原因是 `Strategy3Evaluation` 缺少 `trade_quality` 或新增字段。
- 不是导入错误、语法错误或测试样本拼写错误。

### 任务 2：新增交易质量模型和专用模块

**文件：**

- 修改：`strategy3/models.py`
- 创建：`strategy3/trade_quality.py`

- [ ] 步骤 1：在 `models.py` 新增 `Strategy3TradeQuality` dataclass。
- [ ] 步骤 2：给 `Strategy3Evaluation` 增加 `trade_quality` 字段，默认值为 `Strategy3TradeQuality()`。
- [ ] 步骤 3：创建 `trade_quality.py`，实现 `evaluate_trade_quality(data, ind, risk, config)`。
- [ ] 步骤 4：实现评分辅助函数：量干、价稳、跌不动、涨跌无力、无效条件、交易状态。

运行：

```bash
python -m pytest tests/test_strategy3_engine.py -q
```

预期：

- 交易质量模型相关测试通过。
- 若 DB/API 输出字段仍未接入，DB/API 测试可继续失败。

### 任务 3：补充指标计算

**文件：**

- 修改：`strategy3/models.py`
- 修改：`strategy3/indicators.py`

- [ ] 步骤 1：在 `Strategy3Indicators` 增加 `volume_percentile_60`。
- [ ] 步骤 2：增加 `avg_abs_return_5`。
- [ ] 步骤 3：增加 `new_low_count_5`。
- [ ] 步骤 4：增加 `bear_body_expanding`。
- [ ] 步骤 5：增加 `down_return_contracting`。

运行：

```bash
python -m pytest tests/test_strategy3_engine.py -q
```

预期：

- 新指标测试通过。
- 原有量干、支撑、价稳测试继续通过。

### 任务 4：接入策略3唯一入口

**文件：**

- 修改：`strategy3/engine.py`
- 修改：`strategy3/scorer.py`（仅在需要时追加状态原因优先级）

- [ ] 步骤 1：在 `compute_strategy3_risk()` 后调用 `evaluate_trade_quality()`。
- [ ] 步骤 2：将交易质量层的 `reject_reasons` 合并进最终 `reject_reasons`。
- [ ] 步骤 3：`AVOID` 时 `passed=False`。
- [ ] 步骤 4：`LOW_ABSORB/WATCH/WAIT_BREAKOUT` 且旧条件满足时允许 `passed=True`。
- [ ] 步骤 5：保留旧 `total_score` 和旧 `level`，新增交易状态不覆盖旧等级。

运行：

```bash
python -m pytest tests/test_strategy3_engine.py tests/test_strategy3_independence.py -q
```

预期：

- 策略3引擎测试通过。
- 策略3仍不导入策略1/策略2决策模块。

### 任务 5：增强候选输出、DB 和 API

**文件：**

- 修改：`strategy3/scanner.py`
- 修改：`scanner/db.py`
- 修改：`tests/test_strategy3_db_api.py`

- [ ] 步骤 1：在 `_build_strategy3_discovery()` 追加交易质量字段。
- [ ] 步骤 2：在 `_evaluation_debug_json()` 追加交易状态、触发原因、风险提示、无效条件。
- [ ] 步骤 3：在 `strategy3_candidates` 表兼容迁移新增列。
- [ ] 步骤 4：在 `upsert_strategy3_candidate()` 写入新增列。
- [ ] 步骤 5：在 `_deserialize_strategy3_candidate()` 反序列化新增 JSON list 字段。
- [ ] 步骤 6：更新 DB/API roundtrip 测试，确认旧字段和新字段同时存在。

运行：

```bash
python -m pytest tests/test_strategy3_db_api.py tests/test_strategy3_engine.py -q
```

预期：

- 策略3候选表 roundtrip 通过。
- `/api/strategy3/candidates` 旧字段兼容。

### 任务 6：前端策略3候选页展示

**文件：**

- 修改：`web/src/pages/Strategy3Results.vue`
- 修改：`web/src/pages/__tests__/Strategy3Results.test.js`
- 必要时修改：`web/src/pages/ScannerConsole.vue`

- [ ] 步骤 1：列表新增交易状态、交易质量分、预估 RR。
- [ ] 步骤 2：详情区新增四类评分、触发原因、风险提示、无效条件。
- [ ] 步骤 3：CSV 导出追加新增字段。
- [ ] 步骤 4：保持旧字段仍显示，不删除原有列。

运行：

```bash
npm --prefix web test -- --run Strategy3Results
```

预期：

- 策略3候选页测试通过。
- 旧字段展示断言继续通过。

### 任务 7：最小样本扫描验证

**文件：**

- 修改：`tests/test_strategy3_db_api.py`

- [ ] 步骤 1：用 mock `fetch_with_retry()` 的最小扫描验证候选不重复。
- [ ] 步骤 2：验证 `LOW_ABSORB/WATCH/WAIT_BREAKOUT/AVOID` 分类结果可审计。
- [ ] 步骤 3：验证 `AVOID` 不写入候选，但 `task_stocks.error_detail` 有诊断字段。

运行：

```bash
python -m pytest tests/test_strategy3_db_api.py -q
```

预期：

- 最小样本扫描验证通过。
- 输出字段完整。

### 任务 8：完整验证和自审

运行：

```bash
python -m pytest tests/test_strategy3_engine.py tests/test_strategy3_db_api.py tests/test_strategy3_validation.py tests/test_strategy3_independence.py -q
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py
python -m compileall scanner strategy2 strategy3 server.py -q
npm --prefix web test -- --run
npm --prefix web run build
```

验收：

- 策略3专项全部通过。
- 策略1、策略2隔离和核心回归通过。
- 前端测试和构建通过。
- `git diff` 确认只修改策略3、策略3测试、策略3前端和计划文档。
- 不提交用户已有的 `config.yaml` 和未跟踪 docs，除非用户明确要求。

---

## 六、自检清单

- [ ] 已明确策略3入口，未新建独立策略。
- [ ] 已保留 `StrongPullbackSecondBreakoutEngine.evaluate_at()` 签名。
- [ ] 已保留旧输出字段。
- [ ] 已新增四类评分和交易状态。
- [ ] 已新增交易质量过滤层。
- [ ] `AVOID` 股票不进入高质量候选。
- [ ] 策略1、策略2核心逻辑未修改。
- [ ] 新增 DB 字段使用 `_ensure_column()` 兼容迁移。
- [ ] 前端只调整策略3页面或策略3摘要展示。
- [ ] 测试命令来自项目文档、AGENTS.md、package.json 和现有测试目录。
