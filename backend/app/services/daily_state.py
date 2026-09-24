"""Daily State persistence. No dependency on habits, entries or scoring."""

from dataclasses import asdict
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.db.models.daily_state import DailyState
from app.domain.daily_state import StateValues, ensure_writable, validate_state


def get_state(session: Session, state_date: date) -> DailyState | None:
    return session.scalar(select(DailyState).where(DailyState.state_date == state_date))


def save_state(session: Session, state_date: date, values: StateValues, *, today: date) -> DailyState:
    data = asdict(validate_state(values, state_date=state_date, today=today))
    now = utc_now()
    # A single atomic statement also covers two concurrent first saves. Never
    # SELECT then INSERT, and never REPLACE (which would change id/created_at).
    statement = insert(DailyState).values(state_date=state_date, **data, created_at=now, updated_at=now)
    statement = statement.on_conflict_do_update(
        index_elements=[DailyState.state_date], set_={**data, "updated_at": now},
    ).returning(DailyState)
    result = session.scalars(statement, execution_options={"populate_existing": True}).one()
    session.commit()
    return result


def delete_state(session: Session, state_date: date, *, today: date) -> None:
    ensure_writable(state_date, today)
    session.execute(delete(DailyState).where(DailyState.state_date == state_date))
    session.commit()
