# Operations Log

## 2026-06-11 — 策略2下降趋势证据评分升级

### 变更概述
将旧"四项全部满足"规则替换为多时间尺度证据评分制。
`DOWNTREND = MA20 < MA60 AND evidence_score >= 5`（满分7分）。

### 修改文件

| 文件 | 操作 | 说明 |
|---|---|---|
| `strategy2/trend.py` | **重写** | 新证据评分逻辑，7项证据每项1分，MA20<MA60为必要条件 |
| `strategy2/models.py` | 修改 | Strategy2Trend 新增 evidence_score/ma120/ma60_slope/return_60/price_position_60 |
| `strategy2/engine.py` | 无需修改 | 趋势过滤逻辑不变（仍检查 trend_type） |
| `strategy2/scanner.py` | 修改 | discovery + error_detail 新增字段，补 `import json` |
| `scanner/db.py` | 修改 | strategy2_candidates 兼容式新增6列为5列（v2新增 evidence_score/ma120/ma60_slope/return_60/price_position_60/downtrend_conditions） |
| `web/src/pages/Strategy2Results.vue` | 修改 | 详情面板展示证据分、MA120、MA60斜率、60日涨跌、区间位置 |
| `tests/test_strategy2_trend.py` | **重写** | 30个测试含601607离线回归 |
| `tests/test_strategy2_bug_fixes.py` | 修复 | test_big_drop_on_last_day 增加 MA20>=MA60 保护 |
| `operations-log.md` | 追加 | 本记录 |

### 核心规则
- **必要条件**: MA20 < MA60
- **7项证据** (每项1分): CLOSE_BELOW_MA20, MA20_BELOW_MA60, MA60_BELOW_MA120, MA20_SLOPE_NEGATIVE, MA60_SLOPE_NEGATIVE, RETURN60_BELOW_MINUS_5_PERCENT, PRICE_POSITION60_BOTTOM_30_PERCENT
- **阈值**: evidence_score >= 5 → DOWNTREND
- **601607回归**: 7项证据全部命中，判定 DOWNTREND ✓

### 测试结果
- 策略2趋势测试: 30 passed (含601607回归)
- 后端全量: **482 passed** (新增15个趋势测试)
- 前端构建: **通过**

### 遗留问题
无

---

## 2026-06-11 — 策略2走势趋势过滤增量开发

### 开发目标
在不修改策略2现有评分/否决/风险规则的前提下，新增独立走势趋势前置过滤模块。

### 修改文件

| 文件 | 操作 | 说明 |
|---|---|---|
| `strategy2/trend.py` | 新增 | 走势趋势判断模块，计算MA20/MA60/MA20斜率/20日涨跌幅 |
| `strategy2/models.py` | 修改 | 新增 `Strategy2Trend` dataclass，`Strategy2Evaluation` 增加 `trend` 字段 |
| `strategy2/engine.py` | 修改 | V20检查后、风险前插入趋势过滤步骤 |
| `strategy2/scanner.py` | 修改 | `_build_strategy2_discovery` 增加趋势字段；下降趋势写入 `error_detail` JSON |
| `scanner/db.py` | 修改 | `strategy2_candidates` 表兼容式新增5个趋势字段；`upsert` 函数读写趋势字段 |
| `server.py` | 无需修改 | `SELECT *` 自动包含新字段 |
| `web/src/pages/Strategy2Results.vue` | 修改 | 新增走势趋势列 + 详情面板展示MA20/MA60/MA20斜率/20日涨跌幅 |
| `tests/test_strategy2_trend.py` | 新增 | 15个单元测试：全命中/单缺失/边界值/下标口径/数据不足/无效行情 |
| `tests/test_strategy2_independence.py` | 修改 | 将 `trend.py` 加入8个策略2模块列表 |

### 核心逻辑

**趋势判断执行顺序（engine.py evaluate_at）：**
```
指标计算 → V20=0检查 → 走势趋势过滤 → 风险计算 → 否决 → 评分 → 入选判断
```

**下降趋势四个条件（严格不等）：**
1. current_close < MA20
2. MA20 < MA60
3. MA20_SLOPE_5 < 0
4. RETURN_20 < -0.05

四项同时命中 → `DOWNTREND_FILTERED`（不写入候选表）
未同时命中 → `UPTREND_OR_SIDEWAYS`（继续原有流程）

**Python下标口径：**
- MA20 = mean(closes[-20:])
- MA60 = mean(closes[-60:])
- MA20(-5) = mean(closes[-25:-5])
- RETURN_20 = closes[-1] / closes[-21] - 1

### 数据库变更
`strategy2_candidates` 表兼容式新增：`trend_type TEXT`, `ma20 REAL`, `ma60 REAL`, `ma20_slope REAL`, `return_20 REAL`

### 测试结果
- 策略2趋势单元测试: 15 passed
- 策略2独立性测试: 5 passed
- 后端全量: **467 passed**
- 前端构建: **通过**
- 前端测试: 23/25 passed (预存 [18]/[23] 与本次无关)

### 遗留问题
无

---

## 2026-06-04

- Continued dry-stable strategy implementation: added market environment analysis, API/DB/CSV fields, and frontend display for dry-stable verdicts.
- Verification issue found: `tests/test_db_strategy_fields.py` exposed a `save_candidates()` SQL placeholder mismatch after adding market environment columns.
- Fix applied: corrected `scanner/db.py` candidate insert placeholders to match the 40 persisted columns.
- Final verification: `python -m pytest tests/ -q` passed with 62 tests; `python -m compileall analyzer scanner main.py server.py output tests` passed; `npm.cmd run build` passed with existing Vite chunk-size warnings.
- Strategy completion verification: `python -m pytest tests/ -q` passed with 66 tests; `python -m compileall analyzer scanner main.py server.py output tests` passed; `npm.cmd run build` passed. Remaining build notices are the Vite CJS Node API deprecation and the intentionally lazy-loaded `echarts` chunk exceeding 500 kB.

## 2026-06-09

