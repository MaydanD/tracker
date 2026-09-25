# Stage 7E — Confidence Engine contract (7E.1)

Read-only evaluation of **how well the existing history supports one already
computed association**. Stage 7E does not recompute any coefficient: it reuses
the Stage 7C statistics through the Stage 7D alignment, splits the requested
target period into chronological segments, and labels the evidence.

There is no probability, no causal claim, no forecast, no ranking, no
recommendation, no automatic insight, no LLM text and no analytics UI here. The
semantics below are the single source of truth for the label and its caveats.

## What confidence is, and what it is not

Stage 7C answers: **how large is the observed association?** (`strength`).
Stage 7E answers: **how well is that association supported by the available
history?** (`confidence`).

They are independent. `r = 0.95` measured on six pairs is `preliminary`;
`r = 0.20` reproduced identically across a long, well-covered history is
`well_supported`. Both directions of the mismatch are tested.

Confidence is **not**:

- a probability that the association is true, causal, or actionable;
- statistical significance, a p-value, or a multiple-comparison correction;
- a prediction, a trend, or an expected future value;
- a measure of the coefficient's size.

It is a product-policy maturity label over: sample size, pair coverage, temporal
replication, direction consistency, magnitude stability, method agreement and
known data limitations. Stage 7E deliberately adds **no p-values, bootstrap,
permutation, Monte Carlo or Bayesian machinery**; there are no new dependencies.

## API

`GET /api/analytics/confidence?start=2026-09-01&end=2026-11-30&x=state.sleep_minutes&y=state.mood&lag=0`

Required: inclusive calendar `start`, `end`, two distinct canonical variable keys
`x`, `y`. Optional `lag` (integer, `-7..+7`, default `0`) selects one Stage 7D
offset; without it the request is the same-period Stage 7C relationship. There is
no endpoint that evaluates all pairs or all lags automatically, and confidence is
never merged across lags: one response describes exactly one hypothesis,
`X ↔ Y` or `X(t − lag × unit) ↔ Y(t)`.

The service is `app.services.confidence.get_confidence(session, start, end, x, y,
lag=0, today=...)`. Uses the injected calendar clock; no timezone conversion and
no UTC timestamp arithmetic. Invalid keys, dates, duplicate X/Y or offsets return
localized HTTP 422 before any source is loaded.

## Policy (version `1`)

All thresholds live in one frozen object,
`app.domain.analytics.confidence_types.Policy`, echoed in every response as
`policy` plus `confidence_policy_version`. They are product policy for evidence
maturity, not statistical truth. Direction uses the existing Stage 7C
`negligible_below = 0.10` band, so Stage 7E introduces no second near-zero
threshold.

| Level | Requirements |
| --- | --- |
| `preliminary` | The relationship is computable (`n >= 5`) but at least one `stable` requirement below fails. |
| `stable` | `n >= 20`; pair coverage `>= 0.60`; at least **2** analyzable segments; majority of analyzable segments share the full-period direction; no segment with an **opposite moderate/strong** relationship; maximum segment deviation from the full coefficient `<= 0.35`; Pearson/Spearman do not point in opposite directions. |
| `well_supported` | All `stable` requirements, plus `n >= 40`; pair coverage `>= 0.75`; the period splits into all **3** segments and all 3 are analyzable; no opposite-direction segment at all; at most one segment that is not directionally matching (i.e. at most one `near_zero`); maximum segment deviation `<= 0.20`. |

`preliminary` never means "the association is wrong". It means the history is not
yet sufficient to judge its stability. A relationship that cannot be computed at
all (grain mismatch, unsupported types, incompatible units, too few pairs, zero
variance, invalid values, numerical error) is **`not_evaluable` with
`confidence = null`** and a typed `reason` — never `preliminary`.

A two-segment history can be `stable` but can never be `well_supported`
(`segment_count < 3`).

## Evidence basis

Every response contains machine-readable `evidence`, so a consumer can see *why*
the label was assigned instead of only reading `confidence`:

