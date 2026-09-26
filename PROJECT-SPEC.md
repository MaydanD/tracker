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

> Implemented in Stage 3 (§6.1). The daily screen is «Итоги дня».

A daily habit record supports at least:

- habit_id;
- date;
- status;
- quantity_value, nullable (stored as an exact integer number of millionths; the
  unit is *not* duplicated here but resolved from the habit configuration of that
  date);
- note, nullable;
- skip_reason, nullable;
- created_at;
- updated_at.

`habit_id + entry_date` is unique: saving a day edits its one record rather than
appending another.

Statuses:

- `done`
- `missed`
- `skipped`

Historical days must remain editable.

Future planned skips may be entered.

### 6.1 Implemented semantics (Stage 3)

A day can be recorded by hand: open a date and state, per habit, what happened.

**«No entry» is a state of its own.** The absence of a record means the user has
said nothing about that habit on that day. Nothing derives `missed` from silence —
not for recent days and not for old ones. `missed` exists only because the user
stated it. Automatic evaluation, overdue detection and streaks belong to Stage 4
and must never be back-filled into the records.

**One habit and one date hold at most one record** (a uniqueness constraint in the
database, not just a convention in code). Saving a day again edits that record
rather than adding a second one.

**States.**

| Status | Meaning | Allowed on |
| --- | --- | --- |
| `done` | The habit was performed | today, past |
| `missed` | The user states it was not performed | today, past |
| `skipped` | A deliberate/planned skip | past, today, **future** |

A future date accepts a planned skip and nothing else. The rule is enforced by
the backend, independently of what the screen offers.

**Skip reason** is stored separately from the note and belongs only to `skipped`,
where it is required (and must not be blank). For `done`/`missed` the field is
empty. **Note** is a free-form remark available for any status.

**Editing and clearing.** A recorded day can be changed at any time, and can be
removed entirely — which returns it to «no entry», never to `missed`.

**Quantity** is optional and structured, and only exists for habits whose
tracking mode is `binary_quantity`. It is validated against the habit
configuration that was effective **on that date** (unit and decimal rule), not
against the habit's current settings, and it is stored as an exact value rather
than a floating-point number or a string in the note. Notes and quantities are
never conflated.

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

### 7.1 Implemented (Stage 3)

The reason is a dedicated field on the daily entry, not part of the note. It is
required for `skipped` and rejected for `done`/`missed`, so a reason can never be
silently reinterpreted as a different kind of remark. Only `skipped` may be
recorded for a date that has not happened yet; a planned skip may later be edited
or removed.

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

Five numeric levels, displayed with Russian labels (emoji are optional):

1. Очень плохое
2. Плохое
3. Нормальное
4. Хорошее
5. Отличное

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

Optional exact duration is stored in integer minutes (0–1440), independently
of the subjective category. Neither field requires the other.

### 9.5 Daily factors

Initial factors:

- alcohol;
- heavy computer use;
- gaming.

Each factor should support:

- explicit unspecified/no/yes (nullable boolean, never false by default);
- optional structured clarification where useful;
- optional note.

The common path should remain one-click yes/no.

The model must allow future factors without a major redesign.

### 9.6 Daily note

Each date may have one general free-text note.

### 9.7 Реализовано: Stage 5 — Daily State

Состояние дня — отдельная сущность `daily_states`, без связи с Habit.
`UNIQUE(state_date)` обеспечивает максимум одну запись на календарную дату.
Таблица содержит `id`, `state_date`, nullable-поля наблюдений и UTC-метки
`created_at`/`updated_at`. Числа шкал хранятся числами, подписи — только в UI.

| Поле | Семантика |
| --- | --- |
| `mood`, `energy`, `wellbeing` | Целые 1–5; `null` — не указано |
| `sleep_status` | `underslept` / `normal` / `overslept` / `null` |
| `sleep_minutes` | Целые 0–1440 или `null`, независимо от категории сна |
| `alcohol` | `null` — не указано; `false` — не было; `true` — был |
| `alcohol_detail` | Необязательный текст до 200 символов только при `alcohol=true` |
| `gaming` | Nullable boolean с теми же тремя различными состояниями |
| `gaming_minutes` | Целые 0–1440; при `gaming=null` только NULL, при false — NULL или 0 |
| `computer_overuse` | Nullable boolean: субъективная оценка чрезмерного времени за компьютером |
| `computer_minutes` | Целые 0–1440 или NULL, независимо от `computer_overuse` |
| `note` | Отдельная заметка дня до 500 символов |

