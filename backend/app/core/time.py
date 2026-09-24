"""Time helpers and the application clock.

Every stored timestamp is UTC. SQLite's ``DATETIME`` type has no timezone
support, so the offset is dropped on the way in and values come back as naive
UTC; date *logic* (daily entries, schedules, streaks, day boundaries) must
therefore work from explicit calendar dates rather than from local timestamps.

Calendar rules need "today", and a rule that reads the wall clock directly is
impossible to test and easy to scatter. Everything that depends on the current
date therefore goes through :class:`Clock`, injected once per application
instance (``app.state.clock``). Tests substitute a frozen clock instead of
patching ``datetime``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Protocol


def utc_now() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def today_local() -> date:
    """Today as a calendar date in the machine's local timezone.

    Tracker runs on the user's own machine, so the local calendar date is the
    authoritative "today" for schedules, weekly quotas and configuration
    history. Timestamps stay UTC, but calendar logic must never be shifted by a
    timezone offset — a habit completed at 00:30 belongs to that local day.
    """
    return datetime.now().date()


class Clock(Protocol):
    """Source of the current local date and wall-clock time."""

    def today(self) -> date:
        """Today as a local calendar date."""
        ...

    def now(self) -> datetime:
        """The current local wall-clock time, used for user-facing names.

        Naive on purpose: it never becomes a stored timestamp (those are UTC) and
        exists for things like backup file names, which a user reads in their own
        local time.
        """
        ...


class SystemClock:
    """The real clock: the machine's local time.

    Both of its methods are local-time based and share one calendar: ``today()``
    is the local date, ``now()`` the local wall clock, so a backup written at
    00:30 belongs to the new day just like an entry recorded at 00:30.
    """

    def today(self) -> date:
        return today_local()

    def now(self) -> datetime:
        return datetime.now()


#: Process-wide clock for callers that are not wired through the application.
SYSTEM_CLOCK = SystemClock()
