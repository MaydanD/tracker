# Stage 7D — Statistical Guardrails contract (7F.1)

Numbering note: this layer is the *original* Stage 7D of the analytics plan, but
it was implemented after the current Stage 7D (Lag Analysis) and Stage 7E
(Confidence Engine) that already existed in the codebase, so its contract version
is the next free analytics label, `7F.1`. The request path
(`/api/analytics/guardrails`), the module name and the older contracts are
unchanged.

Statistical guardrails sit between the association/lag engines and any future
Insights layer. They answer one question:

> **May this computed association be used as evidence at all?**

They never re-derive a coefficient, a lag alignment, a coverage number or a
temporal split: Stage 7A supplies the canonical dataset, Stage 7C the
coefficients and pairwise deletion, Stage 7D (lag engine) the alignment and the
shifted source range, and Stage 7E the chronological segments and stability
metrics. Guardrails add sample-size, coverage, group-balance, effect-size,
within-weekday, temporal-blocking and multiple-comparison rules, and report
every check explicitly.

Guardrails are read-only and deterministic. They do not prove causation, do not
recommend anything, do not forecast, do not rank behaviour and do not produce
user-facing insights.

## Guardrails versus confidence

| | Statistical guardrails (this layer) | Confidence engine (Stage 7E) |
|---|---|---|
| Question | is the result admissible as evidence? | how well is it supported by the whole history? |
| Looks at | sample size, coverage, balance, effect, weekday confounding, multiplicity, temporal blocking | sample size, coverage, segment replication, magnitude stability, method agreement |
| Output | `pass` / `pass_with_warnings` / `blocked` / `not_evaluable` + reasons | `preliminary` / `stable` / `well_supported` + caveats |

Both verdicts are reported side by side and never merged. `confidence` describes
*evidence maturity*; `guardrail` describes *admissibility*. An association can be
historically stable and still inadmissible (`confidence = stable`,
`guardrail = blocked`) — for example when it does not survive FDR control in a
discovery family, or when it is a pure weekday rhythm.

A blocked guardrail can never raise confidence to `well_supported`: the Stage 7E
response caps `well_supported` at `stable` and sets
`guardrail.confidence_capped = true`. Everything else about confidence is
unchanged.

## API

```http
GET /api/analytics/guardrails?start=...&end=...&x=...&y=[&lag|&lags|&lag_start&lag_end]
GET /api/analytics/guardrails?start=...&end=...&variables=a&variables=b[&variables=...]
```

- Explicit inclusive `start`/`end`; the requested period always belongs to **Y**.
- One hypothesis: `x` + `y` (optionally `lag`, default 0).
- Lag family: one X/Y pair and `lags=1&lags=2...`, or `lag_start`/`lag_end`
  (inclusive, `-7..+7`, at most 15 values). All of them form **one family**.
- Relationship family: `variables` (2..24) evaluates every pair as **one family**.
- Read-only `GET`; `422` with a Russian message for invalid input, `405` for
  anything else.

A single request performs exactly **one** Stage 7A dataset build. Hypotheses,
lag values, temporal segments and weekday strata are all evaluated in memory.

## Policy (version `1`)

All thresholds live in `app.domain.analytics.guardrail_types.Policy` and are
returned with every response. They are product rules for evidence maturity, not
statistical truth.

| Check | Threshold | Below threshold |
|---|---|---|
| sample size | `n >= 20` passed, `n >= 10` warning, `n < 10` blocking | `small_sample` warning / `insufficient_sample` blocker |
| pair coverage | `>= 60%` passed, `>= 40%` warning, `< 40%` blocking | `moderate_coverage` warning / `insufficient_coverage` blocker |
| group balance | `>= 5` observations in each binary group **and** minority `>= 15%` | blocking `insufficient_group_balance` |
| contingency | every cell of a boolean↔boolean table `>= 5` | blocking `sparse_contingency_cell` |
| effect size | `|coefficient| >= 0.15` | blocking `below_effect_threshold` |
| FDR | `q <= 0.10` inside a family of more than one tested hypothesis | blocking `false_discovery_risk` |
| weekday control | relative attenuation `<= 50%`, no direction change | `weekday_attenuation` warning / `weekday_explained` / `weekday_reversal` blocker |
| temporal | `>= 2` analyzable segments, direction consistent, no meaningful reversal | `insufficient_temporal_evidence` / `magnitude_instability` warnings, `temporal_direction_inconsistency` / `temporal_reversal` blockers |