Для алкоголя непустое уточнение при false/null отклоняется (422), а не
сохраняется и не теряется молча. Для игр false с положительными минутами и null
с любыми минутами отклоняются. Время за компьютером не выводит флаг автоматически:
180 минут и false/null валидны. Длительности в UI вводятся часами и минутами,
API/БД используют только целые минуты. Строки вместо чисел, дробные минуты,
boolean вместо числовой шкалы и 0/1 вместо boolean API не принимает.

Текст обрезается по краям, пробельный текст становится NULL. Заметка дня,
заметка Habit entry, skip reason и alcohol detail не смешиваются.
Частичное состояние допустимо: одно настроение, только note, явное «Нет»
или нулевые минуты. После нормализации хотя бы одно поле должно отличаться
от NULL; полностью пустой PUT отклоняется. NULL никогда не заменяется false
или нулём при чтении, записи или отображении.

API: GET/PUT/DELETE `/api/days/{date}/state`. GET возвращает
`{state_date, today, state}`, без записи — `state: null`. PUT полностью заменяет
значения (пропущенные поля очищаются), возвращает запись и атомарно выполняет
SQLite upsert с сохранением id/created_at, включая concurrent insert.
DELETE идемпотентно удаляет запись (204); GET после удаления снова возвращает null.

Сегодня и прошлое полностью редактируются, без ограничений глубины истории
или даты появления Habit. Будущие PUT/DELETE запрещены backend через injected
Clock; будущий GET разрешён. UI использует серверное today и показывает
«Состояние будущего дня нельзя заполнять». Будущий planned skip Habit сохраняет
свои правила Stage 3 и продолжает работать.

«Состояние дня» встроено в «Итоги дня», весь интерфейс русский. Шкалы и tri-state
представлены компактными кнопками; «Не указано» отличается от «Нет». Уточнение
алкоголя и время игр раскрываются при «Да». Сохранение, редактирование и очистка
обновляют только этот блок. Смена даты создаёт отдельный ресурс и черновик,
поэтому запоздалые GET/PUT/DELETE не заменяют данные под другой датой.

Daily State не создаёт и не меняет `daily_habit_entries`, не превращает no-entry
в missed, не меняет done/missed/skipped и не участвует в obligations, required/
completed weight, daily/weekly score, schedule или streak. Формула Stage 4
не изменена; регрессия сравнивает результаты до/после создания, правки и удаления.

Миграция `d5a1c09e2401` поверх `fc1efb50fa8d` (Stage 4 не менял схему) создаёт
только новую таблицу. CHECK защищают шкалы, целые минуты, enum, boolean,
согласованность уточнений и непустоту; ORM и миграция совпадают. Upgrade и
downgrade проверяются с сохранением существующих Habit/Entry данных.

Граница Stage 5 — **сбор Daily State**. Аналитика, корреляции, средние,
графики, lag analysis, прогнозы, рекомендации, автоматические выводы,
эксперименты, достижения, уведомления, напоминания, cloud sync и auth/multi-user
на этом этапе не реализуются. Stage 6 не начат.

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

Stage 4 includes only `daily` obligations in day score. Flexible habits have a
separate weekly progress and contribute to the weekly score (§10.4).

### 10.3 Recomputability

Do not treat stored score values as authoritative historical facts.

Scores must be recomputable from raw entries, schedule history, and weights.

### 10.4 Реализовано: Stage 4 — Schedule + Streak + Score

**Неделя всегда Пн–Вс**, без rolling windows. `daily` создаёт одно обязательство
на каждый активный календарный день. `weekdays` задаёт предпочтительные дни и
квоту, равную их количеству; `times_per_week` задаёт квоту N. Выполнение в любой
другой день той же недели закрывает недельную квоту. Переноса между неделями нет.
Одна запись `done` даёт одно выполнение, независимо от quantity.

**Оценка:** `completed_required_weight / total_required_weight × 100`.
Вес 1 — обычная, 2 — важная, 3 — ключевая привычка. Дополнительных коэффициентов
нет. Дневной знаменатель включает только `daily`, по весу версии конкретного дня.
Недельный включает сумму ежедневных обязательств и `quota × weight` недельных
компонентов. Их числитель — `min(done_count, quota) × weight`; фактический progress
может превышать quota, оценка — никогда не превышает 100%. При нулевом знаменателе
score равен `null`, UI показывает «Нет обязательных привычек».