- Completed a read-only strategy-focused code audit for the `multi-source-daily-kline` worktree.
- Added `docs/reviews/2026-06-09-strategy-code-audit.md` with evidence-backed findings, repair guidance, and regression-test requirements.
- Key findings include fixed-2R RR1 filtering, incorrect market-index symbol mapping, ATR stop warnings not blocking buys, one-sided Pivot proximity, scan/backtest strategy drift, configured source-chain bypass, and mixed adjustment risk across data sources.
- Verification: focused strategy/data-source tests passed with 66 tests; full suite completed with 144 passed and 1 external Dongcai connection failure; frontend production build passed.
- Audit clarification: `mootdx` is intentionally excluded from the active source chain; `min_price_stable_score: 5` is an intentional user-tuned value; the 12-point volume-dry scale is correct and only its outdated documentation needs synchronization.
- Reviewed `docs/superpowers/plans/2026-06-09-code-review-bug-fixes.md` and added `docs/reviews/2026-06-09-bug-fix-plan-review.md`; the plan is blocked from direct execution until it addresses backtest lookahead, real-resistance RR1, structured ATR-stop state, complete VCP-only contracts, source-busy semantics, and a concrete adjustment/caching strategy.
- Rechecked the implemented bug-fix commits and added `docs/reviews/2026-06-09-bug-fix-recheck.md`. Remaining blockers include backtest use of synthetic stop loss, incomplete VCP identity/serialization, non-nearest resistance selection, and unimplemented forward-adjustment consistency.
- Recheck verification: focused strategy tests passed with 58 tests; full suite completed with 147 passed and 1 external Dongcai connection failure.
- Completed the second bug-fix recheck and added `docs/reviews/2026-06-09-bug-fix-recheck-round2.md`. Per user confirmation, BUG-008 forward-adjustment consistency was removed from the review scope. Remaining blockers include a backtester `NameError`, unstable VCP identity, synthetic fallback targets/stops, partial index-config wiring, and non-persisted source error details.
- Round-two verification: focused strategy tests passed with 58 tests; full suite completed with 147 passed and 1 external Dongcai connection failure.
- Completed the third bug-fix recheck and added `docs/reviews/2026-06-09-bug-fix-recheck-round3.md`. Confirmed remaining blockers with direct reproductions: existing databases do not migrate the new `source_errors` column, and the same VCP receives a different ID on adjacent detection dates. Also identified invalid-stop and VCP false-breakout aggregation bias.
- Round-three verification: focused strategy tests passed with 70 tests; full suite completed with 147 passed and 1 external Dongcai connection failure; compileall passed.
- Completed the fourth bug-fix recheck and added `docs/reviews/2026-06-09-bug-fix-recheck-round4.md`. Confirmed the prior migration, VCP structure-date identity, invalid-stop, VCP false-breakout, error-detail persistence, and market-data injection fixes. Remaining issues are unobserved-horizon samples polluting backtest rates, empty compatibility error fields after all sources fail, and VCP identity tests that can pass without exercising the intended assertion.
- Round-four verification: targeted tests passed with 58 tests; offline suite passed with 155 tests; full suite completed with 156 passed and 2 external network failures; compileall passed.
- Completed the fifth bug-fix recheck and added `docs/reviews/2026-06-09-bug-fix-recheck-round5.md`. Confirmed unobserved hit/false-breakout metrics and all-failed compatibility fields were repaired. Remaining issues are verdict summaries treating unobserved returns as zero, missing primary compatibility errors when a fallback succeeds, mismatched fallback source/error in mixed failed/busy scenarios, and conditional VCP test assertions.
- Round-five verification: targeted tests passed with 65 tests; offline suite passed with 161 tests; compileall passed.
- Expanded `docs/reviews/2026-06-09-bug-fix-recheck-round5.md` into a final executable repair plan with exact data semantics, recommended helper structure, success/failure-path behavior, a seven-scenario source compatibility test matrix, unconditional VCP identity tests, and one-pass completion criteria.
- Completed the final bug-fix recheck and added `docs/reviews/2026-06-09-bug-fix-final-recheck.md`. Confirmed verdict return summaries, primary/fallback compatibility fields, and VCP identity assertions are repaired. One final edge case remains: when the primary source fails and every fallback source is busy, `fallback_source` incorrectly points to the primary source while fallback attempts/error remain empty.
- Final recheck verification: targeted suites passed with 16, 47, and 13 tests respectively; offline suite passed with 172 tests and 1 warning; compileall passed.
- Completed the final completion recheck and added `docs/reviews/2026-06-09-bug-fix-completion-recheck.md`. Confirmed FINAL-001 is fixed: primary-failed/all-fallbacks-busy fields are consistent, and single-source failure truly mirrors primary fields. No new required fixes were found.
- Completion verification: source/task targeted tests passed with 49 tests; strategy/backtest targeted tests passed with 29 tests; offline suite passed with 174 tests; compileall and diff check passed. Full suite had 175 passed and 2 external-network failures (Dongcai proxy connection and Yahoo Finance rate limiting).

## 2026-06-10

