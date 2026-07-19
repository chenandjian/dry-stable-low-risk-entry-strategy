# 策略6全面参数调优实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 实现并运行策略6七阶段全面参数调优，使用训练期选择、2025验证期确认、真实压力重放和锁定OOS，输出不自动修改生产配置的参数建议。

**架构：** 在 `strategy6/backtest/` 中新增参数注册表、阶段清单、训练选择器和综合报告器。粗筛对完整股票池使用2023-2024训练期及固定5日评估步长；每层入围参数必须独立使用完整2023-2025逐日As-Of重建。SQLite保存阶段、父参数、试验状态和逐股断点，所有生产策略判断继续只调用 `StrongVcpTailEngine.evaluate_at()`。

**技术栈：** Python 3.10+、dataclasses、SQLite、ProcessPoolExecutor、pytest、现有策略6回测模块、JSON/CSV/Markdown。

---

### 任务1：全面参数注册表与合法组合

**文件：**
- 创建：`strategy6/backtest/parameter_registry.py`
- 修改：`strategy6/backtest/validation.py`
- 测试：`tests/test_strategy6_comprehensive_parameter_registry.py`

- [ ] 编写失败测试，断言七个阶段、全部可调参数、默认值、候选值、类型和父阶段顺序完整。
- [ ] 编写失败测试，断言固定参数不会出现在搜索空间。
- [ ] 编写失败测试，覆盖成交额、年龄、杯柄深度、量干阈值、箱体、紧密K线、评分和RR联动约束。
- [ ] 实现 `ParameterSpec`、`StageSpec`、`build_comprehensive_registry()` 和 `validate_stage_combination()`。
- [ ] 实现等级振幅/回撤成组扰动和紧密K线窗口相关合法值生成。
- [ ] 运行 `python -m pytest tests/test_strategy6_comprehensive_parameter_registry.py -q`。
- [ ] 提交 `feat: add strategy6 comprehensive parameter registry`。

### 任务2：阶段与试验持久化

**文件：**
- 修改：`scanner/db.py`
- 测试：`tests/test_strategy6_comprehensive_optimization_db.py`

- [ ] 编写旧库兼容建表失败测试，要求创建 `strategy6_optimization_campaigns`、`strategy6_optimization_stages` 和 `strategy6_optimization_trials`。
- [ ] 编写campaign、阶段、父参数集、粗筛/完整运行ID、状态、淘汰原因和选择指标往返测试。
- [ ] 编写相同campaign清单幂等重建测试。
- [ ] 实现兼容表、唯一索引和原子upsert，不修改已有回测表含义。
- [ ] 实现只允许 `COMPLETED` 或 `COMPLETED_WITH_SKIPS` 且零FAILED试验进入选择器的查询。
- [ ] 运行 `python -m pytest tests/test_strategy6_comprehensive_optimization_db.py -q`。
- [ ] 提交 `feat: persist strategy6 optimization campaigns`。

### 任务3：粗筛评估步长与完整重跑门禁

**文件：**
- 修改：`strategy6/backtest/runner.py`
- 修改：`strategy6/backtest/models.py`
- 修改：`strategy6/backtest/validation.py`
- 测试：`tests/test_strategy6_comprehensive_evaluation_schedule.py`

- [ ] 编写训练期日期选择测试：粗筛只允许2023-2024且每5个真实交易日评估一次。
- [ ] 编写完整重跑测试：入围参数必须逐日覆盖2023-2025，不得读取2026日期。
- [ ] 编写运行身份测试：`evaluation_step`、阶段、父参数集和日期范围必须进入run ID及配置哈希。
- [ ] 实现 `build_evaluation_schedule()` 和运行元数据，默认旧CLI仍保持逐日行为。
- [ ] 在逐股进度和报告中记录实际评估日期数，禁止粗筛任务标记为最终可信结果。
- [ ] 运行专项回测测试并提交 `feat: add staged strategy6 evaluation schedules`。

### 任务4：单参数敏感性与联合试验清单

**文件：**
- 创建：`strategy6/backtest/campaign.py`
- 修改：`strategy6/backtest/optimization.py`
- 测试：`tests/test_strategy6_comprehensive_campaign.py`

- [ ] 编写每阶段默认基线和逐参数候选均生成独立参数集的失败测试。
- [ ] 编写同一固定种子重复生成相同联合试验的测试。
- [ ] 编写只改变当前阶段字段、冻结父阶段字段和未来阶段默认字段的测试。
- [ ] 实现OAT敏感性清单、合法区域筛选和每阶段最多24组固定种子联合试验。
- [ ] 实现campaign重启时复用已完成试验并只调度缺失/FAILED试验。
- [ ] 运行专项测试并提交 `feat: build strategy6 staged optimization campaigns`。

### 任务5：训练期选择器、硬门槛与提前拒绝

**文件：**
- 创建：`strategy6/backtest/selector.py`
- 修改：`strategy6/backtest/metrics.py`
- 测试：`tests/test_strategy6_comprehensive_selector.py`

