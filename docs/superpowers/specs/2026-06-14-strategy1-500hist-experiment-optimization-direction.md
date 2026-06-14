# Strategy1 500-Day History Experiment Optimization Direction

## 1. Context

The local market-data snapshot was expanded to about 500 trading rows for most stocks.

Data snapshot:

- Local DB: `data/cuphandle.db`
- Daily range: `2024-03-18` to `2026-06-12`
- OHLC rows: `2444267`
- Stocks with OHLC: `4976`
- Stocks with at least 500 rows: `4804`
- Strategy1 backtest evaluation window: `data.backtest_window_days=250`
- No external data source was used.

`liquidity.min_listing_days=500` is a scan/listing-day setting. Strategy1 local DB backtest still evaluates with `backtest_window_days=250`.

## 2. New Trusted Baseline

- Task ID: `s1bt-20260614-500hist-250w-baseline`
- Requested evaluation range: `2025-09-01` to `2026-05-15`
- Actual evaluation range: `2025-09-01` to `2026-05-15`
- Observation data end: `2026-06-12`
- Status: `completed`
- Credibility: `TRUSTED_BASELINE`
- Integrity check: passed
- Total stocks: `5527`
- Processed stocks: `5527`
- Failed stocks: `0`
- Insufficient stocks: `635`
- Raw signals: `3282`
- Opportunities: `1844`
- Entered: `1823`
- Target count: `811`
- Stop count: `988`
- Target rate: `44.4871%`
- Stop rate: `54.1964%`
- Average realized return: `+0.3190%`
- Median realized return: `-2.2371%`

Pattern split:

| Pattern | Opportunities | Entered | Target | Stop | Avg Return |
| --- | ---: | ---: | ---: | ---: | ---: |
| cup_handle | 1438 | 1422 | 607 | 795 | +0.2328% |
| vcp | 406 | 401 | 204 | 193 | +0.6244% |

Monthly split:

| Month | Opportunities | Entered | Target | Stop | Avg Return |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2025-09 | 257 | 256 | 92 | 159 | +1.9260% |
| 2025-10 | 145 | 136 | 76 | 56 | +0.8188% |
| 2025-11 | 257 | 255 | 79 | 173 | -1.1816% |
| 2025-12 | 237 | 237 | 127 | 100 | +0.8970% |
| 2026-01 | 221 | 219 | 111 | 107 | +0.3748% |
| 2026-02 | 321 | 320 | 158 | 161 | +0.4470% |
| 2026-03 | 142 | 141 | 40 | 101 | -1.8753% |
| 2026-04 | 203 | 198 | 106 | 92 | +0.7553% |
| 2026-05 | 61 | 61 | 22 | 39 | -0.7292% |

## 3. Experiment Results

All tasks below were derived from `s1bt-20260614-500hist-250w-baseline` and were comparable to the baseline.

| Experiment | Task ID | Opportunities | Target Rate | Stop Rate | Avg Return | Median Return | Read |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `score>=70` | `s1bt-20260614-500hist-exp-score70` | 1122 | 43.2327% | 55.5015% | -0.0978% | -2.1352% | Worse than baseline |
| `score>=75` | `s1bt-20260614-500hist-exp-score75` | 702 | 43.0285% | 55.7721% | +0.0114% | -2.2124% | Worse than baseline |
| `score>=80` | `s1bt-20260614-500hist-exp-score80` | 283 | 37.5451% | 61.0108% | -0.3158% | -2.3927% | Not stable, reject as hard filter |
| `volumeDry>=9` | `s1bt-20260614-500hist-exp-vol9` | 512 | 41.0204% | 58.1633% | -0.3025% | -2.3972% | Worse |
| `priceStable>=7` | `s1bt-20260614-500hist-exp-price7` | 205 | 47.2906% | 52.7094% | +0.4017% | -1.6398% | Slightly better quality, sparse |
| `priceStable>=8` | `s1bt-20260614-500hist-exp-price8` | 51 | 45.0980% | 54.9020% | +0.3243% | -1.8498% | Too sparse |
| `rr1>=2.5` | `s1bt-20260614-500hist-exp-rr25` | 47 | 54.5455% | 40.9091% | +0.3826% | +5.0000% | Too sparse, diagnostic only |
| `score80 + price7` | `s1bt-20260614-500hist-exp-score80_price7` | 41 | 43.9024% | 56.0976% | +0.2709% | -1.9940% | Too sparse |
| `score70 + timeExit5` | `s1bt-20260614-500hist-exp-score70_time5` | 1122 | 33.0088% | 43.6222% | +0.0271% | -1.1000% | Lower stop, weaker target |
| `price7 + timeExit5` | `s1bt-20260614-500hist-exp-price7_time5` | 205 | 34.9754% | 44.8276% | +0.2256% | -1.0695% | Good risk control, sparse |
| `WATCH_BREAKOUT only` | `s1bt-20260614-500hist-exp-watch_only` | 17 | 58.8235% | 41.1765% | +0.4961% | +5.0000% | Too few opportunities |

