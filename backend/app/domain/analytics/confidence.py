"""Stage 7E: evidence-based confidence over Stage 7C/7D relationships.

Pure and deterministic: chronological segmentation, per-segment reuse of the
7C/7D engine, stability metrics, policy classification and typed caveats. No
coefficient is reimplemented here, no source is loaded, and no database, network
or wall clock is touched. One caller-provided dataset feeds the full period and
every segment.
"""

from datetime import date
from statistics import median

from app.domain.analytics.confidence_types import (
    CAVEAT_ORDER, POLICY, Caveat, CaveatCode, ConfidenceAnalytics, ConfidenceEvidence,
    ConfidenceLevel, ConfidenceSegment, CoverageEvidence, MethodEvidence, NotEvaluableReason,
    Policy, RelationToFull, SampleEvidence, SegmentName, StabilityEvidence,
)
from app.domain.analytics.descriptive_types import Period
from app.domain.analytics.lags import (
    analyze as analyze_lag, normalize_lags, request_variables, required_source_range,
)
from app.domain.analytics.relationship_types import (
    POLICY as RELATIONSHIP_POLICY, Direction, Relationship,
)
from app.domain.analytics.relationships import classify
from app.domain.analytics.types import AnalyticsDataset, Grain, VariableType as T
from app.domain.progress import week_bounds


CAVEATS: dict[CaveatCode, tuple[str, str]] = {
    "small_sample": ("Мало наблюдений",
                     "Связь рассчитана на небольшом числе пар наблюдений; для устойчивой "
                     "оценки нужна более длинная история."),
    "limited_history": ("Короткая история",
                        "Запрошенный период слишком короткий, чтобы разделить историю на "
                        "три последовательных отрезка."),
    "low_coverage": ("Низкое покрытие",
                     "Доля пар наблюдений от подходящих дат ниже порога: часть дат не "
                     "имеет обеих переменных."),
    "systematic_missingness_possible": ("Возможен систематический пропуск",
                                        "Пропуски могут быть неслучайными: покрытие заметно "
                                        "различается между отрезками истории или низкое."),
    "segment_inconsistency": ("Несогласованные отрезки",
                              "Связь воспроизводится не на всех отрезках истории."),
    "direction_reversal": ("Смена направления",
                           "Хотя бы на одном отрезке знак связи противоположен знаку "
                           "связи за весь период."),
    "magnitude_instability": ("Нестабильная величина",
                              "Сила связи заметно различается между отрезками истории."),
    "partial_period": ("Неполный период",
                       "Часть недель периода неполные и исключена из расчёта коэффициента."),
    "method_disagreement": ("Методы расходятся",
                            "Pearson и Spearman дают разную силу или направление связи; "
                            "результат чувствителен к выбору метода."),
    "constant_series": ("Нет вариации",
                        "Одна из переменных не меняется на выбранном периоде, поэтому "
                        "коэффициент не определён."),
    "incompatible_units": ("Несовместимые единицы",
                           "За период встречаются разные единицы измерения одной величины; "
                           "связь не рассчитывается."),
    "unsupported_variable_types": ("Неподдерживаемые типы",
                                   "Для выбранного сочетания типов переменных коэффициент "
                                   "не предусмотрен."),
    "ordinal_distance_limitation": ("Шкала порядка",
                                    "Для порядковых переменных предполагается сопоставимость "
                                    "расстояний между уровнями; это не гарантировано."),
    "autocorrelation_possible": ("Возможна автокорреляция",
                                 "Соседние наблюдения во времени не обязательно независимы: "
                                 "объём независимой информации может быть меньше n."),
    "association_not_causation": ("Связь не причинность",
                                  "Наблюдаемая ассоциация не доказывает причинного влияния "
                                  "X на Y."),
}

SEGMENT_NAMES: dict[int, tuple[SegmentName, ...]] = {
    1: ("only",),
    2: ("early", "recent"),
    3: ("early", "middle", "recent"),
}


def _balanced(items: tuple, count: int) -> tuple[tuple, ...]:
    """Split ordered items into contiguous groups whose lengths differ by <= 1.

    Extra units go to the earliest groups so the split is deterministic and the
    chronological reading order (early -> recent) stays meaningful.
    """
    if not items or count < 1:
        return ()
    groups = min(count, len(items))
    size, remainder = divmod(len(items), groups)
    result, start = [], 0
    for index in range(groups):
        length = size + (1 if index < remainder else 0)
        result.append(items[start:start + length])
        start += length
    return tuple(result)