- [ ] 编写训练指标排序不读取验证/OOS字段测试。
- [ ] 编写样本、期望R、PF、盈亏比、回撤和集中度硬门槛测试。
- [ ] 编写负训练期、样本不足和FAILED任务返回 `KEEP_PREVIOUS_STAGE` 测试。
- [ ] 编写Pareto与邻域60%/85%稳定平台测试。
- [ ] 实现稳健分、阶段选择结果、淘汰原因和最多3个完整重跑入围参数。
- [ ] 提前拒绝只允许读取训练期完整终态，任何验证/OOS字段触发 `OOSAccessError` 或选择器错误。
- [ ] 运行专项测试并提交 `feat: select robust strategy6 stage parameters`。

### 任务6：综合调优CLI与可恢复调度

**文件：**
- 修改：`strategy6/backtest/cli.py`
- 修改：`strategy6/backtest/runner.py`
- 创建：`strategy6/backtest/comprehensive_runner.py`
- 测试：`tests/test_strategy6_comprehensive_cli.py`

- [ ] 新增 `comprehensive-plan`、`comprehensive-run`、`comprehensive-status` 和 `comprehensive-report` 命令解析测试。
- [ ] 编写阶段必须串行、同阶段参数试验可恢复、父阶段未冻结不得启动下一阶段测试。
- [ ] 编写Ctrl+C/进程中断后数据库保留RUNNING并可重入测试。
- [ ] 实现campaign创建、阶段粗筛、训练选择、最多3组完整重跑、验证确认和冻结/保留上一阶段编排。
- [ ] 参数集内部继续使用现有逐股多进程；SQLite只由父进程写入。
- [ ] 输出campaign、阶段、参数集和逐股四级进度与预计剩余工作量。
- [ ] 运行专项测试并提交 `feat: orchestrate strategy6 comprehensive optimization`。

### 任务7：执行参数和压力重放

**文件：**
- 修改：`strategy6/backtest/stress.py`
- 修改：`strategy6/backtest/execution.py`
- 测试：`tests/test_strategy6_comprehensive_execution_tuning.py`

- [ ] 编写买入有效期和最大持有期独立于信号参数重放测试。
- [ ] 编写费用不能低于BASE、T+1和涨跌停语义不可调测试。
- [ ] 编写高成本、70%成交率、延迟一天必须基于冻结信号重放测试。
- [ ] 实现执行参数清单、重放指标和压力通过判定。
- [ ] 运行专项测试并提交 `feat: tune strategy6 execution parameters safely`。

### 任务8：全面报告与候选明细

**文件：**
- 创建：`strategy6/backtest/comprehensive_report.py`
- 修改：`strategy6/backtest/report.py`
- 测试：`tests/test_strategy6_comprehensive_report.py`

- [ ] 编写全参数字典、阶段敏感性、联合试验、训练/验证、Pareto、邻域、压力和推荐字段测试。
- [ ] 编写无合格参数时仍输出完整空结果和 `KEEP_PREVIOUS_STAGE` 原因测试。
- [ ] 编写生产配置差异只读测试。
- [ ] 输出Markdown、JSON、阶段试验CSV、每日候选CSV、订单CSV和交易CSV。
- [ ] 报告必须包含Git提交、数据版本、campaign/run/parameter ID、幸存者偏差和OOS锁。
- [ ] 运行专项测试并提交 `feat: report strategy6 comprehensive optimization`。

### 任务9：真实七阶段全面调优

**文件：**
- 生成：`docs/reviews/strategy6-comprehensive-optimization/`
- 创建：`docs/reviews/2026-07-12-strategy6-comprehensive-parameter-optimization-report.md`

- [ ] 运行 `comprehensive-plan`，保存七层参数和预计试验数。
- [ ] 对每层运行全股票池训练期5日步长OAT和联合粗筛。
- [ ] 使用训练期选择器冻结稳定区域或记录 `KEEP_PREVIOUS_STAGE`。
- [ ] 每层最多3个入围参数使用2023-2025逐日全量重跑。
- [ ] 只用2025验证期确认，不根据结果新增组合。
- [ ] 最后单独运行执行参数和三类压力重放。
- [ ] 生成完整报告和每日候选；生产 `config.yaml` 保持不变。
- [ ] 若运行超过单次命令时限，使用campaign断点恢复，禁止缩小股票池。

### 任务10：双角色验收与交付

**文件：**
- 修改：`AGENTS.md`
- 修改：`CLAUDE.md`
- 修改：审核发现问题的实现、测试和报告文件

- [ ] 审核参数覆盖、阶段冻结、训练/验证/OOS隔离、未来数据、恢复幂等、压力真实性和生产配置只读。
- [ ] 对每个中高问题先写失败测试再修复，循环至无中高问题。
- [ ] 运行 `python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py`。
- [ ] 运行 `python -m compileall scanner strategy6 server.py -q`、`git diff --check`。
- [ ] 运行 `npm.cmd --prefix web test -- --run` 和 `npm.cmd --prefix web run build`。
- [ ] 验证 `git diff -- config.yaml` 为空、最终报告可追溯、工作区干净。
- [ ] 提交并推送 `codex/strategy6-strong-vcp-tail`，不合并main，除非用户另行要求。
