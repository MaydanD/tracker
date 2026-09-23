# Tracker — Project Specification v2

## 1. Product summary

**Tracker** is a local, single-user desktop application for habit tracking, daily state tracking, long-term personal analytics, and automatically generated behavioral insights.

The product is not primarily a checkbox tracker. Its main purpose is to accumulate a clean longitudinal dataset about one person and gradually answer questions such as:

- which behaviors are associated with better or worse mood;
- what tends to happen after alcohol use;
- whether gaming or heavy computer use is associated with lower habit completion;
- which habits tend to occur together;
- what tends to precede good or bad weeks;
- whether certain effects appear immediately or after several days;
- which habits or life areas are currently slipping;
- whether deliberate personal experiments change later outcomes.

The application is for **one local user only**.

Primary platform: **Windows desktop**.

Mobile support may be added later, but it is not a current requirement.

---

## 2. Product principles

1. **Local first**
   - No account system.
   - No cloud dependency.
   - No server deployment requirement.
   - All primary data lives locally.

2. **Analytics first**
   - Tracking exists to create useful historical data.
   - Raw observations are authoritative.
   - Derived analytics should be recomputable.

3. **Fast daily input**
   - A normal daily check-in should take roughly 30 seconds.
   - Common actions should require as few clicks as practical.

4. **Actions and state are separate**
   - Habits describe things the user intends to do.
   - Mood, sleep, energy, alcohol, gaming, etc. describe state/context.
   - State metrics must not directly increase or decrease habit score.

5. **No fake certainty**
   - Correlation is not causation.
   - Insights must describe associations in the user's data.
   - Insights require sufficient data and statistical guardrails.

6. **History must remain interpretable**
   - Habit settings can change over time.
   - Historical records should remain tied to the settings that were valid when they were recorded.

7. **Data is long-term**
   - Historical data is kept indefinitely unless explicitly deleted by the user.
   - Backups must exist before real long-term usage begins.

---

### 2.1 Язык приложения — постоянное требование

Основной и текущий язык пользовательского интерфейса Tracker — **русский**.

- Все пользовательские тексты должны быть на естественном русском: навигация, кнопки, формы, статусы, валидация, пустые состояния, подсказки, ошибки и системные сообщения.
- Нельзя случайно смешивать русский и английский в интерфейсе. Название продукта Tracker, технические команды и введённые пользователем данные сохраняются как есть.
- Python/TypeScript identifiers, API fields, DB schema, enum values и filenames могут оставаться английскими. Технические коды и сообщения API преобразуются в понятные русские сообщения на границе UI; error envelope сохраняется.
- Полноценная мультиязычная i18n-система пока не нужна: для одного языка достаточно русских строк и небольших функций форматирования.
- Все будущие этапы обязаны соблюдать это правило. Английские примеры и названия разделов в спецификации описывают понятия, а не готовый текст интерфейса.
- Термин Check-in в интерфейсе — **«Итоги дня»**, последовательно во всех разделах.

---

## 3. Areas

An Area is a broad, persistent life sphere.

Expected count: approximately **4–6**.

Examples:

- Health
- Development
- Work
- Household

An Area:

- has a name;
- has a color;
- may have multiple habits;
- is used for grouping and visual identity.

A habit belongs to exactly one Area.

No deeper hierarchy is required.

---

## 4. Habits

A Habit is an action the user intends to perform.

### 4.1 Habit fields

Each habit should support:

- id;
- name;
- description, optional;
- area_id;
- active/archived status;
- weight;
- schedule;
- tracking mode;
- optional quantity configuration;
- optional default unit;
- created_at;
- archived_at;
- history/version information.

### 4.2 Habit weights

Keep weighting simple:

- `1` — normal;
- `2` — important;
- `3` — key.

Weights are used in day/week score calculations.

### 4.3 Habit tracking modes

A habit can be:

1. **Binary only**
   - done / not done.

