"""Observations about a calendar day, independent of habit tracking."""

from dataclasses import asdict, dataclass
from datetime import date

from app.domain.errors import InvalidConfigurationError


class InvalidDailyStateError(InvalidConfigurationError):
    code = "invalid_daily_state"
    message = "Check the daily state values and their consistency."


class EmptyDailyStateError(InvalidDailyStateError):
    code = "empty_daily_state"
    message = "Record at least one value, or use DELETE to clear the day."


class FutureDailyStateError(InvalidDailyStateError):
    code = "future_daily_state"
    message = "A future day's state cannot be changed."


@dataclass(frozen=True, slots=True)
class StateValues:
    mood: int | None = None
    energy: int | None = None
    wellbeing: int | None = None
    sleep_status: str | None = None
    sleep_minutes: int | None = None
    alcohol: bool | None = None
    alcohol_detail: str | None = None
    gaming: bool | None = None
    gaming_minutes: int | None = None
    computer_overuse: bool | None = None
    computer_minutes: int | None = None
    note: str | None = None


def ensure_writable(state_date: date, today: date) -> None:
    if state_date > today:
        raise FutureDailyStateError()


def validate_state(values: StateValues, *, state_date: date, today: date) -> StateValues:
    ensure_writable(state_date, today)
    data = asdict(values)
    for field in ("mood", "energy", "wellbeing", "sleep_minutes", "gaming_minutes", "computer_minutes"):
        value = data[field]
        low, high = (0, 1440) if field.endswith("minutes") else (1, 5)
        if value is not None and (type(value) is not int or not low <= value <= high):
            raise InvalidDailyStateError(details={"field": field})
    for field in ("alcohol", "gaming", "computer_overuse"):
        if data[field] is not None and type(data[field]) is not bool:
            raise InvalidDailyStateError(details={"field": field})
    if values.sleep_status not in (None, "underslept", "normal", "overslept"):
        raise InvalidDailyStateError(details={"field": "sleep_status"})
    for field, limit in (("alcohol_detail", 200), ("note", 500)):
        value = data[field]
        if value is not None:
            if not isinstance(value, str) or len(value.strip()) > limit:
                raise InvalidDailyStateError(details={"field": field})
            data[field] = value.strip() or None
    # Reject contradictions rather than silently discarding submitted information.
    if values.alcohol is not True and data["alcohol_detail"] is not None:
        raise InvalidDailyStateError(details={"field": "alcohol_detail"})
    if values.gaming_minutes is not None and (
        values.gaming is None or (values.gaming is False and values.gaming_minutes > 0)
    ):
        raise InvalidDailyStateError(details={"field": "gaming_minutes"})
    if all(value is None for value in data.values()):
        raise EmptyDailyStateError()
    return StateValues(**data)
