"""Same-period relationships over Stage 7B series from the Stage 7A dataset.

No database access, source reconstruction, aggregation, or time shifting here.
"""

from dataclasses import dataclass
from datetime import date
from itertools import combinations

from app.domain.analytics.builder import slice_dataset, validate_range
from app.domain.analytics.correlation import finite_number, pearson, phi, point_biserial, spearman
from app.domain.analytics.descriptive import MISSING, coverage, make_series, source_coverage, units
from app.domain.analytics.descriptive_types import POLICY as DESCRIPTIVE_POLICY, Period, SeriesPoint
from app.domain.analytics.relationship_types import (
    POLICY, BooleanCounts, Contingency, Direction, Exclusion, Method, Metric, PairCoverage,
    Relationship, RelationshipAnalytics, Strength,
)
from app.domain.analytics.types import (
    AnalyticsDataset, Availability as A, Grain, Variable, VariableType as T,
)


def validate_request(start: date, end: date, keys: tuple[str, ...], *, pair: bool = False) -> None:
    validate_range(start, end)
    if (end - start).days + 1 > POLICY.max_period_days:
        raise ValueError(f"Период аналитики не должен превышать {POLICY.max_period_days} дней.")
    if not 2 <= len(keys) <= POLICY.max_variables or (pair and len(keys) != 2):
        raise ValueError(f"Выберите две переменные для пары или от 2 до {POLICY.max_variables} для матрицы.")
    if len(set(keys)) != len(keys) or any(not key.strip() or len(key) > 160 for key in keys):
        raise ValueError("Ключи переменных должны быть непустыми, уникальными и не длиннее 160 символов.")


def valid_value(point: SeriesPoint, variable: Variable) -> bool:
    value = point.value
    if variable.type == T.BOOLEAN:
        return type(value) is bool
    if variable.type == T.CATEGORICAL:
        return type(value) is str
    return type(value) in (int, float) and finite_number(value)


def low_source_coverage(point: SeriesPoint, variable: Variable) -> bool:
    if not variable.source.startswith("observed_mean:"):
        return False
    source = point.source_coverage
    return (source is None or source.ratio is None or
            source.ratio < DESCRIPTIVE_POLICY.minimum_coverage)


@dataclass(frozen=True)
class PairedObservations:
    x: tuple[SeriesPoint, ...]
    y: tuple[SeriesPoint, ...]
    coverage: PairCoverage


def extract_pairs(x: Variable, y: Variable, xs: tuple[SeriesPoint, ...],
                  ys: tuple[SeriesPoint, ...], *, today: date) -> PairedObservations:
    """Align by date/week key, never by position. Loss reasons form a partition."""
    if x.grain != y.grain:
        raise ValueError("Нельзя сопоставить дневные и недельные наблюдения напрямую.")
    ix, iy = {p.date: p for p in xs}, {p.date: p for p in ys}
    if len(ix) != len(xs) or len(iy) != len(ys):
        raise ValueError("Повторяющиеся даты наблюдений недопустимы.")
    dates = sorted(ix.keys() | iy.keys())
    return filter_pairs(
        x, y,
        tuple(ix.get(on, SeriesPoint(on, None, A.SOURCE_MISSING, False)) for on in dates),
        tuple(iy.get(on, SeriesPoint(on, None, A.SOURCE_MISSING, False)) for on in dates),
        today=today,
    )


def filter_pairs(x: Variable, y: Variable, xs: tuple[SeriesPoint, ...],
                 ys: tuple[SeriesPoint, ...], *, today: date) -> PairedObservations:
    """Apply the shared availability policy to already aligned observations.

    Preserve original timestamps: 7D pairs can have different dates, and either
    side can be in the future. Alignment is the caller's responsibility.
    """
    if x.grain != y.grain or len(xs) != len(ys):
        raise ValueError("Требуются выровненные пары одного временного масштаба.")
    losses: dict[Exclusion, int] = {reason: 0 for reason in (
        "future", "incomplete_period", "not_eligible", "missing", "invalid_value", "low_source_coverage")}
    aligned_x, aligned_y, paired_x, paired_y = [], [], [], []
    for a, b in zip(xs, ys, strict=True):
        aligned_x.append(a)
        aligned_y.append(b)
        reason: Exclusion | None = None
        if a.date > today or b.date > today:
            reason = "future"
        elif x.grain == Grain.WEEKLY and (a.incomplete or b.incomplete):
            reason = "incomplete_period"
        elif any(p.availability not in (A.PRESENT, *MISSING) for p in (a, b)):
            reason = "not_eligible"
        elif any(p.availability != A.PRESENT for p in (a, b)):
            reason = "missing"
        elif not valid_value(a, x) or not valid_value(b, y):
            reason = "invalid_value"
        elif low_source_coverage(a, x) or low_source_coverage(b, y):
            reason = "low_source_coverage"
        if reason is not None:
            losses[reason] += 1
        else:
            paired_x.append(a)
            paired_y.append(b)
    total, n = len(aligned_x), len(paired_x)
    excluded = sum(losses[r] for r in ("future", "incomplete_period", "not_eligible"))
    eligible = total - excluded
    covered = PairCoverage(
        total, eligible, n, losses["missing"], total - n, excluded,
        n / eligible if eligible else None, losses, coverage(aligned_x), coverage(aligned_y),
        source_coverage(aligned_x), source_coverage(aligned_y),
        source_coverage(paired_x), source_coverage(paired_y),
        x.grain == Grain.DAILY and any(p.date == today for p in (*paired_x, *paired_y)),
    )
    return PairedObservations(tuple(paired_x), tuple(paired_y), covered)