2. **Binary + optional quantity**
   - can be marked done with one click;
   - may additionally store a structured numeric quantity.

Examples:

- Reading: done + `35` pages.
- Walking: done + `6.4` km.
- Push-ups: done + `80` reps.
- Meditation: done + `20` minutes.

### 4.4 Quantity is structured data

Quantity MUST NOT be stored only inside notes.

A daily habit entry should have a dedicated numeric field such as:

- `quantity_value`
- `quantity_unit`

The note remains a separate free-text field.

Quantity is nullable because a habit may be completed without entering an exact amount.

Possible units include:

- pages;
- minutes;
- km;
- repetitions;
- glasses;
- custom text unit.

Do not hardcode analytics to a fixed unit list.

### 4.5 Partial behavior

No separate "partial completion" status is required initially.

If the user did a meaningful amount, the habit may be marked done.

If a quantity is entered, it is stored independently for later analytics.

A future target quantity may exist, but the MVP should not require percentage-based completion.

---

## 5. Scheduling

### 5.1 Definition of a week

For habit quotas, streaks, weekly score, and schedule completion:

**A week is always calendar Monday–Sunday.**

Do not use a rolling 7-day window for schedule compliance or weekly streaks.

Rolling windows may later be used for analytics only.

### 5.2 Supported schedule types

#### Daily

Expected every day.

#### Specific weekdays

Example:

- Monday
- Wednesday
- Friday

Configured weekdays are **preferred days**, not rigid immutable slots.

The schedule also implies a weekly required count.

Example:

- preferred days: Mon/Wed/Fri;
- weekly required count: 3.

A Tuesday completion may satisfy one of that week's required completions.

#### N times per week

Example:

- 3 times per week;
- no preferred weekdays required.

### 5.3 Flexible same-week completion

The engine should distinguish:

- preferred schedule;
- required weekly quota.

Example:

A habit is configured for Mon/Wed/Fri.

If it is completed Tuesday instead of Wednesday, that completion may satisfy one pending weekly occurrence.

By the end of Sunday:

- 3/3 → weekly requirement completed;
- 2/3 → weekly requirement missed.

Preferred weekdays influence presentation and planning, not punishment.

### 5.4 Missed required completion

A non-required day does not count as a miss.

For weekly habits, the requirement is resolved at the end of the calendar week.

---

## 6. Daily habit entry

A daily habit record should support at least:

- habit_id;
- date;
- status;
- quantity_value, nullable;
- quantity_unit or resolved unit reference;
- note, nullable;
- skip_reason, nullable;
- created_at;
- updated_at.

Suggested statuses:

- `done`
- `missed`
- `skipped_with_reason`

Historical days must remain editable.

Future planned skips may be entered.

---

## 7. Skip with reason

A skip with reason is descriptive, not protective.

It:

- still counts as a missed required habit for streak purposes;
- preserves why the habit was missed;
- may be analyzed later;
- may be created for a future date.

Example reasons:

- illness;
- travel;
- recovery;
- rest;
- workload;
- planned break;
- other.

A custom note may accompany the reason.

---

## 8. Streaks

### 8.1 Daily habits

A required missed day breaks the streak.

### 8.2 Weekly/flexible habits

A streak represents successful calendar weeks.

Example:

- quota: 3 per week;
- completed: 3/3;
- weekly streak continues.

If only 2/3 are completed by Sunday end, the streak breaks.

Preferred weekdays do not invalidate a flexible completion.

### 8.3 Streak calculation principle

Streaks must be derived from authoritative historical records and schedule history.

Do not permanently store an irreversible "current streak" counter as the only source of truth.

---

## 9. Daily state tracking

The application has one main daily check-in, typically completed in the evening or the following morning for the previous day.

State tracking is separate from habits.

### 9.1 Mood

Five fixed levels with emoji and text:

1. 😫 Terrible
2. 😕 Bad
3. 😐 Normal
4. 🙂 Good
5. 😄 Great

