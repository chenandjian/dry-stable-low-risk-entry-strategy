# 策略6双路径历史回测与参数调优实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在策略6冻结生产入口上实现P0-P3历史信号、真实成交、组合实验和稳健参数研究，并锁定但不运行OOS。

**架构：** 新建 `strategy6/backtest/` 专用研究包；策略信号只由 `StrongVcpTailEngine.evaluate_at()` 按日期截断重建，成交和优化读取不可变快照。SQLite保存版本、参数、信号、订单、交易和指标，CLI生成可审计报告，生产配置只读。

**技术栈：** Python 3.10+、dataclasses、SQLite、pytest、现有Strategy6引擎、JSON/CSV/Markdown。

**完成状态（2026-07-12）：** P0-P3已完成实现、真实全市场运行、压力验证和报告交付；P4 OOS按设计保持锁定，未运行。真实结论为 `KEEP_DEFAULT / REJECT_BOX_EXPANSION`，详见 `docs/reviews/2026-07-12-strategy6-box-backtest-parameter-optimization-final-report.md`。

---

### 任务1：数据模型、运行配置与OOS保护

**文件：**
- 创建：`strategy6/backtest/__init__.py`
- 创建：`strategy6/backtest/models.py`
- 创建：`strategy6/backtest/config.py`
- 创建：`strategy6/backtest/validation.py`
- 测试：`tests/test_strategy6_backtest_models.py`
- 测试：`tests/test_strategy6_backtest_validation.py`

- [ ] 先写运行ID、参数集ID、配置哈希、时间切分和可信度标签测试。
- [ ] 先写OOS收益访问抛出 `OOSAccessError` 的失败测试。
- [ ] 实现冻结配置、默认费用、成交、仓位和研究约束。
- [ ] 实现 `min_box_days <= max_box_days` 等参数合法性校验。
- [ ] 验证相同输入和随机种子生成相同ID和参数顺序。

### 任务2：SQLite兼容表与原子读写

**文件：**
- 修改：`scanner/db.py`
- 测试：`tests/test_strategy6_backtest_db.py`

- [ ] 先写旧数据库初始化后自动创建7张策略6回测表的测试。
- [ ] 先写运行、参数、信号、订单、交易、指标往返测试。
- [ ] 实现兼容建表和索引，不修改现有表含义。
- [ ] 单参数集的信号替换必须在同一事务中完成且幂等。
- [ ] OOS查询默认拒绝，只有最终人工授权接口可读取。

### 任务3：本地数据审计和真实指数历史

**文件：**
- 创建：`strategy6/backtest/data.py`
- 创建：`strategy6/backtest/index_history.py`
- 测试：`tests/test_strategy6_backtest_data.py`
- 测试：`tests/test_strategy6_backtest_index_history.py`

- [ ] 先写个股/指数日期排序、重复、OHLC非法和数据指纹测试。
- [ ] 先写指数覆盖不足时返回 `BLOCKED_INDEX_HISTORY` 的测试。
- [ ] 复用现有指数抓取器补齐四个宽基指数，只写 `market_index_ohlc`。
- [ ] 对历史日期构造 `sh000001/sz399001/sz399006/hs300` 截断视图。
- [ ] 记录当前股票池偏差、缺失状态和 `UNKNOWN_NO_BAR` 统计。

### 任务4：As-Of信号重建和不可变快照

**文件：**
- 创建：`strategy6/backtest/snapshot.py`
- 测试：`tests/test_strategy6_backtest_snapshot.py`

- [ ] 先写未来5日形成更优箱体但历史信号不得读取的测试。
- [ ] 先写ORIGINAL/BOX/BOTH归因、失败箱体不抬分测试。
- [ ] 先写相同setup连续信号保留、订单层去重的测试。
- [ ] 逐日截断个股与指数数据并调用正式引擎。
- [ ] 保存完整候选JSON、策略版本、配置哈希、数据指纹和setup签名。
- [ ] 参数改变时生成独立快照，禁止复用旧箱体结果。

### 任务5：保守订单与单笔成交模拟

**文件：**
- 创建：`strategy6/backtest/execution.py`
- 测试：`tests/test_strategy6_backtest_execution.py`

- [ ] 先写下一交易日、买入区间、有效期、低开取消和高开不追测试。
- [ ] 先写一字涨停、零成交量和 `UNKNOWN_NO_BAR` 不成交测试。
- [ ] 先写买入日止损穿越但T+1不得卖出测试。
- [ ] 先写后续同日止损与目标同时触发时止损优先测试。
- [ ] 先写费用、最低佣金、印花税、过户费和滑点测试。
- [ ] 实现冻结交易计划回放，不重新计算买点、止损和目标。

### 任务6：P0基线服务和E0回归