def segment_names(count: int) -> tuple[SegmentName, ...]:
    if count not in SEGMENT_NAMES:
        raise ValueError("Число отрезков истории должно быть от 1 до 3.")
    return SEGMENT_NAMES[count]


def split_period(period: Period, grain: Grain, *, segments: int = POLICY.segment_count
                 ) -> tuple[Period, ...]:
    """Chronological, contiguous, non-overlapping, calendar-balanced Y segments.

    Daily history is split by calendar days; weekly history by whole canonical
    Monday-start weeks. Weekly segment bounds are clipped to the requested period,
    so the segments always tile the target range exactly without gaps. A period
    with fewer units than ``segments`` yields one segment per unit.
    """
    if grain == Grain.DAILY:
        units = tuple(date.fromordinal(period.start.toordinal() + offset)
                      for offset in range((period.end - period.start).days + 1))
        return tuple(Period(group[0], group[-1]) for group in _balanced(units, segments))
    if grain == Grain.WEEKLY:
        first, last = week_bounds(period.start)[0], week_bounds(period.end)[0]
        weeks = tuple(date.fromordinal(first.toordinal() + 7 * offset)
                      for offset in range((last.toordinal() - first.toordinal()) // 7 + 1))
        return tuple(Period(max(group[0], period.start), min(week_bounds(group[-1])[1], period.end))
                     for group in _balanced(weeks, segments))
    raise ValueError("Неизвестный временной масштаб.")


def relation_to_full(full: Direction | None, segment: Direction | None) -> RelationToFull:
    """Same / weaker (near zero) / opposite, reusing the Stage 7C direction band."""
    if full is None or segment is None:
        return "insufficient"
    if segment == full:
        return "same"
    return "near_zero" if "near_zero" in (full, segment) else "opposite"


def evaluable(relationship: Relationship) -> bool:
    """A confidence label needs a computed coefficient; otherwise it is not_evaluable."""
    return relationship.status == "ok" and relationship.coefficient is not None


def not_evaluable_reason(relationship: Relationship) -> NotEvaluableReason:
    if relationship.grain is None:
        return "grain_mismatch" if relationship.reason == "grain_mismatch" else "unsupported"
    return {
        "mixed_quantity_units": "incompatible_units",
        "unsupported_types": "unsupported_types",
        "zero_variance": "constant_series",
        "too_few_pairs": "insufficient_data",
        "nonfinite_or_invalid_values": "invalid_values",
        "unstable_calculation": "numerical_error",
    }.get(relationship.reason or "", "unsupported")


def evaluate_sample(relationship: Relationship, policy: Policy) -> SampleEvidence:
    coverage = relationship.coverage
    return SampleEvidence(
        n=relationship.n,
        requested_count=coverage.requested_count if coverage else 0,
        eligible_count=coverage.eligible_count if coverage else 0,
        excluded_count=coverage.excluded_count if coverage else 0,
        missing_count=coverage.missing_count if coverage else 0,
        unavailable_count=coverage.unavailable_count if coverage else 0,
        pair_coverage=coverage.pair_coverage if coverage else None,
        minimum_n_met=relationship.n >= policy.preliminary_minimum_n,
        stable_n_met=relationship.n >= policy.stable_minimum_n,
        well_supported_n_met=relationship.n >= policy.well_supported_minimum_n,
    )


def evaluate_coverage(relationship: Relationship, segments: tuple[ConfidenceSegment, ...],
                      policy: Policy) -> CoverageEvidence:
    pair_coverage = relationship.coverage.pair_coverage if relationship.coverage else None
    values = tuple(segment.relationship.coverage.pair_coverage if segment.relationship.coverage
                   else None for segment in segments)
    known = tuple(value for value in values if value is not None)
    minimum = min(known) if known else None
    maximum = max(known) if known else None
    imbalance = maximum - minimum if known else None
    return CoverageEvidence(
        pair_coverage=pair_coverage,
        eligible_count=relationship.coverage.eligible_count if relationship.coverage else 0,
        stable_coverage_met=(pair_coverage is not None
                             and pair_coverage >= policy.stable_minimum_pair_coverage),
        well_supported_coverage_met=(pair_coverage is not None
                                     and pair_coverage >= policy.well_supported_minimum_pair_coverage),
        segment_pair_coverage=values,
        minimum_segment_coverage=minimum,
        maximum_segment_coverage=maximum,
        coverage_imbalance=imbalance,
        low_coverage=(pair_coverage is not None
                      and pair_coverage < policy.stable_minimum_pair_coverage),
        segment_instability=(imbalance is not None
                             and imbalance >= policy.segment_coverage_imbalance_threshold),
    )


def evaluate_stability(relationship: Relationship, segments: tuple[ConfidenceSegment, ...],
                       policy: Policy) -> StabilityEvidence:
    relations = tuple(segment.relation_to_full for segment in segments)
    analyzable = tuple(segment for segment in segments if segment.relation_to_full != "insufficient")
    coefficients = tuple(segment.relationship.coefficient for segment in analyzable)
    values = tuple(value for value in coefficients if value is not None)
    full = relationship.coefficient
    deviations = tuple(abs(value - full) for value in values) if full is not None else ()
    same = relations.count("same")
    opposite = relations.count("opposite")
    return StabilityEvidence(
        segment_count=len(segments),
        analyzable_segment_count=len(analyzable),
        insufficient_segment_count=relations.count("insufficient"),
        same_direction_count=same,
        near_zero_count=relations.count("near_zero"),
        opposite_direction_count=opposite,
        coefficients=values,
        median_coefficient=median(values) if values else None,
        median_absolute_coefficient=median(tuple(abs(value) for value in values)) if values else None,
        coefficient_range=(max(values) - min(values)) if values else None,
        maximum_deviation_from_full=max(deviations) if deviations else None,
        direction_consistent=bool(analyzable) and same * 2 > len(analyzable),
        meaningful_reversal=any(segment.relation_to_full == "opposite"
                                and segment.strength in ("moderate", "strong")
                                for segment in analyzable),
        magnitude_stable=(not deviations
                          or max(deviations) <= policy.stable_maximum_deviation_from_full),
        magnitude_well_supported=(not deviations
                                  or max(deviations) <= policy.well_supported_maximum_deviation_from_full),
    )


def evaluate_methods(relationship: Relationship) -> MethodEvidence:
    directions = tuple(classify(metric.coefficient, relationship.n)[0] for metric in relationship.metrics)
    if not directions:
        agreement = "unavailable"
    elif len(directions) == 1:
        agreement = "single_method"
    elif any(direction is None for direction in directions):
        agreement = "unavailable"
    elif len(set(directions)) == 1:
        agreement = "agree"
    elif len({direction for direction in directions if direction != "near_zero"}) > 1:
        agreement = "disagree"
    else:
        agreement = "partial"
    return MethodEvidence(
        primary_method=relationship.method,
        methods=tuple(metric.method for metric in relationship.metrics),
        coefficients=tuple(metric.coefficient for metric in relationship.metrics),
        directions=directions,
        agreement=agreement,
    )


def classify_confidence(sample: SampleEvidence, coverage: CoverageEvidence,
                        stability: StabilityEvidence, methods: MethodEvidence,
                        policy: Policy) -> ConfidenceLevel:
    """Classify evidence maturity. Sample size alone can never buy a higher level."""
    if (not sample.stable_n_met or not coverage.stable_coverage_met
            or stability.analyzable_segment_count < policy.stable_minimum_analyzable_segments
            or not stability.direction_consistent or stability.meaningful_reversal
            or not stability.magnitude_stable or methods.agreement == "disagree"):
        return "preliminary"
    if (not sample.well_supported_n_met or not coverage.well_supported_coverage_met
            or stability.segment_count < policy.segment_count
            or stability.analyzable_segment_count < policy.well_supported_minimum_analyzable_segments
            or stability.opposite_direction_count > 0
            or stability.same_direction_count < (stability.analyzable_segment_count
                                                 - policy.well_supported_maximum_non_matching_segments)
            or not stability.magnitude_well_supported):
        return "stable"
    return "well_supported"


def collect_caveats(relationship: Relationship, sample: SampleEvidence, coverage: CoverageEvidence,
                    stability: StabilityEvidence, methods: MethodEvidence, policy: Policy,
                    *, evaluated: bool) -> tuple[Caveat, ...]:
    """Deterministic caveats, emitted in the canonical order for this result."""
    codes: list[CaveatCode] = ["association_not_causation"]
    if relationship.grain is not None:
        codes.append("autocorrelation_possible")
        if relationship.coverage and relationship.coverage.losses["incomplete_period"] > 0:
            codes.append("partial_period")
    if relationship.status == "incompatible_units":
        codes.append("incompatible_units")
    if relationship.status == "constant_series" or relationship.reason == "zero_variance":
        codes.append("constant_series")
    if relationship.reason == "unsupported_types":
        codes.append("unsupported_variable_types")
    if T.ORDINAL in (relationship.x.type, relationship.y.type):
        codes.append("ordinal_distance_limitation")
    # Evidence-threshold caveats only describe a relationship that was computed;
    # otherwise the typed status/reason is the explanation.
    if evaluated:
        if sample.n < policy.stable_minimum_n:
            codes.append("small_sample")
        if 0 < stability.segment_count < policy.segment_count:
            codes.append("limited_history")
        if coverage.low_coverage:
            codes.append("low_coverage")
        if coverage.low_coverage or coverage.segment_instability:
            codes.append("systematic_missingness_possible")
        if 0 < stability.segment_count and (not stability.direction_consistent
                                            or stability.analyzable_segment_count < stability.segment_count):
            codes.append("segment_inconsistency")
        if stability.opposite_direction_count > 0:
            codes.append("direction_reversal")
        if stability.maximum_deviation_from_full is not None and not stability.magnitude_stable:
            codes.append("magnitude_instability")
        if methods.agreement in ("partial", "disagree"):
            codes.append("method_disagreement")
    present = set(codes)
    return tuple(Caveat(code, *CAVEATS[code]) for code in CAVEAT_ORDER if code in present)


def analyze(dataset: AnalyticsDataset, start: date, end: date, keys: tuple[str, str],
            lag: int = 0) -> ConfidenceAnalytics:
    """Evaluate one X/Y hypothesis (same-period when lag is 0) on one dataset."""
    request_variables(start, end, keys)
    lag = normalize_lags((lag,))[0]
    known = {variable.key: variable for variable in dataset.variables}
    unknown = sorted(set(keys) - known.keys())
    if unknown:
        raise ValueError("Переменные отсутствуют в наборе данных: " + ", ".join(unknown))
    x, y = (known[key] for key in keys)
    compatible = x.grain == y.grain
    required = required_source_range(Period(start, end), (lag,), x.grain) if compatible else Period(start, end)
    if required.start < dataset.start or required.end > dataset.end:
        raise ValueError("Набор данных не покрывает расширенный диапазон сдвигов.")

    relationship = analyze_lag(dataset, start, end, keys, (lag,)).results[0]
    periods = split_period(Period(start, end), x.grain) if compatible else ()
    names = segment_names(len(periods)) if periods else ()
    segments = []
    for index, period in enumerate(periods):
        segment = analyze_lag(dataset, period.start, period.end, keys, (lag,)).results[0]
        segments.append(ConfidenceSegment(
            index=index, name=names[index], period=period, relationship=segment,
            relation_to_full=relation_to_full(relationship.direction, segment.direction),
            direction=segment.direction, strength=segment.strength))
    segments = tuple(segments)

    sample = evaluate_sample(relationship, POLICY)
    coverage = evaluate_coverage(relationship, segments, POLICY)
    stability = evaluate_stability(relationship, segments, POLICY)
    methods = evaluate_methods(relationship)
    computed = evaluable(relationship)
    return ConfidenceAnalytics(
        contract_version="7E.1", dataset_contract_version=dataset.contract_version,
        confidence_policy_version=POLICY.version, today=dataset.today,
        x=x, y=y, grain=relationship.grain, lag=lag,
        lag_unit=relationship.lag_unit, target_period=relationship.target_period,
        source_range=Period(dataset.start, dataset.end),
        habit_entry_source_range=Period(week_bounds(dataset.start)[0], week_bounds(dataset.end)[1]),
        status="evaluated" if computed else "not_evaluable",
        reason=None if computed else not_evaluable_reason(relationship),
        confidence=classify_confidence(sample, coverage, stability, methods, POLICY) if computed else None,
        policy=POLICY, relationship_policy=RELATIONSHIP_POLICY, relationship=relationship,
        evidence=ConfidenceEvidence(sample, coverage, stability, methods),
        segments=segments,
        caveats=collect_caveats(relationship, sample, coverage, stability, methods, POLICY,
                                evaluated=computed),
    )