Store the numeric level for analytics.

### 9.2 Energy

Five-level scale.

### 9.3 Well-being

Five-level scale.

### 9.4 Sleep

No hour counting is required.

Use:

- underslept;
- normal;
- overslept.

The model should permit future extension.

### 9.5 Daily factors

Initial factors:

- alcohol;
- heavy computer use;
- gaming.

Each factor should support:

- simple yes/no;
- optional structured clarification where useful;
- optional note.

The common path should remain one-click yes/no.

The model must allow future factors without a major redesign.

### 9.6 Daily note

Each date may have one general free-text note.

---

## 10. Score model

Score represents **planned actions**, not state.

Mood, sleep, energy, alcohol, gaming and similar state/context variables must never directly affect the score.

### 10.1 Core formula

The score is based on weighted required habit occurrences.

For any evaluated period:

`score = completed_required_weight / total_required_weight * 100`

Where:

- each required occurrence contributes its habit weight;
- a completed required occurrence contributes the same weight;
- missed/unresolved required occurrences contribute zero;
- state variables contribute nothing.

Example:

- Habit A weight 3, quota 3/week → 9 required weight units.
- Habit B weight 1, quota 7/week → 7 required weight units.
- Total required weekly weight = 16.

If 6 weight units are missed:

- completed = 10;
- weekly score = `10 / 16 * 100 = 62.5`.

### 10.2 Day score

Day score should evaluate only required daily obligations that are meaningfully attributable to that day.

For flexible weekly habits, avoid pretending every preferred day is a rigid failed obligation if the weekly quota can still be satisfied later.

The exact presentation for flexible weekly habits should be resolved during Stage 4, but the weekly score formula above is authoritative.

### 10.3 Recomputability

Do not treat stored score values as authoritative historical facts.

Scores must be recomputable from raw entries, schedule history, and weights.

---

## 11. Dashboard

The Dashboard is the main screen.

Initial content:

1. Today / selected day score.
2. Yesterday's mood/state summary.
3. Today's habit list.
4. Current streaks.
5. Current week progress.
6. Large heatmap.
7. Current problems / things that are slipping.
8. Owl commentary.
9. Recent insights.
10. Recent records.

The dashboard must remain useful before advanced analytics exists.

---

## 12. Calendar

### 12.1 Monthly view

Show days and general completion/state.

Clicking a day opens:

- habit completions;
- quantities;
- notes;
- mood;
- energy;
- well-being;
- sleep;
- factors;
- daily note.

### 12.2 Year view

GitHub-style yearly heatmap.

Heatmap intensity should primarily reflect action completion/day score, not mood.

---

## 13. Analytics goals

Analytics are the central long-term feature.

The system should test as many **meaningful** relationships as practical without flooding the user with false discoveries.

### 13.1 Relationship families

Examples:

- habit ↔ habit;
- habit ↔ mood;
- habit ↔ energy;
- habit ↔ well-being;
- sleep ↔ habits;
- alcohol ↔ mood;
- alcohol ↔ energy;
- gaming ↔ habits;
- heavy computer use ↔ state;
- quantity ↔ state;
- quantity ↔ other habits;
- area completion ↔ state;
- week-level behavior ↔ next-week outcomes.

### 13.2 Time lags

At minimum:

- day 0;
- +1;
- +2;
- +3;
- +4;
- +5;
- +6;
- +7 days.

The architecture should allow:

- longer lags;
- rolling windows;
- week-level aggregates.

### 13.3 Correlation is not causation

Good:

> In your data, alcohol days are associated with lower energy the following day.

Bad:

> Alcohol causes your energy to drop.

Experiments may strengthen interpretation but still should not overclaim causality.

---

## 14. Statistical guardrails

The analytics engine must explicitly handle the risks created by testing many relationships.

### 14.1 Minimum sample size

Do not generate meaningful insights from tiny samples.

Initial conceptual tiers:

