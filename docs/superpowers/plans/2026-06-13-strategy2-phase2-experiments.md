# Strategy2 Phase 2 Experiments Implementation Plan

> **For AI agents:** Execute this plan with the dual-role loop: programmer implementation, reviewer acceptance, fix medium/high findings, repeat. Track progress with checkboxes.

**Goal:** Add Strategy2 backtest experiment mode without changing formal Strategy2 scan rules.

**Architecture:** Keep Strategy2 evaluation as the single source of signal truth. Add `strategy2/backtest_experiments.py` as a pure experiment layer for config normalization, post-signal filters, opportunity tags, entry confirmation, time exit, summaries, and baseline comparison helpers. Wire the experiment snapshot through backtester, service, DB, API, and frontend.

**Tech Stack:** Python 3.10+, SQLite, FastAPI, Vue 3, Vitest, pytest.

---

## File Structure

- Create `strategy2/backtest_experiments.py`: pure experiment helpers.
- Modify `strategy2/backtest_models.py`: add traceability and experiment fields.
- Modify `strategy2/backtester.py`: accept optional experiment, preserve disabled baseline behavior.
- Modify `strategy2/backtest_service.py`: finalize experimental tasks as `EXPERIMENTAL` and save comparison summary.
- Modify `scanner/db.py`: add compatible columns, persist experiment fields, build grouped summary and comparison data.
- Modify `server.py`: validate experiment payload, add preview and comparison endpoints.
- Modify `web/src/composables/useApi.js`: add preview/comparison API helpers.
- Modify `web/src/pages/Strategy2Backtest.vue`: add experiment controls, badge, snapshot, comparison, and summary display.
- Add tests under `tests/` and `web/src/pages/__tests__/`.

## Tasks

- [ ] Task 1: Add failing tests for experiment normalization, filters, entry confirmation, and time exit.
  - Verify red: `python -m pytest tests/test_strategy2_phase2_experiments.py -q`
- [ ] Task 2: Implement `strategy2/backtest_experiments.py` to pass pure helper tests.
  - Verify green: `python -m pytest tests/test_strategy2_phase2_experiments.py -q`
- [ ] Task 3: Add and pass tests for disabled experiment baseline equivalence and filtered signal traceability.
  - Verify: `python -m pytest tests/test_strategy2_phase2_experiments.py tests/test_strategy2_backtester.py -q`
- [ ] Task 4: Add DB migration/persistence tests for experiment snapshot, signal fields, opportunity fields, and summary funnel.
  - Verify: `python -m pytest tests/test_strategy2_phase2_db_api.py -q`
- [ ] Task 5: Add API preview/start/comparison tests and implement server wiring.
  - Verify: `python -m pytest tests/test_strategy2_phase2_db_api.py -q`
- [ ] Task 6: Add frontend tests and UI for experiment controls, EXPERIMENTAL badge, snapshot, and comparison.
  - Verify: `npm.cmd --prefix web test -- --run`
- [ ] Task 7: Reviewer pass for medium/high issues, fix all blockers.
  - Verify: targeted backend/frontend tests after each fix.
- [ ] Task 8: Final verification and commit.
  - Verify: `python -m compileall scanner strategy2 server.py -q`, Strategy2 pytest set, frontend test/build.
  - Update `operations-log.md`.
  - `git add` and `git commit`; do not push.
