# Stage 7C — связи и корреляции

Версия ответа `7C.1`. Анализируются только **одновременные ассоциации** двух
канонических переменных на совпадающих датах или неделях. Коэффициент не означает
причинность, пользу, вред, надёжность или статистическую значимость. Нельзя
интерпретировать положительный знак как «улучшает», отрицательный — как «ухудшает».
Нет лагов, прогнозов, рекомендаций, рейтингов факторов, автоматических инсайтов и UI.

## Архитектура

`services.relationships.get_relationships` один раз вызывает
`services.analytics.get_dataset` за выбранный период. Затем чистые функции Stage 7C
работают в памяти. Stage 7B `make_series`, `coverage`, `source_coverage`, `units`
задают проекции, исторические единицы, coverage и неполноту периодов. Сводки,
rolling и предыдущий период 7B не вычисляются: для корреляции нужны его ряды.
Stage 7C не читает исходные таблицы/конфигурации и не повторяет формулы Stage 4.

- `domain/analytics/correlation.py`: чистые Pearson, average ranks, Spearman,
  point-biserial и Phi; функции возвращают typed `Metric`.
- `domain/analytics/relationships.py`: валидация, выравнивание, pairwise deletion,
  выбор методов, coverage, анализ одной пары и матрицы.
- `domain/analytics/relationship_types.py`: dataclasses и централизованный `POLICY`.
- `services/relationships.py`: единственная загрузка канонического датасета.
- `schemas/relationships.py`, `api/routes/relationships.py`: JSON/OpenAPI и HTTP.

Минимальное обратно совместимое расширение registry `7A.1`:
`habit.<id>.daily.completion` (boolean). Явный `done` → true,
явный `missed` или `skipped` → false. Отсутствие записи остаётся null/source_missing,
вне активности — null/not_applicable, будущее — null/future.
`status` сохраняет различие missed/skipped, причина пропуска остаётся в источнике.
Это индикатор **выполнения среди явных отметок**, а не новый дневной score и не
трактовка неотмеченных дней как невыполненных. Ключ стабилен при переименовании.

## API

Обязательны включительные `start` и `end`. Одна пара:

```text
GET /api/analytics/relationships?start=2026-09-01&end=2026-09-30&x=state.mood&y=state.sleep_minutes
```

Матрица — повторяющийся `variables`:

```text
GET /api/analytics/relationships?start=2026-09-01&end=2026-09-30&variables=state.mood&variables=state.energy&variables=daily.score
```

Смешивать `x/y` с `variables` нельзя. Для пары нужны два разных ключа;
для матрицы 2–24 уникальных ключа длиной 1–160 символов. Период — 1–1830 дней.
Пустые, повторяющиеся, неизвестные ключи и неверные даты дают HTTP 422 с русским
сообщением в существующем `error` envelope. Структурные ограничения проверяются
до загрузки БД; неизвестные ключи — по загруженному registry. Все переменные
автоматически не выбираются. Привычка должна присутствовать в registry периода.

```python
from app.services.relationships import get_relationships

result = get_relationships(
    session, start, end, ("state.mood", "state.sleep_minutes"),
    today=clock.today(), pair=True,
)
# pair=False (по умолчанию): матрица выбранных переменных.
```

Пара сохраняет ориентацию `x/y` запроса. Матрица сортирует ключи лексикографически,
возвращает каждую комбинацию `A < B` ровно один раз, без диагонали. Результаты не
сортируются по силе. Одинаковые данные, даты и Clock дают одинаковый ответ.

Верхний ответ: `contract_version`, `dataset_contract_version`, `today`, `period`,
`mode`, `policy`, `minimum_weekly_source_coverage`, `relationships`.
Каждая связь содержит metadata `x/y`, `grain`, основной `method`, `coefficient`,
`direction`, `strength`, `n`, `coverage`, `status`, `reason`, все `metrics`,
`boolean_x/y`, `contingency`, `units_x/y`, `limitations`.

## Методы и статусы

| Тип X ↔ тип Y | Основной метод | Дополнительно |
| --- | --- | --- |
| numeric ↔ numeric | Pearson r | Spearman rho в `metrics` |
| ordinal ↔ numeric / ordinal | Spearman rho | Pearson не вычисляется |
| boolean ↔ numeric | point-biserial | true/false counts среди пар |
| boolean ↔ ordinal | point-biserial | `ordinal_spacing_assumed` в limitations |
| boolean ↔ boolean | Phi | contingency counts |
| categorical ↔ любой, включая categorical | unsupported | Без integer encoding |

