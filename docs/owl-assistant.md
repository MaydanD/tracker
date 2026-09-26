# Stage 9 — Owl Assistant

Stage 9 — контекстный маскот-помощник поверх уже существующих данных. Сова
показывает **ровно одно** состояние: существующий PNG, короткую эмоциональную
реплику (`caption_line1`) и точное фактическое объяснение (`caption_line2`).
Это компактный баннер в верхней части контента, не модальное окно; весь
пользовательский текст русский.

## Архитектура

- `app.domain.owl` — чистый детерминированный selector и типы. Нет БД, часов,
  random и изменяемого глобального состояния. Правило «после 18:00» приходит
  явным флагом `after_hours`, который route получает из injected `Clock`
  (`clock.now()`); mood/wellbeing передаются значениями.
- `app.services.owl` — адаптеры. Собирают контекст из уже вычисленных данных:
  для Dashboard — из тех же in-memory Stage 4 histories/progress и Daily State,
  для Аналитики — из готового payload Stage 8. Отдельный dataset не строится.
- Контекст проверок/построения: `DashboardRead.owl` и `InsightAnalytics.owl`.

Сова не дублирует аналитическую математику. Daily/weekly score, coverage,
streak, availability, confidence и guardrail verdict берутся у Stage 4/Stage 7/8.
Единственное расширение — `streak_summary` в `app.domain.progress` (тот же
канонический streak-движок), потому что рекорд требует прошлого максимума;
`current_streak` теперь делегирует ему, второго алгоритма нет.

## Priority

Одновременно верно много событий — показывается один. Меньшее число = выше.
Контексты Dashboard и Insights не смешиваются.

| Контекст | owl_id | Приоритет |
| --- | --- | --- |
| Dashboard | `failed` | 10 |
| Dashboard | `pending` | 20 |
| Dashboard | `many_misses` | 30 |
| Dashboard | `streak_broken` | 40 |
| Dashboard | `weekly_drawdown` | 50 |
| Dashboard | `new_record` | 60 |
| Dashboard | `all_completed` | 70 |
| Dashboard | `weekly_positive` | 80 |
| Insights | `no_data` | 10 |
| Insights | `insufficient_data` | 20 |
| Insights | `guardrails_blocked` | 30 |
| Insights | `stable_insight` / `lag_insight` | 40 |
| Insights | `preliminary_only` | 50 |

Победитель детерминирован: сортировка по `(priority, owl_id)`.

## Asset mapping

| owl_id | Asset |
| --- | --- |
| `pending` | `owl_pending` |
| `failed`, `streak_broken` | `owl_failed` |
| `all_completed`, `weekly_positive` | `owl_all_done` |
| `many_misses`, `weekly_drawdown` | `owl_many_misses` |
| `new_record` | `owl_record` |
| `no_data`, `insufficient_data`, `guardrails_blocked`, `preliminary_only`, `stable_insight`, `lag_insight` | `owl_insight` |

Новых PNG нет: для качеств данных и инсайтов используется `owl_insight` с
корректным нейтральным текстом.

## Dashboard-сценарии

- **all_completed** — есть обязательства и `completed_weight >= required_weight`.
- **pending** — после 18:00 есть неотмеченные обязательства; L2 показывает
  реальный счётчик. Отсутствие отметки никогда не считается `failed`.
- **failed** — явно записанный `missed` важной привычки (`weight >= 2`).
- **many_misses** — ≥ 3 записанных `missed` за окно 3 дня и покрытие ≥ 60 %.
- **streak_broken** — `current_streak == 0`, прошлая серия ≥ 7 и оборвалась
  недавно (14 дней); тон `cautionary`.
- **new_record** — текущая серия ≥ 5 и строго больше прошлого максимума.
- **weekly_drawdown** — прошлая завершённая неделя vs предыдущая, обе с ≥ 5
  днями и покрытием ≥ 60 %, падение > 20 п.п.
- **weekly_positive** — прошлая неделя ≥ 85 %, ≥ 5 дней, покрытие ≥ 60 %.

Неполные периоды, плохое покрытие, отсутствующие данные и первый запуск не
дают агрессивных состояний. `weekly_drawdown`/`streak_broken` требуют сравнимых
завершённых периодов.

## Insights-сценарии

- **no_data** — наблюдений нет; нейтрально, без оценки пользователя.
- **insufficient_data** — недостаточно для анализа; `supportive`, показывает
  реальный размер выборки, если он есть.
- **guardrails_blocked** — связь заблокирована; показывается реальная причина
  из Stage 7D (`blocking_reasons`).
- **preliminary_only** — есть только предварительные сигналы.
- **stable_insight** — лучший `stable`/`well_supported` с прошедшим guardrail;
  L2 использует wording Stage 8 (`text.full`).
- **lag_insight** — тот же случай с ненулевым lag; формулировка корреляционная
  (`… сильнее всего наблюдается со сдвигом: …`), без причинности.

Запрещены `вызывает`, `приводит`, `улучшает`, `ухудшает`. Направление lag
берётся из конвенции Stage 8 (`text.timing`), не изобретается заново.

## Sarcasm policy

Сарказм только при реально зафиксированном действии/провале: явный `missed`,
много записанных пропусков при хорошем покрытии. Сарказм запрещён при
`mood <= 2` или `wellbeing <= 2` (только реально записанных; `null` ничего не
подавляет), а также для no data, insufficient, preliminary, blocked и низкого
покрытия. При подавлении тон понижается до `cautionary`/`neutral`.

## Anti-spam

Отдельной таблицы БД нет.

- **Session dismiss** — dismissible-состояние скрывается по стабильному
  `fingerprint` в `sessionStorage`; навигация и re-render не возвращают его.
- **Deduplication** — `fingerprint` зависит от сценария и значимых данных;
  reload не создаёт новый, изменение пропусков — создаёт.
- **Sarcasm cooldown** — не более одного агрессивного сообщения за ~24 часа;
  следующее показывается с `fallback_line1` в тоне `cautionary`. Всё хранится
  локально в браузере.

`failed` не dismissible: записанный провал — факт, который стоит увидеть.
Остальные состояния можно скрыть.

## API и производительность

`owl` добавлен в уже существующие ответы:

- `GET /api/dashboard` → `DashboardRead.owl`;
- `GET /api/analytics/insights` (и в `analytics` ответа refresh) →
  `InsightAnalytics.owl`.

На запрос: один dataset build (для Аналитики — существующий), затем выбор в
памяти. Нет N+1 и запросов внутри scenario loop. Frontend только форматирует
и рендерит; статистические решения остаются на backend.

## UI

`OwlAssistantBanner` подключён на Dashboard и на Аналитике в верхней части
контента, до карточек. Отображает один PNG с сохранением пропорций, L1 и L2,
dismiss-контрол только для dismissible-состояний, `alt="Сова-помощник"`.
Компактность и существующие токены дизайн-системы; отдельной визуальной системы
нет.

## Ограничения

- Состояние не сохраняется: это реконструкция из текущих данных, без истории.
- «Продвинутые» Insights-состояния зависят от выбранного на странице периода и
  фильтров, потому что используют тот же payload, что и лента.
- Cooldown и dismiss — на браузерную сессию, не между устройствами.
- Нет push-уведомлений, достижений, отдельной event-sourcing системы и новой
  базы истории совы.
