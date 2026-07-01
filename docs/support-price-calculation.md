# Support Price Calculation Development Document

## 1. Document Goal

This document defines the development logic for calculating stock support price levels.

The support price module is used by:

```text
Extreme Volume Dry
Price Stability
Dry Cannot Fall
Cup and Handle
VCP
Low-risk Entry Evaluation
```

Core goal:

> Calculate the most important support price zones for a stock, then use them to judge whether price is holding, whether support has failed, and whether the stock still has low-risk observation value.

---

## 2. Core Principle

The system should not output only one fixed support price.

Wrong:

```text
support = 26.30
```

Correct:

```text
short support: 26.90 - 27.10
key support: 26.00 - 26.30
strong support: 25.50 - 25.80
```

Reason:

> Stock prices usually do not stop exactly at one price. A support zone is more practical than a single point.

---

## 3. Support Level Types

| Level | Field | Purpose |
|---|---|---|
| Short-term support | short_support | Judge short-term strength |
| Key support | key_support | Judge whether volume-dry and price-stable conditions are still valid |
| Strong support | strong_support | Judge whether the structure has fully failed |

---

## 4. Support Sources

Support should be calculated from multiple sources and then merged.

### 4.1 Recent Low Support

```text
low_5 = lowest low in recent 5 trading days
low_10 = lowest low in recent 10 trading days
low_20 = lowest low in recent 20 trading days
```

Applicable scenarios:

```text
short-term consolidation
volume-dry price-stable pattern
last contraction of VCP
handle area of Cup and Handle
```

---

### 4.2 Recent Lowest Close Support

Intraday lows may be false breakdowns. Closing prices are usually more important for support validation.

```text
min_close_5 = lowest close in recent 5 trading days
min_close_10 = lowest close in recent 10 trading days
min_close_20 = lowest close in recent 20 trading days
```

Recommendation:

> Key support should prefer the recent 10-day lowest close instead of the lowest intraday low.

---

### 4.3 Platform Low Support

If a stock is consolidating in a narrow range, identify the lower boundary of the platform.

```text
range_n = max(high, N days) / min(low, N days) - 1
```

Default parameters:

```text
N = 10 or 20
range_threshold = 8%
```

If:

```text
range_n <= 8%
```

Then the system can consider the stock to be in platform consolidation.

```text
platform_support = low cluster zone of recent N days
```

---

### 4.4 Support Test Count

The more times support is tested without breaking, the more reliable it is.

```text
support_test_count = number of days in recent N days where low <= support_price * (1 + tolerance)
```

Default parameters:

```text
N = 10
tolerance = 2%
```

Qualified condition:

```text
support_test_count >= 2
```

Strong support condition:

```text
support_test_count >= 3
```

---

### 4.5 Moving Average Support

```text
MA20 = average close of recent 20 trading days
MA50 = average close of recent 50 trading days
MA60 = average close of recent 60 trading days
```

| Moving Average | Meaning |
|---|---|
| MA20 | Short-to-mid-term trend support |
| MA50 | Mid-term trend defense line |
| MA60 | More stable trend support |

Judgment:

```text
If current price is above MA20, MA20 can be short-term support.
If price breaks MA20 but remains above MA50, MA50 can be key support.
If price breaks MA50 and MA50 turns downward, reduce score or reject.
```

---

### 4.6 Breakout Retest Support

If the stock previously broke through a platform or previous high, the old resistance may become support.

```text
breakout_level = previous platform high / previous swing high
```

If after breakout:

```text
low <= breakout_level * 1.03
and
close >= breakout_level
```

Then:

```text
previous resistance becomes support
```

Applicable scenarios:

```text
breakout retest
Cup and Handle breakout retest
VCP breakout retest
```

---

### 4.7 Volume Profile Support

If enough historical volume data is available, calculate volume-concentration zones.

Method:

1. Take the recent 60-day price range.
2. Split the price range into bins.
3. Assign daily volume to the matching price bin.
4. Find the price zone with the highest accumulated volume.