- insufficient;
- preliminary;
- stable;
- well-supported.

Starting guidance:

- preliminary: roughly 30+ valid observations;
- stable: roughly 60+;
- well-supported: roughly 120+.

These are not magic constants and may vary by test type.

### 14.2 Group balance

For categorical comparisons, total N is not enough.

Example:

- 100 tracked days;
- only 4 alcohol days.

That must not produce a strong alcohol insight.

Require a sensible minimum number of observations in each compared group.

### 14.3 Effect size

Statistical significance alone is not enough.

Insights should require a meaningful effect size appropriate to the test.

### 14.4 Multiple comparisons

Because Tracker may test hundreds of combinations:

- apply false-discovery-rate control;
- use Benjamini–Hochberg or an equivalent justified method.

Do not treat raw `p < 0.05` as sufficient when running large batches of tests.

### 14.5 Stability over time

A relationship should gain confidence if it persists across different slices of history.

Example approaches:

- first half vs second half;
- rolling historical windows;
- recent vs older periods.

A relationship that only appears in one short period should remain low-confidence.

### 14.6 Autocorrelation

Daily mood, energy, habits, and behavior are time-dependent.

Naive independent-observation assumptions may overstate confidence.

The architecture should support later use of methods such as:

- block bootstrap;
- time-aware resampling;
- lag-aware regression.

This does not need to be fully implemented in the earliest analytics stage.

### 14.7 Confounders

Day-of-week effects are a known confounder.

Example:

Friday/Saturday may differ in both alcohol probability and normal energy/schedule.

For important relationships, analytics should eventually control or adjust for at least:

- weekday;
- previous-day baseline state where relevant.

This may be implemented through stratification or simple regression before more advanced models are considered.

### 14.8 User-facing confidence

User-facing confirmation levels should combine:

- sample size;
- group balance;
- effect magnitude;
- corrected statistical evidence;
- temporal stability;
- known confounding limitations.

Suggested labels:

- preliminary;
- stable;
- well-supported.

---

## 15. Example insight

> After days with alcohol, next-day energy is 0.8 points lower on average.  
> Stable relationship · 74 observations · corrected significance passed · 5 months of data.

The detailed view may also show:

- group sizes;
- effect size;
- lag;
- confidence tier;
- graph;
- known caveats.

---

## 16. Failure patterns

The application should detect deterioration as well as success.

Examples:

- 3 reading misses in 5 days;
- weekly score materially below recent baseline;
- repeated missed workouts;
- repeated gaming-heavy evenings associated with lower completion;
- decreasing completion trend.

No "never miss twice" mechanic is required.

---

## 17. Owl

The Dashboard contains a persistent owl character.

The owl is a humorous analytical narrator, not a random motivational mascot.

Its comments must be based on real data.

Examples:

> Third reading miss in five days. Literature remains safe from you.

> Three of the last four alcohol days were followed by low energy. Mysterious.

> This week is at 61%. Last week ended at 84%. Excellent reverse optimization.

The owl should prioritize:

- current slippage;
- unusual weakness;
- repeated misses;
- supported insights;
- positive records where appropriate.

The owl must never invent facts.

---

## 18. Insights screen

A dedicated Insights screen should eventually contain:

- automatically discovered relationships;
- filters by habit/factor/state;
- lag;
- period;
- confirmation level;
- effect size;
- sample count;
- supporting graph;
- first detected date;
- whether the relationship remains supported by newer data;
- caveats if the model detects known confounders or weak balance.

---

## 19. Experiments

The user can define a temporary personal experiment.

Fields:

- name;
- description;
- start date;
- end date;
- optional target factor/habit;
- optional expected effect.

Example:

`30 days without alcohol`

The system can compare:

- period before;
- experiment period;
- period after.

Possible outputs:

- mood;
- energy;
- well-being;
- habit completion;
- day/week score;
- specific habit quantities.

Experiments are useful because they introduce deliberate behavioral change rather than relying only on passive correlations.

