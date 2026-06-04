# Operations Log

## 2026-06-04

- Continued dry-stable strategy implementation: added market environment analysis, API/DB/CSV fields, and frontend display for dry-stable verdicts.
- Verification issue found: `tests/test_db_strategy_fields.py` exposed a `save_candidates()` SQL placeholder mismatch after adding market environment columns.
- Fix applied: corrected `scanner/db.py` candidate insert placeholders to match the 40 persisted columns.
- Final verification: `python -m pytest tests/ -q` passed with 62 tests; `python -m compileall analyzer scanner main.py server.py output tests` passed; `npm.cmd run build` passed with existing Vite chunk-size warnings.
