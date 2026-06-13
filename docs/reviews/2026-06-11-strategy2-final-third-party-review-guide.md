# 策略2「极致量干价稳」最终第三方代码审核说明

## 审核范围

策略2「极致量干价稳」独立全市场扫描链路，历经初始开发 + 8 轮修复验收，已完成全部交付。

**分支**: `codex/strategy2-extreme-dry-stable-design`
**工作树**: `.claude/worktrees/strategy2-extreme-dry-stable`
**设计依据**: `docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md`

### 完整提交链（12 个 fix commits）

```
ba85084 Round 8 — single-flight poll session, 17 vitest tests
0e777c5 Round 7 — viewContext stale response prevention, poll epoch
fc00da2 Round 6 — completed task summary, unified error handling, vitest 11 tests
7b95046 Round 5 — history completion state, query switch cleanup, vitest upgrades
6f04564 Round 4 — task summary, completion state, URL watch, vitest, source diagnostics
b43cdcc Round 3 — API 404, source diagnostics, history isolation, terminal tests, source cleanup
948b284 Round 2 — fix failure panel scope, history context, source convergence, terminal tests
c14b974 Final Acceptance — remove cache fallback, converge sources, fix failure UI
1f8e3d5 Final Isolation — cross-strategy execution blocked, progress, frontend, cache
d20dc4b Recheck Fixes — 7 recheck issues (RECHECK-S2-001~007)
136e48f Bug Fixes — 11 bugs from code audit (BUG-S2-001~011)
```

---

## 核心架构

```
共享层: stock_pool → data_source(baidu/sina/tencent) → daily_data_service → liquidity_filter
├─ 策略1: scanner/engine → CupHandleStrategyEngine → analyzer/* → candidates
└─ 策略2: strategy2/scanner → ExtremeDryStableStrategyEngine → strategy2_candidates
```

**策略2 独立边界**: `strategy2/` 包完全不导入策略1的形态检测、评分、分析、决策模块。

---

## 审核重点（8 项）

### 1. 跨策略执行隔离 ✅

| 接口 | 策略2 task_id | 策略1 task_id |
|------|-------------|-------------|
| `POST /api/scan/tasks/{id}/retry-failed` | 400 `TASK_STRATEGY_MISMATCH` | 200 |
| `POST /api/scan/tasks/{id}/re-evaluate` | 400 `TASK_STRATEGY_MISMATCH` | 200 |
| `GET /api/candidates?task_id={id}` | 400 `TASK_STRATEGY_MISMATCH` | 200 |
| `GET /api/strategy2/candidates?task_id={id}` | 200 | 400 `TASK_STRATEGY_MISMATCH` |

```bash
python -m pytest tests/test_strategy2_final_fixes.py::TestCrossStrategyExecutionBlocked -v  # 5 passed
```

### 2. 前端竞态防护 ✅
- **viewContext**: `beginViewContext` 每次导航创建新 context；所有 async 函数在 `await` 后校验 `isCurrentViewContext`
- **单飞 poll session**: `activePollSession.inFlight` 防止重叠轮询；`resetPollSession()` 在任务切换/停止轮询时使旧 session 失效
- **17 项 vitest 测试**: 涵盖慢轮询、旧 session 迟到、A→B 竞态、详情/候选迟到→live

### 3. 数据库兼容性 ✅
- `scan_tasks.strategy_type` 向后兼容（NULL → S1）
- `strategy2_candidates` 独立表

### 4. 三数据源收敛 ✅
- `baidu / sina / tencent` 仅三源
- `mootdx_source.py`、`yfinance_source.py` 已删除
- `requirements.txt` 不包含 mootdx/yfinance

### 5. 全源失败规则 ✅
- 三源全失败 → `FetchResult(data=None)` → `failed / ALL_DATA_SOURCES_FAILED`
- 不使用缓存扫描；在线拉取成功时可与历史合并

### 6. 任务生命周期 ✅
- `GET /api/scan/tasks/{id}/stocks` — 不存在返回 404
- 中断恢复按 `strategy_type` 分派
- 任务列表按策略类型隔离

### 7. 历史任务隔离 ✅
- `routeTaskId` / `isHistoricalMode` 两种互斥模式
- URL task 是历史页面唯一任务上下文
- 已完成任务显示真实统计；运行→完成自动刷新

### 8. 六种终态覆盖 ✅

| 终态 | status | status_reason |
|------|--------|---------------|
| 候选 | candidate | None |
| 非候选 | scanned | SCORE_BELOW_THRESHOLD |
| 流动性过滤 | skipped | LIQUIDITY_FILTER_REJECTED |
| 全源失败 | failed | ALL_DATA_SOURCES_FAILED |
| 候选保存失败 | failed | STRATEGY2_CANDIDATE_PERSIST_FAILED |
| 评估异常 | failed | STRATEGY2_EVALUATION_ERROR |

---

## 测试结果

| 类别 | 数量 | 状态 |
|------|------|------|
| 后端全量 | **426** | 0 失败 |
| 策略2 重点 | **176** | 0 失败 |
| 线程 warning 门禁 | **61** | 0 warnings |
| 前端 vitest | **17** | 0 失败 |
| 前端 build | ✓ | 1.81s |

### 验证命令

```bash
python -m pytest tests/ -q                                                    # 426 passed
python -m pytest tests/test_strategy2_acceptance_fixes.py \
  tests/test_strategy2_final_fixes.py tests/test_strategy2_recheck_fixes.py \
  -W error::pytest.PytestUnhandledThreadExceptionWarning -q                    # 61 passed, 0 warnings
cd web && npx vitest run                                                      # 17 passed
cd web && npm run build                                                       # ✓ 1.81s
python -m compileall scanner strategy2 server.py -q                           # passed
git diff --check                                                              # passed
```

---

## 策略2 核心算法（不变）

**量干 50 分**: V5/V20≤0.60:+10, ≤0.50:+10, V3<V5<V10<V20:+10, 60日最低20%:+10, return_5≥-3%:+10
**价稳 50 分**: range_5≤5%:+10, ≤3%:+10, close_range_5≤3%:+10, 无单日跌幅<-3%:+10, close≥key_support:+10
**一票否决**: return_5<-5%, 放量(>V20)单日≤-4%, range_5>8%, close<key_support, return_3≥8%
**key_support**: 不含评估日 T 的前 10 个交易日最低收盘价
**风险比**: (close - stop_loss) / close, ≤3% 低风险, ≤5% 可接受, >5% 排除

---

## 已知不交付项

| 项目 | 原因 |
|------|------|
| 策略2 回测 | 本期不做 |
| 策略2 重新评估 | 本期不做 |
| 策略2 CSV 导出 | 可选增强 |

---

*审核基线: `82e337a` → `ba85084`（12 个 fix commits，8 轮修复）*
*操作日志: `operations-log.md`*
