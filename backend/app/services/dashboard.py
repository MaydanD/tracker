"""Aggregation services for dashboard, calendar, and day overview."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.daily_state import DailyState
from app.domain.progress import current_streak, day_progress, week_progress
from app.schemas.daily import DayItemRead
from app.schemas.daily_state import DailyStateRead
from app.services import daily_state as daily_state_service
from app.services.daily import day_overview
from app.services.progress import load_histories


def get_calendar_range(
    session: Session, start_date: date, end_date: date, *, today: date,
) -> list[dict[str, object]]:
    histories = load_histories(session)
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

        results.append({
            "entry_date": curr,
            "daily_score": daily_score,
            "completed_weight": dp.completed_weight,
            "required_weight": dp.required_weight,
            "has_obligations": has_obligations,
            "has_daily_state": st is not None,
            "mood": st.mood if st is not None else None,
            "is_future": is_future,
        })
        curr += timedelta(days=1)

    return results


def get_dashboard_data(session: Session, *, today: date) -> dict[str, object]:
    histories = load_histories(session)
    yesterday = today - timedelta(days=1)
    y_state = daily_state_service.get_state(session, yesterday)

    return {
        "today": today,
        "today_progress": day_progress(histories, today),
        "week_progress": week_progress(histories, today, today),
        "streaks": [current_streak(h, today) for h in histories],
        "yesterday_state": DailyStateRead.model_validate(y_state) if y_state else None,
        "today_items": [DayItemRead.from_item(i) for i in day_overview(session, today)],
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
