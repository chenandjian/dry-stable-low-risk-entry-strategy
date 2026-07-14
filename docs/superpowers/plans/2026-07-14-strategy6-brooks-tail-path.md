# 策略6 Brooks 价格行为尾部路径实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为策略6新增 Brooks 价格行为第三尾部路径、跨交易日触发重建、完整输出和历史回放支持，同时保持原始尾部、箱体路径及策略1至策略5行为不变。

**架构：** 在 `strategy6/brooks/` 下按指标、背景、卖压、结构、紧密分类、尾部汇总和交易触发拆分。`StrongVcpTailEngine.evaluate_at()` 仍是唯一入口；旧 `tail_path` 保持双路径语义，新三路径字段作为权威输出。SQLite使用关键列与 `brooks_result_json` 混合持久化。

**技术栈：** Python 3.10+、dataclasses、SQLite、FastAPI、Vue 3、Vitest、pytest。

---

## 文件结构

**新增：**

- `strategy6/brooks/__init__.py`：公开 Brooks 分析接口。
- `strategy6/brooks/models.py`：Brooks结果对象与状态常量。
- `strategy6/brooks/metrics.py`：统一K线指标和摆动点工具。
- `strategy6/brooks/context.py`：市场背景判断。
- `strategy6/brooks/selling_pressure.py`：卖压与空方跟进判断。
- `strategy6/brooks/structures.py`：微型双底、假跌破、二次入场和有序收缩。
- `strategy6/brooks/compact.py`：紧密结构分类。
- `strategy6/brooks/tail.py`：Brooks路径评分和候选结论。
- `strategy6/brooks/trigger.py`：跨交易日触发重建。
- `tests/test_strategy6_brooks_metrics.py`
- `tests/test_strategy6_brooks_context.py`
- `tests/test_strategy6_brooks_selling_pressure.py`
- `tests/test_strategy6_brooks_structures.py`
- `tests/test_strategy6_brooks_tail.py`
- `tests/test_strategy6_brooks_trigger.py`
- `docs/reviews/2026-07-14-strategy6-brooks-tail-validation.md`

**修改：**

- `strategy6/models.py`：Brooks结果和三路径字段挂载到评估结果。
- `strategy6/validation.py`：Brooks默认配置、深合并和校验。
- `strategy6/box_tail.py`：复用公共K线指标，不改变箱体行为。
- `strategy6/engine.py`：接入第三路径和触发重建。
- `strategy6/scorer.py`：尾部分使用三路径最高分。
- `strategy6/filters.py`：Brooks-only候选进入现有分层，B级仍最多观察。
- `strategy6/report.py`：追加Brooks和三路径导出字段。
- `strategy6/version.py`：升级策略版本。
- `scanner/db.py`：兼容迁移、保存和读取Brooks结果。
- `server.py`：保持旧API并返回新增字段。
- `config.yaml`：显式写入文档基线 Brooks 配置，不进行参数调优。
- `web/src/utils/strategy6Labels.js`：Brooks状态中文映射。
- `web/src/pages/Strategy6Results.vue`：三路径和Brooks详情展示、CSV追加字段。
- `web/src/pages/StrategyConfig.vue`：Brooks配置展示与保存。
- `web/src/pages/__tests__/Strategy6Results.test.js`
- `web/src/pages/__tests__/StrategyConfig.scheduler.test.js`
- `strategy6/backtest/snapshot.py`：信号快照保存新字段。
- `strategy6/backtest/experiments.py`：新增Brooks分组并保持旧分组语义。
- `strategy6/backtest/report.py`：Brooks分组报告。
- `tests/test_strategy6_box_tail.py`
- `tests/test_strategy6_box_tail_integration.py`
- `tests/test_strategy6_core_rules.py`
- `tests/test_strategy6_db_api.py`
- `tests/test_strategy6_report.py`
- `tests/test_strategy6_backtest_snapshot.py`
- `tests/test_strategy6_backtest_experiments.py`

---

### 任务1：Brooks模型、默认配置与关闭兼容

**文件：**
- 创建：`strategy6/brooks/__init__.py`
- 创建：`strategy6/brooks/models.py`
- 修改：`strategy6/models.py`
- 修改：`strategy6/validation.py`
- 测试：`tests/test_strategy6_brooks_tail.py`
- 测试：`tests/test_strategy6_core_rules.py`

