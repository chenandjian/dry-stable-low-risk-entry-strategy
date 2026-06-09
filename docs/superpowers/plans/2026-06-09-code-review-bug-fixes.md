# Code Review Bug Fix Plan

Per `docs/reviews/2026-06-09-strategy-code-audit.md`, fix 8 high-severity bugs.
Priority order: BUG-002 → BUG-001 → BUG-003 → BUG-004 → BUG-005 → BUG-006 → BUG-007 → BUG-008.

---

## BUG-002: Market index uses wrong symbol

**Root cause:** `scanner/index_source.py:9` has `DEFAULT_MARKET_INDEX = "000001"`. Sina source maps non-6 codes to `sz{code}`, so `000001` becomes `sz000001` (平安银行), not `sh000001` (上证指数).

**Fix:**
1. `scanner/index_source.py`: Change `DEFAULT_MARKET_INDEX = "000001"` to `"sh000001"` and make `fetch_market_index_daily` directly call Sina with the correct symbol rather than passing through the stock-oriented `fetch_sina_daily`
2. OR: Extend `fetch_sina_daily` to accept optional `prefix` param (e.g., `prefix="sh"`) for index codes
3. Config: Add `market_index` to config.yaml under a new section for explicit control

**Test:** Mock Sina response, assert `fetch_market_index_daily()` requests `sh000001` not `sz000001`.

---

## BUG-001: RR1 always = 2.0 (fake pressure target)

**Root cause:** `analyzer/key_prices.py:71` sets `target_1 = current_price + 2 * risk`. Then `risk_reward.py` computes `rr1 = (target_1 - cp) / risk = 2.0` always.

**Fix:**
1. `analyzer/key_prices.py`: `target_1` should use pivot (杯口突破位) as the first target, not a constructed 2R
2. If pivot > current_price → `target_1 = pivot` (real resistance)
3. Fallback: use 2R only if no pivot available
4. `analyzer/decision.py`: `rr1 < min_rr1` now becomes a meaningful filter

**Test:** Set current=100, stop=95, pivot=106. RR1 should be 1.2 → WAIT_RR.

---

## BUG-003: ATR stop too close still allows BUY_LOW

**Root cause:** `analyzer/risk_reward.py:82-85` only adds warning text; `can_buy` still True. Decision module doesn't check `risk_reward.can_buy`.

**Fix:**
1. `analyzer/risk_reward.py`: When `risk_pct < atr14_pct * atr_stop_multiplier`, set `can_buy = False` and `risk_level = "高风险"`
2. `analyzer/decision.py`: Check `risk_reward.can_buy` before allowing BUY_LOW

**Test:** risk=2%, ATR14=3%, multiplier=1.2 → must NOT output BUY_LOW.

---

## BUG-004: Far below pivot still shows WATCH_BREAKOUT

**Root cause:** `analyzer/decision.py:99-100` checks `current <= pivot * 1.05` with no lower bound.

**Fix:**
1. Add lower bound: `current >= pivot * 0.85` (within 15% below pivot)
2. `near_pivot = pivot * 0.85 <= current <= pivot * 1.05`
3. Far below pivot → WAIT_ENTRY or WAIT_STABLE instead

**Test:** current=60, pivot=100 → near_pivot=False → NOT WATCH_BREAKOUT.

---

## BUG-005: Historical backtester uses different strategy than online

**Root cause:** `scanner/backtester.py` uses `score_cup_handle()` not `score_cup_handle_advanced()`, no config passing, no market data.

**Fix:**
1. Replace `scanner/backtester.py` pattern detection with `CupHandleStrategyEngine`
2. Pass actual config and market_data
3. Use actual stop_loss from strategy, not `breakout_price * 0.95`
4. Support VCP-only candidates

**Test:** Same date, same stock → backtester and online produce identical verdict/score/stop_loss.

---

## BUG-006: Single-stock backtest can't identify VCP-only

**Root cause:** `strategy_engine.py:106-116` returns early when cup_handle not found, without running VCP analysis.

**Fix:**
1. Move VCP-only analysis into `StrategyEngine.evaluate_at()` — don't early-return when cup not found
2. Remove duplicate VCP logic from `engine.py:235-241`
3. Single entry point for all scans and backtests

**Test:** `_make_vcp_data()` → backtest finds VCP pattern → scan finds same pattern.

---

## BUG-007: try_acquire_any ignores config priority

**Root cause:** `engine.py:_fetch_with_retry` uses `mgr.try_acquire_any()` which randomizes. No respect for source chain order.

**Fix:**
1. Replace `try_acquire_any()` with ordered iteration over source chain
2. Try each source in config order (baidu → sina → tencent)
3. Primary source uses `retry_attempts`, fallback sources use `fallback_attempts`
4. Track failed sources, don't retry them

**Test:** Config [baidu,sina,tencent] → baidu tried first, sina second, tencent third.

---

## BUG-008: Forward-adjust not unified across sources

**Root cause:** Tencent uses qfq param, Sina/Baidu don't explicitly request adjusted prices.

**Fix:**
1. Verify Sina and Baidu return qfq prices by default
2. If not, add qfq params where supported
3. Remove or implement `config.data.use_fq`
4. Add test comparing same stock across sources for price continuity

---

## Execution Order

1. BUG-002 (index) + BUG-001 (RR1) + BUG-003 (ATR) + BUG-004 (pivot) — core trading safety
2. BUG-005 (backtester) + BUG-006 (VCP) — strategy consistency
3. BUG-007 (source chain) + BUG-008 (复权) — data quality

## Verification

```bash
python -m pytest tests/ -v  # all new + existing tests pass
npm --prefix web run build   # frontend builds
```