- Reviewed commit `c2c6e9c` against `docs/superpowers/specs/2026-06-10-scan-window-unified-strategy-design.md`.
- Added `docs/reviews/2026-06-10-scan-window-unified-strategy-code-review.md` with evidence-backed findings and a one-pass repair plan.
- Confirmed major remaining issues: batch backtest does not request `backtest_window_days + 60`, excludes the exact window-plus-60 boundary, single-stock backtest omits historical market data and lacks enough context, invalid window configs are accepted, `daily_kline_days` still overrides the intended fetch source of truth, candidate detail UI does not display current analysis, and real scan/backtest path consistency tests are missing.
- Verification: offline backend suite passed with 183 tests and 1 warning; frontend production build passed; commit diff check passed. Direct reproductions confirmed the batch fetch, loop-boundary, invalid-config, single-stock-context, and missing-UI behaviors.
- Rechecked fix commit `7da4c2a` and added `docs/reviews/2026-06-10-scan-window-unified-strategy-recheck.md`. Confirmed BUG-001/002/003/005/007/008/009 are fixed, BUG-004 and BUG-006 are partial, and BUG-010 remains incomplete.
- Remaining blockers: CLI `analyze` raises `UnboundLocalError` because `kline_days` is used before assignment; `min_listing_days=0` is silently replaced by 250; candidate detail still bypasses the shared window resolver; and consistency tests still do not execute real scan/backtest business paths.
- Recheck verification: targeted tests passed with 100 tests; offline suite passed with 200 tests; frontend build and compileall passed; full suite had 202 passed and 1 external Dongcai connection failure. Commit-level diff check found one extra blank line at EOF in the prior review document.
- Rechecked fix commit `d1f9203` and added `docs/reviews/2026-06-10-scan-window-unified-strategy-final-recheck.md`. Direct reproductions found two high-severity runtime regressions: `server.py` calls `resolve_strategy_windows()` without importing it, breaking scan start/config update/candidate detail paths, and CLI analyze crashes when both daily data sources fail. The new real-path consistency test still compares fake-engine calls on different decision dates rather than real strategy results.
- Final recheck verification: targeted suites passed with 107 tests; offline suite passed with 207 tests; full suite passed with 210 tests and 3 warnings; compileall and frontend production build passed. Commit-level diff check still reports a trailing blank line in the prior recheck document.
- Rechecked fix commit `3bef48e` and added `docs/reviews/2026-06-10-scan-window-unified-strategy-completion-recheck.md`. Confirmed FINAL-001/002/004/005 are fixed and FINAL-003 is substantially improved, but found a remaining strategy correctness issue: scan, re-evaluation, CLI analysis, and candidate detail pass market-index rows after the stock decision date, while backtests truncate them. A direct real-path reproduction captured stock date `2026-01-30` with market date `2026-02-01`.
- Completion recheck verification: targeted suites passed with 109 tests; offline suite passed with 209 tests; full suite had 211 passed and 1 external Dongcai connection failure; compileall, frontend build, and commit-level diff check passed. Remaining test gaps are the required cup-handle/VCP-only/breakout-exclusion consistency scenarios and entry-level API coverage for the resolver import repair.
- Rechecked fix commit `8ff1384` and added `docs/reviews/2026-06-10-scan-window-unified-strategy-acceptance-recheck.md`. Confirmed the market-data future-leak fix across all strategy entry points and the new API coverage. Direct reproduction now captures stock and market dates both ending at `2026-01-30`; no new required business-code fixes were found.
- Acceptance verification: targeted suites passed with 122 tests; offline suite passed with 222 tests; full suite passed with 225 tests and 3 warnings; compileall and frontend build passed. Remaining non-business cleanup is to add non-conditional scenario assertions to the four-path consistency tests and remove one trailing blank line reported by commit-level diff check.
- Rechecked cleanup commit `ab22fb3` and added `docs/reviews/2026-06-10-scan-window-unified-strategy-final-completion.md`. Confirmed the four scenario assertions now prove their named cases and no new business-code or strategy issues remain.
- Final completion verification: backtester suite passed with 22 tests; offline suite passed with 222 tests; full suite had 224 passed and 1 external Dongcai connection failure; compileall and frontend build passed. The only remaining cleanup is a trailing blank line in the newly committed acceptance-recheck document, which still causes commit-level diff check to fail.
- Created worktree `.claude/worktrees/strategy2-extreme-dry-stable`.
- Created branch `codex/strategy2-extreme-dry-stable-design` from commit `d3b36a1`.
- Reviewed the requested strategy document and current scan, database, API, and frontend configuration structures.
- Confirmed product and architecture decisions with the user.
- Added the Strategy 2 independent full-market scan development design document.
- No strategy implementation code was changed in this phase.
- Confirmed and documented a Strategy 2 pre-score trend filter: stocks classified as downtrends are excluded, while uptrend or sideways stocks may continue to scoring.
- Added a standalone AI-executable incremental development document for the Strategy 2 trend filter.

## 2026-06-10 (Strategy2 Development)

- Implemented strategy2「极致量干价稳」independent full-market scan.
- **Core modules** (strategy2/): models (5 dataclasses), indicators (V3-V20, percentile, range, returns), scorer (vol 50pts + price 50pts + levels), rejection (5 one-vote rules), risk (key_support/buy_zone/stop_loss/risk_ratio), engine (ExtremeDryStableStrategyEngine), scanner (multi-thread orchestrator).
- **Shared infrastructure**: `scanner/daily_data_service.py` — extracted 4-source fetch chain with lock/retry/cache, strategy-agnostic.
- **Database**: Added `strategy_type` to `scan_tasks` (backward-compatible), new `strategy2_candidates` table with 27 columns and 2 indexes.
- **API**: 5 strategy2 endpoints (POST /api/strategy2/scans, GET status/tasks/candidates/candidate detail). Enhanced global scan mutex with strategyType in 409 responses.
- **Frontend**: Strategy2Results.vue page (task selector, candidates table with level/score/risk), dual strategy buttons in ScanEngine.vue, strategy2 nav link, API composable extensions, router addition.
- **Independence verified**: `strategy2/` never imports strategy1 pattern/analysis modules (5 test assertions).
- Test results: **267 passed, 0 failed** (all strategy2 + strategy1 regression).
- Frontend build: **✓ built in 1.62s** (Strategy2Results included).
- **Config**: `config.yaml` strategy2 section with 8 parameters.
- **Known gaps**: re-evaluate/backtest/CSV export not in scope; scanner/engine.py still uses inline fetch (strategy1 stability preserved).
- **Frontend config**: StrategyConfig.vue strategy2 section completed (commit `70a930a`) — 7 parameters, enable toggle, front-end validation, gold-toned visual distinction.

## 2026-06-10 (Strategy2 Third-Party Code Audit)

- Audited Strategy2 implementation at commit `82e337a` against `docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md`.
- Added `docs/reviews/2026-06-10-strategy2-code-audit-and-one-pass-fix-plan.md` with 11 evidence-backed findings and an ordered one-pass repair plan.
- Direct reproductions confirmed that the strategy window is not applied, the first day in the recent-five-day drop window is skipped, and all-zero volume data can pass as an 80-point candidate.
- Direct reproductions also confirmed Strategy2 interrupted tasks lose their strategy type, Strategy2 completion can hide default Strategy1 candidates, Strategy2 JSON list fields are returned as strings, and Strategy1 task IDs are silently accepted by Strategy2 candidate queries.
- Verification: Strategy2 tests passed with 104 tests; offline suite passed with 354 tests; compileall and frontend build passed. Full suite had 356 passed and one external Dongcai connection failure.

## 2026-06-10 (Strategy2 Fix Recheck)

- Rechecked fix commit `136e48f` and added `docs/reviews/2026-06-10-strategy2-fix-recheck.md`.
- Confirmed the recent-five-day boundary, V20=0 rejection, candidate persistence ordering, JSON list deserialization, and stable candidate ordering fixes.
- Direct reproductions found seven remaining issues: Strategy2 frontend refresh/detail runtime failures, future cache accepted as fresh, incomplete task/API isolation, invalid prefix data still affecting the strategy window, missing scanner/unknown-task final defenses, missing terminal progress callbacks, and non-date strings accepted as valid dates.
- Verification: targeted suites passed with 78 tests; offline suite passed with 396 tests; full suite had 400 passed and one external Dongcai connection failure; compileall and frontend build passed. Commit diff check fails on one trailing whitespace line in the prior audit document.

