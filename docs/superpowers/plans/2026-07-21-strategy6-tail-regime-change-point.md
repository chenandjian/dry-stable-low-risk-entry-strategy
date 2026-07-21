# 策略6尾部收缩变点识别实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为策略6新增基于鲁棒变点的尾部收缩影子识别、可追溯输出和历史研究能力，同时严格保证正式固定5日尾段及候选结果不变。

**架构：** 新增纯计算模块 `strategy6/tail_regime.py`，只接收评估日可见K线和引擎已计算的支撑上下文；引擎将结果作为诊断字段附加到 `Strategy6Evaluation`，不得传给评分、过滤或生命周期。SQLite、报表和前端仅持久化与展示影子证据；历史研究逐日调用冻结引擎，将固定尾段和变点标签分为四组，并复用现有成交执行语义。

**技术栈：** Python 3.10+、dataclasses、SQLite、pytest、Vue 3、Vitest、现有 Strategy6 As-Of 回测框架。

---

## 文件职责

- 创建 `strategy6/tail_regime.py`：特征计算、鲁棒BIC、方向约束、变点选择、T/T-1确认。
- 修改 `strategy6/models.py`：新增 `Strategy6TailRegime` 和兼容候选字段。
- 修改 `strategy6/validation.py`：解析唯一公开开关 `tail_regime_shadow_enabled`。
- 修改 `strategy6/engine.py`：调用影子识别，不改变正式决策链。
- 修改 `scanner/db.py`：兼容加列、写入和读取影子字段。
- 修改 `strategy6/report.py`：导出影子证据列。
- 修改 `web/src/pages/Strategy6Results.vue`：候选详情显示“尾部变点观察”，明确不参与正式选股。
- 创建 `strategy6/backtest/tail_regime_research.py`：按评估日重放并生成四组对照和研究指标。
- 创建 `tests/test_strategy6_tail_regime.py`：检测器单元测试。
- 修改 `tests/test_strategy6_core_rules.py`：正式决策不变性测试。
- 修改 `tests/test_strategy6_db_api.py`：旧库迁移和API读取测试。
- 修改 `tests/test_strategy6_report.py`：导出字段测试。
- 创建 `tests/test_strategy6_tail_regime_research.py`：As-Of、分组和OOS边界测试。
- 修改 `web/src/pages/__tests__/Strategy6Results.test.js`：影子详情展示测试。
- 创建 `docs/reviews/2026-07-21-strategy6-tail-regime-change-point-validation.md`：真实验证和最终审计结论。

### 任务 1：实现纯变点检测器

**文件：**
- 创建：`strategy6/tail_regime.py`
- 修改：`strategy6/models.py`
- 测试：`tests/test_strategy6_tail_regime.py`

- [ ] **步骤 1：编写已知变点和无变点失败测试**

构造固定日期K线：前12日使用较高成交量/波幅，后6日使用约55%成交量和更窄实体；断言 `status=CONFIRMED`、起点落在预设日期前后1日、`delta_bic>=6`。另构造全程同分布数据，断言 `NO_REGIME_CHANGE`。

- [ ] **步骤 2：运行测试确认因模块缺失而失败**

运行：`python -m pytest tests/test_strategy6_tail_regime.py -q`

预期：FAIL，提示 `strategy6.tail_regime` 或 `Strategy6TailRegime` 尚不存在。

- [ ] **步骤 3：实现模型、特征与鲁棒BIC最小代码**

实现接口：

```python
def evaluate_tail_regime(
    rows: list[dict],
    *,
    consolidation_start_index: int,
    enabled: bool = True,
    big_down_return: float = -0.04,
    big_down_volume_ratio: float = 1.5,
    key_support_price: float | None = None,
) -> Strategy6TailRegime:
    ...
```

内部为每个合法切点计算 `log1p(volume)`、真实波幅率、实体率和绝对收益，基准最多20日、至少5日，尾段至少3日；逐特征计算单段/两段鲁棒BIC并求和，保留 `delta_bic>=6` 且方向约束成立的切点。

- [ ] **步骤 4：补充边界和风险失败测试**

覆盖：仅量缩但价格剧烈、相近BIC选择最早、放量大跌、后半低点恶化、支撑连续两日破位、样本不足、零价格、缺成交量、T初次成立为FORMING、T/T-1起点稳定为CONFIRMED、追加未来K线不改变历史截断结果。

- [ ] **步骤 5：实现Theil-Sen低点斜率、风险状态和连续确认**

使用所有点对斜率中位数计算低点趋势，并用尾段ATR中位数归一化；T-1必须对 `rows[:-1]` 独立重新检测，不能复用T切点或T支撑结论。当前T触发结构风险时返回 `BROKEN` 并保留证据及风险原因。

- [ ] **步骤 6：运行检测器测试并提交**

