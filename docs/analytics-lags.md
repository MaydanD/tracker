# Stage 7D — Lag Analysis contract (7D.1)

Read-only descriptive associations between one explicitly selected X/Y pair at
calendar offsets. There is no winner, ranking, prediction, recommendation,
automatic insight, causal inference or analytics UI. Adjacent observations may
be autocorrelated: coefficients are not causal effects, and the effective amount
of independent information can be smaller than `n`. No time-series adjustment,
significance testing or multiple-comparison correction is performed.

## API and bounds

`GET /api/analytics/lags?start=2026-09-01&end=2026-09-30&x=state.sleep_minutes&y=state.mood&lag=1`

Required: inclusive calendar `start`, `end`, two distinct canonical variable keys
`x`, `y` (at most 160 characters each). Choose one selector:

| Query | Meaning |
| --- | --- |
| `lag=1` | One offset |
| `lags=-7&lags=-1&lags=0&lags=1&lags=7` | Explicit list |
| `lag_start=-7&lag_end=7` | Inclusive integer range |
| No selector | `lag=0` |

Selectors cannot be combined; both range endpoints are required. Maximum absolute
lag is **7**, in days or weeks according to the canonical grain. Maximum list
length is **15 before deduplication**. Results are deduplicated and sorted by
ascending integer lag, never by coefficient. The target period is at most
**1830 days**, reusing the Stage 7C policy. Invalid dates, keys, duplicate X/Y,
offsets, selectors and out-of-calendar shifts return localized HTTP 422.
There is no variables × variables × lags matrix endpoint.

The service is `app.services.lags.get_lags(session, start, end, x, y, lags,
today=...)`; it uses the injected calendar clock. No timezone conversion or UTC
timestamp arithmetic is involved.

## Direction and period

**Requested start/end always belongs to Y. Positive lag means X earlier than Y.**

| Daily lag | Pair for Y on September 10 |
| --- | --- |
| `-1` | X September 11 ↔ Y September 10 |
| `0` | X September 10 ↔ Y September 10 |
| `+1` | X September 9 ↔ Y September 10 |

Formally `X(Y.date - lag × unit) ↔ Y(Y.date)`. Ordering of X and Y is preserved;
swapping them while keeping the same target period is a different request.

Daily unit is one **calendar day**. Weekly unit is one **calendar week**, joined
by Stage 7A/7B Monday `week_start` identities, including ISO week 52/53 and year
boundaries. For Y week starting January 4, 2021, lag +1 selects X week starting
December 28, 2020 (ISO 2020-W53). Weekly observations are not repeated over seven
daily rows. The weekly target includes weeks intersecting the requested dates,
with partial edge weeks retained in coverage and excluded from coefficients.

Daily and weekly variables cannot be mixed directly: the existing typed Stage
7C equivalent is `status=unsupported`, `reason=grain_mismatch`. Such results have
null grain, lag unit, X period, method and coverage, `n=0` and no coefficients.
No implicit aggregation is introduced. Explicit canonical weekly State variables
(`weekly.state.*`) remain available.

## Required source range

For target `[start, end]`, lag set L and unit size U (1 or 7 calendar days), load:

```text
source_start = start - max(0, max(L)) × U
source_end   = end   - min(0, min(L)) × U
```

Thus September 1–30 with daily +7 loads August 25–September 30, with -7 loads
September 1–October 7, and a scan containing both loads August 25–October 7.
Each result still refers to Y September 1–30. No first or last target dates are
lost just because X lies outside the target period. The X window for an individual
lag is the whole target window shifted by `-lag × U`.

`source_range` reports the actual canonical dataset range. Stage 7A loads habit
entries over enclosing calendar weeks for Stage 4 quota semantics, exposed as
`habit_entry_source_range`. State loading is capped at today by Stage 7A; calendar
slots after today carry canonical availability, not fabricated observations.
Habit metadata/history is loaded as required by Stage 7A. Out-of-calendar
extensions fail with 422 rather than clipping the request or wrapping dates.

## Architecture and performance

1. Validate the request and resolve metadata/grain through the Stage 7A registry.
   Dynamic `habit.<id>.<grain>.<feature>` identity never uses a mutable name;
   actual existence is checked against the loaded dataset registry.
2. Compute the union source range and call Stage 7A `get_dataset` **once**.
3. Use Stage 7A `slice_dataset` and Stage 7B `make_series`. Daily source/target
   series are built once and reused. Weekly X windows are projected in memory
   for each distinct shifted period: this preserves requested edge-week coverage
   and canonical State aggregation. Projections are cached within the request.
   This is not a source reload or another Stage 4 calculation.
4. Pure `align_lagged_pairs` joins existing coordinates using Y keys in order.
   It retains original X/Y timestamps, values, availability, units and source
   coverage; no reapplication of configuration at Y's timestamp takes place.
5. Shared Stage 7C `filter_pairs` applies pairwise availability rules; shared
   `analyze_paired` selects methods, calculates metrics and classifies results.
   Stage 7C same-period extraction uses these same functions.

