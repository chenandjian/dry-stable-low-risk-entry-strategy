# 策略6 VCP 生命周期独立观察池实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在不改变策略6主交易链和现有扫描入口的前提下，新增可独立识别、保存和展示完整 VCP 生命周期的“VCP形态候选”观察板块，并确保 `002156` 不再因尾段切分或新启动重置而丢失 VCP 身份。

**架构：** 新增纯函数观察器，从截至评估日的最近60根日线独立重建 VCP 收缩链，不复用主链 `tail_start_index`。观察结果作为 `Strategy6Evaluation` 的正交维度输出；扫描器分别处理交易生命周期与观察快照，使被主链拒绝但 VCP 有效的股票可以保存，却不进入正式候选计数。数据库继续使用 `strategy6_candidates` 增量字段，原候选 API 返回兼容超集；前端新增与重点/观察候选同级的独立板块。

**技术栈：** Python 3.10+、dataclass、SQLite 增量迁移、FastAPI、Vue 3、Vitest、pytest。

---

## 文件职责

- 创建 `strategy6/vcp_observer.py`：只负责截至评估日的 VCP 收缩链和生命周期状态计算。
- 修改 `strategy6/models.py`：新增 `Strategy6VcpObservation`，并向候选字典追加兼容字段。
- 修改 `strategy6/validation.py`：新增观察窗口、突破保留期和延伸阈值配置及校验。
- 修改 `strategy6/engine.py`：调用观察器；不改变主形态、评分、硬过滤与交易分类输入。
- 修改 `strategy6/scanner.py`：交易候选照旧统计，观察专用记录额外保存。
- 修改 `scanner/db.py`：增量字段、JSON 序列化、观察快照原子保存；旧任务返回安全默认值。
- 修改 `web/src/pages/Strategy6Results.vue`：在市场过滤后新增同级 VCP 板块、详情和 CSV 字段。
- 修改 `web/src/utils/strategy6Labels.js`：新增 VCP 状态、原因和风险中文标签。
- 创建 `tests/test_strategy6_vcp_observer.py`：纯函数、状态转换、As-Of 防未来泄漏与 `002156` 验收。
- 修改 `tests/test_strategy6_core_rules.py`、`tests/test_strategy6_scanner.py`、`tests/test_strategy6_db_api.py`：引擎、扫描、DB/API 兼容测试。
- 修改 `web/src/pages/__tests__/Strategy6Results.test.js`：独立板块、重复展示、详情与导出测试。
- 创建 `docs/reviews/2026-07-15-strategy6-vcp-observation-pool-validation-report.md`：真实数据逐日结果和候选数量对比。

### 任务 1：定义 VCP 观察契约和配置

- [ ] 在 `tests/test_strategy6_vcp_observer.py` 写失败测试，要求默认配置包含：
  - `vcp_observer_enabled=true`
  - `vcp_observer_lookback_days=60`
  - `vcp_observer_breakout_retention_days=10`
  - `vcp_observer_extension_pct=0.08`
- [ ] 在 `tests/test_strategy6_core_rules.py` 写失败测试，要求 `to_candidate_dict()` 总是返回全部 VCP 字段；默认值必须是 `false`、`VCP_NONE`、空字符串、零值或空数组。
- [ ] 运行：
  `python -m pytest tests/test_strategy6_vcp_observer.py tests/test_strategy6_core_rules.py -q`
  预期：因配置和模型尚不存在而失败。
- [ ] 在 `strategy6/models.py` 新增 `Strategy6VcpObservation`，字段名严格使用设计文档第7节；`Strategy6Evaluation.vcp_observation` 使用 `default_factory`，避免破坏旧构造调用。
- [ ] 在 `strategy6/validation.py` 增加默认值并校验：观察窗口为 `20..250` 的整数，保留期为 `1..60` 的整数，延伸阈值为 `(0, 1]`。
- [ ] 在 `Strategy6Evaluation.to_candidate_dict()` 只追加新字段，不删除或改名旧字段。
- [ ] 重跑专项测试至通过。

### 任务 2：TDD 实现独立 VCP 观察器

