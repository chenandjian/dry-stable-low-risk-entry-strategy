# 策略2「极致量干价稳」最终第三方代码审核说明

## 审核范围

本次审核针对策略2开发完成后的三轮修复，提交基准 `82e337a`（初版完成） → `1f8e3d5`（最终修复）。

共 3 个修复提交：

```
1f8e3d5 fix(strategy2): final isolation — cross-strategy execution blocked, progress, frontend, cache
d20dc4b fix(strategy2): resolve all 7 recheck issues (RECHECK-S2-001~007)
136e48f fix(strategy2): resolve all 11 bugs from code audit (BUG-S2-001~011)
```

## 审核重点

### 1. 策略交叉执行隔离（最重要）

策略2任务 ID 不能进入策略1执行链，策略1任务 ID 不能进入策略2执行链。

**验证方法**：

```bash
python -m pytest tests/test_strategy2_final_fixes.py::TestCrossStrategyExecutionBlocked -v
# 预期：5 passed
```

**防护机制**：`server.py:_require_task_strategy()` 统一校验函数，应用于 5 个接口端点。

| 接口 | 策略2 task_id | 策略1 task_id |
|------|-------------|-------------|
| `POST /api/scan/tasks/{id}/retry-failed` | 400 TASK_STRATEGY_MISMATCH | 200 正常 |
| `POST /api/scan/tasks/{id}/re-evaluate` | 400 TASK_STRATEGY_MISMATCH | 200 正常 |
| `GET /api/candidates?task_id={id}` | 400 TASK_STRATEGY_MISMATCH | 200 正常 |
| `GET /api/strategy2/candidates?task_id={id}` | 200 正常 | 400 TASK_STRATEGY_MISMATCH |
| `GET /api/strategy2/candidates/{code}?task_id={id}` | 200 正常 | 400 TASK_STRATEGY_MISMATCH |

---

### 2. 任务列表隔离

策略1任务列表不显示运行中的策略2任务，反之亦然。每个任务项返回 `strategy_type` 字段。

```bash
python -m pytest tests/test_strategy2_final_fixes.py::TestTaskListIsolation -v
# 预期：4 passed
```

---

### 3. 数据库兼容性

`scan_tasks` 新增 `strategy_type TEXT DEFAULT 'STRATEGY_1_CUP_HANDLE'`，旧库自动迁移。新增 `strategy2_candidates` 独立表，不与 `candidates` 混合。

```bash
python -m pytest tests/test_strategy2_bug_fixes.py::TestTaskIsolation -v
python -m pytest tests/test_strategy2_bug_fixes.py::TestJsonDeserialization -v
```

---

### 4. 策略窗口与数据校验

策略窗口外无效数据（close=0、缺失字段）不影响窗口内评估。窗口内异常仍被拒绝。日期使用 `date.fromisoformat()` 严格校验。

```bash
python -m pytest tests/test_strategy2_recheck_fixes.py::TestWindowIsolationAndDateValidation -v
# 预期：8 passed
```

---

### 5. 缓存新鲜度

未来日期缓存拒绝；≤3 自然日视为新鲜（覆盖周末和短假期）。测试覆盖 8 个时间场景。

```bash
python -m pytest tests/test_strategy2_final_fixes.py::TestCacheFreshnessExpectedTradeDate -v
# 预期：8 passed
```

---

### 6. 扫描进度回调

所有终态（candidate/scanned/skipped/failed/persist-failed）均通过 `_finish_stock()` 发送 processed 进度回调。候选持久化成功后才标记 candidate 并广播 discovery。

```bash
python -m pytest tests/test_strategy2_final_fixes.py::TestCandidateTerminalProgress -v
# 预期：1 passed
```

---

### 7. 前端刷新恢复

页面刷新时先获取扫描状态设置 `activeStrategyType`，再加载对应策略结果。策略2结果页支持 `?task=<id>` 参数自动加载。

人工验证步骤：
1. 策略2扫描运行时刷新 ScannerConsole → 首次请求即调用策略2 API
2. 策略2完成后候选保留 → 不会被空数组覆盖
3. `/strategy2/results?task=<id>` → 自动选中任务并加载候选
4. 两个候选分别展开详情 → 无作用域错误

---

### 8. Strategy1 零回归

策略1全部测试不受影响。离线测试中策略1和策略2测试完全隔离。

```bash
python -m pytest tests/ -q --ignore=tests/test_strategy2_*.py --ignore=tests/test_akshare_hist.py --ignore=tests/test_yfinance_hist.py --ignore=tests/test_tushare_hist.py
```

---

## 测试结果总览

| 测试类别 | 数量 | 状态 |
|---------|------|------|
| 策略2 模型 | 11 | ✅ |
| 策略2 指标 | 28 | ✅ |
| 策略2 评分 | 23 | ✅ |
| 策略2 否决 | 12 | ✅ |
| 策略2 风险 | 13 | ✅ |
| 策略2 引擎 | 12 | ✅ |
| 策略2 独立性 | 5 | ✅ |
| BUG 修复 (S2-001~011) | 44 | ✅ |
| 复审修复 (RECHECK-S2-001~007) | 21 | ✅ |
| 最终修复 (FINAL-S2-001~005) | 26 | ✅ |
| 策略1 回归 | ~170 | ✅ |
| **合计（离线）** | **443** | **0 失败** |
| 外部网络测试 | 5 | 2 失败（东财代理 + Yahoo 429） |

## 构建验证

```
python -m compileall strategy2 scanner server.py -q  →  通过
cd web && npm run build  →  ✓ built in 1.63s
git diff --check  →  通过
```

---

## 已知不交付项

| 项目 | 原因 |
|------|------|
| 策略2 回测 | 设计决策：本期不做 |
| 策略2 重新评估 | 设计决策：本期不做 |
| 策略2 CSV 导出 | 可选增强 |

---

*审核基线：`82e337a` → `1f8e3d5`*
*设计依据：`docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md`*
*操作日志：`operations-log.md`*