- [ ] **步骤1：编写失败测试**

验证默认配置完整、非法参数拒绝、`enabled=false` 返回 `BROOKS_DISABLED`，并证明原始/箱体双路径候选字典不变。核心断言：

```python
config = resolve_strategy6_config({"strategy6": {"brooks_tail": {"enabled": False}}})
assert config["brooks_tail"]["scoring"]["pass_score_min"] == 14
result = BrooksTailResult.disabled()
assert result.enabled is False
assert result.status == "BROOKS_DISABLED"
assert result.score == 0
```

- [ ] **步骤2：运行红灯测试**

运行：`python -m pytest tests/test_strategy6_brooks_tail.py tests/test_strategy6_core_rules.py -q`

预期：因 `strategy6.brooks` 和 `brooks_tail` 配置不存在而失败。

- [ ] **步骤3：实现最小模型与配置**

定义 `BrooksTailResult`、`BrooksTradeTriggerResult`、`BrooksStructureResult`，所有列表和字典使用 `default_factory`。将外部文档阈值作为明确默认值，并对窗口、比例、分数和枚举做范围校验。

- [ ] **步骤4：运行绿灯测试**

运行：`python -m pytest tests/test_strategy6_brooks_tail.py tests/test_strategy6_core_rules.py -q`

- [ ] **步骤5：提交**

```bash
git add strategy6/brooks strategy6/models.py strategy6/validation.py tests/test_strategy6_brooks_tail.py tests/test_strategy6_core_rules.py
git commit -m "feat: add strategy6 Brooks models and config"
```

### 任务2：共享K线指标并保持箱体逐字段兼容

**文件：**
- 创建：`strategy6/brooks/metrics.py`
- 修改：`strategy6/box_tail.py`
- 测试：`tests/test_strategy6_brooks_metrics.py`
- 测试：`tests/test_strategy6_compact_kline.py`
- 测试：`tests/test_strategy6_box_tail.py`

- [ ] **步骤1：编写失败测试**

覆盖实体、收盘位置、上下影线、振幅、相邻重叠、方向变化、摆动高低点和异常OHLC：

```python
assert close_position({"high": 10, "low": 8, "close": 9}) == 0.5
metric = kline_metrics({"open": 9, "high": 10, "low": 8, "close": 9})
assert metric.body_ratio == 0
invalid = kline_metrics({"open": 0, "high": 0, "low": 0, "close": 0})
assert "INVALID_CLOSE" in invalid.risk_tags
```

增加箱体结果快照测试，断言抽取前后的 `compact_kline`、`box_tail_pass`、`box_score` 和风险标签完全一致。

- [ ] **步骤2：运行红灯测试**

运行：`python -m pytest tests/test_strategy6_brooks_metrics.py tests/test_strategy6_compact_kline.py tests/test_strategy6_box_tail.py -q`

预期：公共指标模块不存在而失败。

- [ ] **步骤3：实现公共指标并机械替换箱体重复计算**

公共函数只返回客观值，不包含 Brooks 或箱体业务结论。保留箱体原有舍入、阈值和风险标签。

- [ ] **步骤4：运行绿灯与兼容测试**

运行：`python -m pytest tests/test_strategy6_brooks_metrics.py tests/test_strategy6_compact_kline.py tests/test_strategy6_box_tail.py tests/test_strategy6_box_tail_integration.py -q`

- [ ] **步骤5：提交**

```bash
git add strategy6/brooks/metrics.py strategy6/box_tail.py tests/test_strategy6_brooks_metrics.py tests/test_strategy6_compact_kline.py tests/test_strategy6_box_tail.py tests/test_strategy6_box_tail_integration.py
git commit -m "refactor: share strategy6 K-line metrics"
```

### 任务3：上涨背景与卖压衰竭

**文件：**
- 创建：`strategy6/brooks/context.py`
- 创建：`strategy6/brooks/selling_pressure.py`
- 测试：`tests/test_strategy6_brooks_context.py`
- 测试：`tests/test_strategy6_brooks_selling_pressure.py`

- [ ] **步骤1：编写背景红灯测试**

构造上涨、弱上涨、交易区间、下降结构和B级启动样本，断言：