There are no queries inside lag loops. Regression fixtures with 12 habits and
one year of data verify **one loader call, one dataset build and four SELECTs**
for both 1 and 15 lags, for daily and weekly grain. Serialization issues no SQL.
As in Stage 7A, extremely large habit registries can cause SQLAlchemy select-in
loader batching; the bound depends on source volume, not the number of lags.
CPU and temporary series memory grow with requested observations and lag count,
both bounded by policy. No new dependencies, writes, tables, migrations, durable
caches or materialized results are added. Existing Stage 7A `no_autoflush`
protects dirty and pending session objects; full SQLite dumps remain unchanged.

## Missingness, counts and sample rules

Alignment precedes pairwise deletion. Both coordinates must exist; null values
at existing coordinates are preserved until filtering. Canonical daily and
weekly rows cover the required range, so missing source records remain explicit
cells, not absent positions in the series. The pure alignment helper can also
accept sparse inputs, joining only coordinates present on both sides.

For each result:

- `potential_aligned_count` / `coverage.requested_count`: coordinate pairs before
  availability filtering.
- `coverage.excluded_count`: structurally excluded pairs (future, incomplete
  weekly period, not eligible).
- `coverage.eligible_count`: potential count minus structural exclusions.
- `n` / `coverage.valid_pair_count`: valid observed pairs used by statistics.
- `coverage.unavailable_count`: **all** lost pairs (potential minus n), including
  missingness, invalid values and low weekly source coverage.
- `coverage.missing_count`: pairs with eligible but missing observations.
- `coverage.pair_coverage`: n / eligible count, null for zero eligible count.
- `coverage.losses`: disjoint exclusion counts in precedence order `future`,
  `incomplete_period`, `not_eligible`, `missing`, `invalid_value`,
  `low_source_coverage`. Their sum equals unavailable count.
- `coverage.x/y`: original marginal availability; `source_x/y` and
  `paired_source_x/y`: weekly source coverage before/after pairwise deletion.
- `coverage.includes_today`: a valid daily pair uses today on either side.

Never convert null to 0/false, missing to skipped, or not applicable to zero.
Explicit zero and false remain observations. Stage 7A completion remains true
for done, false for explicit missed/skipped, and null for no entry; raw skipped
status is not rewritten. No obligations remains distinct from 0%.

## Reused statistics and units

| X/Y types | Stage 7C method(s) |
| --- | --- |
| Numeric / numeric | Pearson (primary) + Spearman |
| Ordinal / numeric or ordinal | Spearman, including average ranks for ties |
| Boolean / numeric or ordinal | Point-biserial |
| Boolean / boolean | Phi |
| Any categorical | `unsupported`, `unsupported_types` |

Boolean/ordinal retains the Stage 7C `ordinal_spacing_assumed` limitation.
Coefficients require **5 valid pairs**; strength requires **10**. Below 5 returns
`insufficient_data`; zero variance returns `constant_series`; undefined metrics
have null coefficients/direction/strength. The shared numerical engine and
availability filtering prevent NaN/Infinity coefficients. No lag-specific
thresholds or new Pearson/Spearman/Phi implementations exist.

Quantity units and schedule/weight/quota metadata retain each observation's own
historical configuration. Renaming a habit does not change its identity or lag
series. If either selected side's observation window contains multiple historical
quantity units, return `incompatible_units` / `mixed_quantity_units`, even when
the counterpart is missing at a unit-change date. A different lag's source
window cannot contaminate this check. No implicit unit conversion occurs.

Lag 0 equals the full Stage 7C `Relationship` result for the same pair, target
range and today, including all metrics, status, counts and coverage. This is
tested both alone and inside a scan using a broader loaded range.

## Partial and current periods

Observed current-day Y can pair with observed past X. Current-day X can likewise
pair with past Y. Future coordinates on **either side** are excluded, even when
calendar/planning variables have known values. A negative lag needing X after
today loses that pair; it cannot create a false/zero observation.

Weekly pairs exclude partial requested weeks, incomplete habit-activity weeks,
and unfinished current weeks on either side using the Stage 7B series flags.
The current week stays unfinished through Sunday and becomes complete Monday.
Weekly State means also retain Stage 7C's minimum **50%** source coverage on
each side. Expanding the source range does not change the target-period flags.

## Response and limitations

The top-level response includes contract versions, today, target period, actual
source ranges, target side/sign convention, both lag and relationship policies,
weekly coverage threshold and limitations. `results` contains every selected
lag, in numeric order. Each result extends the complete Stage 7C relationship
contract with `lag`, `lag_unit`, `target_period`, `x_period` and
`potential_aligned_count`; X/Y metadata, grain, method, primary coefficient,
all metrics, direction, strength, n, coverage, status/reason, unit sets, boolean
counts and contingency table remain available.

No best lag or max-coefficient field is returned. Associations may reflect
autocorrelation, shared trends, confounding, systematic missingness or chance
when inspecting many lags. Pairwise deletion does not fix selection bias.
Small samples remain unstable, including coefficients displayed at n=5–9
without a strength label. There are no uncertainty intervals, adjusted
effective sample sizes, detrending, causal models or forecasts. Inherited
source limitations (including absence of archive-event history) still apply.