def methods(x: Variable, y: Variable) -> tuple[Method, ...]:
    types = (x.type, y.type)
    if T.CATEGORICAL in types:
        return ()
    if types == (T.BOOLEAN, T.BOOLEAN):
        return ("phi",)
    if T.BOOLEAN in types:
        return ("point_biserial",)
    if T.ORDINAL in types:
        return ("spearman",)
    return ("pearson", "spearman")


def classify(coefficient: float | None, n: int) -> tuple[Direction | None, Strength | None]:
    if coefficient is None:
        return None, None
    magnitude = abs(coefficient)
    direction: Direction = ("near_zero" if magnitude < POLICY.negligible_below else
                            "positive" if coefficient > 0 else "negative")
    strength: Strength | None = None
    if n >= POLICY.strength_minimum:
        strength = ("negligible" if magnitude < POLICY.negligible_below else
                    "weak" if magnitude < POLICY.weak_below else
                    "moderate" if magnitude < POLICY.moderate_below else "strong")
    return direction, strength


def analyze_pair(x: Variable, y: Variable, xs: tuple[SeriesPoint, ...],
                 ys: tuple[SeriesPoint, ...], *, today: date) -> Relationship:
    paired = extract_pairs(x, y, xs, ys, today=today) if x.grain == y.grain else None
    return analyze_paired(x, y, xs, ys, paired)


def analyze_paired(x: Variable, y: Variable, xs: tuple[SeriesPoint, ...],
                   ys: tuple[SeriesPoint, ...], paired: PairedObservations | None) -> Relationship:
    """Shared 7C statistics; xs/ys retain pre-deletion unit history."""
    selected = methods(x, y)
    a = [p.value for p in paired.x] if paired else []
    b = [p.value for p in paired.y] if paired else []
    # Conservative 7B unit policy: suppress a variable with any observed unit
    # change in the selected period, even if the other variable missed that date.
    ux, uy = units(xs), units(ys)
    if x.grain != y.grain:
        status, reason, metrics = "unsupported", "grain_mismatch", ()
    elif not selected:
        status, reason, metrics = "unsupported", "unsupported_types", ()
    elif len(ux) > 1 or len(uy) > 1:
        status, reason = "incompatible_units", "mixed_quantity_units"
        metrics = tuple(Metric(method, status, None, reason) for method in selected)
    else:
        calculated = []
        for method in selected:
            if method == "point_biserial":
                calculated.append(point_biserial(a, b) if x.type == T.BOOLEAN else point_biserial(b, a))
            else:
                calculated.append({"pearson": pearson, "spearman": spearman, "phi": phi}[method](a, b))
        metrics = tuple(calculated)
        status, reason = metrics[0].status, metrics[0].reason
    coefficient = metrics[0].coefficient if metrics else None
    direction, strength = classify(coefficient, len(a))
    boolean_x = BooleanCounts(a.count(True), a.count(False)) if x.type == T.BOOLEAN else None
    boolean_y = BooleanCounts(b.count(True), b.count(False)) if y.type == T.BOOLEAN else None
    contingency = None
    if x.type == y.type == T.BOOLEAN:
        contingency = Contingency(*(sum(u is p and v is q for u, v in zip(a, b))
                                    for p, q in ((True, True), (True, False), (False, True), (False, False))))
    return Relationship(
        x, y, x.grain if paired else None, selected[0] if metrics else None,
        coefficient, direction, strength, len(a), paired.coverage if paired else None,
        status, reason, metrics, boolean_x, boolean_y, contingency, ux, uy,
        ("ordinal_spacing_assumed",) if T.BOOLEAN in (x.type, y.type) and T.ORDINAL in (x.type, y.type) else (),
    )


def analyze(dataset: AnalyticsDataset, start: date, end: date, keys: tuple[str, ...],
            *, pair: bool = False) -> RelationshipAnalytics:
    validate_request(start, end, keys, pair=pair)
    registry = {v.key: v for v in dataset.variables}
    unknown = sorted(set(keys) - registry.keys())
    if unknown:
        raise ValueError("Неизвестные переменные аналитики: " + ", ".join(unknown))
    current = dataset if (start, end) == (dataset.start, dataset.end) else slice_dataset(dataset, start, end)
    by_week = {}
    for row in current.daily:
        by_week.setdefault(row.week_start, []).append(row)
    series = {key: make_series(current, registry[key], by_week) for key in keys}
    pairs = ((keys[0], keys[1]),) if pair else combinations(sorted(keys), 2)
    results = tuple(analyze_pair(registry[a], registry[b], series[a], series[b], today=dataset.today)
                    for a, b in pairs)
    return RelationshipAnalytics("7C.1", dataset.contract_version, dataset.today, Period(start, end),
                                 "pair" if pair else "matrix", POLICY,
                                 DESCRIPTIVE_POLICY.minimum_coverage, results)
