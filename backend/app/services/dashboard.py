"""Aggregation services for dashboard, calendar, and day overview."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Area
from app.db.models.daily_state import DailyState
from app.domain.progress import Streak, day_progress, streak_summary, week_progress
from app.domain.tracking import max_value, normalised_value
from app.schemas.daily import DayItemRead
from app.schemas.daily_state import DailyStateRead
from app.schemas.records import RecordsPreviewRead
from app.services import daily_state as daily_state_service
from app.services import owl as owl_service
from app.services import records as records_service
from app.services.daily import day_overview
from app.services.progress import load_histories


def get_calendar_range(
    session: Session, start_date: date, end_date: date, *, today: date,
    include_trends: bool = False,
) -> list[dict[str, object]]:
    histories = load_histories(session)
    areas = (
        {area.id: area for area in session.scalars(select(Area))}
        if include_trends else {}
    )
    statement = select(DailyState).where(DailyState.state_date.between(start_date, end_date))
    states_by_date = {s.state_date: s for s in session.scalars(statement)}

    results = []
    curr = start_date
    while curr <= end_date:
        dp = day_progress(histories, curr)
        st = states_by_date.get(curr)
        is_future = curr > today
        has_obligations = dp.required_weight > 0
        daily_score = dp.score if not is_future else None
        # Match the cards on the check-in screen, independently of their score
        # or schedule. Zero and negative answers are still recorded answers.
        total_items = 0
        answered_items = 0
        for history in histories:
            version = history.version_on(curr)
            status = history.entries.get(curr)
            if version is None or (history.archived_on is not None and status is None):
                continue
            total_items += 1
            if status is not None and (not version.tracks_value or curr in history.values):
                answered_items += 1
        area_totals: dict[int, list[int]] = {}
        habit_scores: list[dict[str, object]] = []
        if include_trends and not is_future:
            for history in histories:
                version = history.version_on(curr)
                entry_status = history.entries.get(curr)
                if version is None or version.area_id is None or entry_status not in {"done", "missed"}:
                    continue
                area = areas.get(version.area_id)
                if area is None:
                    continue
                raw = history.values.get(curr)
                if version.tracks_value:
                    if raw is None:
                        continue
                    fraction = normalised_value(raw, version.value_type, version.direction)
                    # A neutral trend is the observed scale, without an evaluation.
                    trend = raw / max_value(version.value_type) if fraction is None else fraction
                else:
                    fraction = trend = int(entry_status == "done")
                if fraction is not None:
                    total = area_totals.setdefault(version.area_id, [0, 0])
                    total[1] += 1
                    total[0] += fraction
                habit_scores.append({
                    "habit_id": history.habit_id,
                    "name": version.name,
                    "area_id": area.id,
                    "area_name": area.name,
                    "color": area.color,
                    "score": trend * 100,
                    "value": raw,
                    "value_type": version.value_type,
                    "direction": version.direction,
                })
        area_scores = [
            {
                "area_id": area_id,
                "name": areas[area_id].name,
                "color": areas[area_id].color,
                "score": done / total * 100,
            }
            for area_id, (done, total) in sorted(
                area_totals.items(), key=lambda item: areas[item[0]].name.casefold()
            )
        ]

        results.append({
            "entry_date": curr,
            "daily_score": daily_score,
            "completed_weight": dp.completed_weight,
            "required_weight": dp.required_weight,
            "has_obligations": has_obligations,
            "has_daily_state": st is not None,
            "mood": st.mood if st is not None else None,
            "is_future": is_future,
            "total_items": total_items,
            "answered_items": answered_items,
            "area_scores": area_scores,
            "habit_scores": habit_scores,
        })
        curr += timedelta(days=1)

    return results


def get_dashboard_data(
    session: Session, *, today: date, after_hours: bool,
) -> dict[str, object]:
    histories = load_histories(session)
    yesterday = today - timedelta(days=1)
    y_state = daily_state_service.get_state(session, yesterday)
    # One keyed lookup by the unique date: today's recorded state, when it exists,
    # gates sarcasm. A missing row is not inferred into a bad day.
    today_state = daily_state_service.get_state(session, today)

    day = day_progress(histories, today)
    # Current streaks belong to the habits that exist today: a retired habit keeps
    # its history (and its old dates still read correctly) but is not part of the
    # user's present-day list, exactly as it is absent from the day's items.
    summaries = tuple(
        streak_summary(h, today) for h in histories if h.active_on(today)
    )
    items = day_overview(session, today)
    # Stage 11: the compact records block, computed from the histories already in
    # memory so the dashboard never loads habit history twice.
    records = records_service.records_preview(session, today=today, histories=histories)
    owl = owl_service.dashboard_owl(
        histories, today=today, after_hours=after_hours, day=day, items=items,
        summaries=summaries,
        mood=today_state.mood if today_state is not None else None,
        wellbeing=today_state.wellbeing if today_state is not None else None,
    )

    return {
        "today": today,
        "today_progress": day,
        "week_progress": week_progress(histories, today, today),
        "streaks": [
            Streak(s.habit_id, s.current_streak, s.unit, s.as_of) for s in summaries
        ],
        "yesterday_state": DailyStateRead.model_validate(y_state) if y_state else None,
        "today_items": [DayItemRead.from_item(i) for i in items],
        "owl": owl,
        "records": RecordsPreviewRead.from_preview(records),
    }


def get_day_overview(
    session: Session, entry_date: date, *, today: date,
) -> dict[str, object]:
    histories = load_histories(session)
    st = daily_state_service.get_state(session, entry_date)
    return {
        "entry_date": entry_date,
        "today": today,
        "is_future": entry_date > today,
        "progress": day_progress(histories, entry_date),
        "items": [DayItemRead.from_item(i) for i in day_overview(session, entry_date)],
        "state": DailyStateRead.model_validate(st) if st else None,
    }
