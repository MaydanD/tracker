"""Pure calendar alignment over 7A data / 7B series; statistics remain in 7C."""

from dataclasses import dataclass, fields
from datetime import date

from app.domain.analytics.builder import slice_dataset
from app.domain.analytics.descriptive import make_series
from app.domain.analytics.descriptive_types import POLICY as DESCRIPTIVE_POLICY, Period, SeriesPoint
from app.domain.analytics.lag_types import POLICY, LagAnalytics, LagResult
from app.domain.analytics.relationship_types import POLICY as RELATIONSHIP_POLICY, Relationship
from app.domain.analytics.relationships import analyze_paired, filter_pairs, validate_request
from app.domain.analytics.types import AnalyticsDataset, Grain, Variable
from app.domain.analytics.variables import registry
from app.domain.progress import week_bounds


def normalize_lags(lags: tuple[int, ...]) -> tuple[int, ...]:
    if not 1 <= len(lags) <= POLICY.max_lag_values:
        raise ValueError(f"Укажите от 1 до {POLICY.max_lag_values} сдвигов.")
    if any(type(lag) is not int or abs(lag) > POLICY.max_absolute_lag for lag in lags):
        raise ValueError(f"Сдвиг должен быть целым числом от -{POLICY.max_absolute_lag} "
                         f"до +{POLICY.max_absolute_lag}.")
    return tuple(sorted(set(lags)))


def select_lags(*, lag: int | None = None, lags: tuple[int, ...] | None = None,
                lag_start: int | None = None, lag_end: int | None = None) -> tuple[int, ...]:
    """One lag, repeated lag values, or inclusive bounded range; default is zero."""
    ranged = lag_start is not None or lag_end is not None
    if sum((lag is not None, lags is not None, ranged)) > 1:
        raise ValueError("Укажите только lag, lags или пару lag_start/lag_end.")
    if ranged:
        if lag_start is None or lag_end is None:
            raise ValueError("Для диапазона сдвигов нужны lag_start и lag_end.")
        normalize_lags((lag_start, lag_end))
        if lag_start > lag_end:
            raise ValueError("Начало диапазона сдвигов не может быть больше конца.")
        return normalize_lags(tuple(range(lag_start, lag_end + 1)))
    return normalize_lags(lags if lags is not None else (lag if lag is not None else 0,))


def request_variables(start: date, end: date, keys: tuple[str, str]) -> tuple[Variable, Variable]:
    """Resolve grain from the canonical registry, without loading any sources.

    Candidate habit identities only instantiate 7A metadata. Their actual
    presence is checked against the loaded dataset's registry in analyze().
    """
    validate_request(start, end, keys, pair=True)
    ids = set()
    for key in keys:
        parts = key.split(".")
        if len(parts) == 4 and parts[0] == "habit" and parts[1].isascii() and parts[1].isdigit():
            ids.add(int(parts[1]))
    known = {v.key: v for v in registry(tuple(ids))}
    unknown = sorted(set(keys) - known.keys())
    if unknown:
        raise ValueError("Неизвестные переменные аналитики: " + ", ".join(unknown))
    return known[keys[0]], known[keys[1]]


def shift_date(on: date, lag: int, grain: Grain) -> date:
    """X coordinate for a Y date (or canonical Monday week identity)."""
    normalize_lags((lag,))
    ordinal = on.toordinal() - lag * (7 if grain == Grain.WEEKLY else 1)
    if not date.min.toordinal() <= ordinal <= date.max.toordinal():
        raise ValueError("Сдвиг выходит за границы допустимых календарных дат.")
    return date.fromordinal(ordinal)


def shifted_period(period: Period, lag: int, grain: Grain) -> Period:
    return Period(shift_date(period.start, lag, grain), shift_date(period.end, lag, grain))


def required_source_range(period: Period, lags: tuple[int, ...], grain: Grain) -> Period:
    lags = normalize_lags(lags)
    return Period(shift_date(period.start, max(0, max(lags)), grain),
                  shift_date(period.end, min(0, min(lags)), grain))


@dataclass(frozen=True)
class AlignedPairs:
    x: tuple[SeriesPoint, ...]
    y: tuple[SeriesPoint, ...]


