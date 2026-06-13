# Code Review Bug Fix Plan (Revised)

> 修订依据: `docs/reviews/2026-06-09-bug-fix-plan-review.md`
> 原始问题来源: `docs/reviews/2026-06-09-strategy-code-audit.md`
> v2: 按 8 项强制审核意见全面修订

---

## Phase 1: Core Trading Safety

### BUG-002: Market index uses wrong symbol

**Root cause:** `scanner/index_source.py:9` `DEFAULT_MARKET_INDEX = "000001"` → `sina_source.py` non-6 codes mapped to `sz{code}` → `sz000001` = 平安银行, not 上证指数.

**Fix:**
1. Create dedicated `fetch_sina_index_daily(symbol, days)` in index_source.py — does NOT go through stock code mapping
2. Use symbol `sh000001` as default
3. Add config `market_environment.index_symbol: sh000001`
4. On fetch failure → return None → `assess_market_environment()` defaults to "一般"

**Tests:**
- Mock assert request uses `sh000001` not `sz000001`
- Fetch failure → returns "一般"

---

### BUG-001: Real RR1 from real resistance (not fake 2R)

**Root cause:** `analyzer/key_prices.py:71` sets `target_1 = current_price + 2 * risk`. `risk_reward.py` computes `rr1 = 2.0` always.

**Fix (per PLAN-002):**
1. Add `find_real_target(data, cp)` to key_prices.py:
   - Priority: ① pivot > cp → pivot, ② recent_high > cp → that high, ③ platform top
   - If NO real target above cp → `target_1_real = None`
2. `rr1 = (target_1_real - cp) / risk` if target_1_real exists, else `rr1 = 0`
3. **NEVER** fall back to 2R for RR1 — no fake targets
4. Already broke above pivot → pivot is support, not target; find NEXT resistance
5. No real target → `rr1 < min_rr1` → `WAIT_RR`, forbid BUY_LOW

**Tests:**
- cp=100, stop=95, pivot=106 above → rr1=1.2 → WAIT_RR
- cp=110, stop=105, pivot=100 (broken) → must find higher resistance
- No real resistance → rr1=0 → WAIT_RR

---

### BUG-003: ATR stop-too-close blocks BUY_LOW with structured state

**Root cause:** ATR check only adds warning text; `can_buy` unaffected; overridden later.

**Fix (per PLAN-003):**
1. Add `RiskRewardResult.stop_too_close: bool = False`
2. Set `r.stop_too_close = True` when `risk_pct < atr14_pct * atr_stop_multiplier`
3. In `all_good` check: `not r.stop_too_close and ...`
4. `stop_too_close=True` → `WAIT_ENTRY`, forbid `BUY_LOW`
5. Does NOT just set `can_buy=False` (which gets overridden)

**Tests:**
- risk=2%, ATR14=3%, mult=1.2 → stop_too_close=True → WAIT_ENTRY
- Normal risk → behaves as before

---

### BUG-004: Pivot distance has both upper and lower bounds

**Root cause:** `near_pivot = current <= pivot * 1.05` with no lower bound.

**Fix (per PLAN-007):**
1. Add config:
```yaml
decision:
  chase_threshold_pct: 5     # existing
  near_pivot_below_pct: 10   # new: max % below pivot to be "near"
```
2. `near_pivot = pivot>0 and current >= pivot*(1 - below_pct/100) and current <= pivot*(1 + chase_pct/100)`
3. Current > pivot*(1+chase_pct) → `is_chasing=True` → REJECT
4. Current < pivot*(1-below_pct/100) and not in entry zone → `WAIT_ENTRY`

**Tests:**
- cp=60, pivot=100 → near_pivot=False → NOT WATCH_BREAKOUT
- cp=95, pivot=100 → near_pivot=True → WATCH_BREAKOUT

---

## Phase 2: Unified Strategy Engine

### BUG-006: VCP-only into unified engine (done before BUG-005)

**Root cause:** `engine.py:235-241` has extra VCP logic outside engine. `strategy_engine.py` returns early on not-found.

**Fix (per PLAN-004):**
1. Remove early-return; always run `analyze_dry_stable`
2. Add `pattern_kind: "cup_handle" | "vcp"` to CupHandleResult
3. VCP score → `score * 5` for 0-100 (existing logic)
4. VCP identity: `vcp-{code}-{contraction_dates}` — NOT using cup dates
5. `_candidate_rules` checks `pattern_kind` for correct scoring
6. Remove duplicate VCP logic from `engine.py:235-241`
7. Single entry for scan, re-eval, backtest, single-backtest

**Tests:**
- VCP-only passes engine and becomes candidate
- Scan and backtest same VCP conclusions
- Two VCPs not deduped by empty cup dates

---

### BUG-005: Historical backtester uses unified engine

**Root cause:** Uses `score_cup_handle()` not `score_cup_handle_advanced()`, no config, no market data.

**Fix (per PLAN-001):**
1. Replace with `CupHandleStrategyEngine`
2. Pass actual config and actual stop_loss
3. **Market data per-date:** slice market_data to only rows ≤ current eval date
   ```python
   detect_date = window[-1]["date"]
   market_window = [r for r in market_data if r["date"] <= detect_date]
   ```
4. Support VCP-only via unified engine (BUG-006 must be done first)
5. Record real verdict_key, entry_zone, stop_loss

**Tests:**
- Future market crash doesn't affect past evaluation
- Same date → backtester and online identical verdict/score

---

## Phase 3: Data Quality

### BUG-007: Respect source chain order and retry semantics

**Root cause:** `try_acquire_any()` randomizes, ignoring config priority.

**Fix (per PLAN-005):**
1. Replace `try_acquire_any()` with ordered iteration over `source_chain`
2. State per source: `not_tried → busy → failed → succeeded`
3. For each source in config order:
   - `mgr.acquire(ds_name)` non-blocking
   - Lock acquired → fetch with `retry_attempts`(primary) or `fallback_attempts`(fallback)
   - Lock busy → mark `busy`, continue (NOT failed)
   - Fetch success → mark `succeeded`, return
   - Fetch failure → mark `failed`, continue
4. All busy → `data source busy` → scan requeue
5. All failed → None (no cache fallback)
6. `finally` always releases lock

**Tests:**
- Config [baidu,sina,tencent] → order respected
- Busy skipped, next tried
- All busy → requeue not permanent fail
- Failed not retried in same fetch
- Fallback uses `fallback_attempts`

---

### BUG-008: Unified forward-adjusted prices

**Fix (per PLAN-008):**
Investigation first (Phase 1), implementation after:
1. Verify each source's output adjustment type
2. If not adjusted → add qfq where supported
3. Cache: clear old OHLC on deploy to avoid mixed-adjustment data

**Tests:**
- Cross-source price continuity for ex-dividend stock
- Different adjustment data not silently merged

---

## Execution Order (per review)

| Phase | Bugs | Dependency |
|-------|------|------------|
| 1. Core Safety | 002 → 001 → 003 → 004 | None |
| 2. Unified Engine | 006 → 005 | BUG-006 before 005 |
| 3. Data Quality | 007 → 008 | None |

Each bug: write failing test → implement fix → verify.

## Final Verification

```bash
python -m pytest tests/ -v    # all pass
npm --prefix web run build     # frontend builds
```