运行：`python -m pytest tests/test_strategy6_tail_regime.py -q`

预期：全部PASS。

提交：`git add strategy6/tail_regime.py strategy6/models.py tests/test_strategy6_tail_regime.py && git commit -m "feat: add strategy6 tail regime detector"`

### 任务 2：影子接入引擎并锁定正式行为

**文件：**
- 修改：`strategy6/validation.py`
- 修改：`strategy6/engine.py`
- 修改：`strategy6/models.py`
- 修改：`tests/test_strategy6_core_rules.py`

- [ ] **步骤 1：编写开关与正式结果不变性失败测试**

对同一批K线分别以 `tail_regime_shadow_enabled=true/false` 调用 `StrongVcpTailEngine.evaluate_at()`，断言 `dry_tail_pass`、`tail_score`、`total_score`、`reject_reasons`、`candidate_type`、交易计划完全一致；开启时仅新增影子字段，关闭时状态为禁用。

- [ ] **步骤 2：运行测试确认新字段/配置缺失**

运行：`python -m pytest tests/test_strategy6_core_rules.py -q`

预期：新增测试FAIL，原因是引擎未输出 `tail_regime_*`。

- [ ] **步骤 3：最小接入影子计算**

在阶段和支撑计算完成后调用 `evaluate_tail_regime()`，结果只写入 `Strategy6Evaluation.tail_regime`。不得把它传给 `score_strategy6()`、`classify_candidate()`、交易计划或生命周期函数；默认开关为True，V1阈值保持模块常量。

- [ ] **步骤 4：验证正式与研究画像不回归**

运行：`python -m pytest tests/test_strategy6_core_rules.py tests/test_strategy6_phase.py tests/test_strategy6_dry_tail_non_overlap.py -q`

预期：全部PASS，formal_original和research_quality_v2既有行为不变。

- [ ] **步骤 5：提交引擎接入**

提交：`git add strategy6/validation.py strategy6/engine.py strategy6/models.py tests/test_strategy6_core_rules.py && git commit -m "feat: expose strategy6 tail regime shadow evidence"`

### 任务 3：持久化与导出兼容

**文件：**
- 修改：`scanner/db.py`
- 修改：`strategy6/report.py`
- 修改：`tests/test_strategy6_db_api.py`
- 修改：`tests/test_strategy6_report.py`

- [ ] **步骤 1：编写旧库迁移、往返和导出失败测试**

创建不含新列的临时SQLite候选表，触发兼容迁移后保存含理由/风险数组的策略6候选；读取后断言数值、日期、版本和JSON数组保持一致。报告测试断言新列存在且旧候选空值可导出。

- [ ] **步骤 2：运行测试确认缺列失败**

运行：`python -m pytest tests/test_strategy6_db_api.py tests/test_strategy6_report.py -q`

预期：新增断言FAIL，提示影子字段未持久化或未导出。

- [ ] **步骤 3：实现兼容列、写入映射和报告列**

通过现有 `_ensure_column()` 模式增加标量/文本列；`reasons`、`risks`沿用候选JSON序列化与反序列化助手。不得改变旧字段类型、唯一键或候选查询过滤。

- [ ] **步骤 4：验证数据库和报告**

运行：`python -m pytest tests/test_strategy6_db_api.py tests/test_strategy6_report.py -q`

预期：全部PASS。

- [ ] **步骤 5：提交持久化与导出**

提交：`git add scanner/db.py strategy6/report.py tests/test_strategy6_db_api.py tests/test_strategy6_report.py && git commit -m "feat: persist strategy6 tail regime diagnostics"`

### 任务 4：前端候选详情展示

**文件：**
- 修改：`web/src/pages/Strategy6Results.vue`
- 修改：`web/src/pages/__tests__/Strategy6Results.test.js`

- [ ] **步骤 1：编写影子详情失败测试**

候选fixture加入CONFIRMED起点、天数、BIC、四项比值、斜率、理由和风险；断言页面出现“尾部变点观察”“不参与正式选股”“已确认”、起点及核心比值。禁用或旧任务空字段时不得显示误导性的确认状态。

- [ ] **步骤 2：运行测试确认展示缺失**

运行：`npm.cmd --prefix web test -- --run Strategy6Results`

预期：新增断言FAIL，页面尚无“尾部变点观察”。

- [ ] **步骤 3：实现只读诊断卡片**

在候选详情中新增同级卡片，中文映射五种状态，使用百分比/小数安全格式化；顶部固定展示“影子研究，不参与正式评分、过滤和候选分层”。不得增加列表过滤、排序或候选数量计算。

- [ ] **步骤 4：运行前端专项测试并提交**

运行：`npm.cmd --prefix web test -- --run Strategy6Results`

预期：全部PASS。

提交：`git add web/src/pages/Strategy6Results.vue web/src/pages/__tests__/Strategy6Results.test.js && git commit -m "feat: show strategy6 tail regime shadow details"`