Simplified parameter:

```text
price_bin_size = current_price * 1%
```

Output:

```text
volume_support_zone = price zone with the highest accumulated volume
```

---

## 5. Support Candidate Generation

The system should first generate multiple support candidates.

```text
support_candidates = [
    min_close_5,
    min_close_10,
    min_close_20,
    low_5,
    low_10,
    low_20,
    MA20,
    MA50,
    MA60,
    platform_low,
    breakout_retest_level,
    volume_profile_zone
]
```

Each candidate must record its source.

```json
{
  "price": 26.30,
  "source": "min_close_10",
  "weight": 0
}
```

---

## 6. Support Candidate Scoring

Each support candidate should be scored.

Total score:

```text
100 points
```

### 6.1 Touch Count: 30 Points

| Condition | Score |
|---|---:|
| Touched once in recent 10 days | 10 |
| Touched twice in recent 10 days | 20 |
| Touched 3 or more times in recent 10 days | 30 |

Touch definition:

```text
low <= support_price * 1.02
and
close >= support_price * 0.98
```

---

### 6.2 No Closing Breakdown: 25 Points

| Condition | Score |
|---|---:|
| No close below support in recent 5 days | 10 |
| No close below support in recent 10 days | 10 |
| Price recovers after testing support | 5 |

Effective breakdown definition:

```text
close < support_price * 0.98
```

---

### 6.3 Reasonable Distance From Current Price: 15 Points

```text
distance = (current_close - support_price) / current_close
```

| Condition | Score |
|---|---:|
| 0% <= distance <= 3% | 15 |
| 3% < distance <= 6% | 10 |
| 6% < distance <= 10% | 5 |
| distance > 10% | 0 |

---

### 6.4 Overlap With Moving Average Or Platform: 15 Points

| Condition | Score |
|---|---:|
| Near MA20 | 5 |
| Near MA50 | 5 |
| Near platform low | 5 |

Near definition:

```text
abs(candidate_price - reference_price) / reference_price <= 2%
```

---

### 6.5 Volume Confirmation: 15 Points

| Condition | Score |
|---|---:|
| Volume shrinks when testing support | 5 |
| Volume expands on rebound after support test | 5 |
| No high-volume breakdown near support | 5 |

High-volume breakdown definition:

```text
single_day_return <= -4%
and
volume >= V20 * 1.3
```

---

## 7. Support Merge Rules

Different algorithms may produce very close support prices. These should be merged into one support zone.

### 7.1 Merge Tolerance

```text
merge_tolerance = max(current_price * 1.5%, ATR14 * 0.5)
```

If two support prices satisfy:

```text
abs(price_a - price_b) <= merge_tolerance
```

Then merge them into one support zone.

---

### 7.2 Merged Support Price

```text
support_price = sum(price * score) / sum(score)
```

---

### 7.3 Support Zone

Normal volatility:

```text
support_zone_low = support_price * 0.99
support_zone_high = support_price * 1.01
```

High volatility:

```text
support_zone_low = support_price - ATR14 * 0.3
support_zone_high = support_price + ATR14 * 0.3
```

---

## 8. Three-Level Support Calculation

### 8.1 Short-Term Support

Purpose:

```text
judge short-term strength
```

Priority sources:

```text
1. recent 5-day lowest close
2. recent 5-day low cluster
3. MA20
```

---

### 8.2 Key Support

Purpose:

```text
judge whether volume-dry price-stable pattern is valid
judge whether dry-cannot-fall condition is valid
judge whether the structure is broken
```

Priority sources:

```text
1. recent 10-day lowest close
2. recent 10-day low cluster
3. last contraction low of VCP
4. handle low of Cup and Handle
5. MA20 / MA50 overlapping zone
```

This is the most important support level.

Strategy judgment:

```text
current_close >= key_support
```

If broken:

```text
volume-dry price-stable condition fails
dry-cannot-fall condition fails
```

