# Stage 8 — Insights

Stage 8 — пользовательский слой над Stage 7, контракт `8A.1`. Страница
`/#/insights` («Инсайты» → «Аналитика») показывает наблюдаемые ассоциации,
доказательства, ограничения и историю оценок. Формулировки детерминированы;
LLM, прогнозов, causal inference и recommendation engine нет.

## Архитектура

1. `app.services.insights.evaluate` валидирует период и строит один Stage 7A
   dataset с расширением диапазона для lag alignment и временных сегментов.
2. Discovery задаёт ограниченное пространство гипотез. Stage 7 relationships,
   lags и guardrails оценивают всё семейство, включая BH/FDR, до выбора карточек.
3. Engine группирует пары, выбирает representative lag и использует Stage 7E
   confidence. Большой коэффициент сам по себе не означает `well_supported`.
4. Типизированный formatter превращает evidence в русский текст, сохраняя
   раздельно strength, confidence, guardrail verdict и presentation status.
5. Detail содержит ту же гипотезу и то же семейство, графики и историю. Открытие
   discovery-карточки не заменяет общую поправку проверкой одной пары.
6. Только explicit refresh материализует снимки. GET не пишет данные.

Frontend форматирует числа и масштабирует SVG. Он не рассчитывает коэффициенты,
coverage, confidence, guardrails, BH/FDR или rolling averages.

## Discovery и candidate policy

По умолчанию: 90 дней, допустимый период 7–730 дней, конец не позднее сегодня.
Бюджет 6 переменных: daily score, первые 3 Daily State по фиксированному приоритету,
completion двух активных привычек по весу и ID. Можно расширить бюджет до 8,
уменьшить ниже 6 нельзя. Отсутствующие привычки не замещаются произвольными
показателями. Default lags: 0…+7 дней; максимум 480 гипотез.

Для 6 доступных переменных: 15 пар × (1 same-period + 14 направленных lagged)
= 225 гипотез. Они образуют одно correction family. Фильтры применяются к
результатам, не уменьшая FDR denominator. Явная проверка X/Y — explorer одной
заранее выбранной гипотезы, `family_mode=single`; FDR и family rank не применяются.
Это другая постановка вопроса; её нельзя читать как результат общего поиска.

| Результат | Показ |
| --- | --- |
| `pass` | Default feed с уровнем preliminary/stable/well-supported |
| `pass_with_warnings` | Default feed, статус «Есть ограничения», отдельный confidence и caveats |
| `blocked` | Скрыт из default feed; доступен фильтром, помечен «Не прошло проверки» |
| Нерассчитываемая связь | `not_evaluable`, confidence=null, объяснение причины; не предварительный сигнал |
| Отрицательный lag | Explorer/явное включение скрытых, с обратным временным порядком |

Пустые данные определяются по наблюдаемым парам (`sample.n > 0`), а не только
eligible dates. Различаются no data, insufficient data, no guardrails passed,
preliminary only и отсутствие совпадений с фильтрами. Сводные counts по статусам
относятся ко всему discovery; показанное число — к отфильтрованной ленте.

## Политика формулировок

- Preliminary: «Пока есть предварительный сигнал…» — без обещания устойчивости.
- Stable: «В вашей истории наблюдается связь…».
- Well-supported: «Эта связь устойчиво повторяется в вашей истории…».
- Positive / negative: «выше / ниже», «чаще / реже» по направлению ассоциации;
  near-zero не превращается в направленную ассоциацию.
- Boolean: дни с отметкой, частота совместных отметок или сравнение групп «Да/Нет».
- Numeric/ordinal: относительные значения показателей, без нормативной оценки.
- Lagged: `+1` означает X раньше Y; `-1` означает Y раньше X. Для отрицательного
  lag предложение начинается с более раннего показателя, добавляются подпись
  «Обратный порядок» и caveat. Это временная последовательность, не причинность.
- Weekly: backend explorer поддерживает недельные показатели и слова «неделя /
  на следующей неделе»; дневные и недельные единицы не смешиваются.

Запрещены утверждения «влияет», «вызывает», «приводит к», «из-за», «причина»,
а также рекомендации «вам следует», «вам нужно», «лучше», «избегайте».
Шаблоны проверяются тестами. Отрицание причинности в caveats поясняет границу
вывода; оно не является causal claim. Пользовательские названия вставляются
как названия показателей и не анализируются как инструкции.

## Fingerprint и группировка задержек

SHA-256 от версии идентичности, kind, стабильных variable keys, grain и lag.
Дата, mutable label, коэффициент, confidence и версии аналитических политик
в fingerprint не входят. Rename привычки сохраняет идентичность.

При lag=0 X↔Y канонизируется сортировкой keys и не дублируется. Ненулевые lag
и направления имеют отдельные fingerprint. Display group объединяет пару
независимо от порядка. Representative выбирается только после family-level
guardrails/FDR: admissibility, confidence, абсолютная величина, sample size,
меньший абсолютный lag и стабильные tie-breakers. Это не «оптимальная задержка».
Все secondary lags остаются в detail с индивидуальными verdict, confidence,
числами и русской подписью пары/временного порядка, различающей два направления.

## Snapshot / history

Миграция `b2631e796164` (после `d5a1c09e2401`) создаёт `insight_snapshots`.
Существует DB unique constraint `(fingerprint, evaluated_on)`, индексы по
fingerprint и evaluated_on. SQLite conflict handling защищает параллельные
refresh от дублирования и ошибки уникальности; это не только SELECT→INSERT.

