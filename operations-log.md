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