---

### 8.3 Strong Support

Purpose:

```text
judge whether the whole pattern has fully failed
```

Priority sources:

```text
1. recent 20-day lowest close
2. recent 20-day lowest low
3. MA50
4. MA60
5. previous major platform low
```

If strong support is broken:

```text
the structure is basically damaged
do not use volume-dry price-stable strategy anymore
```

---

## 9. Effective Breakdown Rules

Do not judge only by intraday breakdown. Focus on closing breakdown.

### 9.1 Normal Breakdown

```text
close < support_zone_low
```

### 9.2 Effective Breakdown

Any of the following conditions means an effective breakdown:

```text
two consecutive closes < support_zone_low
```

or:

```text
single close < support_zone_low
and
volume >= V20 * 1.3
```

or:

```text
single_day_return <= -4%
and
close < support_zone_low
```

---

## 10. Valid Support Rules

Support is valid when:

```text
low touches or approaches support_zone
and
close recovers above support_zone
```

Detailed condition:

```text
low <= support_zone_high
and
close >= support_zone_low
```

Stronger condition:

```text
low <= support_zone_high
and
close >= support_price
```

If there is a long lower shadow:

```text
lower_shadow_ratio >= 0.4
```

Then increase the support validity score.

---

## 11. Output Fields

```json
{
  "stock_code": "000921",
  "stock_name": "example stock",
  "current_close": 27.10,
  "short_support": {
    "price": 26.90,
    "zone_low": 26.70,
    "zone_high": 27.10,
    "score": 78,
    "sources": ["min_close_5", "low_cluster_5"]
  },
  "key_support": {
    "price": 26.20,
    "zone_low": 26.00,
    "zone_high": 26.30,
    "score": 86,
    "sources": ["min_close_10", "support_test", "platform_low"]
  },
  "strong_support": {
    "price": 25.60,
    "zone_low": 25.40,
    "zone_high": 25.80,
    "score": 82,
    "sources": ["min_close_20", "MA50"]
  },
  "support_status": "VALID",
  "break_status": "NOT_BROKEN",
  "support_test_count": 3,
  "nearest_support_distance": 0.033,
  "reject_reason": []
}
```

---

## 12. Support Status Definition

| Status | Meaning |
|---|---|
| VALID | Support is valid |
| TESTING | Price is testing support |
| WEAKENING | Support is weakening |
| BROKEN | Support is broken |
| FAILED | Support has effectively failed |

---

## 13. Status Judgment Logic

### 13.1 VALID

```text
current_close >= key_support.zone_high
```

### 13.2 TESTING

```text
key_support.zone_low <= current_close <= key_support.zone_high
```

### 13.3 WEAKENING

```text
current_close < key_support.zone_low
but
not two consecutive closes below support
and
no high-volume breakdown
```

### 13.4 BROKEN

```text
current_close < key_support.zone_low
```

### 13.5 FAILED

```text
two consecutive closes below key_support.zone_low
```

or:

```text
break below key_support.zone_low
and
volume >= V20 * 1.3
```

---

## 14. Pseudocode