## 2026-06-10 (Strategy2 Final Fix Recheck)

- Rechecked fix commit `d20dc4b` against `136e48f` and added `docs/reviews/2026-06-10-strategy2-final-fix-recheck.md`.
- Confirmed fixes for strategy-window validation, ISO date validation, unknown interrupted-task rejection, and several Strategy2 API isolation paths.
- Direct API reproduction confirmed that a Strategy2 failed task is still accepted by the generic retry endpoint and is incorrectly marked/routed as `STRATEGY_1_CUP_HANDLE`; Strategy2 tasks are also accepted by Strategy1 re-evaluate and candidate endpoints.
- Confirmed remaining issues in candidate terminal progress callbacks, frontend refresh/result-task restoration, long-holiday cache freshness, and current-running task list isolation.
- Verification: targeted suites passed with 87 tests; offline suite passed with 417 tests; full suite had 421 passed and one external Yahoo Finance 429 failure; compileall, frontend build, and diff check passed.

## 2026-06-10 (Strategy2 Final Acceptance Recheck)

- Reviewed final fix commit `1f8e3d5` and guide commit `b427df1`; added `docs/reviews/2026-06-10-strategy2-final-acceptance-recheck.md` and a separate repair-AI prompt document.
- Confirmed task-id API isolation, task-list isolation, candidate processed callback, frontend load ordering, route task selection, and prior strategy-window validation fixes.
- Direct reproduction found that all-source-failed and evaluation-exception paths call `_finish_stock` with the old signature, crash the worker, and leave stocks permanently in `fetching`.
- Direct API reproduction confirmed Strategy1 live candidate list/detail endpoints still return Strategy2 discoveries when Strategy2 is running.
- Confirmed cache freshness is still a fixed three-calendar-day heuristic; a 2026-09-30 cache is rejected on 2026-10-08, and the Monday-after-close test is an unconditional `pass`.
- Confirmed the production source chain still includes yfinance and retains mootdx registration despite the user-confirmed baidu/sina/tencent-only scope.
- Verification: final-fix tests passed 26 but contain coverage gaps; targeted suites passed 87; offline suite passed 443; full suite had 446 passed and two external-network failures; compileall and frontend build passed; commit-range diff check reported one EOF whitespace issue.
- User decision after review: remove cache fallback entirely. When all online data sources fail, both strategies must mark the stock failed and must not use local OHLC cache; trading-day/holiday freshness logic is no longer required.
- User requirement added: failed stocks must be visible in the frontend with a clear Chinese reason, per-source errors, accurate total count, and a historical Strategy2 failure-list entry point. Strategy2 must not expose the Strategy1-only retry action.

## 2026-06-10 (Strategy2 Final Acceptance Recheck Round 2)

- Reviewed commit `c14b974` against the ACCEPT-S2-001~006 requirements and added the Round 2 acceptance report plus repair-AI prompt.
- Confirmed the backend now rejects cache fallback on all-source failure, records Strategy2 failed terminal states and processed callbacks, isolates live Strategy discoveries, and returns correct failed-stock pagination/source errors.
- Found a high-severity frontend runtime error: ScannerConsole failure detail references `f` outside its `v-for`; the compiled bundle reads undefined `e.f.code` when the failure panel renders.
- Confirmed Strategy2Results still has no historical failure entry and historical ScannerConsole routes cannot restore the target task's strategy type.
- Confirmed source convergence remains incomplete in `scanner/engine.py`, single-stock backtest, requirements, tests, and design documentation.
- Verification: targeted suites passed 115; offline suite passed 445; full suite had 448 passed and two external failures plus an unhandled background-thread warning; compileall, frontend build, and diff check passed.

## 2026-06-11 (Strategy2 Final Acceptance Recheck Round 3)

- Reviewed fix commit `948b284` and added `docs/reviews/2026-06-11-strategy2-final-acceptance-recheck-round3.md` plus a direct repair-AI prompt.
- Confirmed the previous failure-panel scope error, Strategy2 historical failure entry, task-stock strategy type response, and production source mapping were fixed.
- Found that a historical task route is overwritten by an unrelated currently running task, causing wrong failures/candidates/strategy actions; Strategy1 historical candidate loading is also not scoped by task ID.
- Direct reproduction confirmed Strategy2 all-source failure records preserve `source_errors` but lose primary/fallback attempts and errors, so the frontend displays misleading zero attempts.
- Direct API reproduction confirmed a nonexistent task-stock request returns 200 and is silently labeled Strategy1.
- Confirmed the six-terminal-state test does not assert each exact terminal state, and targeted tests still emit an unhandled background-thread SQLite exception.
- Verification: targeted suites passed 53 with one unhandled thread warning; offline suite passed 449; full suite had 450 passed and four external/environment diagnostic failures; compileall and frontend build passed; commit-range diff check reported two EOF whitespace issues.
- Expanded the Round 3 repair-AI prompt into an ordered one-pass implementation guide with exact per-file edits, code skeletons, regression-test matrices, frontend runtime-test requirements, and phase/final acceptance gates.

## 2026-06-11 (Strategy2 Final Acceptance Recheck Round 4)

- Reviewed fix commit `b43cdcc` and added the Round 4 acceptance report plus one-pass repair-AI prompt.
- Confirmed API 404 semantics, complete Strategy2 source diagnostic persistence, exact six-terminal-state tests, thread-warning cleanup, default offline test boundary, and production source-file cleanup.
- Direct reproduction confirmed `/api/scan/status` returns full task statistics while running but returns `task_id=null` and empty stats after completion.
- Found that ScannerConsole applies the empty completion status before completion handling, resetting final processed/failed/candidate counts to zero; historical tracked tasks also stop before final result/failure refresh.
- Confirmed ScannerConsole does not watch query task changes, frontend runtime tests were not added (`npm run test` reports a missing script), and the Strategy2 main design/shared-service comment still describe four sources and failed-source cache fallback.
- Verification: targeted backend tests passed 57; six-terminal tests passed 6; thread-warning suite passed 17; default full suite passed 422; compileall and frontend build passed; frontend test command failed because no test script exists; diff check passed.

## 2026-06-11 (Strategy2 Final Acceptance Recheck Round 5)