Pearson — центрированная нормированная ковариация. Spearman — Pearson по рангам
**после удаления неполных пар**, совпадения получают средний ранг. Нет формулы,
предполагающей отсутствие ties. Point-biserial — Pearson с observed false=0,
true=1; null исключается **до** кодирования. Для ordinal этот показатель зависит
от расстояний между числовыми кодами шкалы и служит только описательной мерой.
Phi математически равен Pearson для двух бинарных рядов; таблица возвращает
`true_true`, `true_false`, `false_true`, `false_false` относительно ориентации x/y.
Boolean counts и contingency вычисляются даже при недостаточном n.

Масштабирование и центрирование защищают от переполнения/исчезновения дисперсии
на экстремальных числах. Округлённый коэффициент ограничивается [-1, 1].
Непредставимый результат не выходит в JSON как NaN/Infinity.

| status | reason / значение |
| --- | --- |
| ok | Коэффициент вычислен; reason=null |
| insufficient_data | too_few_pairs; coefficient=null |
| constant_series | zero_variance хотя бы одной переменной; coefficient=null |
| incompatible_units | mixed_quantity_units; coefficient=null |
| unsupported | unsupported_types или grain_mismatch; coefficient=null |
| invalid_values | nonfinite_or_invalid_values в прямом вызове math-функций |
| numerical_error | unstable_calculation; coefficient=null |

Невалидные ячейки исключаются pair extraction с отдельным счётчиком; Stage 7A
уже запрещает NaN/Infinity. Низкое n проверяется до константности, поэтому пустой
или единственный pair имеет статус insufficient_data, а не нулевую корреляцию.
Вычислительный сбой дополнительного метода отражается в его `metrics` независимо
от основного: верхний status/coefficient описывает только основной метод.
При unsupported_types coverage/n всё равно доступны. При grain_mismatch общего
знаменателя не существует: grain/coverage/method=null, n=0, metrics=[];
этот ноль не означает, что исходные ряды пусты.

## Sample policy и нейтральное описание

В `relationship_types.POLICY`: минимум **5 валидных пар** для каждого коэффициента;
минимум **10** для strength. При n=5–9 коэффициент и направление доступны,
strength=null. Порог сам по себе не подтверждает надёжность, а большие n также
не устраняют систематические пропуски или зависимость соседних наблюдений.

По абсолютному коэффициенту: `<0.1` negligible, `[0.1,0.3)` weak,
`[0.3,0.5)` moderate, `>=0.5` strong. Для signed metrics direction=near_zero при
`abs(c)<0.1`, иначе positive/negative по знаку. При невычисленном коэффициенте
direction/strength=null. Strength не подменяет коэффициент, n и coverage.

## Выравнивание, пропуски и coverage

Выравнивание выполняется по точным `date` / `week_start`, никогда по позиции в
массиве. Никаких сдвигов и lag analysis. Дневные и недельные переменные напрямую
дают unsupported/grain_mismatch. Для общего weekly grain вызывающий код должен
явно выбрать уже существующие `weekly.state.*.mean` и другие ключи 7A; Stage 7C
не изобретает агрегации. Weekly ordinal mean имеет **канонический numeric тип**,
как определено Stage 7A, поэтому для него действует numeric-строка таблицы.

Pairwise deletion оставляет только пары, где обе ячейки present и соответствуют
типу. `[1,2,null,4]` ↔ `[2,null,6,8]` даёт `(1,2),(4,8)`, n=2.
Null не становится 0/false, нет mean fill, carry-forward и интерполяции.
Число `n` всегда равно `coverage.valid_pair_count`. Канонические present-планы,
календарные признаки и результаты Stage 4 остаются допустимыми значениями;
происхождение видно из metadata.source. Это не утверждение, что пользователь
явно ввёл каждое значение score или плана.

`coverage`:

- `requested_count`: количество потенциальных временных пар, объединение ключей
  двух рядов (в каноническом датасете ключи одного grain совпадают).
- `excluded_count`: будущие даты, неполные недели, структурная неприменимость.
- `eligible_count = requested_count - excluded_count`.
- `valid_pair_count`: обе ячейки валидны и проходят политику покрытия.
- `pair_coverage = valid_pair_count / eligible_count`; null при нулевом знаменателе.
- `missing_count`: eligible-пары с хотя бы одним source_missing, field_missing
  или no_observations. Одна пара считается один раз, даже если пропали оба поля.
