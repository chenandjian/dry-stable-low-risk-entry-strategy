# Strategy6 Market Downgrade Origin Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist and display the exact Strategy6 candidate tier that existed before weak-market downgrade.

**Architecture:** The Strategy6 engine computes a market-neutral classification audit alongside the authoritative classification without changing scoring or final candidate semantics. The audit value is persisted as an optional candidate column and rendered by the existing Strategy6 results page.

**Tech Stack:** Python 3.10 dataclasses, SQLite, Vue 3, Vitest, pytest.

## Global Constraints

- Preserve current Strategy6 scan entry, scoring, final candidate type and old output fields.
- Do not modify Strategies 1-5.
- Old Strategy6 databases and tasks must remain readable.
- Do not stage unrelated report changes already present in the worktree.

---

### Task 1: Strategy classification audit

**Files:**
- Modify: `tests/test_strategy6_core_rules.py`
- Modify: `strategy6/filters.py`
- Modify: `strategy6/engine.py`
- Modify: `strategy6/models.py`

- [ ] Add failing tests proving a true weak-market downgrade records `KEY_CANDIDATE` or `READY_CANDIDATE`, while a native watch candidate records no origin.
- [ ] Run the focused pytest tests and confirm failure because `pre_market_candidate_type` is absent.
- [ ] Add a side-effect-isolated pre-market classification helper and optional evaluation field.
- [ ] Run focused tests and confirm they pass without changing total score or final candidate type.

### Task 2: SQLite compatibility

**Files:**
- Modify: `tests/test_strategy6_db_api.py`
- Modify: `scanner/db.py`

- [ ] Add a failing round-trip test for `pre_market_candidate_type`.
- [ ] Run the focused test and confirm the column/value is absent.
- [ ] Add the nullable compatibility column and include it in Strategy6 upsert values.
- [ ] Run the focused test and confirm it passes.

### Task 3: Frontend explanation and export

**Files:**
- Modify: `web/src/pages/__tests__/Strategy6Results.test.js`
- Modify: `web/src/pages/Strategy6Results.vue`

- [ ] Add failing tests for list badge, detail explanation, CSV column and old-task fallback wording.
- [ ] Run the focused Vitest test and confirm the new text is absent.
- [ ] Add display helpers and render the exact origin without changing candidate grouping.
- [ ] Run focused frontend tests and confirm they pass.

### Task 4: Closed-loop verification

**Files:**
- Review all modified files from Tasks 1-3.

- [ ] Run Strategy6 backend tests, frontend Strategy6 tests, compileall and frontend build.
- [ ] Review the diff for compatibility, false strong-candidate labels and unrelated changes.
- [ ] Fix any medium/high finding and repeat verification.
- [ ] Stage only this feature's files, commit and push the current branch.