`missed`, `skipped` (с любой причиной) и отсутствие строки дают нулевой числитель,
не уменьшая знаменатель. Причина — описание события, не освобождение от
обязательства. **No entry остаётся no entry:** вычисления никогда не добавляют и
не переписывают строки `daily_habit_entries` и не сохраняют score/streak counters.
Состояние пользователя (настроение, сон и т. п.) в формулу не входит.

**Незавершённые периоды:** дневная и недельная оценка live, включая ещё не
выполненные обязательства и оставшиеся дни текущей недели в знаменателе.
Прогресс `satisfied` означает, что выполнены все обязательства компонента/недели;
`pending` — квота ещё не достигнута и воскресенье ещё не завершилось (в том числе
для будущей недели); `failed` — неполная уже завершённая неделя.

**Серии:** daily streak — последовательные дни `done`; исторические `missed`,
`skipped` и no entry его обрывают. Сегодняшний незавершённый день сохраняет
вчерашнюю серию, а сегодняшний `done` сразу добавляет день. Для недельного
расписания серия измеряется последовательными календарными неделями с закрытой
квотой; текущая неполная неделя не обрывает предыдущую серию, достигнутая квота
сразу добавляет неделю. Незакрытая квота обрывает серию после завершения
воскресенья. Отдельный пропущенный предпочтительный день серию не обрывает.
Текущую дату даёт injected Clock. Серия относится к текущей дате, даже когда
пользователь просматривает прошлый день; UI явно подписывает дату серии.

**Effective-dated configuration и изменения внутри недели:**

1. Ежедневные обязательства используют существующий `habit_versions` lookup
   отдельно на каждую дату. Изменение веса с среды меняет ежедневный вес только
   со среды, прошлые дни сохраняют старый вес.
2. Для недельной части берётся версия **первого активного дня этой календарной
   недели, на который действует недельное расписание**. Она определяет quota,
   weight и preferred weekdays всей недельной части. Изменение недельного веса,
   квоты или preferred days посреди недели применяется к недельной части со
   следующей недели. Новых snapshots и ссылок на версию в entries нет.
3. В недельную часть входят только `done` на активных датах с недельным
   расписанием. Даты с `daily` учитываются отдельно как дневные обязательства.
   При переходе daily ↔ weekly неделя имеет обе части: одно выполнение не
   зачитывается дважды, пропуски daily нельзя закрыть лишними weekly completions.
   Например: Пн–Вт daily weight 1, со Ср 3/week weight 2 → знаменатель `2 + 6`.
4. Первая неполная неделя после создания и недельная часть смешанной недели имеют
   **полную квоту без пропорционального уменьшения**, даже если оставшихся дней
   меньше квоты. Daily учитывает только реально существующие активные даты.
   Это сознательное минимальное правило, а не округление или перенос долга.
5. Единица серии определяется расписанием на текущую (для архива — последнюю
   активную) дату. Daily streak заканчивается на переходе к недельному расписанию;
   weekly streak проходит по смежным неделям с недельной частью и заканчивается
   на неделе без неё. В смешанной неделе для weekly streak важна недельная квота;
   daily часть влияет на weekly score и общий статус недели отдельно.
6. Существующее same-day collapse сохраняется: редактирование версии в её день
   заменяет её, и derived значения пересчитываются. Поздние версии не меняют
   прошлые календарные недели. API отдаёт `weekly_effective_from` и
   `weekly_weight`, а для смешанной недели — отдельные daily/weekly counts.

**Архив:** используется существующий `archived_at`, сохранённый в UTC и
преобразованный в локальную календарную дату. Граница исключающая: начиная с
даты архивации новые обязательства не учитываются. Расчёты до этой даты сохраняют
исторические версии и записи. Уже начатая недельная квота остаётся полной;
последующие недели не создаются. Серия архивной привычки вычисляется по последней
активной дате; её последняя недельная квота разрешается на границе Пн–Вс.
Записи на дату архивации и позднее по-прежнему читаются/редактируются через Stage 3,
но не дают credit вне активного периода. Ничего не удаляется.

Модель Stage 2 хранит только текущее архивирование: unarchive очищает
`archived_at`. После восстановления расчёт снова считает период после создания
активным; прежние архивные интервалы неизвестны. Stage 4 не вводит историю
архивирования и не выдумывает её из `updated_at`. Неконсистентная старая строка
`is_archived=true, archived_at=null` не создаёт вычисляемых обязательств; её
реальные записи остаются доступны через Stage 3. Смена системного часового пояса
может изменить локальную дату UTC-границы; отдельная историческая timezone-модель
в этот этап не входит.

