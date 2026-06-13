# Strategy2 Phase 1 Medium/High Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `docs/reviews/2026-06-13-strategy2-phase1-medium-high-recheck.md` 中 MH-001 至 MH-005，使策略2回测可恢复、可重试、可校验数据版本，并生成准确可信的审计和汇总。

**Architecture:** 将 `server.py` 内嵌的回测循环提取为 `strategy2/backtest_service.py` 统一执行器。start、resume、retry-failed 只负责选择目标股票并启动执行器；执行器统一处理逐股状态、进度、最终化、可信度和数据版本校验。数据库继续使用现有兼容迁移和单股原子替换模式。

**Tech Stack:** Python 3.10+, FastAPI, SQLite, pytest, Vue 3/Vitest

---

### Task 1: 可信度、零机会和汇总统计

**Files:**
- Modify: `scanner/db.py`
- Test: `tests/test_strategy2_medium_high_fixes.py`

- [ ] 写失败测试：取消/中断/失败/部分完成任务不能通过完整性校验。
- [ ] 写失败测试：完整零机会任务生成 3/5/10/20 完整零值周期并通过校验。
- [ ] 写失败测试：汇总包含逐股漏斗、`avg_days_to_target` 和 `avg_days_to_stop`。
- [ ] 运行专项测试确认按预期失败。
- [ ] 最小修改 `build_strategy2_backtest_summary()` 和 `validate_strategy2_backtest_integrity()`。
- [ ] 运行专项测试确认通过。

### Task 2: 数据版本指纹

**Files:**
- Modify: `scanner/db.py`
- Create: `strategy2/backtest_service.py`
- Test: `tests/test_strategy2_medium_high_fixes.py`

- [ ] 写失败测试：相同快照数据产生相同 SHA-256；同日任一 OHLC 字段变化后指纹变化。
- [ ] 为任务表兼容新增 `data_revision_id`。
- [ ] 实现按 `code,date,open,high,low,close,volume` 稳定排序的流式 SHA-256。
- [ ] 写失败测试：恢复/重试时数据版本变化被拒绝。
- [ ] 实现执行器启动前版本校验。

### Task 3: 统一执行器和逐股审计

**Files:**
- Create: `strategy2/backtest_service.py`
- Modify: `scanner/db.py`
- Modify: `server.py`
- Test: `tests/test_strategy2_medium_high_fixes.py`

- [ ] 写失败测试：`NO_LOCAL_DATA` 保存真实 `started_at/finished_at` 并增加实时 processed。
- [ ] 写失败测试：成功原子替换保存 `started_at/finished_at/invalid_data_days/earliest_date/latest_date`。
- [ ] 实现统一逐股执行结构和所有终态的 finally 进度更新。
- [ ] 实现任务两阶段最终化，聚合值全部来自数据库。
- [ ] 将 start 接口改为调用统一执行器。

### Task 4: Resume 和 Retry-Failed 行为

**Files:**
- Modify: `server.py`
- Modify: `strategy2/backtest_service.py`
- Test: `tests/test_strategy2_medium_high_fixes.py`

- [ ] 写失败测试：resume 仅执行 PENDING 和遗留 RUNNING 股票，保留已完成股票结果。
- [ ] 写失败测试：retry-failed 仅执行 FAILED 股票，不影响其他股票。
- [ ] 写失败测试：同一任务重复启动返回 HTTP 409。
- [ ] 实现 resume 状态限制、原快照解析和目标股票选择。
- [ ] 实现 retry-failed 目标股票选择。
- [ ] 验证 cancel 后任务不可信且已完成结果保持不变。

### Task 5: 验证、日志和提交

**Files:**
- Modify: `operations-log.md`

- [ ] 运行策略2专项测试。
- [ ] 运行策略2验收相关测试。
- [ ] 运行后端离线全量测试。
- [ ] 运行 Python 编译检查。
- [ ] 运行前端 Vitest 和构建。
- [ ] 运行 `git diff --check` 并审查改动。
- [ ] 更新 `operations-log.md`，记录真实测试结果和残余风险。
- [ ] 自动提交已验证改动，不执行 push。