Coverage is deliberately consistent with Stage 7E: coverage passes at `60%`
there, blocks below `40%` here, and `40–60%` is only a warning, so the two layers
can never contradict each other.

`n < 5` (the Stage 7C calculation minimum), grain mismatch, unsupported types,
incompatible units, constant series and numerical errors produce
`verdict = not_evaluable` and no confidence level. `not_evaluable` is not
`preliminary`.

## Effect sizes

| Type combination | Primary statistic | Additional evidence |
|---|---|---|
| numeric ↔ numeric | Pearson (+ Spearman as second metric) | — |
| boolean ↔ numeric | point-biserial | true/false counts, mean, median, absolute difference, Cohen's *d* |
| boolean ↔ ordinal | point-biserial | true/false counts, mean, median, absolute difference (no *d*) |
| boolean ↔ boolean | Phi | 2×2 contingency counts and smallest cell |
| ordinal ↔ * | Spearman | — |
| categorical ↔ * | unsupported | — |

Cohen's *d* is the pooled-standard-deviation effect size and is only computed
when both groups have at least two observations and the pooled variance is
positive; otherwise it is `null`, never imputed. Every effect metric is
descriptive. The full-period coefficient is always preserved in the response
even when it blocks.

## Multiple comparisons

An **analysis family** is the set of hypotheses inspected together:

- one pre-selected hypothesis (`mode = single`),
- one X/Y pair over several lags (`mode = lag_scan`),
- the pairs of a relationship matrix (`mode = matrix`).

For every hypothesis with a computable p-value a two-sided raw p-value is
reported:

- Pearson, point-biserial and Spearman use the standard `t` test with `df = n - 2`
  (point-biserial is Pearson on the 0/1 encoding, so it coincides with the pooled
  two-sample t-test; Spearman uses the standard t-approximation on the rank
  coefficient).
- Phi uses the exact 1-df chi-square tail (`n * phi²`), which is the correct
  reference for a 2×2 table.
- Any other method reports `null` instead of a fabricated p-value.

The Student-t tail is evaluated through the regularized incomplete beta function
and the chi-square tail through `erfc`; both are implemented in
`app.domain.analytics.inference` with no new dependency.

Adjusted q-values use the standard Benjamini–Hochberg procedure: p-values are
ranked ascending, `q(i) = min(p(i) * m / i)` is clamped to `[0, 1]`, q-values are
monotone in p, identical p-values get identical q-values, and the input order is
preserved. Ties are broken by original index so the result is deterministic.

**Denominator rule.** Hypotheses whose p-value cannot be computed stay in the
response with `status = not_evaluable` and are excluded from the correction
denominator (`tested_size`). A family with at most one tested hypothesis gets
`status = not_applicable`: `multiple_comparisons_checked = false` and the raw
p-value still reported. Correction is applied to the whole family — never to a
pre-selected "best" lag or pair.

### What p-values and q-values are not

- `p` is **not** the probability that the association is true.
- `q` is **not** the probability that a discovery is false in this dataset; it
  bounds the expected proportion of false discoveries among the hypotheses that
  pass, under the assumptions of the procedure.
- `p >= 0.05` does not mean "no relationship", and `p < 0.05` does not mean
  "important", "causal" or "actionable".
- Passing every guardrail does **not** imply causality.

## Weekday control

Personal trackers easily produce weekday artifacts: if a behaviour and an outcome
both happen more often on Fridays, a strong association can be nothing more than
a weekly rhythm.

For daily, non-categorical relationships the guardrail performs a transparent
within-weekday control:

1. valid paired observations are grouped by the **weekday of the Y target date**;
2. strata with fewer than 3 observations are dropped (and at least 2 strata are
   required, otherwise the control is `not_evaluable` with a
   `weekday_control_unavailable` warning);
3. each value is centred on its own stratum mean;
4. **the same statistic as the raw coefficient** (Pearson, Spearman or the 0/1
   encoding used by point-biserial and Phi) is recomputed on the centred values.

Centring by stratum mean and recomputing the coefficient is exactly a partial
correlation controlling for the day of week, so the raw and adjusted magnitudes
are directly comparable. The raw coefficient is never modified.

Outcomes:

| Outcome | Meaning | Effect |
|---|---|---|
| `retained` | adjusted association survives | check passed |
| `attenuated` | relative attenuation `> 50%` | warning |
| `explained_by_weekday` | after centring the series is constant: the "association" is the week pattern itself | blocking |
| `reversed` | the sign flips after control | blocking |
| `insufficient_strata` | too few usable weekdays | warning, no adjusted value |
| `not_applicable` | weekly grain | check not applied |
| `not_supported` | categorical pair | check not applied honestly instead of forced |