- Reviewed fix commit `6f04564` and added the Round 5 acceptance report plus final focused repair-AI prompt.
- Confirmed task-stock summary response, live completion summary recovery, reactive query watcher implementation, Vitest setup, full source-diagnostic persistence tests, and core three-source/no-cache-fallback design synchronization.
- Found that historical tracked tasks still return before final refresh because the historical task-id mismatch branch precedes completion handling in `pollStatus`.
- Found that switching from a valid historical task to an unknown task leaves old failures, strategy context, and statistics visible and does not show the unknown-task error.
- Confirmed the six passing frontend tests do not actually exercise interval-driven historical completion or reactive query A-to-B/missing-task transitions; the route mock is not reactive.
- Confirmed remaining stale cache-freshness wording and a weak busy-diagnostic test.
- Verification: targeted backend tests passed 61; default full suite passed 426; frontend Vitest passed 6 tests; frontend build, compileall, and diff check passed; task summary API direct reproduction passed.

### Commit history
```
eff4597 feat(strategy2): full implementation — engine, scanner, DB, API, frontend
538c5ea test(strategy2): add independence boundary checks
965b385 feat(strategy2): add ExtremeDryStableStrategyEngine
b262c8b feat(strategy2): add scorer, rejection rules, and risk calculator
68d6c26 feat(strategy2): add indicator computation module
905f733 feat(strategy2): add data models for extreme dry-stable strategy
```

## 2026-06-12 (Strategy2 Phase 1 Completion Recheck)

- Reviewed commits through `b23d254` and analyzed task `s2bt-20260612-155934-n35sdk`.
- Added `docs/reviews/2026-06-12-strategy2-phase1-completion-recheck-and-task-155934-analysis.md`.
- Confirmed task-stock count closure, stable signal/opportunity counts, and complete target/stop exit dates.
- Found remaining high-severity gaps: empty horizon summary accepted as `TRUSTED_BASELINE`, nonfunctional resume/retry/cancel behavior, and non-transactional per-stock persistence with missing signal links.
- Found incomplete audit metadata and two remaining ScannerConsole frontend test failures.
- New task result: 641 actual entries, 265 targets, 374 stops, 2 unresolved, 41.34% target-hit rate, and -0.3191% average realized return.
- Verification: Strategy2 targeted tests passed 23; offline backend suite passed 506 with 2 warnings; frontend build, compileall, and diff check passed; frontend Vitest had 23 passed and 2 failed.

## 2026-06-12 (Strategy2 Phase 1 Recheck and Task 220015 Analysis)

- Reviewed fixes through `cd78cc2` and analyzed task `s2bt-20260612-220015-qmr54h`.
- Added `docs/reviews/2026-06-12-strategy2-phase1-recheck-and-task-220015-analysis.md`.
- Confirmed atomic per-stock persistence, complete signal ID links, non-empty horizon summary, parsed detail summary, UTC task timing, and all 25 frontend tests.
- Found that integrity validation runs before final task fields are saved, so completed tasks retain stale integrity errors and cannot become trusted.
- Found horizon summaries use final trade returns instead of each horizon's own performance fields, while frontend expects fields the backend does not provide.
- Confirmed backtest resume/retry remain placeholders and cancel does not stop the worker.
- Same config hash and same `data_snapshot_date` produced different results: 69 old-only and 53 new-only signals, with 4850 changed stock evaluation ranges.
- New task result: 628 entries, 253 targets, 373 stops, 2 unresolved, 40.29% target-hit rate, and -0.4071% average realized return.
- Verification: Strategy2 targeted tests passed 26; frontend Vitest passed 25; frontend build and compileall passed; backend suite had 508 passed and one external yfinance 429 failure.

## 2026-06-13 (Strategy2 Phase 1 Medium/High Recheck)

- Reviewed commit `997d8f8` plus current uncommitted changes and added `docs/reviews/2026-06-13-strategy2-phase1-medium-high-recheck.md`.
- Confirmed corrected horizon statistics, two-phase finalization, observation-date aggregation, real cancellation signaling, real available-day persistence, and passing frontend tests.
- Found three remaining high-severity issues: backtest resume/retry are still placeholders, same-day data changes are not protected by the date-only snapshot, and credibility validation mishandles canceled and zero-opportunity tasks.
- Direct reproduction confirmed a fully terminal `CANCELED` task passes integrity validation, while a complete zero-opportunity task fails due to missing horizon keys.
- Found two medium-severity gaps: incomplete per-stock audit/progress fields and empty funnel/target-stop timing summaries.
- Verification: Strategy2 targeted tests passed 26; acceptance-related tests passed 65; offline backend suite passed 508 with one warning; frontend Vitest passed 25; frontend build, compileall, and diff check passed.

## 2026-06-13 (Strategy2 Phase 1 Medium/High Fixes)

- Optimized `AGENTS.md` to match the current dual-strategy architecture, Strategy2 backtest invariants, worktree commands, TDD workflow, and automatic commit/no-push rule.
- Added `strategy2/backtest_service.py` as the shared start/resume/retry-failed executor. Resume now targets only PENDING/RUNNING stocks; retry-failed targets only FAILED stocks; cancellation stops at stock boundaries and cannot become trusted.
- Added task-level `data_revision_id` using a stable SHA-256 over selected local OHLC rows. Start, resume/retry, and finalization validate the same data revision; changed data marks the task `DATA_REVISION_CHANGED`.
- Fixed integrity validation so only `completed` tasks can become `TRUSTED_BASELINE`; complete zero-opportunity tasks now produce full zero-value horizon summaries and can pass integrity checks.
- Completed per-stock audit persistence for real `started_at`, `finished_at`, `invalid_data_days`, `earliest_date`, and `latest_date`; all terminal paths update live processed progress.
- Completed task summary funnel aggregation and per-horizon `avg_days_to_target` / `avg_days_to_stop`; Strategy2Backtest now displays both.
- Added `tests/test_strategy2_medium_high_fixes.py` with 10 behavior tests covering resume, retry-failed, cancel, data revision changes, zero opportunities, credibility, audit fields, funnel/timing summaries, and reproducibility.
- Reproducibility integration result: two tasks using the same data revision produced signal symmetric difference `0` and opportunity symmetric difference `0`.
- Verification before final commit:
  - Strategy2 backtester + independence: **26 passed**.
  - Acceptance/recheck/medium-high fixes: **54 passed**.
  - Strategy2-related suite: **274 passed**.
  - Offline backend full suite: **518 passed, 1 existing dateutil deprecation warning**.
  - Frontend Vitest: **25 passed**.
  - Frontend production build: **passed**.
  - Python compileall and `git diff --check`: **passed**.
