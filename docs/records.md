# Stage 11 — Records & Achievements

Stage 11 добавляет слой долгосрочного прогресса: пользователь видит свои **реальные
личные рекорды, вехи и достижения**, полученные **из уже существующих данных**
Tracker.

Это **presentation/domain layer поверх существующей истории**, а не новая
параллельная система истины. Рекорды и достижения вычисляются детерминированно из
source-of-truth: конфигурации привычек, `daily_habit_entries`, Daily State,
экспериментов и `insight_snapshots`.

## Records ≠ Achievements

- **Record** — динамический максимум, который можно побить: самая длинная серия,
  лучший день, лучшая неделя, максимум выполненных привычек за день, лучший месяц
  конкретной привычки.
- **Achievement** — дискретная веха, которая, будучи достигнутой, остаётся
  достигнутой: первая серия 7 дней, 100 выполнений привычки, первый устойчивый
  инсайт.

## Никакой дешёвой геймификации

Нет XP, уровней, монет, loot, daily rewards, fake rarity, battle pass, leaderboard
и social comparison. Каталог намеренно короткий: 17 достижений вместо 150. Каждое
отмечает то, что пользователь реально сделал.

## Persistence

**Миграция не нужна.** Ни рекорды, ни достижения не хранятся: нет таблицы
`records` и нет mutable-счётчиков вида `best_streak = 17`. Рекорд — чистая функция
текущей истории, поэтому удаление исходных данных может законно изменить рекорд
или «снять» достижение. Это осознанное поведение для локального однопользовательского
приложения; immutable fantasy history, противоречащей текущей БД, не создаётся.
Alembic head остаётся Stage 10: `c3f1a7b24d90`.

## Архитектура

- `app.domain.records` — чистый доменный слой: один ограниченный проход по дню,
  из которого выводятся недели и месяцы. Ни БД, ни часов, ни random: `today`
  передаётся явно.
- `app.domain.achievements` — статический versioned-каталог из 17 достижений,
  детерминированная оценка и порядок. Определения живут в коде, не в БД.
- `app.services.records` — orchestration: **не более пяти** пакетных чтений на
  запрос, независимо от размера истории (истории привычек; даты Daily State;
  строки экспериментов; первые даты по confidence из snapshots). Данные грузятся
  один раз, вычисление — в памяти. Dashboard переиспользует уже загруженные
  in-memory histories и не делает отдельный dataset build.
- `app.schemas.records` — типизированные контракты (`RecordsRead`,
  `RecordsPreviewRead`).
- `app.api.routes.records` — тонкий handler: берёт injected `Clock`, вызывает
  сервис, проецирует результат.

## Canonical math

Рекорды не заводят третий алгоритм streak. Серия берётся из
`app.domain.progress.streak_summary` (Stage 4/9), который после Stage 11 использует
единый span-итератор `_iter_daily_spans` — тот же, что `daily_runs` и
`daily_streak_milestones`. Дневной score, недельный score, веса и обязательства —
тоже канонические (`day_progress` / `week_progress`).

**missing ≠ failure.** День без отметки просто отсутствует: он не добавляет день в
серию и не обнуляет её. Серия не меняет семантику ради достижений. Незавершённый
сегодняшний день сохраняет вчерашнюю серию; архивный период замораживается на
последнем активном дне (`streak_as_of`).

## Record types

| Record | Что показывает | Детерминизм |
| --- | --- | --- |
| `longest_streak` | Лучшая серия по одной привычке (дни или недели) + текущая серия и диапазон дат. | Лучшая серия по длине; tie-break по текущей серии и `habit_id`. |
| `best_day` | Лучший канонический дневной score. | Побеждает **самый ранний** из равных дней; ties подсчитываются. |
| `best_week` | Лучшая **завершённая** календарная неделя. | Только недели с ≥ 4 наблюдаемыми днями и покрытием ≥ 60 %. Текущая частичная неделя не сравнивается с полными. |
| `most_completed` | Максимум реально выполненных обязательств за день (unweighted). | Самый ранний из равных; ties подсчитываются. |
| `consistency` | Лучший полностью прошедший календарный месяц по доле выполненных дней, по каждой привычке. | Только месяцы с ≥ 10 днями обязательств; ratio — `done / obligation`; weekly-привычки представлены своей серией. |

## Summary

Верхний блок честно показывает только выводимые метрики: `tracked_days`,
`first_tracked_day`, `habit_completions`, `experiments_created`,
`completed_experiments`, `stable_insight_on`, `well_supported_insight_on`. Ничего
не придумывается.

## Achievement catalogue