- `evidence.sample`: `n`, `requested_count`, `eligible_count`, `excluded_count`,
  `missing_count`, `unavailable_count`, `pair_coverage`, and the three explicit
  threshold flags `minimum_n_met`, `stable_n_met`, `well_supported_n_met`.
- `evidence.coverage`: full-period `pair_coverage` and `eligible_count`, the two
  coverage flags, `segment_pair_coverage` in chronological order,
  `minimum_segment_coverage`, `maximum_segment_coverage`, `coverage_imbalance`,
  `low_coverage`, `segment_instability`.
- `evidence.stability`: `segment_count`, `analyzable_segment_count`,
  `insufficient_segment_count`, `same_direction_count`, `near_zero_count`,
  `opposite_direction_count`, per-segment `coefficients`, `median_coefficient`,
  `median_absolute_coefficient`, `coefficient_range`,
  `maximum_deviation_from_full`, `direction_consistent`, `meaningful_reversal`,
  `magnitude_stable`, `magnitude_well_supported`.
- `evidence.methods`: `primary_method`, all `methods`, their `coefficients` and
  `directions`, and `agreement`.

`coverage` is always the Stage 7C/7D **pair coverage** (`n / eligible`), never a
count of calendar days: 30 days of history with only 8 days holding both
variables is 8/30, not 100%.

## History robustness

The requested **Y target period** is split into three consecutive, contiguous,
non-overlapping, calendar-equal segments — `early`, `middle`, `recent` — in
chronological order. Weekly histories are split by whole canonical Monday-start
weeks; daily histories by calendar days. Segment bounds are clipped to the
requested period, so segments always tile it exactly: no gaps, no overlap, no
observation beyond `start`/`end`. Extra units go to the earliest segment, so the
split is deterministic. A period too short to split into three units yields one
segment per unit (`only`, or `early`/`recent`), which is reported as
`limited_history` and can never be `well_supported`.

Each segment runs the **same hypothesis** — same method selection, same lag, same
pairwise deletion, same weekly rules, same historical unit policy, same minimum
sample rules — through the shared Stage 7C/7D engine. Segment directions come
from the Stage 7C `classify` band, so `near_zero` means the same thing everywhere.

- **Direction consistency** compares every analyzable segment with the
  full-period direction: `same`, `near_zero` (one side is inside the negligible
  band — weaker than confirmation, weaker than refutation), or `opposite`.
  `direction_consistent` means the majority of analyzable segments are `same`.
  `meaningful_reversal` means an `opposite` segment that is itself
  moderate/strong, which blocks `stable` outright.
- **Magnitude stability** measures `maximum_deviation_from_full` (and
  `coefficient_range`, `median_coefficient`, `median_absolute_coefficient`)
  between segment coefficients. Sections may differ by up to the policy bound;
  identical coefficients are not required.

For lagged requests the segmentation happens on the **Y** period and each
segment's X window is extended by the Stage 7D lag semantics
(`X(date) ↔ Y(date − lag × unit)`). The loaded source range is the union of the
full period's and every segment's shifted X window, so no segment can lose X
before its own start.

## Coverage, missingness and data quality

Pair coverage drives `low_coverage` below `0.60`. `systematic_missingness_possible`
is emitted when coverage is low **or** when segment pair coverage varies by at
least `0.25` between segments. This is a transparent warning only: Stage 7E does
not model missingness, does not impute, and never converts null into `0`/`false`
or missing into skipped. Null values at existing coordinates stay excluded pairs,
exactly as in Stage 7C/7D.

A coverage collapse in one recent segment therefore cannot be hidden by a good
full-period average: it is reported through `segment_pair_coverage`,
`coverage_imbalance`, `segment_instability` and the caveat. Note that the
*level* itself is gated by the full-period pair coverage policy; uneven segment
coverage is surfaced as a caveat and left visible rather than silently
downgrading the label.

## Method agreement

For numeric ↔ numeric, Stage 7C already returns Pearson and Spearman, so their
agreement is used as an extra signal:

