"""Stage 9 Owl adapters.

The service layer only *loads and reshapes* data that already exists:

* for the dashboard it reads the same in-memory Stage 4 histories/progress that
  the dashboard itself uses — no extra SQL per scenario and no second dataset;
* for insights it reads the already-built Stage 8 payload.

All selection rules live in :mod:`app.domain.owl`; this module never decides a
tone or a priority.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, timedelta

from app.domain.analytics.insight_types import InsightCandidate, InsightSummary
from app.domain.owl import (
    IMPORTANT_WEIGHT,
    MISS_WINDOW_DAYS,
    DashboardContext,
    InsightFact,
    InsightsContext,
    OwlState,
    StreakFact,
    select_dashboard,
    select_insights,
)
from app.domain.progress import (
    DAY,
    DayProgress,
    HabitHistory,
    StreakSummary,
    day_progress,
    week_bounds,
    week_progress,
)
from app.services.daily import DayItem


def _habit_names(histories: Iterable[HabitHistory]) -> dict[int, str]:
    return {h.habit_id: h.versions[-1].name for h in histories if h.versions}


def _window_metrics(
    histories: tuple[HabitHistory, ...], today: date,
) -> tuple[int, float | None]:
    """Real misses and pair coverage over the last ``MISS_WINDOW_DAYS`` days.

    Missing days are never counted as misses: only a recorded ``missed`` status
    counts. Coverage is recorded obligations over total obligations.
    """

    misses = 0
    total = 0
    recorded = 0
    for offset in range(MISS_WINDOW_DAYS):
        progress = day_progress(histories, today - timedelta(days=offset))
        total += len(progress.obligations)
        recorded += sum(1 for o in progress.obligations if o.entry_status is not None)
        misses += sum(1 for o in progress.obligations if o.entry_status == "missed")
    coverage = recorded / total if total else None
    return misses, coverage


def _week_metrics(
    histories: tuple[HabitHistory, ...], anchor: date, today: date,
) -> tuple[float | None, int, float | None]:
    """Weekly score (Stage 4), active days and coverage for one calendar week."""

    progress = week_progress(histories, anchor, today)
    start, end = week_bounds(anchor)
    days = 0
    total = 0
    recorded = 0
    cursor = start
    while cursor <= end:
        day = day_progress(histories, cursor)
        if day.required_weight > 0:
            days += 1
        total += len(day.obligations)
        recorded += sum(1 for o in day.obligations if o.entry_status is not None)
        cursor += DAY
    coverage = recorded / total if total else None
    return progress.score, days, coverage


def dashboard_owl(
    histories: tuple[HabitHistory, ...],
    *,
    today: date,
    after_hours: bool,
    day: DayProgress,
    items: Sequence[DayItem],
    summaries: Sequence[StreakSummary],
    mood: int | None,
    wellbeing: int | None,
) -> OwlState | None:
    """Build the dashboard context from already-computed Stage 4/5 data."""

    unmarked = sum(1 for o in day.obligations if o.entry_status is None)
    failed = tuple(
        item.version.name
        for item in items
        if item.entry is not None
        and item.entry.status == "missed"
        and item.version.weight >= IMPORTANT_WEIGHT
    )

    misses, coverage = _window_metrics(histories, today)
    names = _habit_names(histories)
    streaks = tuple(
        StreakFact(
            habit_id=summary.habit_id,
            name=names.get(summary.habit_id, f"Привычка #{summary.habit_id}"),
            current_streak=summary.current_streak,
            previous_best_streak=summary.previous_best_streak,
            previous_best_end=summary.previous_best_end,
            unit=summary.unit,
            active=summary.active,
        )
        for summary in summaries
    )

    current_week, _ = week_bounds(today)
    last_score, last_days, last_coverage = _week_metrics(histories, current_week - DAY * 7, today)
    prev_score, prev_days, prev_coverage = _week_metrics(histories, current_week - DAY * 14, today)

    context = DashboardContext(
        today=today,
        after_hours=after_hours,
        required_weight=day.required_weight,
        completed_weight=day.completed_weight,
        unmarked_obligations=unmarked,
        obligation_count=len(day.obligations),
        failed_important=failed,
        mood=mood,
        wellbeing=wellbeing,
        misses_last_window=misses,
        coverage_last_window=coverage,
        streaks=streaks,
        last_week_score=last_score,
        last_week_days=last_days,
        last_week_coverage=last_coverage,
        previous_week_score=prev_score,
        previous_week_days=prev_days,
        previous_week_coverage=prev_coverage,
    )
    return select_dashboard(context)


def _stable_fact(insights: Sequence[InsightCandidate]) -> InsightFact | None:
    """First visible stable/well-supported association, in display order."""

    for candidate in insights:
        if candidate.guardrail.verdict not in ("pass", "pass_with_warnings"):
            continue
        if candidate.confidence.level in ("stable", "well_supported"):
            return InsightFact(
                x_label=candidate.x.label,
                y_label=candidate.y.label,
                statement=candidate.text.full,
                timing=candidate.text.timing,
                lag=candidate.lag,
            )
    return None


def insights_owl(
    summary: InsightSummary,
    insights: Sequence[InsightCandidate],
    *,
    blocked_reason: str | None,
    max_sample_n: int,
) -> OwlState | None:
    """Build the insights context from the already-built Stage 8 payload."""

    context = InsightsContext(
        availability=summary.availability,
        availability_message=summary.message,
        hypothesis_count=summary.counts.hypotheses,
        max_sample_n=max_sample_n,
        preliminary_count=summary.counts.by_status.get("preliminary", 0),
        blocked_reason=blocked_reason,
        stable=_stable_fact(insights),
    )
    return select_insights(context)