```python
def calculate_support_levels(stock, data, config):
    if len(data) < config["min_data_days"]:
        return reject("insufficient data")

    current_close = data[-1]["close"]
    indicators = calculate_indicators(data)

    candidates = []
    candidates += build_recent_low_candidates(data)
    candidates += build_min_close_candidates(data)
    candidates += build_ma_candidates(data)
    candidates += build_platform_candidates(data)
    candidates += build_breakout_retest_candidates(data)

    if config["enable_volume_profile"]:
        candidates += build_volume_profile_candidates(data)

    scored_candidates = []

    for candidate in candidates:
        score = score_support_candidate(
            candidate=candidate,
            data=data,
            indicators=indicators,
            current_close=current_close
        )
        candidate["score"] = score
        scored_candidates.append(candidate)

    merged_supports = merge_nearby_supports(
        candidates=scored_candidates,
        tolerance=max(current_close * 0.015, indicators["ATR14"] * 0.5)
    )

    sorted_supports = sorted(
        merged_supports,
        key=lambda x: x["score"],
        reverse=True
    )

    short_support = select_short_support(sorted_supports, data, indicators)
    key_support = select_key_support(sorted_supports, data, indicators)
    strong_support = select_strong_support(sorted_supports, data, indicators)

    support_status = calculate_support_status(
        current_close=current_close,
        key_support=key_support,
        data=data,
        indicators=indicators
    )

    return {
        "stock_code": stock.code,
        "stock_name": stock.name,
        "current_close": current_close,
        "short_support": short_support,
        "key_support": key_support,
        "strong_support": strong_support,
        "support_status": support_status,
        "support_test_count": count_support_tests(data, key_support),
        "nearest_support_distance": calculate_nearest_support_distance(
            current_close,
            key_support
        ),
        "reject_reason": []
    }
```

---

## 15. Module Design

```text
analyzer/
  support/
    support_levels.py        # main support calculation entrance
    support_candidates.py    # support candidate generation
    support_score.py         # support scoring
    support_merge.py         # support merge logic
    support_status.py        # support status judgment
    volume_profile.py        # optional volume profile logic
```

---

## 16. Config Suggestions

```json
{
  "min_data_days": 60,
  "short_support_days": 5,
  "key_support_days": 10,
  "strong_support_days": 20,
  "support_touch_tolerance": 0.02,
  "support_break_tolerance": 0.98,
  "merge_tolerance_pct": 0.015,
  "platform_range_threshold": 0.08,
  "valid_break_days": 2,
  "big_down_return": -0.04,
  "big_down_volume_ratio": 1.3,
  "enable_volume_profile": true,
  "volume_profile_days": 60,
  "volume_profile_bin_pct": 0.01
}
```

---

## 17. Unit Test Requirements

### 17.1 Valid Support

Input:

```text
current_close > key_support.zone_high
support tested multiple times in recent 10 days
no high-volume breakdown
```

Expected:

```text
support_status = VALID
```

---

### 17.2 Testing Support

Input:

```text
key_support.zone_low <= current_close <= key_support.zone_high
```

Expected:

```text
support_status = TESTING
```

---

### 17.3 Weakening Support

Input:

```text
current_close < key_support.zone_low
but not two consecutive closes below support
and no volume expansion
```

Expected:

```text
support_status = WEAKENING
```

---

### 17.4 Failed Support

Input:

```text
two consecutive closes < key_support.zone_low
```

Expected:

```text
support_status = FAILED
```

---

### 17.5 High-Volume Breakdown

Input:

```text
current_close < key_support.zone_low
and
volume >= V20 * 1.3
```

Expected:

```text
support_status = FAILED
```

---

## 18. Development Notes

### 18.1 Support Must Be A Zone

Do not output only a single price.

Correct output:

```text
26.00 - 26.30
```

---

### 18.2 Closing Price Is More Important Than Intraday Low

An intraday breakdown does not always mean support failure.

Prioritize:

```text
whether the stock closes below support
```

---

### 18.3 Support Needs Multi-Source Confirmation

Strong support is usually created by multiple overlapping factors:

```text
recent low
lowest close
moving average
platform low
volume profile
```

---

### 18.4 Support Must Serve The Strategy

For volume-dry price-stable strategies, the most important field is:

```text
key_support
```

If price breaks key_support, the system should not continue to mark the stock as:

```text
dry cannot fall
```

---

## 19. Final Summary

The core of support calculation is not to find an absolutely precise price.

The real goal is to find:

```text
the zone where price repeatedly fails to fall further
```

Final output:

```text
short support: judge short-term strength
key support: judge whether volume-dry price-stable condition is valid
strong support: judge whether the full structure has failed
```

One sentence:

> Support is not a point. It is the zone where price cannot fall further.