- `agree`: the methods share one direction band → no caveat.
- `single_method`: one primary coefficient (Phi, point-biserial, Spearman-only).
- `partial`: one method is inside the negligible band while another is definite
  (for example Pearson strong, Spearman near zero) → `method_disagreement`.
- `disagree`: the methods point in opposite definite directions → `method_disagreement`
  and `stable` is blocked.
- `unavailable`: no metrics, or a coefficient is undefined (for example a
  constant series).

No separate classification model exists for methods; the agreement is one
evidence flag plus one caveat.

## Caveats

Caveats are deterministic codes with Russian labels/messages for a future UI.
They are emitted in a fixed order (`CAVEAT_ORDER`) and only when they apply.
Stage 7E generates no free-form text.

| Code | Meaning |
| --- | --- |
| `small_sample` | `n` is below the `stable` sample requirement. |
| `limited_history` | The period split into fewer than three segments. |
| `low_coverage` | Pair coverage is below `0.60`. |
| `systematic_missingness_possible` | Coverage is low or varies strongly between segments. |
| `segment_inconsistency` | Not every segment reproduced the full-period direction, or some segment lacked data. |
| `direction_reversal` | At least one segment has the opposite sign. |
| `magnitude_instability` | Segment coefficients deviate from the full coefficient by more than the policy bound. |
| `partial_period` | Incomplete weeks exist and were excluded from coefficients. |
| `method_disagreement` | Pearson and Spearman differ in strength or direction. |
| `constant_series` | One side has no variation, so the coefficient is undefined. |
| `incompatible_units` | The period mixes historical quantity units; no coefficient is computed. |
| `unsupported_variable_types` | The type combination has no coefficient. |
| `ordinal_distance_limitation` | An ordinal scale's level spacing is assumed comparable. |
| `autocorrelation_possible` | Adjacent time-ordered observations are not guaranteed independent. |
| `association_not_causation` | An observed association is not evidence of causal influence. |

Status-specific caveats (`incompatible_units`, `constant_series`,
`unsupported_variable_types`) and the universal ones
(`association_not_causation`, `autocorrelation_possible`, `partial_period`,
`ordinal_distance_limitation`) also apply to `not_evaluable` results; the
threshold-driven caveats are emitted only for a computed relationship, because
otherwise the typed `status`/`reason` is the explanation.

## Response

The root object carries `contract_version` (`7E.1`),
`dataset_contract_version`, `confidence_policy_version`, `today`, both `Variable`
metadata objects, `grain`, `lag`, `lag_unit`, `target_period`, the actual
`source_range` and `habit_entry_source_range`, `status`, `reason`, `confidence`,
the full `policy` and Stage 7C `relationship_policy`, the complete Stage 7D
`relationship` (a `LagResult`, so a lag-0 result is field-for-field the Stage 7C
`Relationship`), `evidence`, `segments` and `caveats`.

Each `segments` entry has its chronological `index`, `name`, the segment `period`
(Y range), `relation_to_full`, `direction`, `strength` and the complete
`relationship` (Stage 7D `LagResult`, including the shifted `x_period`, counts,
coverage and status). `status = not_evaluable` with `grain = null` returns an
empty `segments` list, since the grain needed for segmentation is undefined.

No best lag, maximum coefficient, probability, interval or recommended action is
returned anywhere.

## Limitations

- Observational data: associations may reflect autocorrelation, shared trends,
  confounding, systematic missingness or chance when many hypotheses are
  inspected. Stage 7E does not adjust for any of these.
- Temporal replication is not independent replication; three segments of one
  user's history are correlated by construction.
- Lagged associations are especially easy to misread causally, so
  `autocorrelation_possible` and `association_not_causation` are always present
  for lag analyses.
- The engine cannot prove missingness is non-random; it can only warn.
- Short histories, sparse state entries and dynamic habit histories limit all
  three levels. `preliminary` is the honest label there, not a failure.
- Pairwise deletion does not fix selection bias, and no uncertainty intervals,
  effective sample sizes or detrending exist.
