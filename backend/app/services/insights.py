"""Stage 8 insight service.

Read-only where it can be: ``GET`` recomputes the current candidate set and never
writes anything, so refreshing the page cannot grow the history. History is only
written by the explicit refresh operation, at most once per hypothesis per
calendar day (enforced by a unique constraint, not by convention).

Every request performs exactly **one** Stage 7A dataset build. The guardrail
family, the confidence evaluations and every chart are computed in memory on that
one dataset.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.time import utc_now
from app.db.models import Area, InsightSnapshot
from app.db.queries import load_habits
from app.domain.analytics.builder import validate_range
from app.domain.analytics.confidence import split_period
from app.domain.analytics.confidence_types import ConfidenceLevel
from app.domain.analytics.guardrails import analyze as analyze_guardrails
from app.domain.analytics.guardrail_types import GuardrailAnalytics
from app.domain.analytics.insight_types import (
    DISCOVERY_POLICY, POLICY, DiscoveryPolicy, InsightAnalytics, InsightArea, InsightCatalogue,
    InsightCounts, InsightDetail, InsightFeedMode, InsightRefreshResult, InsightSnapshotRead,
    InsightSnapshotSummary, InsightSummary, InsightVariable, InsightCandidate,
)
from app.domain.analytics.insights import (
    build_chart, build_feed, build_hypotheses, candidate_for, canonical_keys, discover_variables,
    group_identity, insight_fingerprint, known_fingerprints, supported_variable, sweep_lags,
    variable_group,
)
from app.domain.analytics.lags import normalize_lags, request_variables, required_source_range
from app.domain.analytics.types import Grain
from app.domain.errors import (
    InsightIdentityMismatchError, InsightNotFoundError, InsightRequestError,
    InsightTooLargeError,
)
from app.domain.owl import OwlState
from app.services import analytics
from app.services import owl as owl_service


CONTRACT_VERSION = "8A.1"
SNAPSHOT_POLICY = (
    "Снимок истории создаётся только явным обновлением аналитики и не чаще одного "
    "раза на календарный день для одной гипотезы."
)

# Evidence columns compared to decide whether a same-day refresh really changed
# anything. Timestamps are deliberately excluded, so a repeated identical refresh
# leaves the row completely untouched.
EVIDENCE_FIELDS: tuple[str, ...] = (
    "period_start", "period_end", "x_key", "y_key", "x_label", "y_label", "grain", "lag",
    "lag_unit", "orientation", "relationship_method", "coefficient", "n", "pair_coverage",
    "confidence", "guardrail_verdict", "presentation_status", "blocking_reasons", "warnings",
    "statement", "insight_policy_version", "guardrail_policy_version",
    "confidence_policy_version", "template_version",
)


@dataclass(frozen=True)
class InsightRequest:
    """Everything that defines the hypothesis space of one request.

    ``mode`` decides what the *family* is: ``explorer`` evaluates exactly one
    pre-selected pair (one hypothesis, no multiplicity control — the Stage 7D
    ``single`` semantics), ``discovery`` evaluates the whole bounded sweep as one
    family with one FDR correction. ``x``/``y``/``lag`` in discovery mode are a
    result selector and the identity of the insight being opened, never a way to
    narrow the corrected family.
    """

    start: date
    end: date
    mode: InsightFeedMode = "discovery"
    x: str | None = None
    y: str | None = None
    lag: int = 0
    lags: tuple[int, ...] | None = None
    max_variables: int | None = None
    include_hidden: bool = False
    confidence: tuple[ConfidenceLevel, ...] | None = None
    verdicts: tuple[str, ...] | None = None
    variables: tuple[str, ...] | None = None


@dataclass(frozen=True)
class HabitMetadata:
    habit_id: int
    name: str
    area_id: int
    area_name: str
    is_archived: bool
    weight: int


# --------------------------------------------------------------------------- #
# Metadata (labels, areas, catalogue)
# --------------------------------------------------------------------------- #


def load_habit_metadata(session: Session) -> dict[int, HabitMetadata]:
    """One query plus the eager version load; never a query per habit."""

    habits = load_habits(session, include_archived=True)
    areas = {area.id: area for area in session.scalars(select(Area))}
    metadata: dict[int, HabitMetadata] = {}
    for habit in habits:
        version = habit.current_version
        area = areas.get(version.area_id)
        metadata[habit.id] = HabitMetadata(
            habit_id=habit.id, name=version.name, area_id=version.area_id,
            area_name=area.name if area is not None else "", is_archived=habit.is_archived,
            weight=version.weight)
    return metadata


def habit_id_of(key: str) -> int | None:
    parts = key.split(".")
    if len(parts) >= 4 and parts[0] == "habit" and parts[1].isascii() and parts[1].isdigit():
        return int(parts[1])
    return None


def _habit_label(variable_label: str, key: str, habit: HabitMetadata) -> str:
    """Human label of a habit variable, always ending in the archive marker."""

    marker = " (в архиве)" if habit.is_archived else ""
    if key.endswith(".daily.completion"):
        return f"{habit.name}{marker}"
    suffix = variable_label.split(": ", 1)[1] if ": " in variable_label else variable_label
    return f"{habit.name}: {suffix}{marker}"


def _label_map(dataset, metadata: Mapping[int, HabitMetadata]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for variable in dataset.variables:
        habit = metadata.get(variable.habit_id) if variable.habit_id is not None else None
        if habit is not None:
            labels[variable.key] = _habit_label(variable.label, variable.key, habit)
    return labels


def get_catalogue(session: Session) -> InsightCatalogue:
    """Selectable variables with Russian labels, for filters and the explorer."""

    metadata = load_habit_metadata(session)
    areas = tuple(InsightArea(row.id, row.name, row.color, row.is_archived)
                  for row in session.scalars(select(Area).order_by(Area.name, Area.id)))
    from app.domain.analytics.variables import registry

    sweep = discover_variables(
        _registry_only_dataset(metadata), habit_ids=_ordered_habit_ids(metadata),
        budget=DISCOVERY_POLICY.default_variable_budget)
    variables = []
    for variable in registry(tuple(sorted(metadata))):
        habit = metadata.get(variable.habit_id) if variable.habit_id is not None else None
        variables.append(InsightVariable(
            key=variable.key,
            label=(_habit_label(variable.label, variable.key, habit) if habit is not None
                   else variable.label),
            type=variable.type.value, grain=variable.grain,
            group=variable_group(variable), habit_id=variable.habit_id,
            area_id=habit.area_id if habit is not None else None,
            area_name=habit.area_name if habit is not None else None,
            is_archived=bool(habit.is_archived) if habit is not None else False,
            supported=supported_variable(variable),
            in_default_sweep=variable.key in sweep))
    return InsightCatalogue(contract_version=CONTRACT_VERSION, discovery_policy=DISCOVERY_POLICY,
                            areas=areas, variables=tuple(variables))


def _ordered_habit_ids(metadata: Mapping[int, HabitMetadata]) -> tuple[int, ...]:
    """Active habits by importance, then by identity: the discovery priority."""

    active = [item for item in metadata.values() if not item.is_archived]
    return tuple(item.habit_id for item in
                 sorted(active, key=lambda item: (-item.weight, item.habit_id)))


def _registry_only_dataset(metadata: Mapping[int, HabitMetadata]):
    """A registry-only dataset, so variable discovery needs no source load."""

    from app.domain.analytics.types import AnalyticsDataset

    from app.domain.analytics.variables import registry

    return AnalyticsDataset(contract_version="registry", start=date.min, end=date.min,
                            today=date.min, variables=registry(tuple(sorted(metadata))),
                            daily=(), weekly=())


# --------------------------------------------------------------------------- #
# Request handling
# --------------------------------------------------------------------------- #


def _validate(request: InsightRequest, *, today: date) -> None:
    try:
        validate_range(request.start, request.end)
    except ValueError as exc:
        raise InsightRequestError(str(exc)) from exc
    window = (request.end - request.start).days + 1
    if window < DISCOVERY_POLICY.minimum_window_days:
        raise InsightRequestError(
            f"Период аналитики должен быть не короче {DISCOVERY_POLICY.minimum_window_days} дней.")
    if window > DISCOVERY_POLICY.maximum_window_days:
        raise InsightRequestError(
            f"Период аналитики не должен превышать {DISCOVERY_POLICY.maximum_window_days} дней.")
    if request.end > today:
        # Insights explain history. A period that has not happened yet can only
        # produce empty categories, so it is a request error, not "no data".
        raise InsightRequestError("Период аналитики не может заканчиваться в будущем.")
    if (request.x is None) != (request.y is None):
        raise InsightRequestError("Укажите обе переменные x и y или ни одной.")
    if request.mode == "explorer":
        if request.x is None or request.y is None:
            raise InsightRequestError("Для одной пары нужны обе переменные x и y.")
        if request.lags is not None or request.max_variables is not None:
            raise InsightRequestError(
                "Для одной пары укажите сдвиг lag, а не набор сдвигов и число переменных.")
        if request.variables is not None:
            raise InsightRequestError("Фильтр по переменным не применяется к одной паре x и y.")
    elif request.lag and request.x is None:
        raise InsightRequestError("Сдвиг указывается вместе с парой x и y.")
    if request.max_variables is not None and not DISCOVERY_POLICY.default_variable_budget <= \
            request.max_variables <= DISCOVERY_POLICY.maximum_variable_budget:
        # The sweep may be widened, never narrowed: a smaller variable set would
        # shrink the FDR denominator and let a hypothesis pass here that fails in
        # the documented sweep. A targeted question goes through the explorer.
        raise InsightRequestError(
            f"Набор переменных можно только расширять: от "
            f"{DISCOVERY_POLICY.default_variable_budget} до "
            f"{DISCOVERY_POLICY.maximum_variable_budget}.")


def _hypothesis_count(variables: int, lags: Sequence[int]) -> int:
    pairs = variables * (variables - 1) // 2
    lagged = sum(1 for lag in lags if lag != 0)
    return pairs * (1 + 2 * lagged)


def _segments(period_start: date, period_end: date) -> tuple:
    from app.domain.analytics.descriptive_types import Period

    return split_period(Period(period_start, period_end), Grain.DAILY)


def _discovery_source_range(request: InsightRequest, lags: Sequence[int]):
    from app.domain.analytics.descriptive_types import Period

    window = Period(request.start, request.end)
    ranges = [required_source_range(window, tuple(lags), Grain.DAILY)]
    ranges.extend(required_source_range(segment, tuple(lags), Grain.DAILY)
                  for segment in _segments(request.start, request.end))
    return Period(min(item.start for item in ranges), max(item.end for item in ranges))


def _explorer_source_range(request: InsightRequest, keys: tuple[str, str], lag: int):
    from app.domain.analytics.descriptive_types import Period

    variables = request_variables(request.start, request.end, keys)
    window = Period(request.start, request.end)
    if variables[0].grain != variables[1].grain:
        return window
    grain = variables[0].grain
    ranges = [required_source_range(window, (lag,), grain)]
    ranges.extend(required_source_range(segment, (lag,), grain)
                  for segment in split_period(window, grain))
    return Period(min(item.start for item in ranges), max(item.end for item in ranges))


@dataclass(frozen=True)
class Evaluated:
    dataset: object
    result: GuardrailAnalytics | None
    mode: InsightFeedMode
    lags: tuple[int, ...]
    labels: Mapping[str, str]
    metadata: Mapping[int, HabitMetadata]
    representative_lag: int | None = None


def evaluate(session: Session, request: InsightRequest, *, today: date) -> Evaluated:
    """One dataset build, one guardrail family; no per-hypothesis SQL."""

    _validate(request, today=today)
    metadata = load_habit_metadata(session)
    if request.mode == "explorer":
        assert request.x is not None and request.y is not None  # guaranteed by _validate
        lag = normalize_lags((request.lag,))[0]
        key_x, key_y = canonical_keys(request.x, request.y, lag)
        try:
            source = _explorer_source_range(request, (key_x, key_y), lag)
        except ValueError as exc:
            raise InsightRequestError(str(exc)) from exc
        dataset = analytics.get_dataset(session, source.start, source.end, today=today)
        try:
            result = analyze_guardrails(dataset, request.start, request.end,
                                        ((key_x, key_y, lag),), mode="single")
        except ValueError as exc:
            raise InsightRequestError(str(exc)) from exc
        return Evaluated(dataset=dataset, result=result, mode="explorer", lags=(lag,),
                         labels=_label_map(dataset, metadata), metadata=metadata,
                         representative_lag=lag)

    try:
        lags = sweep_lags(request.lags)
    except ValueError as exc:
        raise InsightRequestError(str(exc)) from exc
    source = _discovery_source_range(request, lags)
    dataset = analytics.get_dataset(session, source.start, source.end, today=today)
    keys = discover_variables(dataset, habit_ids=_ordered_habit_ids(metadata),
                              budget=request.max_variables)
    if len(keys) < 2:
        return Evaluated(dataset=dataset, result=None, mode="discovery", lags=lags,
                         labels=_label_map(dataset, metadata), metadata=metadata)
    count = _hypothesis_count(len(keys), lags)
    if count > DISCOVERY_POLICY.maximum_hypotheses:
        raise InsightTooLargeError(
            f"Для выбранного периода проверка даёт {count} гипотез, а допустимо не более "
            f"{DISCOVERY_POLICY.maximum_hypotheses}. Уменьшите число переменных или набор сдвигов.")
    hypotheses = build_hypotheses(keys, lags)
    result = analyze_guardrails(dataset, request.start, request.end, hypotheses, mode="discovery")
    return Evaluated(dataset=dataset, result=result, mode="discovery", lags=tuple(lags),
                     labels=_label_map(dataset, metadata), metadata=metadata)


def _display_filter(request: InsightRequest) -> tuple[str, ...] | None:
    """Result filter: an explicit variable list plus an optional pair selector."""

    selected = set(request.variables or ())
    if request.mode == "discovery" and request.x is not None and request.y is not None:
        selected.update(canonical_keys(request.x, request.y, 0))
    return tuple(sorted(selected)) if selected else None


def _empty_summary() -> InsightSummary:
    from app.domain.analytics.insight_types import AVAILABILITY_MESSAGES

    return InsightSummary(
        availability="no_data", message=AVAILABILITY_MESSAGES["no_data"],
        counts=InsightCounts(hypotheses=0, evaluated_hypotheses=0, admissible_hypotheses=0,
                             blocked_hypotheses=0, unevaluable_hypotheses=0, groups=0,
                             shown=0, in_default_feed=0,
                             by_status={name: 0 for name in (
                                 "preliminary", "stable", "well_supported", "warning",
                                 "hidden", "not_evaluable")},
                             by_blocking_reason={}))


def _first_seen(session: Session) -> dict[str, date]:
    """Earliest snapshot date per fingerprint; one grouped query, small history."""

    rows = session.execute(
        select(InsightSnapshot.fingerprint, func.min(InsightSnapshot.evaluated_on))
        .group_by(InsightSnapshot.fingerprint)).all()
    return {fingerprint: first for fingerprint, first in rows}


def _owl(evaluated: Evaluated, summary: InsightSummary,
         insights: tuple[InsightCandidate, ...]) -> OwlState | None:
    """The one Owl state for this already-built payload; no extra dataset."""

    hypotheses = evaluated.result.hypotheses if evaluated.result is not None else ()
    blocked = next((item for item in hypotheses if item.verdict == "blocked"), None)
    blocked_reason = (blocked.blocking_reasons[0].message
                      if blocked is not None and blocked.blocking_reasons else None)
    max_sample_n = max((item.sample.n for item in hypotheses), default=0)
    return owl_service.insights_owl(summary, insights, blocked_reason=blocked_reason,
                                    max_sample_n=max_sample_n)


def _analytics(evaluated: Evaluated, request: InsightRequest, *, today: date,
               summary: InsightSummary, insights: tuple[InsightCandidate, ...],
               owl: OwlState | None = None) -> InsightAnalytics:
    from app.domain.analytics.descriptive_types import Period
    from app.domain.analytics.insight_types import SORT_ORDER

    dataset = evaluated.dataset
    return InsightAnalytics(
        contract_version=CONTRACT_VERSION,
        dataset_contract_version=getattr(dataset, "contract_version", ""),
        insight_policy_version=POLICY.version,
        guardrail_policy_version=(evaluated.result.guardrail_policy_version
                                  if evaluated.result is not None else "1"),
        confidence_policy_version=_confidence_policy_version(evaluated),
        template_version=POLICY.template_version,
        today=today, mode=evaluated.mode,
        window=Period(request.start, request.end),
        source_range=Period(getattr(dataset, "start"), getattr(dataset, "end")),
        lags=evaluated.lags, include_hidden=request.include_hidden,
        discovery_policy=DISCOVERY_POLICY, sort_order=SORT_ORDER,
        summary=summary, insights=insights, owl=owl)


def _confidence_policy_version(evaluated: Evaluated) -> str:
    from app.domain.analytics.confidence_types import POLICY as CONFIDENCE_POLICY

    return CONFIDENCE_POLICY.version


def get_insights(session: Session, request: InsightRequest, *, today: date) -> InsightAnalytics:
    """Current candidates for the requested period. Read-only: writes nothing."""

    evaluated = evaluate(session, request, today=today)
    if evaluated.result is None:
        empty = _empty_summary()
        return _analytics(evaluated, request, today=today, summary=empty, insights=(),
                          owl=_owl(evaluated, empty, ()))
    summary, insights = build_feed(
        evaluated.dataset, request.start, request.end, evaluated.result, mode=evaluated.mode,
        labels=evaluated.labels, first_seen=_first_seen(session),
        include_hidden=request.include_hidden, confidence_filter=request.confidence,
        verdict_filter=request.verdicts, variable_filter=_display_filter(request))
    return _analytics(evaluated, request, today=today, summary=summary, insights=insights,
                      owl=_owl(evaluated, summary, insights))


def _locate(evaluated: Evaluated, key_x: str, key_y: str, lag: int):
    assert evaluated.result is not None
    for hypothesis in evaluated.result.hypotheses:
        if (hypothesis.x.key, hypothesis.y.key, hypothesis.lag) == (key_x, key_y, lag):
            return hypothesis
    return None


def get_detail(session: Session, fingerprint: str, request: InsightRequest, *,
               today: date) -> InsightDetail:
    """One insight with its charts and its persisted history."""

    evaluated = evaluate(session, request, today=today)
    if evaluated.result is None or request.x is None or request.y is None:
        raise InsightNotFoundError("Наблюдение не найдено для выбранного периода.")
    lag = normalize_lags((request.lag,))[0]
    key_x, key_y = canonical_keys(request.x, request.y, lag)
    known = {variable.key: variable for variable in evaluated.dataset.variables}
    if key_x not in known or key_y not in known:
        raise InsightNotFoundError("Наблюдение не найдено для выбранного периода.")
    x_variable, y_variable = known[key_x], known[key_y]
    grain = x_variable.grain if x_variable.grain == y_variable.grain else None
    if insight_fingerprint(key_x, key_y, grain, lag) != fingerprint:
        # A digest this dataset could have produced for another pair is a moved
        # identity (the feed is stale); anything else is simply not ours.
        if fingerprint in known_fingerprints(evaluated.dataset, lag):
            raise InsightIdentityMismatchError(
                "Наблюдение изменилось. Обновите список аналитики и откройте его снова.")
        raise InsightNotFoundError("Наблюдение не найдено для выбранного периода.")
    hypothesis = _locate(evaluated, key_x, key_y, lag)
    if hypothesis is None:
        raise InsightNotFoundError("Наблюдение не найдено для выбранного периода.")
    identity = group_identity(key_x, key_y)
    group = [item for item in evaluated.result.hypotheses
             if group_identity(item.x.key, item.y.key) == identity]
    candidate = candidate_for(evaluated.dataset, request.start, request.end, evaluated.result,
                              hypothesis, group, labels=evaluated.labels,
                              first_seen=_first_seen(session), mode=evaluated.mode)
    history = get_history(session, fingerprint)
    chart = build_chart(evaluated.dataset, candidate, history_count=len(history))
    return InsightDetail(contract_version=CONTRACT_VERSION, today=today, mode=evaluated.mode,
                         window=candidate.target_period, snapshot_policy=SNAPSHOT_POLICY,
                         candidate=candidate, chart=chart, history=history)


def get_history(session: Session, fingerprint: str) -> tuple[InsightSnapshotRead, ...]:
    """Chronological snapshots of one hypothesis; empty when never refreshed."""

    rows = list(session.scalars(
        select(InsightSnapshot).where(InsightSnapshot.fingerprint == fingerprint)
        .order_by(InsightSnapshot.evaluated_on.desc(), InsightSnapshot.id.desc())
        .limit(POLICY.maximum_history_returned)))
    archived = {habit.id: habit.is_archived
                for habit in load_habits(session, include_archived=True)}
    return tuple(_snapshot_read(row, archived) for row in reversed(rows))


def _archived_flag(key: str, archived: Mapping[int, bool]) -> bool | None:
    habit_id = habit_id_of(key)
    return archived.get(habit_id) if habit_id is not None else None


def _snapshot_read(row: InsightSnapshot, archived: Mapping[int, bool]) -> InsightSnapshotRead:
    from app.domain.analytics.descriptive_types import Period

    return InsightSnapshotRead(
        id=row.id, fingerprint=row.fingerprint, evaluated_on=row.evaluated_on,
        period=Period(row.period_start, row.period_end), x_key=row.x_key, y_key=row.y_key,
        x_label=row.x_label, y_label=row.y_label,
        x_archived=_archived_flag(row.x_key, archived),
        y_archived=_archived_flag(row.y_key, archived),
        grain=row.grain, lag=row.lag, lag_unit=row.lag_unit, orientation=row.orientation,
        method=row.relationship_method, coefficient=row.coefficient, n=row.n,
        pair_coverage=row.pair_coverage, confidence=row.confidence,
        guardrail_verdict=row.guardrail_verdict, status=row.presentation_status,
        blocking_reasons=tuple(row.blocking_reasons or ()), warnings=tuple(row.warnings or ()),
        statement=row.statement, insight_policy_version=row.insight_policy_version,
        guardrail_policy_version=row.guardrail_policy_version,
        confidence_policy_version=row.confidence_policy_version,
        template_version=row.template_version, created_at=row.created_at,
        updated_at=row.updated_at)


def _snapshot_values(candidate: InsightCandidate, today: date) -> dict:
    now = utc_now()
    return {
        "fingerprint": candidate.fingerprint, "evaluated_on": today,
        "period_start": candidate.target_period.start, "period_end": candidate.target_period.end,
        "x_key": candidate.x.key, "y_key": candidate.y.key,
        "x_label": candidate.x.label, "y_label": candidate.y.label,
        "grain": candidate.grain.value if candidate.grain is not None else "none",
        "lag": candidate.lag, "lag_unit": candidate.lag_unit,
        "orientation": candidate.orientation,
        "relationship_method": candidate.relationship.method,
        "coefficient": candidate.relationship.coefficient,
        "n": candidate.evidence.sample.n,
        "pair_coverage": candidate.evidence.coverage.pair_coverage,
        "confidence": candidate.confidence.level,
        "guardrail_verdict": candidate.guardrail.verdict,
        "presentation_status": candidate.status,
        "blocking_reasons": [reason.code for reason in candidate.guardrail.blocking_reasons],
        "warnings": [reason.code for reason in candidate.guardrail.warnings],
        "statement": candidate.text.full,
        "insight_policy_version": POLICY.version,
        "guardrail_policy_version": candidate.guardrail.policy_version,
        "confidence_policy_version": candidate.confidence.policy_version,
        "template_version": candidate.text.template_version,
        "created_at": now, "updated_at": now,
    }


def refresh(session: Session, request: InsightRequest, *, today: date) -> InsightRefreshResult:
    """Recompute the candidate set and materialize at most one snapshot per day."""

    discovery = replace(request, mode="discovery", x=None, y=None, lag=0, include_hidden=True,
                        confidence=None, verdicts=None, variables=None)
    evaluated = evaluate(session, discovery, today=today)
    if evaluated.result is None:
        empty = _empty_summary()
        return InsightRefreshResult(
            analytics=_analytics(evaluated, discovery, today=today, summary=empty,
                                 insights=(), owl=_owl(evaluated, empty, ())),
            snapshots=InsightSnapshotSummary(evaluated_on=today, created=0, updated=0,
                                              unchanged=0, total=0))
    first_seen = _first_seen(session)
    _full, snapshots_candidates = build_feed(
        evaluated.dataset, discovery.start, discovery.end, evaluated.result, mode="discovery",
        labels=evaluated.labels, first_seen=first_seen, include_hidden=True)
    summary, insights = build_feed(
        evaluated.dataset, discovery.start, discovery.end, evaluated.result, mode="discovery",
        labels=evaluated.labels, first_seen=first_seen)

    existing = {row.fingerprint: row for row in session.scalars(
        select(InsightSnapshot).where(InsightSnapshot.evaluated_on == today))}
    created = updated = unchanged = 0
    for candidate in snapshots_candidates:
        values = _snapshot_values(candidate, today)
        row = existing.get(candidate.fingerprint)
        if row is None:
            # Another refresh can finish after the bulk SELECT above. Resolve
            # that race against the database's unique key, without a 500 or a
            # duplicate row. Tracker's persistence is SQLite.
            inserted = session.execute(sqlite_insert(InsightSnapshot).values(**values)
                .on_conflict_do_nothing(index_elements=["fingerprint", "evaluated_on"])
                .returning(InsightSnapshot.id)).scalar_one_or_none()
            if inserted is not None:
                created += 1
                continue
            row = session.scalars(select(InsightSnapshot).where(
                InsightSnapshot.fingerprint == candidate.fingerprint,
                InsightSnapshot.evaluated_on == today)).one()
        if any(getattr(row, name) != values[name] for name in EVIDENCE_FIELDS):
            for name in EVIDENCE_FIELDS:
                setattr(row, name, values[name])
            row.updated_at = values["updated_at"]
            updated += 1
        else:
            unchanged += 1
    session.commit()
    return InsightRefreshResult(
        analytics=_analytics(evaluated, discovery, today=today, summary=summary,
                             insights=insights, owl=_owl(evaluated, summary, insights)),
        snapshots=InsightSnapshotSummary(evaluated_on=today, created=created, updated=updated,
                                        unchanged=unchanged,
                                        total=len(snapshots_candidates)))