- `unavailable_count = requested_count - valid_pair_count`: все потерянные пары.
- `losses`: непересекающиеся причины потери с приоритетом future,
  incomplete_period, not_eligible, missing, invalid_value, low_source_coverage.
  Сумма равна unavailable_count. Последние три причины входят в eligible_count;
  первые три образуют excluded_count. missing_count не включает неприменимость.
- `x/y`: исходная Stage 7B coverage каждого выровненного ряда со всеми причинами
  Availability. Это отдельные знаменатели, не знаменатель пары.
- `source_x/y`: суммарное исходное дневное покрытие weekly State за весь запрос;
  `paired_source_x/y`: только по неделям оставленных пар. Для рядов без исходного
  coverage эти поля null.
- `includes_today`: хотя бы одна валидная дневная пара относится к today.

Для weekly observed means каждая сторона каждой недели должна иметь исходное
дневное coverage >= **0.5**, переиспользуется порог Stage 7B. Полная календарная
неделя с единственной записью не становится полностью наблюдаемой неделей только
из-за present mean. Такие пары дают low_source_coverage, не missing.
Для явных observed_count/true_count/false_count этот фильтр не применяется: число
наблюдений само является выбранной переменной, а ноль — каноническим счётчиком.
Их исходное coverage всё равно раскрывается.

## Частичные периоды и единицы

Дневной today допускается при двух present значениях. Будущие даты исключаются,
включая известные планы и календарные признаки. Сегодняшняя неотмеченная привычка
не превращается в false. Live daily score сохраняет Stage 4 семантику и может
меняться до завершения дня; `includes_today` раскрывает это.

Weekly-пара исключается, если хотя бы одна точка `make_series` Stage 7B incomplete:
текущая неделя (включая воскресенье), обрезанный запросом край или частичная
активность привычки/Stage 4 в неделе. Полные остальные недели остаются пригодными.
Если после исключений меньше 5 пар, результат insufficient_data. Нет попытки
приравнять неполный недельный показатель к завершённому или пересчитать квоту.

Единицы quantity берутся через Stage 7B из исторического контекста 7A. Если в
выбранном периоде у одной переменной больше одной observed единицы, вся связь
подавляется как incompatible_units, даже если противоположная сторона пропущена
на дате смены. `units_x/y` показывают наблюдаемые единицы. Конвертации отсутствуют.
Разные постоянные единицы **разных** переменных допустимы (например, минуты сна
и количество километров): корреляция безразмерна; запрещено склеивание разных
единиц внутри одного исторического ряда.

## Производительность, чтение и проверки

Один запрос пары/матрицы = **один dataset build**, затем один ряд на выбранную
переменную, in-memory пары. До 276 пар для 24 ключей, без запросов в цикле пар.
Обычно Stage 7A выполняет **4 SELECT**; загрузка версий может разбиваться selectin
на пакеты при >500 habits, как до Stage 7C. SQL не зависит от количества пар.
Сериализация не обращается к БД. Нет insert/update/delete, flush/commit,
корреляционных таблиц, кэшей, фоновой материализации, изменений схемы и миграций.

Regression test сравнивает 2 ключа / 1 день и 24 ключа / високосный год с 12
привычками: один build, четыре SELECT, отсутствие autoflush даже с pending/dirty
ORM-объектами, одинаковый полный логический дамп до/после. Повторные HTTP-запросы
также сохраняют БД и возвращают одинаковый ответ.
Pure-тесты покрывают известные коэффициенты, ties, константы, минимумы, экстремальные
числа, пропуски, все сочетания типов, grain, даты, частичные недели и матрицу.
Интеграционные тесты проверяют динамические привычки, rename/config/unit history.

## Ограничения и будущий Stage 7D

Categorical-анализ, включая Cramér's V, пока unsupported. Нет p-values,
доверительных интервалов, поправок на multiple comparisons, оценки временной
автокорреляции и автоматического выбора факторов. Это описательная матрица:
поиск максимального коэффициента среди множества пар не является доказательством.
Пропуски могут быть систематическими; pairwise deletion этого не исправляет.
Количество пар не описывает баланс boolean-групп — для этого возвращены counts.
Недели State могут опираться на разные подмножества дней: source coverage явно
возвращается, но агрегаты остаются каноническими, без пересчёта по общим дням.
Унаследовано ограничение единственной текущей архивной границы, без archive history.
Stage 7D должен реализовать отдельную явную политику сдвигов и выравнивания;
same-period контракт Stage 7C не содержит скрытого lag-параметра.