| key | title | category |
| --- | --- | --- |
| `first_habit_completion` | Первое выполнение | consistency |
| `streak_7` | Серия 7 дней | streak |
| `streak_30` | Месяц без отрыва | streak |
| `streak_100` | Сто дней подряд | streak |
| `habit_50_completions` | 50 выполнений | consistency |
| `habit_100_completions` | 100 выполнений | consistency |
| `first_perfect_day` | Идеальный день | consistency |
| `perfect_week` | Идеальная неделя | consistency |
| `tracked_30_days` | 30 дней трекинга | tracking |
| `tracked_100_days` | 100 дней трекинга | tracking |
| `daily_state_30` | 30 дней состояния | daily_state |
| `daily_state_100` | 100 дней состояния | daily_state |
| `first_experiment` | Первый эксперимент | experiments |
| `first_completed_experiment` | Первый завершённый эксперимент | experiments |
| `experiments_5` | Пять экспериментов | experiments |
| `first_stable_insight` | Первый устойчивый инсайт | insights |
| `first_well_supported_insight` | Первый подтверждённый инсайт | insights |

Каждое достижение имеет stable `key`, русские `title`/`description`, `category`,
`achieved`, `achieved_on` и `progress { current, target }`. Для locked-достижений
progress идёт из source-of-truth, без отдельных incremental-счётчиков.

`cancelled` эксперимент **не** считается завершённым: completed датируется
эффективным последним днём окна.

## Historical achievement date

`achieved_on` — **реальная дата первого достижения**, восстановленная из истории:
для серии — день, когда run впервые дошёл до цели (`daily_streak_milestones`); для
100 выполнений — сотый по счёту `done`; для трекинга — n-й уникальный день; для
экспериментов — дата завершения окна. Если дату разумно восстановить нельзя,
`achieved_on = null`, и UI показывает «—». **Сегодняшняя дата задним числом не
проставляется.**

Insights используют существующие `insight_snapshots` (min `evaluated_on` по
confidence), а не текущую ленту — иначе давно устойчивая связь датировалась бы
сегодня. Старые insights специально не пересчитываются.

## Порядок достижений

Порядок стабильный и не «прыгает» между refresh:

1. недавно достигнутые (новейшая дата первой);
2. locked — по близости к цели (`current / target`);
3. индекс в каталоге — финальный детерминированный tie-break.

`RECENT_ACHIEVEMENT_DAYS = 7`; используется injected `Clock`, не naked
`date.today()`. «Недавно получено» — presentation, не notification system.

## Archived habits

Исторические рекорды архивной привычки **не исчезают**: record history и
достижения остаются. UI помечает привычку как `Чтение · в архиве`.
Stable identity — `habit_id`; текущее display name берётся из последней версии
(`versions[-1].name`), без новой snapshot-истории имён.

## Experiments и Insights

Experiments: Records page показывает число созданных и завершённых экспериментов и
achievements вокруг них; отдельного record-analytics движка нет. Insights:
достижения используют snapshots (см. выше), новых статистических вычислений нет.

## API

| Метод | Путь | Назначение |
| --- | --- | --- |
| `GET` | `/api/records` | `summary`, `records`, `achievements`, `recent_achievements`, `achieved_count`, `total_count`. |

Dashboard включает компактный `records: RecordsPreviewRead | null` в
`GET /api/dashboard` (top record + latest achievement + `X из Y`). Отдельного
endpoint на каждый record нет.

## Performance

Рекорды требуют полной истории, поэтому full-history здесь допустим, но dataset
строится **один раз**: не более пяти batched SQL-запросов на запрос, без
`for habit: SELECT entries`. Dashboard переиспользует in-memory histories, уже
загруженные для себя.

## Owl

Сова (Stage 9) уже умеет `owl_record` (`new_record`, приоритет 60): она
празднует новый канонический рекорд серии (`current_streak ≥ 5` и строго выше
прошлого максимума) через `StreakSummary`, переиспользуя `owl_record.png`. Новых
PNG нет. Приоритет `new_record` **ниже** execution failures (`failed` 10,
`pending` 20, `many_misses` 30), `streak_broken` 40 и `weekly_drawdown` 50, поэтому
celebration не перебивает более важные события. Stage 11 не переписывает Owl: он
опирается на тот же canonical streak.

## Frontend

`/#/records` («Рекорды и достижения»): общая статистика, карточки личных рекордов
(включая consistency), достижения, сгруппированные в «Недавно получено» /
полученные / «Следующие цели» с progress-барами. Компактный `RecordsPreviewCard`
на Dashboard. UI полностью русский; raw enum keys и unit-идентификаторы не
печатаются. Новых картинок и тяжёлых icon library нет — только CSS.

## Гарантии

- derivable from source history; no fake counters;
- no XP / levels / currency / rewards;
- canonical streak и canonical progress;
- archived history preserved;
- achievements use stable catalogue keys;
- missing ≠ failure;
- deterministic historical dates where possible, `null` (не «сегодня») иначе;
- no new migration.