POST refresh заново оценивает discovery и сохраняет representative каждой
группы, включая скрытые. Он не сохраняет произвольную explorer-пару вне этого
обзора. Один fingerprint — одна строка за календарный день оценки:

- первый refresh создаёт строку;
- повторный идентичный refresh не меняет строку и timestamps;
- изменение evidence, labels или периода в тот же день обновляет строку;
- следующий день добавляет строку;
- смена representative lag может создать другой fingerprint в той же группе.

Snapshot хранит период, stable keys, labels на момент оценки, coefficient, n,
coverage, confidence, verdict, причины, wording и версии insight/guardrail/
confidence policies и шаблона, created_at/updated_at. Это summary, не копия
dataset и не полная архивная evidence. История отдаёт последние 200 снимков
в хронологическом порядке; first_seen считается по всем сохранённым снимкам.
Архивирование не удаляет историю: старые labels сохраняются, текущее архивное
состояние отдельно возвращается и отмечается в UI. Архивные привычки исключены
из default discovery, но остаются в каталоге и explorer.

GET list/detail/history и browser reload не создают снимков. Обновление истории
явное, через кнопку. Она сохраняет общий обзор, что объяснено рядом с кнопкой.

## API

Все пути имеют префикс `/api/analytics/insights`.

| Метод / суффикс | Назначение |
| --- | --- |
| GET (без суффикса) | Aggregated feed: обязательные start/end; x/y/lag включают explorer; lags/max_variables задают sweep; include_hidden/confidence/verdicts/variables фильтруют результат |
| GET `/variables` | Каталог русских labels, типов, сфер, архивности и участия в default sweep |
| GET `/{fingerprint}` | Обязательные start/end/x/y; lag и mode должны соответствовать выбранной карточке; charts и history включены |
| GET `/{fingerprint}/history` | Только сохранённая история, без построения dataset; неизвестная история — пустой массив |
| POST `/refresh` | JSON start/end, необязательные lags/max_variables; возвращает analytics и created/updated/unchanged/total |

GET `/refresh` возвращает 405. Невалидный период/бюджет — 422; несоответствие
известной идентичности — 422 `insight_identity_mismatch`, неизвестный fingerprint
detail — 404 `insight_not_found`. Frontend передаёт identity и режим карточки,
не реконструируя их по label или coefficient.

## UI и evidence

Русская страница включает presets 30/90/180/365 дней, custom range, фильтры
confidence, проверок (включая hidden), сферы и показателя. Explorer выбирает
конкретную дневную пару и сдвиг (0…+7, -1…-3). Другие поддерживаемые сдвиги и
weekly доступны через API; UI не обещает недельный discovery.

Карточка показывает формулировку, timing, раздельные confidence и verdict, n,
coverage, caveats и первый снимок. Detail раскрывает метод, коэффициент,
направление/strength, eligible sample, coverage и минимальное покрытие сегмента,
порог эффекта, q/FDR и размер семейства, weekday-adjusted coefficient,
согласованность методов, все checks, альтернативные задержки, временные сегменты
и сохранённую историю с provenance. Цвет дополняет текстовые состояния.

SVG: числовые временные ряды с backend rolling, boolean strip, scatter числовых
пар, сравнение boolean-групп, lag profile и early/middle/recent segments.
Null остаётся отсутствием точки/столбца, разрывы не соединяются через пропуск.
Negative segment bars не обрезаются. Графики сопровождаются текстом и evidence
таблицами; коэффициенты и caveats доступны без чтения цвета или рисунка.

`useAsyncData` отменяет запросы и игнорирует устаревшие ответы. Feed/detail
дополнительно привязаны к ключу запроса, поэтому evidence старого периода или
другой карточки не показывается под новой подписью. Refresh response также
игнорируется после смены запроса. Есть loading, error и empty states.
Узкие экраны используют одну колонку; широкие таблицы прокручиваются внутри
detail, без горизонтального переполнения всей страницы.

## Производительность и проверки

List/detail/refresh: один dataset build и одно guardrail family evaluation на
запрос, затем вычисления в памяти. Detail заново проверяет семейство ради
согласованной поправки; серверного кеша нет. Feed — один запрос на все карточки,
плюс отдельный catalogue. Detail — один запрос на evidence/charts/history.
History не строит dataset: один запрос snapshots плюс пакетные habit metadata;
нет SQL на строку истории. Метаданные и first_seen загружаются пакетно.
Snapshot writes идут по сохраняемым группам, а не по всем гипотезам.

Регрессии проверяют один build/family, одинаковый SQL count при расширении
набора lag, read purity, идемпотентность, конкурентный refresh, rename/archive,
latest-history limit, gating, wording, UI identity, stale responses и chart gaps.
Migration drift и downgrade→upgrade покрываются полным pytest.

## Ограничения

Наблюдательные данные: association ≠ causation. `blocked` не означает отсутствия
связи; preliminary не означает плохую связь. Autocorrelation, пропуски,
неравномерное покрытие, ordinal scales и продуктовые пороги остаются ограничениями.
Discovery ограничен бюджетом/приоритетом, не перебирает все возможные показатели;
изменение состава активных привычек меняет семейство. Snapshot — последняя оценка
за день, не неизменяемый журнал всех запусков. Нет автоматического snapshot при
чтении, истории всех вторичных lag, causal inference, рекомендаций, prediction
или LLM generation.
