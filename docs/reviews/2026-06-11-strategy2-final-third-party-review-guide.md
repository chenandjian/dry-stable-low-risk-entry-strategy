# 策略2「极致量干价稳」最终第三方代码审核说明

## 审核范围

策略2「极致量干价稳」独立全市场扫描链路，历经初始开发 + 6 轮修复验收，当前已完成全部交付。

**分支**: `codex/strategy2-extreme-dry-stable-design`
**工作树**: `.claude/worktrees/strategy2-extreme-dry-stable`
**设计依据**: `docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md`

### 完整提交链（10 个 fix commits）

```
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

策略2与策略1共享基础设施（股票池、数据源、日线存储、流动性过滤），但业务判断链路完全独立。

```
共享层: stock_pool → data_source(baidu/sina/tencent) → daily_data_service → liquidity_filter
├─ 策略1: scanner/engine → CupHandleStrategyEngine → analyzer/* → candidates 表
└─ 策略2: strategy2/scanner → ExtremeDryStableStrategyEngine → strategy2_candidates 表
```

**策略2 独立边界**: `strategy2/` 包完全不导入策略1的形态检测、评分、分析、决策模块。已验证通过 AST 扫描。

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
python -m pytest tests/test_strategy2_final_fixes.py::TestCrossStrategyExecutionBlocked -v
# 5 passed
```

### 2. 实时 API 策略隔离 ✅

- Strategy1 扫描期间 `GET /api/candidates` 不返回 S2 discovery
- Strategy2 扫描期间 `GET /api/candidate/{code}` 返回 404

### 3. 数据库兼容性 ✅

- `scan_tasks.strategy_type` 向后兼容（NULL → S1）
- `strategy2_candidates` 独立表，`UNIQUE(task_id, code)`
- 旧库自动迁移，无破坏性操作

### 4. 三数据源收敛 ✅

生产链仅 `baidu / sina / tencent`：
- `config.yaml`、`DataSourceManager`、`DEFAULT_DAILY_SOURCES`、`_daily_fetch_fn`、`single_stock_backtest.py`、`requirements.txt` 全部收敛
- `mootdx_source.py`、`yfinance_source.py` 及对应测试已删除
- 诊断脚本移至 `tools/data_source_diagnostics/`（不进入默认 pytest）

```bash
rg -n "mootdx\|yfinance" scanner/ strategy2/ config.yaml
# 0 matches
```

### 5. 全源失败规则 ✅

- 三个在线数据源全部失败 → `FetchResult(data=None)` → 股票标记 `failed / ALL_DATA_SOURCES_FAILED`
- 不使用本地缓存继续扫描
- 在线拉取成功时，允许与数据库历史合并并持久化
- 全源失败后完整持久化三源诊断（primary/fallback source、attempts、errors、source_errors JSON）

### 6. 任务生命周期 ✅

- `GET /api/scan/tasks/{id}/stocks` — 不存在返回 404 `TASK_NOT_FOUND`
- 中断恢复按 `strategy_type` 分派（S1→scan_all，S2→scan_strategy2_all）
- 任务列表按策略类型隔离（S1 列表不含 S2，反之亦然）

### 7. 前端历史任务 ✅

- `routeTaskId` / `isHistoricalMode` 两种互斥模式
- URL task 参数是历史页面唯一任务上下文
- `watch(route.query.task)` 支持 A→B→A→none 切换
- 已完成任务首次加载显示真实统计
- 运行任务完成后自动刷新最终 summary
- 错误语义：404→任务不存在 / 非404→加载失败 / 异常→加载失败
- 策略2历史任务隐藏重试按钮

### 8. 六种终态覆盖 ✅

| 终态 | status | status_reason |
|------|--------|---------------|
| 候选 | candidate | None |
| 非候选 | scanned | SCORE_BELOW_THRESHOLD |
| 流动性过滤 | skipped | LIQUIDITY_FILTER_REJECTED |
| 全源失败 | failed | ALL_DATA_SOURCES_FAILED |
| 候选保存失败 | failed | STRATEGY2_CANDIDATE_PERSIST_FAILED |
| 评估异常 | failed | STRATEGY2_EVALUATION_ERROR |

每个终态均断言：DB 状态、finished_at、summary 互斥、scanning/processed 回调、discovery 回调。

---

## 策略2 核心算法（不变）

**量干 50 分**：V5/V20≤0.60:+10, ≤0.50:+10, V3<V5<V10<V20:+10, 60日最低20%:+10, return_5≥-3%:+10

**价稳 50 分**：range_5≤5%:+10, ≤3%:+10, close_range_5≤3%:+10, 无单日跌幅<-3%:+10, close≥key_support:+10

**一票否决**：return_5<-5%, 放量(>V20)单日≤-4%, range_5>8%, close<key_support, return_3≥8%

**key_support**：不含评估日 T 的前 10 个交易日最低收盘价

**风险比**：(close - stop_loss) / close, ≤3% 低风险, ≤5% 可接受, >5% 排除

---

## 测试结果总览

| 类别 | 数量 | 状态 |
|------|------|------|
| 策略2 核心（模型/指标/评分/否决/风险/引擎/独立性） | 104 | ✅ |
| BUG 修复 (S2-001~011) | 44 | ✅ |
| 复审修复 (RECHECK-S2-001~007) | 21 | ✅ |
| 最终修复 (FINAL-S2-001~005) | 26 | ✅ |
| 验收修复 (ROUND2~6) | 61 | ✅ |
| 策略1 回归 | ~170 | ✅ |
| **后端合计** | **426** | **0 失败** |
| **前端组件测试 (vitest)** | **11** | **0 失败** |
| **前端构建** | ✓ | **1.89s** |

### 运行命令

```bash
# 后端全量
python -m pytest tests/ -q                               # 426 passed

# 策略2 全套 + 线程 warning 门禁
python -m pytest tests/test_strategy2_acceptance_fixes.py \
  tests/test_strategy2_final_fixes.py \
  tests/test_strategy2_recheck_fixes.py \
  -W error::pytest.PytestUnhandledThreadExceptionWarning -q  # 61 passed, 0 warnings

# Python 编译
python -m compileall scanner strategy2 server.py -q      # passed

# 前端组件测试
cd web && npx vitest run                                 # 11 passed

# 前端构建
cd web && npm run build                                  # ✓ built in 1.89s

# 代码质量
git diff --check                                          # passed
```

---

## 已知不交付项

| 项目 | 原因 |
|------|------|
| 策略2 回测 | 设计决策：本期不做 |
| 策略2 重新评估 | 设计决策：本期不做 |
| 策略2 CSV 导出 | 可选增强 |

---

## 审核建议优先级

1. **优先审核**: `strategy2/engine.py`（唯一入口）、`scanner/db.py`（数据库）、`server.py` 策略2 API
2. **关注风险**: `key_support` 排除评估日、`V20=0` 除零保护、全源失败不使用缓存、跨策略执行隔离
3. **回归确认**: `pytest tests/ --ignore=tests/test_strategy2_*.py` 确认策略1零影响
4. **前端验证**: URL task 参数隔离、历史任务完成态刷新、失败面板渲染

---

*审核基线: `82e337a` → `fc00da2`（10 个 fix commits）*
*操作日志: `operations-log.md`*