- Full-market baseline rerun was not started in this repair session because it is a long-running operational job; reproducibility and behavior were verified with temporary SQLite integration tasks.

## 2026-06-13 (Strategy2 Phase 1 Final Acceptance)

- Reviewed fix commit `7a3430e` against baseline `997d8f8` and added `docs/reviews/2026-06-13-strategy2-phase1-final-acceptance.md`.
- Confirmed real resume/retry-failed/cancel behavior, completed-only credibility validation, complete zero-opportunity summaries, funnel/timing aggregation, per-stock audit fields, and data revision enforcement.
- Found two remaining high-severity issues: the data revision fingerprint omits `turnover`, although liquidity filtering depends on it; and historical failed/running or revision-less tasks can remain labeled `TRUSTED_BASELINE`.
- Found one remaining medium-severity issue: revision calculation reads all market rows and filters task stocks in Python, causing avoidable startup and validation delay for small tasks.
- Direct reproduction confirmed that changing only `turnover` changes liquidity eligibility while leaving the revision unchanged.
- Database inspection found 11 currently trusted tasks that violate the current completed/revision-backed credibility rules.
- Verification: Strategy2 targeted and acceptance tests passed 70; offline backend suite passed 518 with one warning; frontend Vitest passed 25; frontend build, compileall, `git show --check`, and `git diff --check` passed.

## 2026-06-13 (Strategy2 Phase 1 Final Acceptance Fixes)

- Fixed ACCEPT-001: Strategy2 task data revisions now hash `code/date/open/high/low/close/volume/turnover`; changing only turnover changes the SHA-256 and blocks resume/retry-failed.
- Fixed ACCEPT-002: added explicit revision algorithm version `daily-ohlc-v2`. Compatibility migration conservatively downgrades historical trusted tasks with an old/missing revision version, non-completed status, missing summary/revision, incomplete processing, pending/running stocks, failures, or evaluation errors.
- Fixed ACCEPT-003: production revision calculation now joins `daily_ohlc` to `strategy2_backtest_task_stocks` by task ID, so small tasks only read their own stocks.
- Actual database migration check: remaining trusted tasks before migration `0`, newly downgraded `0`, existing `LEGACY_UNTRUSTED` tasks `21`. Temporary migration tests prove old-algorithm and otherwise-invalid trusted tasks are downgraded while a current valid task is preserved.
- Turnover-only proof:
  - Before: `1745e21d6668ff2e91b9265f8b99eb4129c3c92d1164c6f8ffdc762712ae7fe2`
  - After: `e499155246f19bdcd1b19673ca08a056713067cd85117e6c7f59f12fd0eaf09e`
- Actual database revision timings:
  - Single stock: `0.002596s`
  - 200 stocks: `0.4497s`
  - 5527 stocks: `18.2354s`
- Final verification: offline backend suite passed `523` with one existing warning; frontend Vitest passed `25`; frontend production build, Python compileall, and `git diff --check` passed.
- The first final frontend test run overlapped the frontend build and failed during Vitest sandbox-path module resolution before collecting tests. A standalone rerun passed all `25` tests.

## 2026-06-13 (Strategy2 Phase 1 Final Acceptance Recheck Fixes)

- Fixed Strategy2 backtest startup recovery: tasks left `running` by a previous process are transactionally marked `INTERRUPTED`, only `RUNNING` stocks return to `PENDING`, completed results remain intact, and startup failures are logged instead of silently ignored.
- Added explicit implementation revisions in `strategy2/version.py`. New tasks persist both backtest and strategy engine versions; integrity validation, resume, retry-failed, and execution reject version mismatches with `ENGINE_REVISION_CHANGED`.
- Historical trusted tasks with missing or old engine revisions are conservatively downgraded instead of being upgraded or resumed under new code.
- Added paginated and status-filtered Strategy2 backtest history responses while keeping configuration and summary JSON out of list responses.
- Completed the Strategy2 backtest frontend task-control loop: credibility/version display, failed-stock details, cancel/resume/retry actions, running-task restoration after refresh, automatic final-detail loading, and history pagination/filtering.
- Added backend behavior tests for restart recovery, engine mismatch rejection with result preservation, integrity version checks, and history pagination; added frontend behavior tests for credibility, failed-stock retry, resume, revision-change blocking, and refreshed-task cancellation.
- Verification:
  - Strategy2 targeted and acceptance suites: **90 passed**.
  - Offline backend full suite: **528 passed, 1 existing dateutil deprecation warning**.
  - Frontend Vitest: **29 passed**.
  - Frontend production build, Python compileall, and `git diff --check`: **passed**.

## 2026-06-13 (Strategy2 Phase 2 Experiment Layer Development)

- Implemented Strategy2 Phase 2 backtest experiment layer without changing formal Strategy2 scan rules or `config.yaml`.
- Added `strategy2/backtest_experiments.py` for experiment config normalization, post-signal filters, opportunity type labels, entry confirmation, and time-exit handling.
- Wired `experiment` payload through Strategy2 backtest start, service execution, per-stock backtest, DB persistence, task summaries, preview API, and baseline comparison API.
- Added compatible SQLite migrations for `experiment_snapshot`, `baseline_task_id`, comparison summary, filtered signal traceability, entry confirmation, time-exit, opportunity type, and experiment funnel counters.
- Experimental tasks now freeze normalized `experiment_snapshot` and finalize as `EXPERIMENTAL`; disabled/missing experiments preserve Phase 1 baseline behavior.
- Filtered baseline-passed signals are retained in `strategy2_backtest_signals` with `experiment_passed=0` and `experiment_filter_reason`.
- Added Strategy2Backtest UI controls for experiment mode, score thresholds, time exit, entry confirmation, baseline task ID, EXPERIMENTAL badge, experiment snapshot, experiment funnel, and comparison summary.
- Reviewer fixes during this session:
  - Rolled up experiment funnel counts to task fields and `summary_json`.
  - Corrected horizon performance to start from actual entry date after entry confirmation.
  - Corrected time-exit precedence so only earlier TARGET/STOP overrides time exit; later TARGET/STOP is replaced by `TIME_EXIT`.
  - Added experiment fields to legacy save helpers to avoid traceability loss outside the main replace path.
- Verification:
  - Phase 2 backend tests: **22 passed**.
  - Strategy2 backtester + medium/high regression set: **62 passed**.
  - Frontend Vitest: **31 passed**.
  - Frontend production build: **passed**.
  - Python compileall: **passed**.
