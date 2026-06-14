# Strategy1 Backtest Experiment Results and Optimization Decision

## 1. Status

Strategy1 trusted backtest and experiment capability is implemented and usable.

Formal Strategy1 scan parameters are not upgraded in this round.

Reason: the trusted baseline and comparable experiments show that stricter score filters can improve average return, but the improvement is not stable enough across months and often reduces opportunity count too sharply.

## 2. Trusted Baseline

- Task ID: `s1bt-20260614-250d-baseline`
- Requested evaluation range: `2026-03-01` to `2026-06-01`
- Actual evaluation range: `2026-03-02` to `2026-06-01`
- Data source: local SQLite only, `data/cuphandle.db`
- Backtest window: `data.backtest_window_days=250`
- Execution model: `NEXT_OPEN`
- Status: `completed`
- Credibility: `TRUSTED_BASELINE`
- Integrity check: passed
- Total stocks: `5527`
- Processed stocks: `5527`
- Failed stocks: `0`
- Insufficient stocks: `635`
- Raw signals: `819`
- Opportunities: `521`
- Entered opportunities: `515`
- Target count: `194`
- Stop count: `321`
- Target rate: `37.6699%`
- Stop rate: `62.3301%`
- Average realized return: `-0.8490%`
- Median realized return: `-2.7742%`

Pattern split:

| Pattern | Opportunities | Entered | Target | Stop |
| --- | ---: | ---: | ---: | ---: |
| cup_handle | 394 | 389 | 137 | 252 |
| vcp | 127 | 126 | 57 | 69 |

Monthly split:

| Month | Opportunities | Entered | Target | Stop | Average Return |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-03 | 169 | 168 | 47 | 121 | -1.7881% |
| 2026-04 | 206 | 201 | 108 | 93 | +0.8052% |
| 2026-05 | 145 | 145 | 39 | 106 | -2.0350% |
| 2026-06 | 1 | 1 | 0 | 1 | -3.5831% |

## 3. Important Correction

An intermediate fix incorrectly used `liquidity.min_listing_days` as the Strategy1 backtest evaluation gate. That made the user's temporary `350` setting invalidate the `2026-03-01` to `2026-06-01` evaluation range.

Correct rule:

- `liquidity.min_listing_days` controls scan fetch/listing-day semantics.
- Strategy1 local DB backtest evaluation uses `data.backtest_window_days`.
- A stock is insufficient for Strategy1 backtest only when its local history is shorter than `backtest_window_days`.

Code has been corrected so Strategy1 backtests use `backtest_window_days=250` for the local historical replay.

## 4. Comparable Experiments

All experiments below are derived from trusted baseline raw signals and have comparable data revision, date range, stock scope, strategy version, and execution model.

| Experiment | Task ID | Opportunities | Target Rate | Stop Rate | Avg Return | Decision |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `minimumTotalScore=70` | `s1bt-20260614-exp-score70` | 344 | 38.1381% | 61.5616% | -0.6526% | Better than baseline, still negative |
| `minimumTotalScore=80` | `s1bt-20260614-exp-score80` | 66 | 43.9394% | 56.0606% | +0.0839% | Best simple score filter, but sparse |
| `minVolumeDryScore=9` | `s1bt-20260614-exp-vol9` | 135 | 39.3939% | 60.6061% | -0.3985% | Improves, still negative |
| `minPriceStableScore=7` | `s1bt-20260614-exp-price7` | 71 | 42.2535% | 57.7465% | -0.1244% | Improves, still negative |
| `maxRiskPercent=6` | `s1bt-20260614-exp-risk6` | 448 | 36.2587% | 63.5104% | -0.8283% | Not useful |
| `minRr1=2.5` | `s1bt-20260614-exp-rr25` | 8 | 50.0000% | 50.0000% | +0.7484% | Too few samples |
| `score80 + price7` | `s1bt-20260614-exp-score80_price7` | 13 | 53.8462% | 46.1538% | +0.8934% | Too few samples |
| `score80 + timeExitDays=5` | `s1bt-20260614-exp-score80_time5` | 66 | 33.3333% | 48.4848% | +0.0609% | Lowers stop rate but reduces target rate |
| `score70 + timeExitDays=5` | `s1bt-20260614-exp-score70_time5` | 344 | 30.9309% | 53.4535% | -0.5404% | Improves drawdown, still negative |

## 5. Interpretation

Findings:

1. Baseline Strategy1 performance in this local snapshot is weak: high stop rate and negative average return.
2. Raising total score to 80 is the clearest positive single filter, but opportunity count drops from 521 to 66.
3. Combining high score with stricter price stability improves metrics but leaves only 13 opportunities, which is not enough for a formal scan rule.
4. `minRr1=2.5` produces positive average return, but only 8 opportunities, so it is diagnostic only.
5. Time exit reduces stop rate but also reduces target rate; it may be useful as reporting guidance, not yet as a formal exit rule.
6. March and May remain weak under most filters. The improvement is not broad enough across months.

## 6. Formal Strategy Decision

Do not upgrade formal Strategy1 scan parameters yet.

Specifically, do not change these production values in `config.yaml` in this round:

- `scoring.medium_threshold`
- `decision.min_volume_dry_score`
- `decision.min_price_stable_score`
- `decision.max_risk_percent`
- `decision.min_rr1`
- cup/handle hard filters

Rationale:

- Evidence does not yet satisfy the design document's formal upgrade requirement.
- The only clearly positive filters are either too sparse or unstable by month.
- Changing production scan rules now would risk hiding usable candidates without enough proof of better live behavior.

## 7. Recommended Next Experiments

Before formal Strategy1 upgrade, run at least one wider local dataset or a longer evaluation period with enough 250-day history.

Priority experiments:

1. `minimumTotalScore=80` on a longer date range.
2. `minimumTotalScore=80 + timeExitDays=5` as short-term guidance.
3. `minimumTotalScore=80 + minPriceStableScore=7`, but only if sample count becomes sufficient.
4. Month-by-month robustness check.
5. Separate analysis for cup_handle vs vcp opportunities.

Formal upgrade can be reconsidered only if:

- Opportunity count remains practical.
- Average return improves in most months, not just one.
- Stop rate decreases materially.
- Median return improves, not only average return.
- Comparable task integrity passes.

## 8. Handoff To Future AI

Use `s1bt-20260614-250d-baseline` as the current valid Strategy1 trusted baseline.

Ignore older Strategy1 baseline tasks created while the backtest used `min_listing_days=350` as the evaluation gate. Those tasks are not useful for optimization decisions.

Do not enable formal Strategy1 optimized parameters from the current experiment batch.