```python
assert bull.market_context_type == "BULL_CONTEXT"
assert bull.passed is True
assert bear.market_context_type == "BEAR_CONTEXT"
assert bear.passed is False
assert grade_b.watch_only is True
```

- [ ] **步骤2：编写卖压红灯测试**

覆盖强空方有跟进、无跟进后收回中点、连续三阴且低点下降、单根弱阴和异常K线。

- [ ] **步骤3：运行红灯测试**

运行：`python -m pytest tests/test_strategy6_brooks_context.py tests/test_strategy6_brooks_selling_pressure.py -q`

- [ ] **步骤4：实现背景和卖压模块**

摆动高低点只从评估日及之前数据选择。空方跟进日期必须输出，便于前端和报告解释。

- [ ] **步骤5：运行绿灯测试并提交**

运行：`python -m pytest tests/test_strategy6_brooks_context.py tests/test_strategy6_brooks_selling_pressure.py -q`

```bash
git add strategy6/brooks/context.py strategy6/brooks/selling_pressure.py tests/test_strategy6_brooks_context.py tests/test_strategy6_brooks_selling_pressure.py
git commit -m "feat: analyze strategy6 Brooks context and selling pressure"
```

### 任务4：Brooks结构、紧密分类和尾部分数

**文件：**
- 创建：`strategy6/brooks/structures.py`
- 创建：`strategy6/brooks/compact.py`
- 创建：`strategy6/brooks/tail.py`
- 测试：`tests/test_strategy6_brooks_structures.py`
- 测试：`tests/test_strategy6_brooks_tail.py`

- [ ] **步骤1：编写结构红灯测试**

覆盖两个低点间隔、2%相似度、支撑距离、假跌破2日内收回、空方跟进失败、有序支撑收缩，以及第二低点跌破5%的反例。

- [ ] **步骤2：编写紧密分类红灯测试**

断言 `COMPACT_ORDERLY` 可作为结构，`COMPACT_NEUTRAL` 只能观察，`BARB_WIRE` 阻止交易准备，`COMPACT_BEARISH` 硬拒绝。

- [ ] **步骤3：编写评分和通过红灯测试**

```python
assert premium.score >= 17
assert premium.passed is True
assert bearish.hard_reject is True
assert bearish.passed is False
assert volume_dry_new_lows.volume_dry_pass is True
assert volume_dry_new_lows.passed is False
```

- [ ] **步骤4：运行红灯测试**

运行：`python -m pytest tests/test_strategy6_brooks_structures.py tests/test_strategy6_brooks_tail.py -q`

- [ ] **步骤5：实现结构、分类、评分和候选路径**

Brooks结构分只取最高值，不能累计。Brooks通过同时要求全部硬条件和最低分。

- [ ] **步骤6：运行绿灯测试并提交**

运行：`python -m pytest tests/test_strategy6_brooks_structures.py tests/test_strategy6_brooks_tail.py -q`

```bash
git add strategy6/brooks/structures.py strategy6/brooks/compact.py strategy6/brooks/tail.py tests/test_strategy6_brooks_structures.py tests/test_strategy6_brooks_tail.py
git commit -m "feat: evaluate strategy6 Brooks tail structures"
```

### 任务5：跨日触发、三路径汇总和正式引擎接入

**文件：**
- 创建：`strategy6/brooks/trigger.py`
- 修改：`strategy6/models.py`
- 修改：`strategy6/box_tail.py`
- 修改：`strategy6/engine.py`
- 修改：`strategy6/scorer.py`
- 修改：`strategy6/filters.py`
- 修改：`strategy6/version.py`
- 测试：`tests/test_strategy6_brooks_trigger.py`
- 测试：`tests/test_strategy6_core_rules.py`
- 测试：`tests/test_strategy6_box_tail_integration.py`
- 测试：`tests/test_strategy6_versioning.py`

- [ ] **步骤1：编写触发红灯测试**

覆盖信号日只准备、下一日突破、三日后过期、跳空过远、支撑失效、B级、铁丝网、假跌破确认和突破后1至2日跟进。

- [ ] **步骤2：编写三路径红灯测试**

```python
assert paths.legacy_path == "NONE"
assert paths.paths == ["BROOKS"]
assert paths.summary == "BROOKS"
assert paths.primary == "BROOKS"
assert paths.score == brooks.score
```

