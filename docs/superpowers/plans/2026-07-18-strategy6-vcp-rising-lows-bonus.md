# Strategy6 VCP Rising Lows Bonus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add exactly two main-chain pattern points when every completed VCP round avoids a new low and average low uplift is at least one percent.

**Architecture:** `strategy6.pattern` owns evidence calculation and adds one explicit reason tag. `strategy6.scorer` consumes that tag and adds two points inside the existing 15-point pattern/phase cap.

**Tech Stack:** Python 3.10, dataclasses, pytest.

## Global Constraints

- Add no configuration, hard filter, database column, frontend control, or observation-pool score change.
- Keep `pattern_score_component <= 15` and `total_score <= 100`.
- Do not modify Strategies 1-5.
- Do not stage existing uncommitted review reports.

---

### Task 1: VCP low-uplift evidence

**Files:**
- Modify: `tests/test_strategy6_pattern.py`
- Modify: `strategy6/pattern.py`

- [ ] Add parameterized failing tests for exact 1%, below 1%, one lower low, and insufficient rounds.
- [ ] Run the focused tests and verify failure because the evidence helper does not exist.
- [ ] Implement `_has_vcp_rising_lows_bonus(rounds) -> bool` using adjacent `low_close` changes.
- [ ] Add `VCP_LOW_RISING_BONUS` only to qualifying main-chain VCP reasons.
- [ ] Run focused tests and verify they pass.

### Task 2: Main-chain score integration

**Files:**
- Modify: `tests/test_strategy6_pattern.py`
- Modify: `strategy6/scorer.py`

- [ ] Add a failing scorer test proving the reason tag adds exactly two pattern points and no tag adds zero.
- [ ] Run the focused test and verify the expected two-point difference is absent.
- [ ] Add the fixed two-point bonus inside the existing 15-point pattern cap and record `vcp_low_trend_bonus=2` in score reasons.
- [ ] Run focused tests and verify they pass.

### Task 3: Closed-loop verification

**Files:**
- Review all files modified by Tasks 1-2.

- [ ] Run Strategy6 pattern, core-rule, backtest snapshot and report tests.
- [ ] Run all Strategy6 backend tests and Python compileall.
- [ ] Review the diff for score duplication, boundary errors and unintended observation-pool changes.
- [ ] Fix all medium/high findings, repeat verification, then stage only this feature, commit and push.
