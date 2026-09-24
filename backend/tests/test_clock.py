"""The application clock and its one source of "today".

Calendar rules (which day an entry belongs to, what counts as the future, which
habit configuration applies) must not read the wall clock in ten different
places: they take a date, and "today" comes from the injected clock. These tests
pin that convention, including a scan of the application source, so a stray
``date.today()`` cannot creep back into a service.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.time import SYSTEM_CLOCK, Clock, SystemClock, today_local, utc_now
from app.domain.habits import HabitConfig
from app.domain.schedule import Schedule
from app.domain.tracking import TrackingMode
from app.services import areas as area_service
from app.services import habits as habit_service
from tests.helpers import FrozenClock

APP_DIR = Path(__file__).resolve().parents[1] / "app"

#: Reads of the wall clock that are allowed to exist, and why.
CLOCK_IMPLEMENTATIONS = {"core/time.py"}

_WALL_CLOCK_PATTERN = re.compile(r"\b(datetime\.now|datetime\.today|date\.today)\s*\(")


class TestSystemClock:
    def test_today_is_the_machines_local_calendar_date(self) -> None:
        assert SYSTEM_CLOCK.today() == today_local()

    def test_now_is_a_local_wall_clock_time(self) -> None:
        """Backup file names are local, while stored timestamps stay UTC."""
        moment = SYSTEM_CLOCK.now()

        assert moment.tzinfo is None
        assert moment.date() == SYSTEM_CLOCK.today()

    def test_stored_timestamps_are_utc(self) -> None:
        assert utc_now().tzinfo is UTC

    def test_a_frozen_clock_satisfies_the_same_shape(self) -> None:
        """Both clocks are interchangeable, so tests swap one for the other."""
        frozen = FrozenClock(SYSTEM_CLOCK.today())
        clocks: list[Clock] = [SystemClock(), frozen]

        for clock in clocks:
            assert isinstance(clock.today(), date)
            assert isinstance(clock.now(), datetime)
        assert frozen.today() == SYSTEM_CLOCK.today()


class TestWallClockIsNotScattered:
    def test_only_the_clock_module_reads_the_wall_clock(self) -> None:
        offenders: list[str] = []

        for path in sorted(APP_DIR.rglob("*.py")):
            relative = path.relative_to(APP_DIR).as_posix()
            if relative in CLOCK_IMPLEMENTATIONS:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if _WALL_CLOCK_PATTERN.search(line):
                    offenders.append(f"{relative}:{number}")

        assert offenders == [], (
            "calendar rules must take a date from the injected clock instead of "
            f"reading the wall clock: {offenders}"
        )


def test_the_service_default_effective_date_comes_from_the_clock(
    session: Session,
) -> None:
    """A caller that omits the effective date still gets the clock's today."""
    area_id = area_service.create_area(session, name="Health").id

    created = habit_service.create_habit(
        session,
        HabitConfig.create(
            name="Reading",
            area_id=area_id,
            weight=1,
            tracking_mode=TrackingMode.BINARY,
            schedule=Schedule.create("daily"),
        ),
    )

    assert created.current_version.effective_from == SYSTEM_CLOCK.today()
