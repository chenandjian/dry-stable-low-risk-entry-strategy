# Operations Log

## 2026-06-04

- Continued dry-stable strategy implementation: added market environment analysis, API/DB/CSV fields, and frontend display for dry-stable verdicts.
- Verification issue found: `tests/test_db_strategy_fields.py` exposed a `save_candidates()` SQL placeholder mismatch after adding market environment columns.
- Fix applied: corrected `scanner/db.py` candidate insert placeholders to match the 40 persisted columns.
- Final verification: `python -m pytest tests/ -q` passed with 62 tests; `python -m compileall analyzer scanner main.py server.py output tests` passed; `npm.cmd run build` passed with existing Vite chunk-size warnings.
- Strategy completion verification: `python -m pytest tests/ -q` passed with 66 tests; `python -m compileall analyzer scanner main.py server.py output tests` passed; `npm.cmd run build` passed. Remaining build notices are the Vite CJS Node API deprecation and the intentionally lazy-loaded `echarts` chunk exceeding 500 kB.

## 2026-06-10

- Added a decision confirmation document for scan/backtest fixed windows and the single strategy entry point.
- Updated the unified strategy design document with six confirmed implementation decisions.
- Resolved documentation ambiguities: fixed-window selection returns `None` on insufficient data, `window_min` is removed from `run_backtest()`, `--min-score` is report-only and deprecated, and candidate detail responses distinguish persisted scan results from current-config analysis.
- Documentation verification: placeholder and contradiction scans completed; `git diff --check` passed.
- Added the yfinance four-source daily K-line design, preserving the existing model where independent data-source locks process different stocks concurrently.
- Defined yfinance A-share symbol mapping, explicit adjusted-price behavior, normalized SQLite OHLC fields, rate-limit propagation, four-source concurrency tests, and offline CI boundaries.

## 2026-06-13

- Synchronized Codex session provider metadata after switching the active provider to `custom` in `C:\Users\pp\.codex\config.toml`.
- Backed up `state_5.sqlite` and the affected session JSONL files to `C:\Users\pp\.codex\backups\provider-sync-20260613-144650` before writing changes.
- Updated 76 `threads.model_provider` rows in `state_5.sqlite` and 79 `session_meta.payload.model_provider` entries in `C:\Users\pp\.codex\sessions` from `openai` to `custom`.
- Verification: `state_5.sqlite` provider counts are now `custom=76`; session meta provider counts are now `custom=80`; no non-current provider entries or JSON parse errors remain.