**文件：**
- 创建：`strategy6/backtest/service.py`
- 创建：`strategy6/backtest/cli.py`
- 测试：`tests/test_strategy6_backtest_service.py`

- [ ] 先写 `box_tail.enabled=false` 的E0基线信号测试。
- [ ] 先写运行失败、恢复、幂等重跑和完整终态测试。
- [ ] 编排数据审计、快照、订单和交易持久化。
- [ ] 生成P0漏斗、未成交原因和单笔交易汇总。
- [ ] CLI支持 `audit-data`、`fetch-index`、`baseline`。

### 任务7：组合资金和双路径实验

**文件：**
- 创建：`strategy6/backtest/portfolio.py`
- 创建：`strategy6/backtest/experiments.py`
- 测试：`tests/test_strategy6_backtest_portfolio.py`
- 测试：`tests/test_strategy6_backtest_experiments.py`

- [ ] 先写固定等权、固定风险、现金不足和并发持仓测试。
- [ ] 先写同日候选按生产分层和总分排序测试。
- [ ] 实现E0-E5和9组消融实验，使用相同数据、费用和资金约束。
- [ ] 计算BOX增量交易、资金挤占和组合净值差。
- [ ] 紧密排列只用于分组和显式研究排序实验。

### 任务8：指标、分组与收益集中度

**文件：**
- 创建：`strategy6/backtest/metrics.py`
- 测试：`tests/test_strategy6_backtest_metrics.py`

- [ ] 先写期望R、利润因子、最大回撤、夏普、索提诺和卡玛测试。
- [ ] 先写ORIGINAL/BOX/BOTH、箱体状态、紧密标签分组测试。
- [ ] 先写单股、前5股、年度、月度和路径利润贡献测试。
- [ ] 实现信号层、交易层和组合层指标，零交易返回完整零值结果。
- [ ] 命中集中度阈值时输出高风险标签。

### 任务9：参数敏感性、Pareto和稳定平台

**文件：**
- 创建：`strategy6/backtest/optimization.py`
- 测试：`tests/test_strategy6_backtest_optimization.py`

- [ ] 先写非法组合拒绝、固定随机种子重复性测试。
- [ ] 先写单参数敏感性和分组搜索只改变指定参数测试。
- [ ] 先写硬约束过滤和Pareto支配关系测试。
- [ ] 先写邻域60%通过、分数中位数85%和边界峰值拒绝测试。
- [ ] 实现最多2000次分层随机抽样，不执行全笛卡尔积。
- [ ] 优化结果只生成推荐对象，不修改生产配置。

### 任务10：时间验证、压力测试和OOS锁定

**文件：**
- 创建：`strategy6/backtest/walk_forward.py`
- 创建：`strategy6/backtest/stress.py`
- 测试：`tests/test_strategy6_backtest_walk_forward.py`
- 测试：`tests/test_strategy6_backtest_stress.py`

- [ ] 先写训练/验证不重叠和OOS不可读测试。
- [ ] 数据不足标准3+1窗口时输出 `INSUFFICIENT_DATA`，不得伪造结果。
- [ ] 实现成本、低成交、延迟一天、持有期和参数扰动场景。
- [ ] OOS只保存锁定范围和哈希，P0-P3不生成OOS交易指标。

### 任务11：完整报告和真实数据运行

**文件：**
- 创建：`strategy6/backtest/report.py`
- 创建：`docs/reviews/2026-07-11-strategy6-box-backtest-parameter-optimization-report.md`
- 测试：`tests/test_strategy6_backtest_report.py`

- [ ] 先写JSON、CSV、Markdown必须字段测试。
- [ ] 输出每日信号候选、订单、交易、E0-E5、参数试验、Pareto和压力测试。
- [ ] 联网补齐四个指数并验证覆盖范围。
- [ ] 使用本地个股数据运行P0-P3；若运行量过大，保存可恢复进度，不缩小股票池冒充全量。
- [ ] 报告明确 `RESEARCH_ONLY_CURRENT_UNIVERSE`、幸存者偏差和OOS未运行。

### 任务12：双角色验收、回归与交付

**文件：**
- 修改：`AGENTS.md`
- 修改：`CLAUDE.md`
- 修改：上述实现和测试中发现问题的文件

- [ ] 审核未来数据、成交顺序、重复信号、资金占用、OOS隔离和配置只读。
- [ ] 发现中高问题先写失败测试再修复，循环至无中高问题。
- [ ] 运行全部策略6回测测试、策略6测试、后端全量回归和compileall。
- [ ] 验证真实报告可追溯到策略提交、参数、数据指纹和信号快照。
- [ ] 提交并推送 `codex/strategy6-strong-vcp-tail`，保持工作区干净。