- Not performed in this development step: full-market trusted baseline run, experiment task batch run, or formal Strategy2 parameter upgrade. Those require operational backtest evidence from completed comparable tasks.

## 2026-06-13 (Strategy2 Phase 2 Experiment Results and Grouped Summary Fix)

- Ran and analyzed one trusted baseline plus five comparable experimental Strategy2 backtest tasks on the local dataset.
- Baseline task `s2bt-20260613-174358-baseline` was corrected to `total_stocks=5527` after the manual runner initially omitted the field; final integrity passed as `TRUSTED_BASELINE`.
- Baseline result: 5527 processed stocks, 669 opportunities, 1373 raw signals, 0 failed stocks, 635 insufficient stocks, average realized return `-0.004071`, target hit rate `40.29%`.
- Comparable experiment results:
  - `s2bt-20260613-174929-vol40`: `minimumVolumeDryScore=40`, 377 opportunities, 347 entered, average return `0.001903`, delta average return `+0.005974`, success-rate delta `+0.066875`.
  - `s2bt-20260613-175258-vol50`: 160 opportunities, 148 entered, average return `0.003014`, delta average return `+0.007085`, success-rate delta `+0.076864`.
  - `s2bt-20260613-175657-vol40-exit5`: 377 opportunities, 347 entered, average return `0.006787`, 169 time exits, delta average return `+0.010858`.
  - `s2bt-20260613-180134-vol40-exit10`: 377 opportunities, 347 entered, average return `0.005287`, 48 time exits, delta average return `+0.009358`.
  - `s2bt-20260613-180601-vol40-break5`: entry confirmation failed 206 times, only 29 entered, average return `-0.023904`; this confirmation rule should not be promoted without redesign.
- Review finding fixed in this session: Phase 2 design required grouped experiment statistics, but `summary_json` did not expose grouped stats and opportunities did not persist `volume_dry_score` / `price_stable_score`.
- Added grouped summary buckets under `summary["groups"]`: month, opportunity type, volume-dry score band, price-stable score band, total score band, and entry-confirmation status.
- Added compatible opportunity-table migrations and propagated volume/price scores from `BacktestSignal` to `BacktestOpportunity`, API dicts, and both opportunity persistence paths.
- Current interpretation: `minimum_volume_dry_score=50` improves average return and success rate while sharply reducing opportunity count; `minimum_volume_dry_score=40 + time_exit_days=5` has the best average return in this batch but changes exit semantics. No formal Strategy2 scan parameter upgrade was made.
- Verification:
  - Grouped summary TDD test: **1 passed** after first confirming the red failure.
  - Strategy2 Phase 2 / backtester / medium-high regression set: **64 passed**.
  - Frontend Vitest: **31 passed**.
  - Frontend production build: **passed**.
  - Python compileall and `git diff --check`: **passed**.

## 2026-06-13 (Strategy2 Formal Optimized Parameter Enablement)

- Enabled Strategy2 optimized formal version `strategy2-v3` based on the trusted baseline and comparable Phase 2 experiment results.
- Decision baseline task: `s2bt-20260613-174358-baseline`.
- Adopted evidence:
  - `s2bt-20260613-174929-vol40`: `minimumVolumeDryScore=40`, average return `0.001903`, delta average return `+0.005974`, success-rate delta `+0.066875`.
  - `s2bt-20260613-175657-vol40-exit5`: `minimumVolumeDryScore=40 + timeExitDays=5`, average return `0.006787`, delta average return `+0.010858`.
- Formal parameters:
  - `strategy2.candidate_min_score=70` unchanged.
  - `strategy2.minimum_volume_dry_score=40` added as a formal scan hard filter.
  - `strategy2.short_term_time_exit_days=5` added as candidate display / short-term observation guidance, not as an entry hard filter.
  - `entry_confirmation` remains disabled for formal scan because `BREAK_RECENT_5D_HIGH` produced too few entries and negative average return.
- Code changes:
  - `strategy2/validation.py` validates the new formal parameters.
  - `strategy2/engine.py` rejects formal candidates with `VOLUME_DRY_BELOW_THRESHOLD`.
  - `strategy2/version.py` bumped strategy engine version to `strategy2-v3`.
  - `scanner/db.py` persists `short_term_time_exit_days` on Strategy2 candidates.
  - `web/src/pages/StrategyConfig.vue` exposes the new formal parameters.
  - `web/src/pages/Strategy2Results.vue` displays the 5-day short-term observation guidance.
- Optimized strategy document: `docs/superpowers/specs/2026-06-13-strategy2-optimized-strategy-parameters.md`.
- Rollback plan: restore `minimum_volume_dry_score=0`, `short_term_time_exit_days=0`, and strategy version behavior if repeated scans become too sparse or new comparable backtests underperform `strategy2-v2`.
- Verification:
  - TDD red checks confirmed missing formal config parsing, missing volume-dry hard filter, and missing candidate persistence before implementation.
  - Strategy2 targeted tests: **164 passed**.
  - Frontend Vitest: **31 passed**.
  - Frontend production build: **passed**.
  - Python compileall: **passed**.
  - Local full test set excluding external yfinance network tests: **529 passed**.
  - Full `python -m pytest tests -q`: **555 passed, 1 failed**; the only failure was `tests/test_yfinance_hist.py::test_yfinance_daily` due to Yahoo `YFRateLimitError: Too Many Requests`, unrelated to Strategy2 changes.

## 2026-06-14 (Strategy1 Trusted Backtest Experiment Capability)

- Created Strategy1 worktree branch `codex/strategy1-backtest-experiment-optimization` from local `main` and restored the Strategy1 optimization design document that had been removed from the current baseline.
- Implemented Strategy1 trusted backtest foundation without changing formal Strategy1 scan parameters:
  - `scanner/strategy1_backtest_models.py` for traceable signals, opportunities, horizons, and insufficient-stock records.
  - `scanner/strategy1_backtest_experiments.py` for normalized experiment config and post-signal filters.
  - `scanner/strategy1_backtester.py` for local OHLC replay, `CupHandleStrategyEngine.evaluate_at()` calls, signal merging, `NEXT_OPEN` entry, 3/5/10/20 horizon outcomes, and optional time exit.
  - `scanner/strategy1_backtest_service.py` for local DB task execution and data revision calculation.
  - `scanner/db.py` Strategy1 backtest tables, task CRUD, signal/opportunity persistence, stock status, DB-derived summary, comparison, and interrupted-task recovery.
  - `server.py` `/api/strategy1/backtests*` endpoints for start/status/list/detail/opportunities/signals/stocks/experiment-preview/comparison.
  - `web/src/pages/Strategy1Backtest.vue` plus API helper, route, navigation, and component tests.