- [ ] 先写以下失败测试：
  - 两段振幅、均量依次收缩且低点不下移，返回 `VCP_FORMING`。
  - 当前价接近最后支点，返回 `VCP_NEAR_PIVOT`。
  - 收盘突破支点且量价确认，返回 `VCP_BREAKOUT_CONFIRMED`。
  - 突破后保留期内返回 `VCP_POST_BREAKOUT`；偏离支点超过阈值返回 `VCP_EXTENDED`。
  - 收盘跌破最后结构低点，或放量跌破后3日未收复，返回 `VCP_INVALID` 且 `eligible=false`。
  - 超过10个交易日且未形成新低风险结构，返回 `VCP_NONE`。
  - 同一前缀数据增加未来K线后，历史评估结果不变。
- [ ] 运行上述测试，确认失败原因是 `evaluate_vcp_observation` 不存在。
- [ ] 在 `strategy6/vcp_observer.py` 实现：
  - 输入只接受已按评估日截断的 `rows` 与已解析配置。
  - 最近 `lookback_days` 内计算峰谷收缩段，沿用主 VCP 的振幅比、均量比、首段最小振幅和低点不下移口径。
  - 支点取最后有效收缩段峰值收盘，结构低点取最后有效收缩段低点。
  - 突破日只能从最后收缩低点之后的已知K线寻找。
  - 输出收缩证据使用可 JSON 序列化的日期、振幅、均量和相邻收缩比。
  - `VCP_EXTENDED` 只打观察风险标签，不生成或修改买价、止损和目标。
- [ ] 重跑观察器测试至通过，并确认 `strategy6/pattern.py` 既有测试结果不变。

### 任务 3：引擎接入且不改变主交易链

- [ ] 在 `tests/test_strategy6_core_rules.py` 写失败测试：同一输入接入前后 `pattern_type`、总分、硬过滤原因、`candidate_type` 和交易计划保持原语义，而 `vcp_observation` 可独立为 eligible。
- [ ] 写失败测试：新强势启动重置主 `tail_start_index` 后，观察器仍保留此前已确认 VCP。
- [ ] 在 `strategy6/engine.py` 完成指标计算后调用 `evaluate_vcp_observation(rows, config)`，把结果放入 `Strategy6Evaluation`；不得把观察状态传给 `score_strategy6()`、`hard_filter_reasons()` 或 `classify_candidate()`。
- [ ] 运行策略6核心与形态专项：
  `python -m pytest tests/test_strategy6_vcp_observer.py tests/test_strategy6_pattern.py tests/test_strategy6_core_rules.py -q`

### 任务 4：扫描持久化、数据库和 API 兼容

- [ ] 在 `tests/test_strategy6_scanner.py` 写失败测试：
  - 正式候选仍按原逻辑计入 `candidates_found`。
  - `candidate_type=REJECTED` 但 `vcp_observation_eligible=true` 的股票被保存到任务快照。
  - 该观察记录不进入扫描返回的正式 `candidates`、不把 `task_stocks` 标为 `candidate`，也不创建或推进交易候选生命周期。
- [ ] 在 `tests/test_strategy6_db_api.py` 写失败测试：新字段完整往返，旧行返回默认值，原候选 API 不变。
- [ ] 在 `scanner/db.py` 对 `strategy6_candidates` 使用 `_ensure_column()` 增量增加字段；数组和收缩明细使用项目 JSON 辅助函数序列化。
- [ ] 新增事务内观察快照写入路径：交易候选继续使用 `persist_strategy6_evaluation()`；观察专用记录直接 upsert 任务候选快照，不调用 `update_strategy6_lifecycle()`，并保留其原始 `candidate_type=REJECTED`。
- [ ] 在 `strategy6/scanner.py` 分开构造：
  - `trading_candidate = evaluation.to_candidate_dict()` 仅当 `evaluation.passed`；
  - `observation_snapshot = evaluation.to_candidate_dict()` 仅当主链未通过但观察资格成立。
  正式候选计数和进度事件只使用第一项。
- [ ] 运行：
  `python -m pytest tests/test_strategy6_scanner.py tests/test_strategy6_db_api.py -q`