## 4. Optimization Direction Found

The 500-day history changed the conclusion from the earlier short snapshot.

Rejected direction:

- `score>=80` should not be promoted as a hard filter.
- It looked promising in the shorter 2026-03 to 2026-06 slice, but over the wider 2025-09 to 2026-05 baseline it underperforms the baseline.

Promising but not yet formal hard filters:

1. `price_stable_score >= 7`
   - Improves target rate from `44.4871%` to `47.2906%`.
   - Improves median return from `-2.2371%` to `-1.6398%`.
   - Keeps only 205 opportunities, so it is better as a quality tier than as a hard production filter.

2. `price_stable_score >= 7 + timeExitDays=5`
   - Reduces stop rate from `54.1964%` to `44.8276%`.
   - Median return improves to `-1.0695%`.
   - Target rate drops, so this should be a short-term risk-control guide, not a scan hard rule.

3. `WATCH_BREAKOUT`
   - Has strong metrics but only 17 opportunities.
   - Good candidate for a separate high-conviction tag, not enough for a formal filter.

4. `rr1 >= 2.5`
   - Metrics are attractive, but only 47 opportunities.
   - Existing RR1 distribution is unusual because many `RR<1` opportunities still perform decently. Treat RR1 as diagnostic until the target/stop model is reviewed.

## 5. Suggested Core Indicator Upgrade

Do not add a new hard filter yet.

Add or expose quality tiers instead:

| Tier | Rule | Meaning |
| --- | --- | --- |
| `PRICE_STABLE_STRONG` | `price_stable_score >= 7` | Better historical quality, should be highlighted |
| `PRICE_STABLE_EXTREME` | `price_stable_score >= 8` | Very stable but sparse |
| `BREAKOUT_OBSERVE` | `verdict_key == WATCH_BREAKOUT` | Strong but low-frequency observation group |
| `SHORT_TERM_RISK_CONTROL` | `timeExitDays=5` simulation available | Use as risk-control guidance, not entry rule |

These tiers can become frontend/result labels first. They should not silently remove candidates from the scanner.

## 6. Formal Strategy Decision

Formal Strategy1 scan parameters should not be changed in this round.

Reasons:

- Baseline already has positive average return over the wider sample.
- Score filters are not stable across the wider sample.
- The strongest quality indicators are too sparse for hard filtering.
- Median return remains negative under almost every experiment, so the optimization problem is not solved by a simple threshold.

## 7. Next Development Recommendation

The next useful development is not another simple threshold. It is adding Strategy1 candidate quality labels and grouped reporting:

1. Persist or expose `price_stable_score`, `volume_dry_score`, `verdict_key`, score band, and optional 5-day time-exit diagnostics on Strategy1 opportunities/results.
2. Show `PRICE_STABLE_STRONG` and `BREAKOUT_OBSERVE` as labels in the Strategy1 backtest page and candidate detail.
3. Run a second experiment after labels exist to compare manual selection behavior without changing scan recall.

This keeps recall broad while surfacing the most promising quality signals.
