# Operations Log

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