They are still N=1 observational/self-experimental data and should not be presented as laboratory-proof causality.

---

## 20. Records and achievements

### Records

Examples:

- longest streak;
- best week;
- best month;
- highest quantity for a habit;
- best rolling completion period.

### Achievements

Decorative only.

Examples:

- first 7-day streak;
- first perfect week;
- 100 total completions;
- first full month of data.

No XP economy is required.

---

## 21. Habit history

Habit settings may change.

Examples:

- weight changes;
- schedule changes;
- rename;
- unit change;
- Area change.

Historical analytics must remain interpretable.

The application needs habit configuration history/versioning.

Do not simply overwrite historical meaning.

### 21.1 Implemented strategy (Stage 2)

Habit configuration is stored as effective-dated versions instead of on the habit row itself. Earlier days' versions are preserved; edits on the current version's day update that version. "Current configuration" is the latest version, and any past date resolves to the version that was effective then.

Rules:

- one version per habit per calendar day: an edit made on the same day updates that day's version instead of stacking duplicates;
- an edit that takes effect after the current version appends a new version;
- an edit that would take effect *before* the current version is rejected rather than rewriting recorded meaning (backdating may be added later if it is genuinely needed);
- saving an unchanged configuration creates no new version.

Same-day collapse remains the Stage 2 rule. Revisit effective-date semantics in Stage 3 when real daily entries exist; do not change it as part of UI localisation. Duplicate habit names within an Area are allowed.

Area name and colour changes are not versioned: they are display metadata, and historical habit configuration keeps referential integrity through `area_id`.

---

## 22. Archive

Habits and Areas should normally be archived rather than hard-deleted once historical records exist.

Archived habits remain visible in history and analytics.

An Area that still has active habits cannot be archived: those habits must be archived or moved first, so an active habit never points at an archived Area.

---

## 23. Backup and export

Data protection starts early.

### 23.1 Early safety backup

Before real daily usage begins, implement a simple automatic SQLite backup.

Minimum early version:

- timestamped database copy;
- safe backup procedure rather than blind copying during an unsafe write state;
- predictable backup directory.

This belongs no later than Stage 3.

### 23.2 Full backup system

Later add:

- retention policy;
- recent daily backups;
- monthly long-term snapshots;
- integrity checks;
- restore workflow.

### 23.3 Excel export

Provide a human-readable `.xlsx` export.

Suggested sheets:

- Habits
- Areas
- Daily Habit Entries
- Daily State
- Factors
- Notes
- Experiments
- optional derived summaries

Excel is an export, not the authoritative database.

---

## 24. Technical direction

### Frontend

- React
- TypeScript
- Vite

### Backend

- Python
- FastAPI
- SQLAlchemy 2.x
- Alembic

### Database

- SQLite

### Future analytics tools

Likely:

- pandas;
- numpy;
- scipy;
- statsmodels where useful.

Add them only when the analytics stage needs them.

### Desktop packaging

Target Windows desktop:

- pywebview;
- PyInstaller.

Expect PyInstaller packaging to require real testing.

Potential issues:

- antivirus false positives;
- executable size;
- path handling;
- bundled resource access.

Do not treat packaging as a trivial final command.

---

## 25. Architecture principles

1. Raw observations are authoritative.
2. Derived analytics are recomputable.
3. Avoid persisting stale derived values unless they are explicitly treated as cache.
4. Use migrations from the beginning.
5. Keep analytics separate from CRUD/domain logic.
6. Keep schedule/streak logic in testable domain services.
7. Avoid business rules inside React components.
8. Daily factors must be extensible.
9. Historical editing is allowed.
10. Date calculations must be deterministic and tested.
11. Schedule configuration history must be queryable for historical calculations.
12. Analytics datasets should be generated through a dedicated analysis layer, not ad hoc SQL scattered through endpoints.

---

## 26. Planned screens

