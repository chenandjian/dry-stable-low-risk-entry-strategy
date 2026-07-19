# 策略6主链质量优化实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修正策略6启动、阶段、路径、评分和交易计划主链，补齐整理质量与支撑反应证据，并用真实历史数据逐层归因验证。

**架构：** 保持 `StrongVcpTailEngine.evaluate_at()` 为唯一入口。新增独立的 `setup_quality` 与 `entry` 模块，旧 ORIGINAL/BOX/BROOKS 作为解释证据保留；所有候选统一经过公共质量和风险规则。生产信号优化与回测执行优化分开验证。

**技术栈：** Python 3.10+、dataclasses、SQLite、pytest、Vue 3/Vitest、策略6现有本地回测框架。

---

## 文件结构

- 创建 `strategy6/setup_quality.py`：整理质量指标、评分和风险标签。
- 创建 `strategy6/entry.py`：入场类型识别及类型上下文。
- 修改 `strategy6/models.py`：增量数据结构和旧字段兼容输出。
- 修改 `strategy6/strong_start.py`：事件本地化评级和多事件择优。
- 修改 `strategy6/phase.py`：动态尾段识别与固定窗口回退。
- 修改 `strategy6/support.py`：支撑测试反应质量。
- 修改 `strategy6/scorer.py`：去重后的100分质量模型。
- 修改 `strategy6/filters.py`：公共拒绝、辅助路径降级和新候选分层。
- 修改 `strategy6/trade_plan.py`：按入场类型计算执行计划。
- 修改 `strategy6/engine.py`：串联新主链。
- 修改 `strategy6/validation.py`、`config.yaml`：新增显式策略6参数并校验。
- 修改 `scanner/db.py`：兼容迁移并保存新字段。
- 修改 `strategy6/backtest/snapshot.py`、`execution.py`、`runner.py`：等待突破不下单及归因字段。
- 修改 `web/src/pages/Strategy6Results.vue`：展示质量、支撑反应与入场类型。
- 修改对应后端和前端测试。
- 创建 `docs/reviews/2026-07-14-strategy6-main-chain-quality-optimization-report.md`：真实数据归因报告。

### 任务1：锁定基线和新增模型契约

**文件：**
- 修改：`tests/test_strategy6_core_rules.py`
- 修改：`tests/test_strategy6_db_api.py`
- 修改：`strategy6/models.py`
- 修改：`scanner/db.py`

- [ ] **步骤1：编写失败测试**

断言候选字典和数据库往返包含：

```python
assert candidate["start_event_quality_score"] >= 0
assert candidate["tail_segmentation_status"]
assert candidate["setup_quality_score"] >= 0
assert candidate["support_reaction_score"] >= 0
assert candidate["path_evidence_score"] >= 0
assert candidate["entry_archetype"] in ENTRY_ARCHETYPES
assert candidate["score_model_version"] == "S6_QUALITY_V2"
```

- [ ] **步骤2：运行测试确认因字段缺失失败**

运行：`python -m pytest tests/test_strategy6_core_rules.py tests/test_strategy6_db_api.py -q`

- [ ] **步骤3：增加 dataclass、中性默认值、候选输出和 SQLite 增量列**

旧任务缺失新列时返回 `0`、`NONE` 或空数组，不改变旧字段。

- [ ] **步骤4：运行专项测试通过**

- [ ] **步骤5：提交**

`git commit -m "feat: add strategy6 quality model contracts"`

### 任务2：修正启动事件语义

**文件：**
- 修改：`tests/test_strategy6_core_rules.py`
- 修改：`strategy6/strong_start.py`
- 修改：`strategy6/models.py`

- [ ] **步骤1：编写失败测试**

覆盖相同启动事件在改变评估日 `return_5/10/20` 后评级不变、低质量新事件不覆盖高质量旧事件、启动失效被排除。

```python
first = evaluate_strong_start(rows, indicators_a, cfg, "000001")
second = evaluate_strong_start(rows, indicators_b, cfg, "000001")
assert first.start_grade == second.start_grade
assert first.event_quality_score == second.event_quality_score
```

- [ ] **步骤2：运行测试，确认旧 `_grade(start, ind)` 导致失败**

- [ ] **步骤3：实现事件质量、5日跟随和确定性择优**

不得读取事件后第6日及以后数据计算事件分；不足5日只使用已发生交易日并保持生命周期为形成中。