三路径同时通过时断言 `score=max(...)`，同分主路径为 Brooks，旧 `tail_path` 仍为 `BOTH`。

- [ ] **步骤3：编写引擎关闭兼容测试**

同一输入分别使用开发前配置和 `brooks_tail.enabled=false`，对旧候选字段逐字段比较。

- [ ] **步骤4：运行红灯测试**

运行：`python -m pytest tests/test_strategy6_brooks_trigger.py tests/test_strategy6_core_rules.py tests/test_strategy6_box_tail_integration.py tests/test_strategy6_versioning.py -q`

- [ ] **步骤5：实现触发、汇总和引擎编排**

现有交易计划保持唯一RR口径。Brooks-only允许进入尾部后续流程，但B级和未触发状态不得伪装为立即买入。

- [ ] **步骤6：运行策略6核心回归并提交**

运行：`python -m pytest tests/test_strategy6_brooks_*.py tests/test_strategy6_core_rules.py tests/test_strategy6_box_tail*.py tests/test_strategy6_versioning.py -q`

```bash
git add strategy6 tests/test_strategy6_brooks_trigger.py tests/test_strategy6_core_rules.py tests/test_strategy6_box_tail_integration.py tests/test_strategy6_versioning.py
git commit -m "feat: integrate Brooks path into strategy6 engine"
```

### 任务6：SQLite、API和报告兼容

**文件：**
- 修改：`scanner/db.py`
- 修改：`server.py`
- 修改：`strategy6/report.py`
- 测试：`tests/test_strategy6_db_api.py`
- 测试：`tests/test_strategy6_report.py`

- [ ] **步骤1：编写数据库红灯测试**

保存并读取 Brooks-only、多路径、详细日期和原因，断言旧任务缺列或空JSON返回默认值。事务失败不得留下部分候选。

- [ ] **步骤2：编写API与报告红灯测试**

候选API保留旧字段并追加结构化 Brooks 字段；CSV保留旧列并追加中文值和原始枚举值。

- [ ] **步骤3：运行红灯测试**

运行：`python -m pytest tests/test_strategy6_db_api.py tests/test_strategy6_report.py -q`

- [ ] **步骤4：实现兼容迁移和混合持久化**

新增常用列与 `brooks_result_json`。列表字段使用JSON，不使用逗号字符串。DB读取统一解析。

- [ ] **步骤5：运行绿灯测试并提交**

运行：`python -m pytest tests/test_strategy6_db_api.py tests/test_strategy6_report.py -q`

```bash
git add scanner/db.py server.py strategy6/report.py tests/test_strategy6_db_api.py tests/test_strategy6_report.py
git commit -m "feat: persist and expose strategy6 Brooks results"
```

### 任务7：前端配置、候选详情和CSV导出

**文件：**
- 修改：`config.yaml`
- 修改：`web/src/utils/strategy6Labels.js`
- 修改：`web/src/pages/Strategy6Results.vue`
- 修改：`web/src/pages/StrategyConfig.vue`
- 修改：`web/src/pages/__tests__/Strategy6Results.test.js`
- 修改：`web/src/pages/__tests__/StrategyConfig.scheduler.test.js`

- [ ] **步骤1：编写前端红灯测试**

断言 Brooks-only 显示“Brooks价格行为”、未触发显示“观察/等待触发”、已触发显示“交易触发已确认”，铁丝网显示风险且不显示买入。旧任务缺字段正常渲染。

- [ ] **步骤2：编写配置红灯测试**

断言配置页可加载、修改和保存 Brooks总开关及分组参数，非法阈值被前端拦截。

- [ ] **步骤3：运行红灯测试**

运行：`npm.cmd --prefix web test -- --run Strategy6Results StrategyConfig.scheduler`

- [ ] **步骤4：实现前端和显式基线配置**

前端展示三路径、Brooks五层证据、结构、触发价、有效期、原因和风险。CSV同时输出中文和原始枚举。`config.yaml` 只写文档基线，不写回测调优值。

- [ ] **步骤5：运行绿灯测试和构建并提交**

运行：

```bash
npm.cmd --prefix web test -- --run Strategy6Results StrategyConfig.scheduler
npm.cmd --prefix web run build
```