- Review fix during this session:
  - Added `mark_running_strategy1_backtests_interrupted()` and startup recovery so Strategy1 backtest tasks left `running` by a previous process become `INTERRUPTED` and only `RUNNING` stocks return to `PENDING`.
- Verification:
  - Baseline Strategy1 tests before development: **77 passed**.
  - Strategy1 experiment + replay + DB/API tests: **29 passed**.
  - Strategy1 targeted regression set: **105 passed**.
  - Frontend Vitest: **33 passed**.
  - Frontend production build: **passed**.
  - Python compileall for `scanner strategy2 server.py`: **passed**.
- Not performed in this development step:
  - Copying the production SQLite market-data snapshot into this worktree.
  - Running a full-market Strategy1 trusted baseline task.
  - Running comparable Strategy1 experiment batches.
  - Enabling optimized formal Strategy1 parameters.
  - Creating `docs/superpowers/specs/YYYY-MM-DD-strategy1-optimized-strategy-parameters.md`.
- Residual risk:
  - The current delivery implements the trusted backtest and experiment capability foundation. Formal Strategy1 optimization still requires completed trusted baseline and comparable experiment evidence before changing production scan parameters.

## 2026-06-14 (Strategy1 Trusted Baseline and Experiment Decision)

- Corrected Strategy1 local DB backtest semantics after reviewing the temporary `liquidity.min_listing_days=350` concern:
  - Strategy1 backtest evaluation now uses `data.backtest_window_days` as the required historical replay window.
  - `liquidity.min_listing_days` remains scan/listing-day/fetch semantics and no longer blocks historical backtest evaluation dates.
  - Added regression tests for both the per-date backtest window gate and task-level insufficient-data status.
- Ran a new full-market trusted Strategy1 baseline using local SQLite only:
  - Task ID: `s1bt-20260614-250d-baseline`.
  - Evaluation range: `2026-03-01` to `2026-06-01`; actual signal range `2026-03-02` to `2026-06-01`.
  - Status: `completed`; credibility: `TRUSTED_BASELINE`; integrity check passed.
  - Total/processed stocks: `5527 / 5527`.
  - Failed stocks: `0`; insufficient stocks: `635`.
  - Raw signals: `819`; opportunities: `521`; entered: `515`.
  - Target rate: `37.6699%`; stop rate: `62.3301%`.
  - Average realized return: `-0.008490`; median realized return: `-0.027742`.
- Ran comparable derived experiment tasks from the trusted baseline:
  - `s1bt-20260614-exp-score70`: 344 opportunities, avg return `-0.006526`, stop rate `61.5616%`.
  - `s1bt-20260614-exp-score80`: 66 opportunities, avg return `0.000839`, stop rate `56.0606%`.
  - `s1bt-20260614-exp-vol9`: 135 opportunities, avg return `-0.003985`, stop rate `60.6061%`.
  - `s1bt-20260614-exp-price7`: 71 opportunities, avg return `-0.001244`, stop rate `57.7465%`.
  - `s1bt-20260614-exp-score80_price7`: 13 opportunities, avg return `0.008934`, stop rate `46.1538%`.
  - `s1bt-20260614-exp-score80_time5`: 66 opportunities, avg return `0.000609`, stop rate `48.4848%`.
- Decision:
  - Formal Strategy1 scan parameters were **not** upgraded in this round.
  - Raising total score to 80 is the clearest improvement direction, but opportunity count falls from 521 to 66 and monthly robustness is not strong enough.
  - Stronger combinations such as `score80 + price7` are promising but too sparse with only 13 opportunities.
  - Time exit improves stop-rate optics but lowers target rate and should remain diagnostic/guidance until a wider sample validates it.
- Added decision document:
  - `docs/superpowers/specs/2026-06-14-strategy1-backtest-experiment-results-and-optimization-decision.md`.

## 2026-06-14 (Strategy1 500-Day History Optimization Direction)

- User expanded local daily OHLC history to about 500 trading rows for most stocks.
- Confirmed local DB coverage:
  - `daily_ohlc` range: `2024-03-18` to `2026-06-12`.
  - `daily_ohlc` rows: `2444267`.
  - Stocks with OHLC: `4976`.
  - Stocks with at least 500 rows: `4804`.
- Ran a new full-market Strategy1 trusted baseline using local DB only:
  - Task ID: `s1bt-20260614-500hist-250w-baseline`.
  - Evaluation range: `2025-09-01` to `2026-05-15`.
  - Status: `completed`; credibility: `TRUSTED_BASELINE`; integrity check passed.
  - Processed stocks: `5527`; failed stocks: `0`; insufficient stocks: `635`.
  - Raw signals: `3282`; opportunities: `1844`; entered: `1823`.
  - Target rate: `44.4871%`; stop rate: `54.1964%`.
  - Average realized return: `+0.003190`; median realized return: `-0.022371`.
- Ran comparable derived experiment tasks. Key findings:
  - `score>=80` no longer holds up on the wider sample: `283` opportunities, avg return `-0.003158`, stop rate `61.0108%`.
  - `priceStable>=7`: `205` opportunities, target rate `47.2906%`, stop rate `52.7094%`, avg return `+0.004017`, median `-0.016398`.
  - `priceStable>=7 + timeExitDays=5`: `205` opportunities, stop rate `44.8276%`, avg return `+0.002256`, median `-0.010695`.
  - `WATCH_BREAKOUT only`: strong metrics but only `17` opportunities, too sparse for formal filtering.
  - `rr1>=2.5`: attractive metrics but only `47` opportunities; treat as diagnostic until RR/target model is reviewed.
- Decision:
  - No formal Strategy1 hard-filter upgrade in this round.
  - New optimization direction is quality tiering, not recall reduction:
    - `PRICE_STABLE_STRONG`: `price_stable_score >= 7`.
    - `PRICE_STABLE_EXTREME`: `price_stable_score >= 8`.
    - `BREAKOUT_OBSERVE`: `verdict_key == WATCH_BREAKOUT`.
    - `SHORT_TERM_RISK_CONTROL`: expose 5-day time-exit diagnostics as guidance.
- Added document:
  - `docs/superpowers/specs/2026-06-14-strategy1-500hist-experiment-optimization-direction.md`.