**API:** `GET /api/progress/days/{on}` возвращает дневной score, обязательства и
их исходные статусы (`null` для no entry), неделю выбранной даты и текущие серии.
`GET /api/progress/weeks/{on}` нормализует любую дату к Пн–Вс и возвращает score,
веса и progress привычек. `GET /api/habits/{habit_id}/progress` возвращает текущую
серию с единицей `days`/`weeks` и текущий недельный progress (либо `null`, если
нет активных дат). Данные загружаются пакетно, формулы живут в pure domain layer.

UI расширяет только «Итоги дня»: оценки дня/недели, веса, прогресс, серии,
предпочтительные дни и пояснение переноса. Все новые пользовательские тексты
русские. Миграция не нужна: расчёты используют существующие версии, записи и
архивную дату. Stage 5+ (состояние, новый dashboard, календарь, heatmap,
аналитика, рекомендации, уведомления и т. п.) не реализован.

---

## 11. Dashboard

The Dashboard is the main screen.

### 11.1 Реализовано: Stage 6 — Dashboard & Calendar

Главный Dashboard открывается на сегодняшнем дне (определяется через injected Clock) и предоставляет краткую сводку:

1. **Сегодня**: дата, daily score %, выполненный и требуемый вес, статус «Нет обязательных привычек» (при score = null), список главных привычек дня с текущими статусами и кнопка быстрого перехода в «Итоги дня».
2. **Эта неделя**: weekly score %, выполненный и требуемый вес недели, прогресс недельных привычек (`выполнено / квота`), статусы (`satisfied`, `pending`, `failed`) и предпочтительные дни недели.
3. **Текущие серии (Streaks)**: отображение действующих серий с разделением дневных (`🔥 N дней`) и недельных (`🔥 N недель`), вычисленных через Stage 4 streak engine.
4. **Вчерашнее состояние (Daily State)**: компактный блок состояния вчерашней даты с сохранением трехзначной семантики (`null` != `false`): настроение, энергия, самочувствие, статус и время сна, алкоголь, игры, время за компьютером, короткий превью заметки либо сообщение «Состояние вчера не заполнено».

---

## 12. Calendar

### 12.1 Monthly view

Месячный календарь с сеткой **Monday-first** (`Пн Вт Ср Чт Пт Сб Вс`), переключением месяцев (← / Сегодня / →) и выбором дня.
Ячейка дня показывает:
- номер дня;
- daily score % (или «—» при отсутствии обязательств либо для будущих дней);
- компактный индикатор настроения (`● 4`).

При клике на день открывается **Карточка дня (Day Card)**:
- общая информация: дата, daily score %, вес;
- записи привычек: название, статус (`Выполнено`, `Пропущено`, `Осознанный пропуск`, `Нет отметки`), количество с единицей измерения и заметка;
- состояние дня (Daily State): все 8 полей либо сообщение «Состояние дня не заполнено»;
- ссылка «Открыть день →» для редактирования в «Итогах дня».

### 12.2 Year view

Годовая heatmap в стиле contribution-grid (53/54 недели x 7 дней):
- **Метрика**: Stage 4 daily score (0–100%).
- **Интенсивность**: 6 уровней (0%, 1–25%, 26–50%, 51–75%, 76–99%, 100%).
- **Отсутствие обязательств и будущие дни**: зафиксированы как `null` и отображаются нейтральным цветом без искажения статистики.
- **Сегодня**: показывает актуальный live daily score.
- **Интерактивность**: клик по историческому или сегодняшнему дню открывает карточку дня.

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

### 20.1 Реализовано (Stage 11)

Рекорды и достижения **не хранятся** и вычисляются из уже существующей истории:
нет таблицы `records`, нет mutable-счётчиков вида `best_streak = 17`, миграция не
нужна (Alembic head остаётся `c3f1a7b24d90`).

**Records:** самая длинная серия по привычке (дни/недели, с диапазоном дат),
лучший день (canonical дневной score, при равенстве побеждает самый ранний),
лучшая **завершённая** неделя (≥ 4 наблюдаемых дня, покрытие ≥ 60 %; частичная
текущая неделя не сравнивается с полными), максимум выполненных привычек за день и
лучший полностью прошедший календарный месяц на привычку (≥ 10 дней обязательств).
Общая статистика показывает только честно выводимые метрики (tracked days,
выполнения, эксперименты, первые даты stable/well_supported insight).