```bash
git add config.yaml web/src/utils/strategy6Labels.js web/src/pages/Strategy6Results.vue web/src/pages/StrategyConfig.vue web/src/pages/__tests__/Strategy6Results.test.js web/src/pages/__tests__/StrategyConfig.scheduler.test.js
git commit -m "feat: add strategy6 Brooks frontend controls"
```

### 任务8：历史回放和回测分组

**文件：**
- 修改：`strategy6/backtest/snapshot.py`
- 修改：`strategy6/backtest/experiments.py`
- 修改：`strategy6/backtest/report.py`
- 修改：`tests/test_strategy6_backtest_snapshot.py`
- 修改：`tests/test_strategy6_backtest_experiments.py`
- 修改：`tests/test_strategy6_backtest_report.py`

- [ ] **步骤1：编写未来数据红灯测试**

同一股票在信号日之后构造突破，断言信号日仍是 `SECOND_ENTRY_LONG_READY`，下一评估日才可升级。

- [ ] **步骤2：编写分组红灯测试**

覆盖 `BROOKS_ONLY`、`ORIGINAL_OR_BOX_OR_BROOKS`、`MULTI_PATH_ONLY` 和结构状态分组；证明旧 ORIGINAL/BOX/BOTH 分组数量不变。

- [ ] **步骤3：运行红灯测试**

运行：`python -m pytest tests/test_strategy6_backtest_snapshot.py tests/test_strategy6_backtest_experiments.py tests/test_strategy6_backtest_report.py -q`

- [ ] **步骤4：实现快照与分组**

所有分组读取通过标志或新 `tail_paths`，不依赖扩展旧枚举。OOS、真实指数和成交规则不变。

- [ ] **步骤5：运行绿灯和回测专项测试并提交**

运行：`python -m pytest tests/test_strategy6_backtest_*.py -q`

```bash
git add strategy6/backtest tests/test_strategy6_backtest_snapshot.py tests/test_strategy6_backtest_experiments.py tests/test_strategy6_backtest_report.py
git commit -m "feat: add Brooks groups to strategy6 backtest"
```

### 任务9：真实本地数据验证与验证报告

**文件：**
- 创建：`docs/reviews/2026-07-14-strategy6-brooks-tail-validation.md`

- [ ] **步骤1：运行本地真实数据最小回放**

使用 `data/cuphandle.db` 和真实指数缓存，禁止联网和修改生产配置。记录评估日期、股票数、候选数、ORIGINAL/BOX/BROOKS/MULTI数量、Brooks状态分布、异常数据和耗时。

- [ ] **步骤2：核对增量归因**

验证新增候选全部满足 `brooks_tail_pass=true`，原始/箱体旧结果未被 Brooks 失败抬分，B级和铁丝网没有交易准备。

- [ ] **步骤3：编写报告**

报告明确标记 `RESEARCH_ONLY_CURRENT_UNIVERSE`，不输出正式参数升级结论。

- [ ] **步骤4：提交**

```bash
git add docs/reviews/2026-07-14-strategy6-brooks-tail-validation.md
git commit -m "docs: validate strategy6 Brooks tail path"
```

### 任务10：双角色验收、修复和最终门禁

**文件：**
- 审核本计划涉及的全部文件。

- [ ] **步骤1：审核专家角色检查**

重点检查未来数据、支撑事后选择、空方跟进日期、B级权限、三路径重复加分、旧字段兼容、SQLite迁移、旧任务读取、前端误导、回测分组和策略1至策略5回归。

- [ ] **步骤2：对每个中高问题先写失败测试再修复**

每个问题单独完成红灯、最小修复和专项回归，低等级纯风格问题不扩大范围。

- [ ] **步骤3：运行后端专项门禁**

```bash
python -m pytest tests/test_strategy6_*.py -q
python -m compileall scanner strategy6 server.py -q
```

- [ ] **步骤4：运行后端完整门禁**

```bash
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
```

- [ ] **步骤5：运行前端完整门禁**

```bash
npm.cmd --prefix web test -- --run
npm.cmd --prefix web run build
```

- [ ] **步骤6：检查工作区与提交**

不得纳入开发前已存在的 `docs/reviews/strategy6-comprehensive-optimization/report.md` 修改。

```bash
git diff --check
git status --short
git add <本任务剩余文件>
git commit -m "test: complete strategy6 Brooks acceptance"
git push origin codex/strategy6-strong-vcp-tail
```