### 任务 5：历史As-Of四组研究

**文件：**
- 创建：`strategy6/backtest/tail_regime_research.py`
- 创建：`tests/test_strategy6_tail_regime_research.py`
- 创建：`docs/reviews/2026-07-21-strategy6-tail-regime-change-point-validation.md`

- [ ] **步骤 1：编写分组、未来隔离和OOS失败测试**

使用小型本地fixture逐日调用冻结引擎，断言每个评估日只看到当日及以前数据；四组由 `dry_tail_pass` 与 `tail_regime_status==CONFIRMED` 唯一决定；请求2026收益时明确拒绝；股票无当日K线时不复制前一日信号。

- [ ] **步骤 2：运行研究测试确认模块缺失**

运行：`python -m pytest tests/test_strategy6_tail_regime_research.py -q`

预期：FAIL，提示研究模块不存在。

- [ ] **步骤 3：实现标签重放和每日明细**

提供纯研究入口，复用冻结 `StrongVcpTailEngine.evaluate_at()`，输出 `evaluation_date/code/group/fixed_pass/fixed_reasons/regime_status/start_date/days/delta_bic`。禁止复制流动性、趋势、启动、形态、支撑、市场和RR判断。

- [ ] **步骤 4：实现REGIME_ONLY假设信号适配与现有成交复用**

仅在其它正式门槛均通过、唯一阻塞来自ORIGINAL固定尾段时建立假设信号；订单、NEXT_OPEN、T+1、费用、滑点、停牌、涨跌停和STOP_FIRST交给现有回测执行器。训练期为2023-2024，2025只确认，2026收益读取返回锁定状态。

- [ ] **步骤 5：运行研究测试与真实本地数据报告**

运行：`python -m pytest tests/test_strategy6_tail_regime_research.py tests/test_strategy6_backtest_* -q`

预期：全部PASS。

在本地真实个股和四指数覆盖允许时运行2023-2025研究，报告四组逐日股票、闭合交易数、期望R、PF、平均盈亏比和压力测试；若指数或历史覆盖不足，报告必须写明 `BLOCKED_INDEX_HISTORY`，不得关闭市场过滤伪造结论。

- [ ] **步骤 6：提交历史研究与报告**

提交：`git add strategy6/backtest/tail_regime_research.py tests/test_strategy6_tail_regime_research.py docs/reviews/2026-07-21-strategy6-tail-regime-change-point-validation.md && git commit -m "feat: add strategy6 tail regime historical research"`

### 任务 6：完整验证与双角色验收

**文件：**
- 修改：`docs/reviews/2026-07-21-strategy6-tail-regime-change-point-validation.md`

- [ ] **步骤 1：运行策略6专项验证**

运行：

```powershell
python -m pytest tests/test_strategy6_tail_regime.py tests/test_strategy6_core_rules.py tests/test_strategy6_db_api.py tests/test_strategy6_report.py tests/test_strategy6_tail_regime_research.py -q
```

预期：全部PASS。

- [ ] **步骤 2：运行后端、编译和前端门禁**

运行：

```powershell
python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner strategy2 strategy3 strategy4 strategy5 strategy6 server.py -q
npm.cmd --prefix web test -- --run
npm.cmd --prefix web run build
```

预期：测试全绿、compileall无错误、前端构建成功。

- [ ] **步骤 3：切换审核专家角色检查中高风险**

逐项审查：未来数据泄漏、T-1复用T上下文、正式决策漂移、研究路径反向污染配置、旧库迁移、旧任务空字段、前端误导、OOS收益读取、用户未提交文件被误改。发现中高问题先写失败测试，再切回程序员角色修复并重跑门禁。

- [ ] **步骤 4：记录真实结果并提交验收文档**

在验证报告中记录真实命令、通过数量、研究任务/阻塞状态、正式行为不变证据和残余风险。

提交：`git add docs/reviews/2026-07-21-strategy6-tail-regime-change-point-validation.md && git commit -m "docs: validate strategy6 tail regime shadow research"`

- [ ] **步骤 5：检查工作区并推送当前分支**

运行：`git status --short`，确认仅保留开发前已存在的用户修改；不得暂存这些文件。运行：`git push`。

预期：`codex/strategy6-strong-vcp-tail`推送成功；不合并main，除非用户另行要求。

## 完成标准

1. 固定5日正式尾段和正式候选结果在影子开关前后逐字段一致。
2. 变点结果可在引擎、SQLite、报告和前端详情完整追溯。
3. T/T-1及历史研究严格As-Of，不读取2026起收益。
4. 历史研究明确给出四组逐日股票和门禁结论；数据不足时阻塞而非降低标准。
5. 后端、前端和编译门禁通过，双角色复审无中高等级问题。
