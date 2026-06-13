# AGENTS.md

This file provides Codex-specific guidance for this repository.

Project facts, architecture notes, gotchas, and historical decisions live in `CLAUDE.md`. Before starting non-trivial work, read `CLAUDE.md` and then inspect the current code/tests because code and tests are the final source of truth.

## Codex Workflow

For development tasks, use the dual-role closed loop:

1. Read the design/spec/review documents and related code first.
2. Implement as the programmer role.
3. Switch to reviewer role for acceptance review.
4. Fix all medium/high issues found by the review.
5. Repeat review/fix until no medium/high issues remain.
6. Ask the user only when a requirement cannot be inferred safely or a blocker cannot be resolved.
7. After verified development work, automatically run `git add`, `git commit`, and `git push` unless the user explicitly says not to push.

For bug fixes, use TDD when practical:

- Reproduce the issue with a failing test.
- Verify the test fails for the expected reason.
- Make the smallest safe fix.
- Re-run targeted tests and relevant regression tests.

## Strategy2 Data Rules

- Strategy2 backtests, experiments, formal parameter upgrades, and acceptance analysis must use local `stock_pool` and `daily_ohlc` data by default.
- Do not fetch fresh Baidu/Sina/Tencent/yfinance/AKShare/Tushare data unless the user explicitly asks for new data.
- External network/data-source tests are manual/on-demand. Routine regression should use local database tests and mock tests.
- Do not modify Strategy2 scoring, trend, rejection, risk, or signal semantics unless the current task explicitly requires it and tests/docs are updated.
- Strategy2 code must not import Strategy1 shape/analysis/decision modules. Shared data, liquidity, and SQLite helpers may be reused.

## Commands

Prefer these commands in worktrees:

```bash
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner server.py -q

npm --prefix web install
npm --prefix web test -- --run
npm --prefix web run build
```

When the current branch/worktree contains Strategy2 files, add the Strategy2-specific checks:

```bash
python -m pytest tests/test_strategy2_backtester.py -v
python -m compileall strategy2 -q
```

Use `npm --prefix web ...` from repository/worktree roots. Do not rely on `cd web && ...` in automation.

## Git Safety

Allowed without additional confirmation after verification:

- `git status`
- `git diff`
- `git log`
- `git branch`
- `git show`
- `git add`
- `git commit`
- `git push`

Never run destructive commands unless the user explicitly approves the exact command:

- `git reset --hard`
- `git clean -fd`
- `git clean -fdx`
- `git checkout .`
- `git restore .`
- `rm -rf`

Do not overwrite or revert user changes. If unrelated files are dirty, leave them alone. Stage only files related to the current task unless the user asks to include more.

## Verification And Delivery

Before declaring work complete:

- Run targeted tests for changed modules.
- Run broader local regression when the change touches shared behavior.
- Run frontend tests/build when frontend files changed.
- Record important execution results, failures, and risks in `operations-log.md` for complex work.

Final responses should include:

- What changed.
- Tests/commands run and real results.
- Any skipped validation and why.
- Commit hash and push status when git actions were performed.