**Lag semantics.** Weekday strata are always taken from the **Y/target date**
(`weekday_basis = "y_target_date"`), because the requested analytical period — and
therefore the lag hypothesis — is defined on Y. The pairing itself is the Stage 7D
one: for lag `+1` the X observation is one day earlier than its Y. Both partitions
are related by a one-day rotation, so the choice is a labelling decision; stating
it explicitly keeps the lag hypothesis and its weekday interpretation consistent.
The control only ever reads already-paired, past-or-today observations, so no
future information can enter the adjustment. For weekly grain, straight
weekday-aligned rhythms are `not_applicable`, and boolean↔boolean or
boolean↔ordinal pairs are still evaluated on their 0/1 encodings, which is the
same linear scale as their raw coefficient.

## Temporal robustness

Segmentation is **not** reimplemented. The guardrail consumes the Stage 7E
segments (target period split into 3 contiguous, equal-length chronological parts;
canonical whole weeks for weekly grain) and their stability metrics, and turns
them into a *blocking* decision:

- `meaningful_reversal` (an analyzable segment confidently opposite the full
  period) → blocking `temporal_reversal`;
- a majority of analyzable segments not supporting the direction → blocking
  `temporal_direction_inconsistency`;
- fewer than 2 analyzable segments → warning `insufficient_temporal_evidence`
  (missing evidence is never treated as evidence of instability);
- unstable magnitude → warning `magnitude_instability`;
- an incomplete current week is excluded by the Stage 7C/7D rules and only
  reported as a `partial_period` warning.

## Response

The response carries `contract_version`, `dataset_contract_version`,
`guardrail_policy_version`, `today`, the `policy` (all thresholds), the Stage 7C
`relationship_policy`, the `target_period`, the actual `source_range` and
`habit_entry_source_range`, the evaluated `lags`, a `family` summary (mode,
requested/evaluable/tested sizes, FDR method and threshold, verdict counts) and
one entry per hypothesis:

`index`, `x`, `y`, `grain`, `lag`, `lag_unit`, `target_period`, `verdict`, the
full Stage 7D `relationship`, `sample`, `coverage`, `stability`, `effect`
(coefficient, absolute value, threshold, group evidence), `weekday` (raw and
adjusted coefficient, attenuation, direction change, strata counts), and
`multiple_comparisons` (family mode and size, rank, method, threshold, raw `p`,
adjusted `q`, `passed`), plus every individual `checks` entry with its own
`status` (`passed` / `failed` / `not_applicable` / `not_evaluable`), `blocking`
flag, `detail` code, observed value and threshold.

`blocking_reasons` and `warnings` are ordered, typed and localized: each entry has
a machine `code` and Russian `label`/`message` ready for a future UI. Blocked
hypotheses are always returned with their coefficient and evidence — guardrails
never silently filter results.

## Interactions with the rest of the pipeline

- Stage 4/5/6, descriptive analytics, relationships and lag semantics are
  untouched: null is still not `false` or `0`, pairwise deletion is unchanged, the
  lag sign is unchanged, lag 0 still equals the Stage 7C same-period relationship,
  historical units and partial-period rules still apply.
- `GET /api/analytics/confidence` now also returns a compact `guardrail` summary
  (status, policy version, family size, blocking reasons, warnings, whether
  confidence was capped) computed from the same dataset — one build, no extra SQL.
- Frontend, recommendations, prediction, ranking, LLM insights and analytics UI are
  not part of this stage.

## Limitations

- Everything here is observational. Guardrails reduce the risk of reading chance
  or calendar artifacts as evidence; they cannot make an association causal, and
  passing them is not proof of anything.
- p-values assume independent observations that the data may not satisfy
  (autocorrelation), and FDR control assumes a valid family definition — a wrong
  family gives a correct answer to the wrong question.
- Weekday control only removes a *linear* weekday baseline per stratum. Seasonal
  effects, holidays, other calendar rhythms, non-linear confounding and
  time-varying exposures are not modelled.
- Coverage is pair coverage, not a missingness model: low or uneven coverage is
  reported, never corrected.
- Boolean group balance cannot be improved by thresholds: a rare exposure simply
  cannot support evidence.
- Effect thresholds are product policy, not a statement about real-world
  importance, and Cohen's *d* is undefined for ordinal or constant groups.
- Long histories with rare events remain underpowered; `blocked` may mean
  "not enough evidence yet" rather than "no association".