**Achievements:** статический versioned-каталог из 17 достижений с stable key,
русскими title/description, category, `achieved`, реальным `achieved_on` (первая
дата достижения, восстановленная из истории; `null`, когда её нельзя восстановить —
никогда «сегодня») и progress `current/target` для locked. Порядок стабильный:
недавние → ближайшие locked → каталог. Категории: streak, consistency, tracking,
daily_state, experiments, insights. Никакого XP, уровней, монет и награды за
запуск приложения. `cancelled` эксперимент не считается завершённым; insights
датируются по существующим `insight_snapshots`, а не по текущей ленте.

Серия берётся из canonical `streak_summary`; missing ≠ failure; архивные привычки
сохраняют свои рекорды. API: `GET /api/records`; Dashboard несёт компактный
`records`-блок. Owl переиспользует `owl_record` (`new_record`), не перебивая
execution failures. Полный контракт: [records.md](docs/records.md).

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

Same-day collapse remains the rule. Stage 3 revisited it now that real daily entries exist and kept it deliberately: an entry stores the user's observation only, with **no configuration snapshot and no `habit_version_id`**, and resolves its unit, decimal rule and weight through this same effective-dated lookup. A snapshot would duplicate the versions table, and a stored version reference would contradict same-day collapse — an edit made today updates today's version, so today's entry must be read through the resulting configuration. Duplicate habit names within an Area are allowed.

Area name and colour changes are not versioned: they are display metadata, and historical habit configuration keeps referential integrity through `area_id`.

---

## 22. Archive

Habits and Areas should normally be archived rather than hard-deleted once historical records exist.

Archived habits remain visible in history and analytics.

An Area that still has active habits cannot be archived: those habits must be archived or moved first, so an active habit never points at an archived Area.

---

## 23. Backup and export

Data protection starts early.

### 23.1 Early safety backup (implemented in Stage 3)

A simple automatic SQLite backup, deliberately no more than that — no scheduler,
no cloud, no restore UI, no integrity dashboard.

Behaviour:

- taken once per application start, before the schema state is inspected;
- at most one automatic backup per calendar day;
- stored in a predictable directory (`<data dir>/backups`), separate from the live
  database;
- named with the date and time (`tracker-2026-09-24-083045.db`);
- **taken with SQLite's own online backup API**, not a file copy: the database runs
  in WAL mode, so recent commits live in `tracker.db-wal` and a blind copy of
  `tracker.db` can be inconsistent or simply miss them;
- skipped for an in-memory database, for the `test` environment, and when the
  database file does not exist yet — a test run or a fresh install must not litter
  backup files;
- a small retention window (the most recent automatic backups) bounds growth;
  files this feature did not create are never touched;
- an existing file is never overwritten (the name is claimed exclusively), so two
  starts in the same second cannot interleave into one file;
- a copy that fails removes the file it had started, because a truncated file with
  a valid-looking name would both look like a real backup and suppress the retry;
- a failure is logged explicitly and never prevents the application from starting.

### 23.2 Logical backup and restore (implemented in Stage 12)

Official format: ZIP with `manifest.json` and `data.json`, `format=tracker-backup`,
`version=1`. Includes all seven persistent user entities: Areas, Habits,
HabitVersion, DailyHabitEntry, DailyState, Experiment, InsightSnapshot. Preserve
IDs, relationships, configuration history, nulls, exact millionths and timestamps.
Exclude infrastructure metadata, secrets, paths, derived records/achievements,
analytics aggregates and browser Owl state.

Settings provides download → select → validate/preview → separate destructive
confirmation. Restore is full replacement, one transaction with foreign keys on;
before deletion retain a durable logical safety copy. Any database failure rolls
back all writes. The app reloads after success. Seven batched read queries; writes
in batches of 1000. Strict version dispatch, DTO and relation validation, ZIP/JSON
corruption and file/path checks, 64 MiB upload / 256 MiB expanded limits configurable
in Settings environment. No migration: `c3f1a7b24d90` stays head.

API: `GET /api/backup`, `POST /api/backup/validate`, `POST /api/backup/restore`,
`GET /api/export/json`, `GET /api/export/csv`. Contract and limitations:
[docs/backup.md](docs/backup.md). No cloud, merge, encryption, scheduled logical
backups, history table or desktop packaging in Stage 12.

### 23.3 Readable export and future Excel output