def align_lagged_pairs(xs: tuple[SeriesPoint, ...], ys: tuple[SeriesPoint, ...],
                       lag: int, grain: Grain) -> AlignedPairs:
    """Join existing coordinates only, sorted by Y. Never shift values/metadata.

    ys already represents the requested target period. Missing values remain
    untouched here; shared 7C pairwise filtering happens after this join.
    """
    normalize_lags((lag,))
    ix, iy = {p.date: p for p in xs}, {p.date: p for p in ys}
    if len(ix) != len(xs) or len(iy) != len(ys):
        raise ValueError("Повторяющиеся даты наблюдений недопустимы.")
    if grain == Grain.WEEKLY and any(on.weekday() != 0 for on in (*ix, *iy)):
        raise ValueError("Недельный ряд должен использовать каноническое начало недели.")
    pairs = [(ix[shift_date(on, lag, grain)], iy[on]) for on in sorted(iy)
             if shift_date(on, lag, grain) in ix]
    return AlignedPairs(tuple(a for a, _ in pairs), tuple(b for _, b in pairs))


def analyze(dataset: AnalyticsDataset, start: date, end: date, keys: tuple[str, str],
            lags: tuple[int, ...]) -> LagAnalytics:
    request_variables(start, end, keys)
    lags = normalize_lags(lags)
    known = {v.key: v for v in dataset.variables}
    unknown = sorted(set(keys) - known.keys())
    if unknown:
        raise ValueError("Переменные отсутствуют в наборе данных: " + ", ".join(unknown))
    x, y = (known[key] for key in keys)
    target = Period(start, end)
    compatible = x.grain == y.grain
    required = required_source_range(target, lags, x.grain) if compatible else target
    if required.start < dataset.start or required.end > dataset.end:
        raise ValueError("Набор данных не покрывает расширенный диапазон сдвигов.")

    # Cache 7B projections in memory. Weekly windows must use 7A slicing so an
    # extended fetch cannot turn a partial requested week into a complete one.
    windows = {}
    series = {}

    def selected(variable: Variable, period: Period) -> tuple[SeriesPoint, ...]:
        if period not in windows:
            data = slice_dataset(dataset, period.start, period.end)
            by_week = {}
            for row in data.daily:
                by_week.setdefault(row.week_start, []).append(row)
            windows[period] = data, by_week
        key = (variable.key, period)
        if key not in series:
            data, by_week = windows[period]
            series[key] = make_series(data, variable, by_week)
        return series[key]

    ys = selected(y, target)
    # Daily source points need no reprojection after selection; build once.
    daily_x = selected(x, required) if compatible and x.grain == Grain.DAILY else None
    results = []
    for lag in lags:
        period_x = shifted_period(target, lag, x.grain) if compatible else None
        if compatible:
            xs = daily_x if daily_x is not None else selected(x, period_x)
            aligned = align_lagged_pairs(xs, ys, lag, x.grain)
            paired = filter_pairs(x, y, aligned.x, aligned.y, today=dataset.today)
            relationship = analyze_paired(x, y, aligned.x, aligned.y, paired)
            potential = len(aligned.x)
        else:
            relationship = analyze_paired(x, y, selected(x, target), ys, None)
            potential = 0
        results.append(LagResult(
            **{f.name: getattr(relationship, f.name) for f in fields(Relationship)},
            lag=lag, lag_unit=("day" if x.grain == Grain.DAILY else "week") if compatible else None,
            target_period=target, x_period=period_x, potential_aligned_count=potential,
        ))
    return LagAnalytics(
        "7D.1", dataset.contract_version, dataset.today, target,
        Period(dataset.start, dataset.end),
        Period(week_bounds(dataset.start)[0], week_bounds(dataset.end)[1]),
        "y", "positive_x_earlier", POLICY, RELATIONSHIP_POLICY,
        DESCRIPTIVE_POLICY.minimum_coverage,
        ("association_not_causation", "autocorrelation_unadjusted",
         "systematic_missingness", "multiple_lags_exploratory"), tuple(results),
    )
