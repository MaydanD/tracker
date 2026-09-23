"""Habit scheduling rules.

Stage 2 stores and validates schedule *configuration* only. Completing habits,
resolving streaks and allocating flexible completions belong to Stage 4.

Product rules encoded here:

* Weekdays are ISO numbers: ``0 = Monday`` … ``6 = Sunday``.
* The canonical week is **Monday → Sunday**, so weekly quotas are calendar-week
  quotas and never rolling seven-day windows.
* For a weekday schedule, the preferred weekdays *are* the weekly quota: the
  required number of completions is derived from the selected days rather than
  stored separately, so ``Mon/Wed/Fri`` with a quota of 2 cannot be expressed.
* A habit completes at most once per calendar date, so a weekly quota can never
  exceed 7.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.errors import InvalidScheduleError

WEEKDAY_LABELS: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

DAYS_PER_WEEK = 7
MIN_TIMES_PER_WEEK = 1
MAX_TIMES_PER_WEEK = DAYS_PER_WEEK


class ScheduleType(StrEnum):
    """Supported schedule types."""

    DAILY = "daily"
    WEEKDAYS = "weekdays"
    TIMES_PER_WEEK = "times_per_week"


def normalise_weekdays(weekdays: object) -> tuple[int, ...]:
    """Validate and canonicalise a weekday selection.

    Accepts any iterable of integers, rejects empty selections, duplicates and
    out-of-range values, and returns them in Monday-first order.
    """
    if weekdays is None:
        raise InvalidScheduleError("Select at least one weekday.")

    try:
        values = list(weekdays)  # type: ignore[arg-type]
    except TypeError as exc:  # pragma: no cover - defensive, schemas send lists
        raise InvalidScheduleError("Weekdays must be a list of numbers.") from exc

    if not values:
        raise InvalidScheduleError("Select at least one weekday.")

    cleaned: list[int] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int):
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise InvalidScheduleError(
                    "Weekdays must be whole numbers between 0 (Monday) and 6 (Sunday)."
                ) from exc
        if not 0 <= value <= DAYS_PER_WEEK - 1:
            raise InvalidScheduleError(
                "Weekdays must be between 0 (Monday) and 6 (Sunday).",
                details={"weekday": value},
            )
        if value in cleaned:
            raise InvalidScheduleError(
                "A weekday can only be selected once.", details={"weekday": value}
            )
        cleaned.append(value)

    return tuple(sorted(cleaned))


def validate_times_per_week(times_per_week: object) -> int:
    """Validate a weekly quota, which must be 1–7."""
    if isinstance(times_per_week, bool) or not isinstance(times_per_week, int):
        raise InvalidScheduleError("Enter how many times per week the habit is planned.")

    if not MIN_TIMES_PER_WEEK <= times_per_week <= MAX_TIMES_PER_WEEK:
        raise InvalidScheduleError(
            "A weekly quota must be between 1 and 7 times.",
            details={"times_per_week": times_per_week},
        )
    return times_per_week


@dataclass(frozen=True, slots=True)
class Schedule:
    """A validated habit schedule."""

    type: ScheduleType
    weekdays: tuple[int, ...] = ()
    times_per_week: int | None = None

    # -- construction -------------------------------------------------------

    @classmethod
    def create(
        cls,
        schedule_type: ScheduleType | str,
        *,
        weekdays: object = None,
        times_per_week: object = None,
    ) -> Schedule:
        """Build a schedule from API/DB parts, enforcing the shape per type.

        Exactly one shape is allowed, so a daily habit cannot carry weekdays and
        a weekday habit cannot carry an independent weekly quota.
        """
        try:
            resolved = ScheduleType(schedule_type)
        except ValueError as exc:
            raise InvalidScheduleError(
                "Unknown schedule type.", details={"schedule_type": str(schedule_type)}
            ) from exc

        if resolved is ScheduleType.DAILY:
            if weekdays or times_per_week is not None:
                raise InvalidScheduleError(
                    "A daily habit must not define weekdays or a weekly quota."
                )
            return cls(ScheduleType.DAILY)

        if resolved is ScheduleType.WEEKDAYS:
            if times_per_week is not None:
                raise InvalidScheduleError(
                    "The weekly quota of a weekday schedule comes from the "
                    "selected weekdays and must not be set separately."
                )
            return cls(ScheduleType.WEEKDAYS, weekdays=normalise_weekdays(weekdays))

        if weekdays:
            raise InvalidScheduleError(
                "A times-per-week habit must not define preferred weekdays."
            )
        return cls(
            ScheduleType.TIMES_PER_WEEK,
            times_per_week=validate_times_per_week(times_per_week),
        )

    # -- derived values -----------------------------------------------------

    @property
    def weekly_required_count(self) -> int:
        """How many completions the week expects for this habit."""
        if self.type is ScheduleType.DAILY:
            return DAYS_PER_WEEK
        if self.type is ScheduleType.WEEKDAYS:
            return len(self.weekdays)
        assert self.times_per_week is not None  # guaranteed by create()
        return self.times_per_week

    @property
    def summary(self) -> str:
        """Short human-readable description, safe to show in the UI.

        Deliberately ASCII: the summaries travel through console tools, logs and
        a Windows terminal whose code page may not be UTF-8, and nothing here is
        worth an encoding failure.
        """
        if self.type is ScheduleType.DAILY:
            return "Every day"
        if self.type is ScheduleType.WEEKDAYS:
            days = ", ".join(WEEKDAY_LABELS[day] for day in self.weekdays)
            return f"{days} ({self.weekly_required_count} per week)"
        return f"{self.weekly_required_count} per week"

    # -- persistence --------------------------------------------------------

    @property
    def stored_weekdays(self) -> list[int] | None:
        """Weekday list for storage (``None`` when the schedule has no weekdays)."""
        return list(self.weekdays) if self.weekdays else None

    @property
    def stored_times_per_week(self) -> int | None:
        """Weekly quota for storage (``None`` unless it is the free quota form)."""
        if self.type is ScheduleType.DAILY:
            return None
        return self.times_per_week