Stage 12 provides structured JSON and ZIP containing seven UTF-8 CSV source
tables (headers, ISO dates, empty nulls, true/false booleans). These are separate
from the official restorable backup. A native human-readable `.xlsx` is deferred.

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
| **3 — Daily Tracking + Early Backup** ✅ | Daily habit entries, done/missed/skip reason, structured quantities, habit notes, historical edit, future skips, simple automatic SQLite backup |
| **4 — Schedule / Streak / Score Engine** ✅ | Implemented: Monday–Sunday quotas, flexible same-week completion, daily/weekly streaks, weighted day/week score, compact daily-screen UI and boundary/regression tests. Semantics: §10.4. |
| **5 — Daily State** ✅ | Mood, energy, well-being, sleep category, alcohol, gaming, heavy computer use, optional clarifications, daily note |
| **6 — Dashboard & Calendar** ✅ | Implemented: main dashboard, active streaks, week progress, yesterday's state, Monday-first monthly calendar, day card, yearly heatmap with Stage 4 daily score metric, and read-only aggregation APIs |
| **7A — Analytics Dataset** | Canonical analysis dataset, variable typing, missing values, daily and weekly features, reproducible dataset builder |
| **7B — Association Engine** | Same-day binary/categorical/numeric associations, effect sizes, supported pair types |
| **7C — Lag Engine** | Lag 0–7, previous-state features, rolling/weekly windows where justified |
| **7D — Statistical Guardrails** | Minimum N, group balance, effect thresholds, Benjamini–Hochberg/FDR, weekday adjustment, temporal stability checks, groundwork for time-aware uncertainty |
| **7E — Confidence Engine** | Preliminary/stable/well-supported classification, caveats, evidence metadata, persistence across time slices |
| **8 — Insights** | Human-readable findings, graphs, filters, evidence detail, insight history |
| **9 — Owl** | Persistent data-backed owl, slippage detection, prioritization, sarcastic commentary without fabricated facts |
| **10 — Experiments** | Experiment CRUD, before/during/after comparison, state and habit outcomes |
| **11 — Records & Achievements** ✅ | Implemented: derived personal records (longest streak, best day, best week, most completed, per-habit consistency), a static 17-entry achievement catalogue with real historical dates and locked-progress, `GET /api/records`, a compact dashboard preview and Owl record celebration. No persistence, no migration. Semantics: §20.1. |
| **12 — Backup / Export / Restore** ✅ | Logical backup v1 of all seven source entities, JSON and CSV ZIP export, strict validation and preview, explicit confirmation, atomic full replace with safety copy, Settings UI. No migration. See §23 and docs/backup.md. |
| **13 — Hardening** | Migration safety, corruption handling, performance profiling, analytics edge cases, packaging edge cases, UI polish |

---

## 28. Stage boundaries

### Stages 1–3

Create a safe data foundation and begin real daily use.

Stage 3 ends at **manual daily tracking plus the early backup**. Concretely it does
not compute overdue days, streaks, scores, completion percentages, weekly
allocation or any automatic `missed`, and it does not decide whether a completion
happened "on the wrong day". Existing schedule configuration is shown as
information in Stage 3. Stage 4 now evaluates it without changing manual records.

### Stages 4–6

Make Tracker a complete practical habit/state tracker.

At the end of Stage 6, the app should already be genuinely useful without advanced analytics.

### Stages 7A–7E

Build the analytics engine incrementally.

Do not attempt all statistical functionality in one giant implementation.

#### Реализовано: Stage 7A — Analytics Dataset

Канонический контракт `7A.1` доступен через `app.services.analytics.get_dataset`
и read-only `GET /api/analytics/dataset?start=YYYY-MM-DD&end=YYYY-MM-DD`.
Он включает типизированный реестр (`numeric`, `ordinal`, `boolean`, `categorical`),
дневные и недельные строки, устойчивые ID динамических привычек, причины отсутствия
значений и исторически корректные конфигурации. Дневные/недельные веса и проценты
переиспользуют Stage 4; missing, skipped, not applicable, future и no obligations
сохраняются отдельно. Daily State не теряет различия null/false/0 и независимость
оценки/длительности сна и использования компьютера.

Недельный прогресс относится к полной календарной неделе, агрегаты наблюдений State —
только к запрошенным датам до сегодня включительно; оба охвата явно обозначены,
частичные недели и количество наблюдений доступны потребителю. Будущие наблюдения
не становятся неудачами. Пакетное чтение не создаёт записей или миграций.

