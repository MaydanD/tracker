"""Time helpers.

Every stored timestamp is UTC. SQLite's ``DATETIME`` type has no timezone
support, so the offset is dropped on the way in and values come back as naive
UTC; date *logic* (schedules, streaks, day boundaries — Stage 4) must therefore
work from explicit calendar dates rather than from local timestamps.
"""

from __future__ import annotations

from datetime import UTC, date, datetime


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
