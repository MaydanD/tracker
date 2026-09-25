"""Pure dataset preparation. All obligation/score/quota formulas stay in Stage 4."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import date

from app.domain.analytics.types import (
    AnalyticsDataset, Availability as A, DailyRow, DatasetInput, Grain,
    HabitContext, Value, VariableType, WeeklyHabitContext, WeeklyRow,
)
from app.domain.analytics.variables import (
    DAILY_HABIT_FIELDS, STATE_FIELDS, WEEKLY_HABIT_FIELDS, habit_key, registry,
)
from app.domain.daily import Quantity
from app.domain.progress import Score, day_progress, week_bounds, week_progress
from app.domain.tracking import TrackingMode


MAX_RANGE_DAYS = 3660


def validate_range(start: date, end: date) -> None:
    if end < start:
        raise ValueError("Начальная дата не может быть позже конечной даты.")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"Диапазон не должен превышать {MAX_RANGE_DAYS} дней.")


def dates(start: date, end: date) -> Iterator[date]:
    # Ordinals avoid overflow when the inclusive endpoint is date.max.
    return (date.fromordinal(n) for n in range(start.toordinal(), end.toordinal() + 1))


def absent(reason: A) -> Value:
    return Value(None, reason)


def score_values(progress: Score, grain: Grain, *, future: bool) -> dict[str, Value]:
    return {
        f"{grain.value}.score": absent(A.FUTURE) if future else (
            absent(A.NO_OBLIGATIONS) if progress.score is None else Value(progress.score)),
        f"{grain.value}.completed_weight": absent(A.FUTURE) if future else Value(progress.completed_weight),
        f"{grain.value}.required_weight": Value(progress.required_weight),
    }


def state_week_values(rows: list[DailyRow], today: date) -> dict[str, Value]:
    """Canonical State aggregation, also used when projecting a dataset range."""
    elapsed = [row for row in rows if row.date <= today]
    values: dict[str, Value] = {}
    for name, _label, kind in STATE_FIELDS:
        observed = [row.values[f"state.{name}"].value for row in elapsed
                    if row.values[f"state.{name}"].availability == A.PRESENT]
        key = f"weekly.state.{name}"
        values[f"{key}.observed_count"] = Value(len(observed)) if elapsed else absent(A.FUTURE)
        if kind in (VariableType.NUMERIC, VariableType.ORDINAL):
            values[f"{key}.mean"] = (Value(sum(observed) / len(observed)) if observed else
                                     absent(A.NO_OBSERVATIONS if elapsed else A.FUTURE))
        if kind == VariableType.BOOLEAN:
            for boolean, suffix in ((True, "true_count"), (False, "false_count")):
                values[f"{key}.{suffix}"] = (
                    Value(sum(value is boolean for value in observed)) if elapsed else absent(A.FUTURE))
    return values


def slice_dataset(dataset: AnalyticsDataset, start: date, end: date) -> AnalyticsDataset:
    """Project loaded 7A rows without loading sources or recalculating Stage 4.

    Weekly progress retains its full calendar-week scope. Weekly State values
    and requested coverage are recomputed from canonical daily cells only.
    The registry (including the union of dynamic habits) is preserved.
    """
    validate_range(start, end)
    if start < dataset.start or end > dataset.end:
        raise ValueError("Диапазон должен находиться внутри набора данных.")
    daily = tuple(row for row in dataset.daily if start <= row.date <= end)
    by_week: dict[date, list[DailyRow]] = {}
    for row in daily:
        by_week.setdefault(row.week_start, []).append(row)
    weekly = []
    for week in dataset.weekly:
        rows = by_week.get(week.week_start)
        if not rows:
            continue
        weekly.append(replace(
            week, requested_start=rows[0].date, requested_end=rows[-1].date,
            requested_days=len(rows),
            elapsed_requested_days=sum(row.date <= dataset.today for row in rows),
            partial_requested_week=rows[0].date != week.week_start or rows[-1].date != week.week_end,
            values={**week.values, **state_week_values(rows, dataset.today)},
        ))
    return replace(dataset, start=start, end=end, daily=daily, weekly=tuple(weekly))


def build_dataset(data: DatasetInput, start: date, end: date, *, today: date) -> AnalyticsDataset:
    """Build from detached inputs. Public DB callers use services.analytics.get_dataset.

    Daily rows cover precisely the request. Weekly progress covers full intersecting
    calendar weeks; State summaries cover only requested dates <= today. Coverage
    fields make these different scopes explicit, without prorating domain quotas.
    """
    validate_range(start, end)
    histories = tuple(h.history for h in data.habits)
    daily_rows: list[DailyRow] = []
    for on in dates(start, end):
        future = on > today
        dp = day_progress(histories, on)
        values = score_values(dp, Grain.DAILY, future=future)
        iso = on.isocalendar()
        values.update({
            "daily.weekday": Value(str(on.weekday())),
            "daily.iso_week": Value(str(iso.week)),
            "daily.iso_year": Value(iso.year),
            "daily.month": Value(str(on.month)),
            "daily.year": Value(on.year),
            "daily.weekend": Value(on.weekday() >= 5),
            "daily.date_relation": Value("future" if future else "today" if on == today else "historical"),
        })
        state = data.states.get(on)
        for name, _label, _kind in STATE_FIELDS:
            raw = getattr(state, name) if state is not None else None
            values[f"state.{name}"] = (
                absent(A.FUTURE) if future else
                absent(A.SOURCE_MISSING) if state is None else
                absent(A.FIELD_MISSING) if raw is None else Value(raw)
            )
        obligations = {o.habit_id: o for o in dp.obligations}
        contexts: dict[int, HabitContext] = {}
        for habit in data.habits:
            history = habit.history
            # Resolve through the same date lookup used by Stage 4. Config snapshots
            # are aligned with its versions by the loader; never use current_version.
            version = history.version_on(on)
            dated = next((c for c in habit.configurations
                          if version is not None and c.effective_from == version.effective_from), None)
            applicable = version is not None and history.active_on(on)
            entry = habit.entries.get(on)
            contexts[history.habit_id] = HabitContext(dated, applicable, entry)
            features = {name: absent(A.NOT_APPLICABLE) for name, _, _ in DAILY_HABIT_FIELDS}
            if applicable:
                assert dated is not None  # loader aligns snapshots and progress versions
                config = dated.configuration
                features["weight"] = Value(config.weight)
                obligation = obligations.get(history.habit_id)
                if obligation is not None:
                    features["required_weight"] = Value(obligation.weight)
                missing = A.FUTURE if future else A.SOURCE_MISSING if entry is None else None
                features["status"] = absent(missing) if missing is not None else Value(entry.status)
                if config.tracking_mode == TrackingMode.BINARY_QUANTITY:
                    features["quantity"] = (
                        absent(missing) if missing is not None else
                        absent(A.FIELD_MISSING) if entry.quantity_micro is None else
                        Value(float(Quantity(entry.quantity_micro).value))
                    )
            values.update({habit_key(history.habit_id, Grain.DAILY, k): v for k, v in features.items()})
        daily_rows.append(DailyRow(on, week_bounds(on)[0], values, contexts,
                                   state if not future else None))

    by_week: dict[date, list[DailyRow]] = {}
    for row in daily_rows:
        by_week.setdefault(row.week_start, []).append(row)
    weekly_rows = []
    for start_week, rows in by_week.items():
        wp = week_progress(histories, start_week, today)
        future_week = start_week > today
        elapsed = [row for row in rows if row.date <= today]
        values = score_values(wp, Grain.WEEKLY, future=future_week)
        iso = start_week.isocalendar()
        values.update({"weekly.iso_week": Value(str(iso.week)), "weekly.iso_year": Value(iso.year)})
        values.update(state_week_values(rows, today))
        progress_by_id = {p.habit_id: p for p in wp.habits}
        for habit in data.habits:
            p = progress_by_id.get(habit.history.habit_id)
            for feature, _label, _kind in WEEKLY_HABIT_FIELDS:
                if p is None or (feature in ("quota", "completed_count") and p.weekly_quota == 0):
                    value = absent(A.NOT_APPLICABLE)
                elif future_week and feature in ("completed_count", "completed_weight", "daily_completed_count"):
                    value = absent(A.FUTURE)
                else:
                    attr = {"quota": "weekly_quota", "completed_count": "weekly_completed_count"}.get(feature, feature)
                    value = Value(getattr(p, attr))
                values[habit_key(habit.history.habit_id, Grain.WEEKLY, feature)] = value
        active_days = sum(
            any(h.version_on(on) is not None and h.active_on(on) for h in histories)
            for on in dates(start_week, wp.week_end)
        )
        weekly_rows.append(WeeklyRow(
            week_start=start_week, week_end=wp.week_end,
            requested_start=rows[0].date, requested_end=rows[-1].date,
            requested_days=len(rows), elapsed_requested_days=len(elapsed),
            calendar_elapsed_days=sum(on <= today for on in dates(start_week, wp.week_end)),
            partial_requested_week=rows[0].date != start_week or rows[-1].date != wp.week_end,
            unfinished_week=wp.week_end >= today, active_habit_days=active_days,
            progress_scope="calendar_week", state_scope="requested_elapsed_dates",
            values=values,
            habits=tuple(WeeklyHabitContext(p.habit_id, p.name, p.weekly_effective_from,
                                           p.weekly_weight, p.preferred_weekdays) for p in wp.habits),
        ))
    return AnalyticsDataset("7A.1", start, end, today,
                            registry(tuple(h.habit_id for h in histories)),
                            tuple(daily_rows), tuple(weekly_rows))
