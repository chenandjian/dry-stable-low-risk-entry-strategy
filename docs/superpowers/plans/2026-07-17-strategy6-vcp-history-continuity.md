# 策略6 VCP历史资格连续性实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 阻止已经发生深度下跌或持续空头趋势的历史正式候选继续进入策略6 VCP观察池。

**架构：** 在 `strategy6/vcp_history.py` 内新增纯函数连续性检查，并在倒序历史重放找到候选后调用。扫描器传入当前VCP第一轮起点；配置层提供三个显式阈值。旧调用方式和旧输出字段保持兼容。

**技术栈：** Python 3.10、dataclass、pytest、SQLite真实日线验证。

---

### 任务1：连续性规则测试与实现

**文件：**
- 修改：`tests/test_strategy6_vcp_history.py`
- 修改：`strategy6/vcp_history.py`

- [ ] 编写失败测试：候选日至VCP起点跌幅超过15%时历史资格失效。
- [ ] 编写失败测试：区间最大回撤超过20%时历史资格失效。
- [ ] 编写失败测试：VCP起点连续5日满足 `close < MA20 < MA50` 时历史资格失效。
- [ ] 编写失败测试：健康横盘和VCP起点后的新候选继续通过。
- [ ] 运行 `python -m pytest tests/test_strategy6_vcp_history.py -q`，确认测试因缺少连续性判断失败。
- [ ] 实现最小连续性检查并接入历史候选倒序重放。
- [ ] 重新运行专项测试并确认通过。

### 任务2：配置与扫描接入

**文件：**
- 修改：`strategy6/validation.py`
- 修改：`strategy6/scanner.py`
- 修改：`config.yaml`
- 修改：`tests/test_strategy6_scanner.py`

- [ ] 编写失败测试：扫描器必须把 `vcp.pattern_start_date` 传给历史资格判断。
- [ ] 为三个阈值增加默认值、范围校验和显式配置。
- [ ] 接入扫描器，保持旧mock和旧调用兼容。
- [ ] 运行策略6历史资格与扫描专项测试。

### 任务3：真实样本与回归验收

**文件：**
- 新增：`docs/reviews/2026-07-17-strategy6-vcp-history-continuity-validation.md`

- [ ] 使用本地 `data/cuphandle.db` 重放600028，确认2026-03-05资格因连续性破坏失效。
- [ ] 对当前VCP观察池全量重算，记录优化前后保留、剔除和新增股票。
- [ ] 运行策略6专项测试、后端全量测试、编译检查、前端测试和构建。
- [ ] 以审核专家角色检查未来数据、配置兼容、误杀和跨策略影响；发现中高问题后修复并复验。
- [ ] 仅暂存本任务文件，提交并推送当前策略6分支。