- [ ] **步骤4：运行启动、生命周期和核心规则测试**

- [ ] **步骤5：提交**

`git commit -m "fix: anchor strategy6 start quality to event data"`

### 任务3：实现动态尾段划分

**文件：**
- 修改：`tests/test_strategy6_phase.py`
- 修改：`strategy6/phase.py`
- 修改：`strategy6/models.py`
- 修改：`strategy6/validation.py`

- [ ] **步骤1：编写失败测试**

构造3日、7日真实收缩和无收缩样本，断言动态窗口、最早合格窗口、固定回退状态以及未来K线不会改变历史评估边界。

- [ ] **步骤2：运行测试确认固定5日实现失败**

- [ ] **步骤3：实现3至10日窗口度量和最早合格选择**

尾段必须以信号日结束；前置基准必须位于尾段之前；没有足够20日基准时回退固定窗口并标记原因。

- [ ] **步骤4：运行阶段、尾部、箱体和 Brooks 集成测试**

- [ ] **步骤5：提交**

`git commit -m "feat: detect strategy6 dynamic tail phase"`

### 任务4：新增整理质量层

**文件：**
- 创建：`strategy6/setup_quality.py`
- 创建：`tests/test_strategy6_setup_quality.py`
- 修改：`strategy6/market.py`
- 修改：`strategy6/models.py`

- [ ] **步骤1：为每个指标编写最小失败测试**

分别覆盖涨幅保持、派发日、上下跌量比、波动收缩、重复假突破和沪深300相对强度趋势；无指数时输出 `UNKNOWN`，不能伪造中性RS趋势。

- [ ] **步骤2：逐项运行确认失败**

- [ ] **步骤3：实现纯函数 `evaluate_setup_quality()`**

函数只返回指标、0至25分、reasons和risk_tags，不决定候选类型。

- [ ] **步骤4：运行新测试和市场指数测试**

- [ ] **步骤5：提交**

`git commit -m "feat: score strategy6 consolidation quality"`

### 任务5：增强支撑反应质量

**文件：**
- 修改：`tests/test_strategy6_support_cluster.py`
- 修改：`strategy6/support.py`
- 修改：`strategy6/models.py`

- [ ] **步骤1：编写失败测试**

覆盖缩量测试后收复、放量跌破未收复、连续测试反弹衰减和测试数据不足。

- [ ] **步骤2：运行确认现有测试次数逻辑不能区分质量**

- [ ] **步骤3：实现0至10分支撑反应和风险标签**

测试次数只是一项证据；反弹衰减不能因次数增加而加分。

- [ ] **步骤4：运行支撑和核心规则测试**

- [ ] **步骤5：提交**

`git commit -m "feat: evaluate strategy6 support reactions"`

### 任务6：统一路径证据和质量评分

**文件：**
- 修改：`tests/test_strategy6_core_rules.py`
- 修改：`tests/test_strategy6_box_tail_integration.py`
- 修改：`tests/test_strategy6_brooks_trigger.py`
- 修改：`strategy6/scorer.py`
- 修改：`strategy6/filters.py`
- 修改：`strategy6/engine.py`

- [ ] **步骤1：编写失败测试**

断言 BOX-only/BROOKS-only 最高只能 WATCH，辅助路径不能绕过严重派发、支撑失效和原路径的结构风险；多路径分不再直接取最大值。

- [ ] **步骤2：运行确认现有 max-path 和 bypass 行为失败**

- [ ] **步骤3：实现15分路径证据和100分质量模型**

公共硬拒绝先于路径分层。旧 `tail_score` 作为兼容别名返回新 `path_evidence_score`。

- [ ] **步骤4：运行策略6全部路径和核心规则测试**

- [ ] **步骤5：提交**

`git commit -m "fix: unify strategy6 path evidence and quality scoring"`

### 任务7：按入场类型生成交易计划

**文件：**
- 创建：`strategy6/entry.py`
- 创建：`tests/test_strategy6_entry.py`
- 修改：`tests/test_strategy6_trade_plan_v4.py`
- 修改：`strategy6/trade_plan.py`
- 修改：`strategy6/engine.py`
- 修改：`strategy6/models.py`

- [ ] **步骤1：编写失败测试**

覆盖支撑低吸、有效突破、收复、等待突破和无合法入场；断言 WAIT_BREAKOUT 没有建议成交价。

