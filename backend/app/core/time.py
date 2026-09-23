"""Time helpers.

Every stored timestamp is UTC. SQLite's ``DATETIME`` type has no timezone
support, so the offset is dropped on the way in and values come back as naive
UTC; date *logic* (schedules, streaks, day boundaries — Stage 4) must therefore
work from explicit calendar dates rather than from local timestamps.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)