- Dashboard
- Daily Check-in
- Calendar
- Habits
- Areas
- Insights
- Experiments
- Records / Achievements
- Settings / Backup

---

## 27. Updated development plan

| Stage | Deliverable |
|---|---|
| **1 — Foundation** | React + FastAPI + SQLite + SQLAlchemy + Alembic, config, health/ready, project shell, tests, README |
| **2 — Areas & Habits** | Areas, habits, weights, archive, tracking modes, quantity config, schedule config, configuration history |
| **3 — Daily Tracking + Early Backup** | Daily habit entries, done/missed/skip reason, structured quantities, habit notes, historical edit, future skips, simple automatic SQLite backup |
| **4 — Schedule / Streak / Score Engine** | Monday–Sunday week rules, daily/weekday/N-per-week schedules, flexible same-week completion, streaks, weighted day/week score, date-boundary tests |
| **5 — Daily State** | Mood, energy, well-being, sleep category, alcohol, gaming, heavy computer use, optional clarifications, daily note |
| **6 — Dashboard & Calendar** | Dashboard, current streaks, week progress, yesterday state, monthly calendar, day detail, yearly heatmap |
| **7A — Analytics Dataset** | Canonical analysis dataset, variable typing, missing values, daily and weekly features, reproducible dataset builder |
| **7B — Association Engine** | Same-day binary/categorical/numeric associations, effect sizes, supported pair types |
| **7C — Lag Engine** | Lag 0–7, previous-state features, rolling/weekly windows where justified |
| **7D — Statistical Guardrails** | Minimum N, group balance, effect thresholds, Benjamini–Hochberg/FDR, weekday adjustment, temporal stability checks, groundwork for time-aware uncertainty |
| **7E — Confidence Engine** | Preliminary/stable/well-supported classification, caveats, evidence metadata, persistence across time slices |
| **8 — Insights** | Human-readable findings, graphs, filters, evidence detail, insight history |
| **9 — Owl** | Persistent data-backed owl, slippage detection, prioritization, sarcastic commentary without fabricated facts |
| **10 — Experiments** | Experiment CRUD, before/during/after comparison, state and habit outcomes |
| **11 — Records & Achievements** | Personal records, decorative achievements, long-term milestones |
| **12 — Full Backup / Export / Desktop Packaging** | Backup retention, integrity checks, restore, Excel export, pywebview, PyInstaller Windows build |
| **13 — Hardening** | Migration safety, corruption handling, performance profiling, analytics edge cases, packaging edge cases, UI polish |

---

## 28. Stage boundaries

### Stages 1–3

Create a safe data foundation and begin real daily use.

### Stages 4–6

Make Tracker a complete practical habit/state tracker.

At the end of Stage 6, the app should already be genuinely useful without advanced analytics.

### Stages 7A–7E

Build the analytics engine incrementally.

Do not attempt all statistical functionality in one giant implementation.

### Stages 8–10

Turn validated analytics into understandable insights, guidance, and personal experiments.

### Stages 11–13

Add long-term polish, records, exports, packaging, reliability, and hardening.

---

## 29. Out of scope for now

Do not build unless requirements change:

- multi-user accounts;
- authentication;
- cloud sync;
- social features;
- public profiles;
- native mobile app;
- push notifications;
- complex XP system;
- habit templates marketplace;
- AI chat assistant;
- Docker deployment;
- PostgreSQL deployment;
- wearable integrations.

---

## 30. Definition of success

Tracker succeeds if:

1. daily behavior can be recorded with minimal friction;
2. quantities are stored as real structured numeric values;
3. actions and state remain cleanly separated;
4. schedule logic matches real flexible weekly behavior;
5. day/week score is understandable and recomputable;
6. years of data can be preserved safely;
7. the dashboard gives a useful current picture;
8. analytics avoid obvious false-discovery traps;
9. insights expose evidence and uncertainty;
10. over time, Tracker surfaces personal patterns that would be difficult to notice manually.
