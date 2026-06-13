# 策略2 Phase 1 最终修复完成验收报告

## 1. 结论

`2026-06-13-strategy2-phase1-final-acceptance-recheck.md` 中的
`FINAL-001`～`FINAL-004` 已全部修复。

当前未发现新的中、高等级阻塞问题。代码已满足 Phase 1 功能验收条件。

## 2. 修复结果

| 编号 | 修复结果 |
|---|---|
| FINAL-001 | 服务启动时事务化将遗留 `running` 回测标记为 `INTERRUPTED`，并仅将逐股 `RUNNING` 恢复为 `PENDING`；异常不再静默吞掉 |
| FINAL-002 | 新任务冻结回测引擎和策略引擎版本；完整性校验、恢复、失败重试和执行器均校验版本，版本变化返回 `ENGINE_REVISION_CHANGED` |
| FINAL-003 | 前端已接入取消、恢复、失败重试、失败股票、可信度、版本展示，并能在刷新后恢复运行中任务及在完成后自动加载详情 |
| FINAL-004 | 历史回测列表已支持后端分页、状态过滤和前端翻页 |

## 3. 数据库与兼容性

- 新任务保存：
  - `backtest_engine_version = phase1-v3`
  - `strategy_engine_version = strategy2-v2`
  - `data_revision_version = daily-ohlc-v2`
- 历史任务不会被伪造版本。
- 旧版本可信任务会保守降级为 `LEGACY_UNTRUSTED`。
- 旧版本任务恢复或失败重试会被拒绝，不会混写新旧实现结果。
- 服务重启只重置未完成股票，已完成信号和机会保持不变。

## 4. 新增验证覆盖

- 服务重启后的任务与逐股状态转换。
- 已完成股票结果在重启恢复后保持不变。
- 策略引擎版本变化时恢复被拒绝。
- 回测引擎版本变化时失败重试被拒绝。
- 缺少策略引擎版本的任务不能通过可信度校验。
- 历史任务分页、过滤和摘要字段边界。
- 前端可信度和版本展示。
- 前端失败股票展示和失败重试。
- 前端恢复、取消及版本变化任务操作限制。
- 页面刷新后重新接管运行中任务。

## 5. 最终测试结果

| 验证项 | 结果 |
|---|---|
| 策略2专项与验收测试 | `90 passed` |
| 后端离线全量测试 | `528 passed, 1 warning` |
| 前端 Vitest | `29 passed` |
| 前端生产构建 | 通过 |
| Python 编译检查 | 通过 |
| `git diff --check` | 通过 |

唯一 warning 为既有 `dateutil` 弃用提示，不影响本次功能。

## 6. 最终说明

Phase 1 代码修复已完成。正式将某个任务作为新的可信基线前，仍应使用当前版本运行一次
全市场任务，并确认其最终状态为：

```text
status = completed
credibility_status = TRUSTED_BASELINE
backtest_engine_version = phase1-v3
strategy_engine_version = strategy2-v2
data_revision_version = daily-ohlc-v2
```