- [ ] **步骤2：运行确认单一交易计划失败**

- [ ] **步骤3：实现入场识别和类型化无效位**

突破止损不能回退到过远关键支撑；收复止损使用失败低点；所有止损必须小于建议买价。

- [ ] **步骤4：运行交易计划、涨跌停和核心规则测试**

- [ ] **步骤5：提交**

`git commit -m "feat: add strategy6 entry-specific trade plans"`

### 任务8：回测执行与归因兼容

**文件：**
- 修改：`tests/test_strategy6_backtest_snapshot.py`
- 修改：`tests/test_strategy6_backtest_execution.py`
- 修改：`tests/test_strategy6_backtest_report.py`
- 修改：`strategy6/backtest/snapshot.py`
- 修改：`strategy6/backtest/execution.py`
- 修改：`strategy6/backtest/runner.py`
- 修改：`strategy6/backtest/report.py`

- [ ] **步骤1：编写失败测试**

断言 WAIT_BREAKOUT 不生成订单，新信号保存入场类型和质量分，报告可按 `entry_archetype`、质量分段和路径证据分组。

- [ ] **步骤2：运行确认失败**

- [ ] **步骤3：实现最小回测兼容和B0至B5研究标签**

不改变费用、T+1、STOP_FIRST、缺失K线和OOS规则。

- [ ] **步骤4：运行策略6回测专项测试**

- [ ] **步骤5：提交**

`git commit -m "feat: attribute strategy6 quality backtests"`

### 任务9：持久化和前端解释

**文件：**
- 修改：`tests/test_strategy6_db_api.py`
- 修改：`web/src/pages/__tests__/Strategy6Results.test.js`
- 修改：`scanner/db.py`
- 修改：`web/src/pages/Strategy6Results.vue`
- 修改：`web/src/utils/strategy6Labels.js`

- [ ] **步骤1：编写后端和前端失败测试**

页面应显示入场类型、整理质量、支撑反应、启动事件质量、阶段来源和风险标签；CSV包含原始值和中文值。

- [ ] **步骤2：运行确认失败**

- [ ] **步骤3：实现增量持久化和中文展示**

旧任务的缺失字段显示 `--`，不能显示为真实0分。

- [ ] **步骤4：运行 API、页面测试和前端构建**

- [ ] **步骤5：提交**

`git commit -m "feat: explain strategy6 quality evidence"`

### 任务10：真实数据归因与参数审批报告

**文件：**
- 创建：`docs/reviews/2026-07-14-strategy6-main-chain-quality-optimization-report.md`
- 创建：`docs/reviews/strategy6-main-chain-quality/*`

- [ ] **步骤1：记录 B0 当前提交、配置哈希、数据版本和指数覆盖**

- [ ] **步骤2：在2023-2024依次运行 B0至B5**

每阶段输出每日候选、订单、交易、共同/新增/删除交易和年度/月度指标。

- [ ] **步骤3：只对训练期通过基础约束的方案运行2025确认**

如果没有训练方案通过，则2025只运行未调参的语义修复基线，不根据验证结果继续搜索。

- [ ] **步骤4：运行高成本、70%成交率和延迟一天压力测试**

- [ ] **步骤5：形成审批结论**

不足60笔交易或未达到PF/期望门槛时明确标记 `INSUFFICIENT_SAMPLE` 或 `REJECT`，不修改生产配置。

### 任务11：双角色验收闭环

**文件：**
- 修改：`docs/reviews/2026-07-14-strategy6-main-chain-quality-optimization-report.md`

- [ ] **步骤1：程序员角色运行完整门禁**

```bash
python -m pytest tests/test_strategy6_*.py -q
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner strategy2 strategy3 strategy4 strategy5 strategy6 server.py -q
npm --prefix web test -- --run
npm --prefix web run build
```

- [ ] **步骤2：审核角色检查业务正确性**

重点检查未来数据泄漏、路径旁路、旧字段兼容、SQLite迁移、WAIT_BREAKOUT成交、旧任务读取和策略1至5回归。

- [ ] **步骤3：发现中高问题时先补失败测试再修复**

- [ ] **步骤4：重复门禁直到没有中高问题**

- [ ] **步骤5：只提交本任务文件，保留用户已有报告改动**

- [ ] **步骤6：推送当前分支并报告提交哈希、真实回测和残余风险**