### 任务 5：前端同级 VCP 形态候选板块

- [ ] 在 `web/src/pages/__tests__/Strategy6Results.test.js` 写失败测试：
  - 页面顺序为“市场过滤数据 → VCP形态候选 → 重点候选 → 观察候选”。
  - `vcp_observation_eligible=true` 的 REJECTED 记录也出现在 VCP 板块。
  - 同时为 KEY/WATCH 的股票在原板块继续显示，允许重复。
  - `VCP_INVALID`、旧任务默认值不显示。
  - 表格显示状态、收缩次数、支点、结构低点、距支点、突破日、总分、原交易分类、风险提示。
  - 点击行复用现有详情；CSV 在旧列之后追加 VCP 字段。
- [ ] 运行：
  `npm.cmd --prefix web test -- --run Strategy6Results`
  预期：因页面尚无 VCP 板块而失败。
- [ ] 在 `Strategy6Results.vue` 增加 `vcpCandidates` 计算属性和独立 `<section>`，位置固定在市场面板后、候选循环前；不从 `candidateGroups` 中移除任何股票。
- [ ] 在详情面板展示生命周期、每段收缩证据、观察原因、风险和失效原因。
- [ ] 在 `strategy6Labels.js` 增加中文映射，未知值继续使用现有回退逻辑。
- [ ] 重跑前端专项至通过。

### 任务 6：真实数据 As-Of 验收和对比报告

- [ ] 从 `data/cuphandle.db` 读取 `002156`，逐日截断到 2026-05-26 至 2026-07-14，禁止把未来K线传入引擎。
- [ ] 把真实样本转为自动化测试，至少断言：
  - 2026-07-08 为 `VCP_NEAR_PIVOT`；
  - 2026-07-09 为 `VCP_BREAKOUT_CONFIRMED`；
  - 2026-07-10 至 2026-07-14 为 `VCP_POST_BREAKOUT` 或 `VCP_EXTENDED`；
  - 主交易分类仍由原链决定，延伸状态没有立即买入语义。
- [ ] 对同一历史区间运行修改前后全股票逐日比较，报告新增、共同、失效和退出数量，并检查是否出现无控制膨胀。
- [ ] 将命令、样本日期、状态、数量和风险写入 `docs/reviews/2026-07-15-strategy6-vcp-observation-pool-validation-report.md`。

### 任务 7：双角色验收、修复和完整门禁

- [ ] 审核专家角色检查：未来数据泄漏、观察/交易身份混淆、生命周期污染、旧库迁移、并发事务、旧任务误显示、前端重复去重、候选计数回归。
- [ ] 对每个中高等级问题先补失败测试，再做最小修复，循环至无中高等级问题。
- [ ] 运行策略6专项：
  `python -m pytest tests/test_strategy6_vcp_observer.py tests/test_strategy6_core_rules.py tests/test_strategy6_pattern.py tests/test_strategy6_scanner.py tests/test_strategy6_db_api.py tests/test_strategy6_backtest_snapshot.py -q`
- [ ] 运行后端回归：
  `python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py`
- [ ] 运行编译检查：
  `python -m compileall scanner strategy6 server.py -q`
- [ ] 运行前端回归和构建：
  `npm.cmd --prefix web test -- --run`
  `npm.cmd --prefix web run build`
- [ ] 仅暂存本计划所列代码、测试和新报告，明确排除用户已有的两份修改报告和 `B2-coarse/`。
- [ ] 提交并推送当前分支，记录 commit hash 和真实 push 结果。

## 自检结论

- 规格覆盖：独立识别、状态生命周期、观察/交易双维度、DB兼容、前端同级展示、重复保留、`002156` As-Of、对比报告和回归门禁均有对应任务。
- 边界已锁定：观察专用 REJECTED 快照不进入交易生命周期，不影响候选计数，不产生买入语义。
- 类型一致：统一使用 `vcp_observation_eligible` 与 `vcp_lifecycle_status`；所有新增数组字段通过 JSON 往返。
- 无占位项：所有实施步骤均指定文件、行为、验证命令和预期结果。