Полное описание ключей, сериализации, missingness, диапазонов и ограничений:
[контракт Stage 7A](docs/analytics-dataset.md). Это обязательная точка входа для
Stage 7B+. Статистические слои Stage 7 и пользовательский слой Stage 8 описаны
в отдельных analytics-контрактах; рекомендации не реализованы.

### Stages 8–10

Turn validated analytics into understandable insights, guidance, and personal experiments.

#### Реализовано: Stage 8 — Insights

Stage 7 dataset → relationships/lags → statistical guardrails с family-level
BH/FDR → confidence → Stage 8 discovery, gating, deterministic wording и UI.
Страница `/#/insights` («Аналитика») содержит русскую ленту, фильтры периода,
подтверждённости, проверок, сферы/показателя и explorer дневной пары. Detail
сохраняет семантику исходного семейства, показывает evidence, caveats, secondary
lags, графики и историю; frontend не пересчитывает аналитические значения.

Формулировки — типизированные русские шаблоны без LLM. Confidence, strength и
admissibility различаются; blocked скрыты по умолчанию, not evaluable не становятся
preliminary. Same-period пары дедуплицируются, representative lag выбирается
после общей поправки, положительный lag означает X раньше Y.

API: GET `/api/analytics/insights`, `/variables`, `/{fingerprint}`,
`/{fingerprint}/history`; POST `/refresh`. GET и reload не создают историю.
Миграция `b2631e796164` добавляет `insight_snapshots`: stable fingerprint,
период/evidence/labels, версии политик и шаблона; unique `(fingerprint, evaluated_on)`
с conflict handling. Повторный идентичный refresh идемпотентен, изменённая оценка
заменяет снимок за тот же день. История сохраняется после rename/archive.

Граница Stage 8: observational insights; без causal inference, рекомендаций,
prediction и LLM generation. Полный контракт, политики, API и ограничения:
[analytics-insights.md](docs/analytics-insights.md).

#### Реализовано: Stage 9 — Owl Assistant

Сова — компактный контекстный баннер в верхней части Dashboard и Аналитики,
а не модальное окно и не витрина. Принимает уже существующие доменные данные и
возвращает **ровно одно** состояние: подходящий существующий PNG (`owl_pending`,
`owl_failed`, `owl_all_done`, `owl_insight`, `owl_many_misses`, `owl_record`),
короткую эмоциональную реплику и точное фактическое объяснение.

Выбор состояния детерминирован и чист: `app.domain.owl` не имеет БД, часов и
случайности. Правило «после 18:00» получает явный флаг от injected `Clock`;
настроение/самочувствие передаются значениями, где `null` — «не записано».
Нет отдельной таблицы истории совы: состояние пересчитывается из Stage 4
(progress/streaks, включая `streak_summary`), Daily State и Stage 8
(availability, confidence, guardrails).

Dashboard-сценарии: всё выполнено; неотмеченные после 18:00 (с реальным счётчиком,
no-entry ≠ failed); явный `missed` важной привычки (сарказм, запрещён при mood/wellbeing
≤ 2); много пропусков при покрытии ≥ 60 %; оборвавшаяся длинная серия (cautionary);
новый рекорд серии (≥ 5 и строго выше прошлого максимума); недельный рост/спад
(минимум 5 дней, покрытие ≥ 60 %, спад > 20 п.п.). Insights-сценарии: no data,
insufficient data, guardrails blocked (с реальной причиной), preliminary only,
stable/well_supported и отдельное подчёркивание ненулевого lag в корреляционной
формулировке. Приоритеты гарантируют одного победителя; контексты Dashboard и
Insights не смешиваются.

API: поле `owl` добавлено в существующие ответы `GET /api/dashboard` и
`GET /api/analytics/insights`; dataset повторно не строится и новых SQL-запросов
на сценарий нет. Anti-spam — client-side: session dismiss по стабильному
fingerprint и cooldown сарказма ~24 часа. Сарказм допустим только при реальном
пользовательском действии/провале; отсутствие данных — это не провал.

Миграция не нужна. Полный контракт, таблица приоритетов/ассетов и ограничения:
[owl-assistant.md](docs/owl-assistant.md).

#### Реализовано: Stage 10 — Experiments

Эксперимент — заданный пользователем ограниченный период (название, гипотеза,
протокол, даты). Tracker описывает, как **уже существующие** данные соотносились
с этим окном: **до / во время / после** — сравнимыми периодами равной длины.
Это описательный, а не причинный анализ: UI говорит «во время было выше/ниже»,
никогда — «эксперимент улучшил/привёл к». Эксперимент не создаёт привычку.

