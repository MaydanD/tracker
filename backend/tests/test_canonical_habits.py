"""The shipped habit set: 24 ordinary habits, created once, editable like any other.

The point of these tests is the claim the whole design rests on: the habits
Tracker creates for the user are not a subsystem. They are the same rows the user
could have made by hand, they are reconciled idempotently on every start, they
line up with the manifest (order, scale, labels, direction, importance), and the
ordinary habit editor can change every part of them afterwards.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import today_local
from app.db.models import Area, DailyHabitEntry, Habit, HabitVersion
from app.domain.canonical import CANONICAL_AREAS, CANONICAL_HABITS
from app.domain.daily import EntryStatus
from app.domain.habits import HabitConfig, Importance
from app.domain.schedule import Schedule, ScheduleType
from app.domain.tracking import TrackingMode
from app.services import canonical, daily as daily_service
from app.services import habits as habit_service


@pytest.fixture()
def reconciled(session: Session) -> canonical.ReconcileSummary:
    """The canonical set as a first start would create it."""
    return canonical.reconcile_canonical(session, today=today_local())


def habit_rows(session: Session) -> list[Habit]:
    return list(session.scalars(select(Habit).order_by(Habit.sort_order)))


def plain_config(area_id: int, *, name: str = "Старая привычка") -> HabitConfig:
    """A habit configuration of the kind that predates the shipped set."""
    return HabitConfig.create(
        name=name,
        area_id=area_id,
        tracking_mode=TrackingMode.BINARY,
        schedule=Schedule.create(ScheduleType.DAILY),
    )


class TestBootstrap:
    def test_creates_the_four_areas_and_the_twenty_four_habits(
        self, session: Session, reconciled: canonical.ReconcileSummary
    ) -> None:
        assert reconciled.areas_created == 4
        assert reconciled.habits_created == 24

        areas = list(session.scalars(select(Area).order_by(Area.sort_order)))
        assert [(area.key, area.name, area.color) for area in areas] == [
            (area.key, area.name, area.color) for area in CANONICAL_AREAS
        ]

        habits = habit_rows(session)
        assert [habit.key for habit in habits] == [row.key for row in CANONICAL_HABITS]
        assert all(not habit.is_archived for habit in habits)

    def test_every_habit_is_in_its_manifest_area(self, session: Session, reconciled) -> None:
        areas = {area.key: area for area in session.scalars(select(Area))}
        habits = {habit.key: habit for habit in habit_rows(session)}

        for definition in CANONICAL_HABITS:
            habit = habits[definition.key]
            assert habit.current_version.area_id == areas[definition.area_key].id

    def test_the_manifest_order_is_the_order_the_user_sees(
        self, session: Session, reconciled
    ) -> None:
        assert [habit.sort_order for habit in habit_rows(session)] == list(range(1, 25))

    def test_every_habit_is_normal_importance(self, session: Session, reconciled) -> None:
        """Tracker does not decide what matters to the user: everything is normal."""
        assert {habit.current_version.importance_enum for habit in habit_rows(session)} == {
            Importance.NORMAL
        }

    def test_every_habit_carries_the_scale_it_is_answered_on(
        self, session: Session, reconciled
    ) -> None:
        habits = {habit.key: habit for habit in habit_rows(session)}

        for definition in CANONICAL_HABITS:
            version = habits[definition.key].current_version
            assert version.value_type_enum is definition.value_type
            assert tuple(version.value_labels or ()) == definition.labels
            assert version.direction_enum is definition.direction
            # Answered as a value, not as a completion: no quantity, and the
            # schedule is every day.
            assert version.tracking_mode == TrackingMode.BINARY.value
            assert version.quantity_unit is None
            assert version.schedule.type is ScheduleType.DAILY

    def test_a_second_start_changes_nothing(self, session: Session, reconciled) -> None:
        """Reconciliation is idempotent: no duplicates, whatever happens on restart."""
        again = canonical.reconcile_canonical(session, today=today_local())

        assert not again.changed
        assert again.habits_created == 0
        assert len(habit_rows(session)) == 24
        assert len(list(session.scalars(select(Area)))) == 4
        assert len(list(session.scalars(select(HabitVersion)))) == 24

    def test_the_habits_read_back_through_the_ordinary_api(
        self, client: TestClient, session: Session, reconciled
    ) -> None:
        areas = client.get("/api/areas").json()
        habits = client.get("/api/habits").json()

        assert [area["name"] for area in areas] == [
            area.name for area in CANONICAL_AREAS
        ]
        assert [habit["name"] for habit in habits] == [
            row.name for row in CANONICAL_HABITS
        ]
        assert [habit["key"] for habit in habits] == [
            row.key for row in CANONICAL_HABITS
        ]
        first = habits[0]
        assert first["importance"] == "normal"
        assert first["weight"] == 1
        assert first["value_type"] == "binary"
        assert first["value_labels"] == ["нет", "да"]
        assert first["direction"] == "positive"


class TestEditableLikeAnyOtherHabit:
    def test_every_part_of_a_shipped_habit_can_be_changed(
        self, client: TestClient, session: Session, reconciled
    ) -> None:
        """Name, area, scale, labels, direction and importance are all ordinary config."""
        target = client.get("/api/habits").json()[2]  # Тело · Прогулка
        another_area = client.get("/api/areas").json()[1]

        response = client.put(
            f"/api/habits/{target['id']}",
            json={
                "name": "Прогулка после обеда",
                "area_id": another_area["id"],
                "importance": "high",
                "tracking_mode": "binary",
                "quantity_unit": None,
                "quantity_allows_decimal": False,
                "value_type": "ordinal_4",
                "value_labels": ["нет", "чуть", "норм", "много"],
                "direction": "neutral",
                "schedule": {"type": "weekdays", "weekdays": [0, 1, 2, 3, 4]},
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["name"] == "Прогулка после обеда"
        assert body["area"]["id"] == another_area["id"]
        assert body["importance"] == "high"
        assert body["value_labels"] == ["нет", "чуть", "норм", "много"]
        assert body["direction"] == "neutral"

        # Still the same habit, still recognised by reconciliation, and the edit is
        # history rather than a rewrite of the past.
        assert body["key"] == "body.walk"
        assert canonical.reconcile_canonical(session, today=today_local()).habits_created == 0

        # One version per habit per calendar day (Stage 2's rule), so an edit made
        # on the day the habit was created updates that day's version instead of
        # stacking a second one. An edit made later adds one and keeps this one.
        history = client.get(f"/api/habits/{target['id']}/versions").json()
        assert [row["version_number"] for row in history] == [1]
        assert [row["importance"] for row in history] == ["high"]
        assert history[0]["name"] == "Прогулка после обеда"

    def test_a_shipped_habit_can_be_archived_and_restored(
        self, client: TestClient, session: Session, reconciled
    ) -> None:
        target = client.get("/api/habits").json()[0]

        assert client.post(f"/api/habits/{target['id']}/archive").status_code == 200
        assert client.get("/api/habits").json()[0]["id"] != target["id"]
        assert client.post(f"/api/habits/{target['id']}/unarchive").status_code == 200
        assert len(client.get("/api/habits").json()) == 24


class TestRetirement:
    def _pre_canonical_habit(self, session: Session) -> Habit:
        """A habit from before the shipped set, with a recorded day of its own."""
        area = session.scalars(select(Area)).first()
        assert area is not None
        before = today_local() - timedelta(days=10)
        habit = habit_service.create_habit(
            session, plain_config(area.id), effective_date=before
        )
        daily_service.save_entry(
            session,
            habit.id,
            before,
            status=EntryStatus.DONE,
            today=today_local(),
        )
        return habit

    def test_pre_canonical_habits_are_archived_and_their_history_kept(
        self, session: Session, reconciled
    ) -> None:
        legacy = self._pre_canonical_habit(session)

        summary = canonical.reconcile_canonical(session, today=today_local())

        assert summary.legacy_habits_archived == 1
        session.refresh(legacy)
        assert legacy.is_archived
        # Nothing is deleted: the day the user recorded is still there.
        assert session.scalar(
            select(DailyHabitEntry).where(DailyHabitEntry.habit_id == legacy.id)
        ) is not None
        assert legacy.versions != []

    def test_a_habit_created_after_the_set_is_never_retired(
        self, client: TestClient, session: Session, reconciled
    ) -> None:
        response = client.post(
            "/api/habits",
            json={
                "name": "Моя привычка",
                "area_id": client.get("/api/areas").json()[0]["id"],
                "importance": "normal",
                "tracking_mode": "binary",
                "schedule": {"type": "daily"},
            },
        )
        assert response.status_code == 201, response.text

        assert canonical.reconcile_canonical(session, today=today_local()).changed is False
        assert response.json()["id"] in {habit.id for habit in habit_rows(session)}


class TestValueHabitsAndTheScore:
    def test_a_value_habit_is_not_a_completion_obligation(
        self, client: TestClient, session: Session, reconciled
    ) -> None:
        """Evaluation includes directed scales; completion includes all 24."""
        progress = client.get(f"/api/progress/days/{today_local().isoformat()}").json()

        assert progress["day"]["required_weight"] == 18
        assert len(progress["day"]["obligations"]) == 18
        assert progress["day"]["total_count"] == 24
        assert progress["day"]["filled_count"] == 0

    def test_the_day_shows_every_value_habit_with_its_scale(
        self, client: TestClient, session: Session, reconciled
    ) -> None:
        day = client.get(f"/api/days/{today_local().isoformat()}").json()

        assert len(day["items"]) == 24
        assert all(item["value_type"] is not None for item in day["items"])
        assert all(item["entry"] is None for item in day["items"])
        assert {item["importance"] for item in day["items"]} == {"normal"}

    def test_an_answer_is_returned_with_its_scale_and_direction(
        self, client: TestClient, session: Session, reconciled
    ) -> None:
        target = client.get("/api/habits").json()[7]  # Тело · Симптомы заболевания
        assert target["direction"] == "negative"

        response = client.put(
            f"/api/habits/{target['id']}/entries/{today_local().isoformat()}",
            json={"status": "done", "value": 3},
        )

        assert response.status_code == 200, response.text
        assert response.json()["value"] == 3
        day = client.get(f"/api/days/{today_local().isoformat()}").json()
        item = next(row for row in day["items"] if row["habit_id"] == target["id"])
        assert item["entry"]["value"] == 3
        assert item["value_labels"] == ["нет", "слабые", "заметные", "сильные"]
        assert item["direction"] == "negative"
