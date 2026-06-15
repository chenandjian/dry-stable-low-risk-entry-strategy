# Strategy1 Quality Tags and Layered Display Design

## 1. Goal

Add Strategy1 quality tags and layered display for backtest opportunities.

This is a low-risk optimization step: it highlights historically stronger opportunity types without changing Strategy1 scan admission rules or formal production parameters.

## 2. Background

The 500-day local-history experiment found that simple hard filters are not safe enough:

- `score>=80` underperformed on the wider sample.
- `price_stable_score>=7` improved quality but reduced opportunities from `1844` to `205`.
- `WATCH_BREAKOUT` had strong results but only `17` opportunities.
- `timeExitDays=5` reduced stop-rate optics but also reduced target rate.

Therefore the next step is not a hard filter. It is quality tiering and display.

## 3. Scope

In scope:

- Add deterministic Strategy1 quality tag generation.
- Attach quality tags to Strategy1 backtest opportunities.
- Add grouped summary counts by quality tag.
- Show tags and layers on `Strategy1Backtest.vue`.
- Keep API backward compatible.

Out of scope:

- No change to `CupHandleStrategyEngine.evaluate_at()` candidate admission.
- No change to `config.yaml` production strategy parameters.
- No change to Strategy2.
- No database destructive migration.
- No candidate-table hard-filter rollout in this phase.

## 4. Quality Tags

Tags are generated from the first signal of an opportunity, because the first signal is the opportunity's initial actionable observation.

| Tag | Rule | Layer | Purpose |
| --- | --- | --- | --- |
| `PRICE_STABLE_EXTREME` | `price_stable_score >= 8` | `premium` | Very stable price behavior, sparse but high interest |
| `PRICE_STABLE_STRONG` | `price_stable_score >= 7` | `strong` | Historically better quality group |
| `BREAKOUT_OBSERVE` | `verdict_key == WATCH_BREAKOUT` | `watch` | Low-frequency breakout observation group |
| `SHORT_TERM_RISK_CONTROL` | opportunity has valid 5-day horizon or `TIME_EXIT` diagnostic | `risk_control` | Candidate has short-term risk-control diagnostics |

If both `PRICE_STABLE_EXTREME` and `PRICE_STABLE_STRONG` match, only `PRICE_STABLE_EXTREME` is emitted.

## 5. Data Model

Extend `Strategy1BacktestOpportunity` with non-breaking fields:

- `volume_dry_score: int`
- `price_stable_score: int`
- `verdict_key: str`
- `quality_tags: list[str]`
- `quality_layer: str`
- `short_term_exit_note: str`

Persist optional columns in `strategy1_backtest_opportunities` with compatible migration:

- `volume_dry_score INTEGER DEFAULT 0`
- `price_stable_score INTEGER DEFAULT 0`
- `verdict_key TEXT`
- `quality_tags TEXT`
- `quality_layer TEXT`
- `short_term_exit_note TEXT`

`quality_tags` is stored as JSON text.

Old rows without columns remain readable; missing tags are calculated on read when possible.

## 6. Backend Flow

1. `scanner/strategy1_quality.py` provides pure helpers:
   - `build_strategy1_quality_tags(...)`
   - `build_strategy1_quality_layer(tags)`
   - `build_strategy1_short_term_exit_note(opportunity)`
2. `_opportunity_from_signal()` copies signal scores and verdict into the opportunity.
3. `_extend_opportunity()` keeps the first-signal quality fields stable; later signals may update score/stop but not the first-signal tag basis.
4. Before persistence, opportunities receive tags, layer, and short-term note.
5. `get_strategy1_backtest_opportunities()` returns these fields.
6. `build_strategy1_backtest_summary()` adds `by_quality_tag`.

## 7. Frontend Flow

`Strategy1Backtest.vue` displays:

- Quality summary chips from `summary.by_quality_tag`.
- Opportunity row fields:
  - code
  - first detected date
  - exit reason
  - quality tags
  - quality layer
  - price stable score
  - volume dry score
  - verdict key

The page does not hide opportunities without tags.

## 8. Compatibility

- Existing API clients can ignore new fields.
- Existing DBs migrate with `_ensure_column()`.
- Existing baseline tasks can be read. New rows get persisted tags; old rows can still display no tags or read-time reconstructed tags if enough fields exist.
- No external data calls are introduced.

## 9. Tests

Backend:

- Tag helper emits expected tags and layer.
- Opportunity persistence round-trips quality fields.
- Summary groups by quality tag.
- Strategy1 backtest replay attaches tags from first signal.

Frontend:

- Strategy1 backtest page renders quality tags and score fields.
- Quality summary groups appear when summary has `by_quality_tag`.

Regression:

- Existing Strategy1 backtest DB/API tests still pass.
- Existing Strategy1 replay tests still pass.
- Existing frontend tests still pass.

## 10. Self-Check

- Placeholder scan: no TODO or undefined placeholder remains.
- Scope check: this design is one bounded feature, not a formal strategy-parameter upgrade.
- Consistency check: tags are generated from first signal, persisted on opportunity, summarized by DB, and displayed by frontend.
- Safety check: production scan admission and Strategy2 are not modified.