Lifecycle (`scheduled`, `active`, `completed`, `cancelled`) не хранится колонкой,
а выводится из дат и `cancelled_on` (injected `Clock`), поэтому статус не может
разойтись с календарём. `before`/`after` равны длине `during`, отмена сокращает
`during` до фактической даты и начинает `after`. Missing ≠ failed: неотмеченный
день влияет только на coverage и не подставляется нулём. Сравнение считается
достаточным при ≥ 3 наблюдаемых днях и покрытии ≥ 60 % в `before` и `during`.

Домен (`app.domain.experiments`) чистый — без БД, часов и random; сервис строит
канонический Stage 7A dataset **один раз** на detail (окно `before + during +
after`), новых формул и SQL-запросов на сценарий нет. Сравниваются общий прогресс
(`daily.score`), привычки (`done / obligation`) и поля Daily State; серия по дням
сохраняет пропуски. Overlap разрешён, но честно помечается на detail.

API: `GET/POST /api/experiments`, `GET/PATCH /api/experiments/{id}`,
`POST /api/experiments/{id}/cancel`; завершение следует из даты, отдельного
`/complete` нет. Миграция `c3f1a7b24d90` (`down_revision = b2631e796164`)
добавляет `experiments` (check-constraints: непустой title, `start_date <= end_date`;
индекс по `start_date`). Правки: `scheduled`/`active` меняют даты и текст,
`completed`/`cancelled` даты immutable.

Сова минимально расширена и переиспользует `owl_insight` (`experiment_active`,
`experiment_no_data`, `experiment_completed`), новых PNG нет. Frontend:
`/#/experiments` (список + форма) и `/#/experiments/:id` (timeline, сравнения,
график без нулей вместо пропусков, coverage, нейтральный итог). Полный контракт:
[experiments.md](docs/experiments.md).


#### Реализовано: Stage 11 — Records & Achievements

Stage 11 добавляет слой долгосрочного прогресса поверх существующей истории:
личные рекорды и дискретные вехи, **вычисляемые**, а не хранимые. Миграция не
нужна — Alembic head остаётся Stage 10 (`c3f1a7b24d90`).

`app.domain.records` — чистый доменный слой: один ограниченный проход по дню,
из которого выводятся недели и месяцы; ни БД, ни часов, ни random. Record types:
самая длинная серия (дни/недели), лучший день (самый ранний wins on tie), лучшая
завершённая неделя (≥ 4 наблюдаемых дня, покрытие ≥ 60 %), максимум выполненных
привычек за день, лучший полностью прошедший месяц на привычку (≥ 10 дней
обязательств). Серия не заводит третий алгоритм: используется canonical
`streak_summary`, после Stage 11 опирающийся на единый span-итератор
(`daily_runs`/`daily_streak_milestones`).

`app.domain.achievements` — статический versioned-каталог из 17 достижений
(streak/consistency/tracking/daily_state/experiments/insights) с stable key,
русскими формулировками, реальным `achieved_on` (первая дата достижения;
`null`, когда восстановить нельзя — никогда «сегодня») и progress для locked.
Порядок стабильный: недавние (порог 7 дней через injected `Clock`) → ближайшие
locked → индекс каталога. Ни XP, ни уровней, ни монет, ни награды за запуск.

`app.services.records` делает **не более пяти** пакетных чтений независимо от
размера истории (истории привычек; даты Daily State; эксперименты; первые даты
confidence из `insight_snapshots`) и переиспользует in-memory histories Dashboard.
Missing ≠ failed, архивные привычки сохраняют рекорды, `cancelled` эксперимент не
считается завершённым, insights датируются по snapshots, а не по текущей ленте.

API: `GET /api/records`; `GET /api/dashboard` несёт компактный `records`-блок.
Frontend: `/#/records` («Рекорды и достижения») и `RecordsPreviewCard` на
Dashboard, полностью на русском, только CSS без новых картинок. Owl (Stage 9)
празднует новый рекорд серии через существующий `owl_record` (`new_record`,
приоритет 60) — ниже execution failures. Полный контракт:
[records.md](docs/records.md).

### Stage 12 — implemented; Stage 13 — next

Stage 12 implements local backup/export/restore as specified in §23. Frozen v1
compatibility, two-database roundtrip, replacement, real late-constraint rollback,
and records/configuration/experiment regressions are integration-tested.
Stage 13 covers hardening and reliability. Desktop packaging remains separately
deferred; it is not part of the completed Stage 12 scope.

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
