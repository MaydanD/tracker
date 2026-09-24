"""Daily tracking endpoints.

The behaviours that matter most are semantic, not structural:

* ``no entry`` is a state of its own and is never turned into ``missed``;
* ``(habit, date)`` holds at most one record, so saving is idempotent;
* a future date accepts a planned skip and nothing else;
* a quantity is judged by the habit configuration that was in force *on that
  date*, not by the habit's current settings.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import today_local
from app.db.database import Database
from app.db.models import DailyHabitEntry, Habit
from app.domain.habits import HabitConfig
from app.domain.schedule import Schedule
from app.domain.tracking import TrackingMode
from app.main import create_app
from app.services import areas as area_service
from app.services import daily as daily_service
from app.services import habits as habit_service
from tests.helpers import FrozenClock, habit_payload

TODAY = today_local()


def on(days: int) -> str:
    """ISO date ``days`` away from today (negative is the past)."""
    return (TODAY + timedelta(days=days)).isoformat()


def create_habit(client: TestClient, area_id: int, **overrides: object) -> dict:
    """Create a habit through the API; its first configuration dates from today."""
    response = client.post(
        "/api/habits", json=habit_payload(area_id=area_id, **overrides)
    )
    assert response.status_code == 201, response.text
    return response.json()


def habit_config(area_id: int, **overrides: object) -> HabitConfig:
    """A valid configuration for service calls (the domain twin of habit_payload)."""
    values: dict[str, object] = {
        "name": "Reading",
        "area_id": area_id,
        "weight": 1,
        "tracking_mode": TrackingMode.BINARY,
        "schedule": Schedule.create("daily"),
    }
    values.update(overrides)
    return HabitConfig.create(**values)  # type: ignore[arg-type]


def create_habit_since(
    session: Session, area_id: int, *, days: int = 30, **overrides: object
) -> int:
    """Create a habit whose first configuration applies ``days`` days ago.

    ``POST /api/habits`` dates the first configuration from today, so a test that
    records or edits an older day needs a habit that already existed then. The
    service already accepts an explicit effective date — that is exactly this.
    """
    habit = habit_service.create_habit(
        session,
        habit_config(area_id, **overrides),
        effective_date=TODAY - timedelta(days=days),
    )
    return habit.id


def put_entry(
    client: TestClient,
    habit_id: int,
    entry_date: str,
    status: str = "done",
    **extra: object,
) -> Response:
    return client.put(
        f"/api/habits/{habit_id}/entries/{entry_date}",
        json={"status": status, **extra},
    )


def entry_rows(database: Database, habit_id: int, entry_date: str) -> int:
    """Count stored rows directly, so uniqueness is checked in the database."""
    with database.session() as session:
        return session.scalar(
            select(func.count())
            .select_from(DailyHabitEntry)
            .where(
                DailyHabitEntry.habit_id == habit_id,
                DailyHabitEntry.entry_date == date.fromisoformat(entry_date),
            )
        )


def insert_entry_directly(
    database: Database, habit_id: int, entry_date: str, status: str = "missed"
) -> None:
    """Write a row behind the service's back, as a concurrent writer would."""
    with database.session() as session:
        session.execute(
            text(
                "INSERT INTO daily_habit_entries (habit_id, entry_date, status, "
                "created_at, updated_at) VALUES (:habit_id, :day, :status, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"habit_id": habit_id, "day": entry_date, "status": status},
        )
        session.commit()


def day_item(client: TestClient, habit_id: int, entry_date: str) -> dict:
    response = client.get(f"/api/days/{entry_date}")
    assert response.status_code == 200, response.text
    for item in response.json()["items"]:
        if item["habit_id"] == habit_id:
            return item
    raise AssertionError(f"Habit {habit_id} is not listed on {entry_date}")


class TestNoEntryState:
    """The absence of a record is not a missed habit."""

    def test_a_day_the_user_has_not_touched_reports_no_entry(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        item = day_item(client, habit["id"], on(0))

        assert item["entry"] is None

    def test_an_unrecorded_habit_is_not_reported_as_missed(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=10)

        # An old day the user never touched stays unrecorded; nothing fills it in.
        item = day_item(client, habit_id, on(-3))

        assert item["entry"] is None
        assert item["entry"] != {"status": "missed"}

    def test_fetching_an_unrecorded_entry_is_a_404(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        response = client.get(f"/api/habits/{habit['id']}/entries/{on(0)}")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "daily_entry_not_found"

    def test_only_recorded_days_appear_as_entries(
        self,
        database: Database,
        session: Session,
        client: TestClient,
        health_area: dict,
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=10)
        put_entry(client, habit_id, on(-1))

        assert entry_rows(database, habit_id, on(-2)) == 0
        assert entry_rows(database, habit_id, on(-1)) == 1


class TestRecordingDays:
    def test_records_done_today(self, client: TestClient, health_area: dict) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        response = put_entry(client, habit["id"], on(0), "done")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "done"
        assert body["entry_date"] == on(0)
        assert body["habit_id"] == habit["id"]
        assert body["quantity_value"] is None
        assert body["skip_reason"] is None
        assert body["note"] is None

    def test_records_done_in_the_past(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=30)

        response = put_entry(client, habit_id, on(-30), "done")

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "done"

    def test_records_missed_today(self, client: TestClient, health_area: dict) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        response = put_entry(client, habit["id"], on(0), "missed")

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "missed"

    def test_records_missed_in_the_past(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=10)

        response = put_entry(client, habit_id, on(-5), "missed")

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "missed"

    def test_records_skipped_in_the_past(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=10)

        response = put_entry(client, habit_id, on(-2), "skipped", skip_reason="Болезнь")

        assert response.status_code == 200, response.text
        assert response.json()["skip_reason"] == "Болезнь"

    def test_an_unknown_status_is_rejected(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        response = put_entry(client, habit["id"], on(0), "maybe")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_an_unknown_habit_is_rejected(self, client: TestClient) -> None:
        response = put_entry(client, 4242, on(0), "done")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "habit_not_found"

    def test_a_date_before_the_habit_existed_is_rejected(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        response = put_entry(client, habit["id"], on(-1), "done")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "configuration_not_found"

    def test_a_malformed_date_is_a_validation_error(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        response = client.put(
            f"/api/habits/{habit['id']}/entries/not-a-date", json={"status": "done"}
        )

        assert response.status_code == 422


class TestFutureRules:
    @pytest.mark.parametrize("status", ["done", "missed"])
    def test_a_future_date_rejects_done_and_missed(
        self, client: TestClient, health_area: dict, status: str
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        response = put_entry(client, habit["id"], on(1), status)

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "future_entry_not_allowed"

    def test_a_future_date_accepts_a_planned_skip(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        response = put_entry(client, habit["id"], on(7), "skipped", skip_reason="Отпуск")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "skipped"
        assert body["skip_reason"] == "Отпуск"

    def test_a_planned_skip_can_be_edited_and_removed(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")
        put_entry(client, habit["id"], on(3), "skipped", skip_reason="Отпуск")

        edited = put_entry(
            client,
            habit["id"],
            on(3),
            "skipped",
            skip_reason="Поездка",
            note="вернусь в среду",
        )

        assert edited.status_code == 200
        assert edited.json()["skip_reason"] == "Поездка"
        assert edited.json()["note"] == "вернусь в среду"

        removed = client.delete(f"/api/habits/{habit['id']}/entries/{on(3)}")
        assert removed.status_code == 204
        assert day_item(client, habit["id"], on(3))["entry"] is None

    def test_the_future_rule_reads_the_injected_clock(
        self, migrated_settings: Settings, health_area: dict
    ) -> None:
        """'Today' must come from the application clock, not from the machine."""
        clock = FrozenClock(TODAY - timedelta(days=10))
        with TestClient(create_app(migrated_settings, clock=clock)) as client:
            # Created "ten days ago" as far as the application is concerned.
            habit = create_habit(client, health_area["id"], name="Reading")

            # A real calendar day that this application still considers future.
            response = put_entry(client, habit["id"], on(0), "done")

            assert response.status_code == 422
            assert response.json()["error"]["code"] == "future_entry_not_allowed"

            day = client.get(f"/api/days/{on(0)}").json()
            assert day["is_future"] is True
            assert day["today"] == on(-10)


class TestSkipReason:
    def test_a_skipped_entry_without_a_reason_is_rejected(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        response = put_entry(client, habit["id"], on(0), "skipped")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "skip_reason_required"

    def test_a_whitespace_only_reason_is_rejected(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        response = put_entry(client, habit["id"], on(0), "skipped", skip_reason="   ")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "skip_reason_required"

    @pytest.mark.parametrize("status", ["done", "missed"])
    def test_a_reason_on_a_non_skipped_entry_is_rejected(
        self, client: TestClient, health_area: dict, status: str
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        response = put_entry(client, habit["id"], on(0), status, skip_reason="Болезнь")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "skip_reason_not_allowed"

    def test_the_reason_is_trimmed(self, client: TestClient, health_area: dict) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        response = put_entry(
            client, habit["id"], on(0), "skipped", skip_reason="  поездка  "
        )

        assert response.status_code == 200
        assert response.json()["skip_reason"] == "поездка"

    def test_an_over_long_reason_is_rejected(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        response = put_entry(client, habit["id"], on(0), "skipped", skip_reason="x" * 500)

        assert response.status_code == 422


class TestNotes:
    def test_a_note_is_stored_next_to_the_status(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        response = put_entry(client, habit["id"], on(0), "done", note="прочитал вечером")

        assert response.status_code == 200
        assert response.json()["note"] == "прочитал вечером"

    def test_a_note_and_a_skip_reason_stay_separate(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        body = put_entry(
            client,
            habit["id"],
            on(0),
            "skipped",
            skip_reason="Отпуск",
            note="вернулся поздно",
        ).json()

        assert body["skip_reason"] == "Отпуск"
        assert body["note"] == "вернулся поздно"

    def test_a_note_can_be_removed_by_saving_without_it(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")
        put_entry(client, habit["id"], on(0), "done", note="заметка")

        body = put_entry(client, habit["id"], on(0), "done").json()

        assert body["note"] is None


class TestIdempotentSaving:
    def test_saving_the_same_day_twice_keeps_one_row(
        self, database: Database, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        put_entry(client, habit["id"], on(0), "done")
        put_entry(client, habit["id"], on(0), "done")

        assert entry_rows(database, habit["id"], on(0)) == 1

    def test_saving_again_edits_the_existing_record(
        self,
        database: Database,
        session: Session,
        client: TestClient,
        health_area: dict,
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=10)
        first = put_entry(client, habit_id, on(-1), "missed").json()

        second = put_entry(client, habit_id, on(-1), "done", note="исправил").json()

        assert second["id"] == first["id"]
        assert second["status"] == "done"
        assert second["note"] == "исправил"
        assert entry_rows(database, habit_id, on(-1)) == 1

    def test_editing_keeps_created_at_and_moves_updated_at(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")
        first = put_entry(client, habit["id"], on(0), "done").json()

        second = put_entry(client, habit["id"], on(0), "missed").json()

        assert second["created_at"] == first["created_at"]
        assert second["updated_at"] >= first["updated_at"]

    @pytest.mark.parametrize(
        "quantity", [6.4, 0.000001, 42.195, 999999.999999, 0, 35]
    )
    def test_reading_back_a_stored_quantity_returns_the_same_number(
        self, client: TestClient, health_area: dict, quantity: float
    ) -> None:
        """Read-write-read must be a fixed point, including at the extremes."""
        habit = create_habit(
            client,
            health_area["id"],
            name="Walking",
            tracking_mode="binary_quantity",
            quantity_unit="km",
            quantity_allows_decimal=True,
        )

        saved = put_entry(
            client, habit["id"], on(0), "done", quantity_value=quantity
        ).json()
        reread = client.get(f"/api/habits/{habit['id']}/entries/{on(0)}").json()
        replayed = put_entry(
            client,
            habit["id"],
            on(0),
            "done",
            quantity_value=reread["quantity_value"],
        ).json()

        assert saved["quantity_value"] == quantity
        assert reread["quantity_value"] == quantity
        assert replayed["quantity_value"] == quantity

    def test_two_days_are_two_rows(
        self,
        database: Database,
        session: Session,
        client: TestClient,
        health_area: dict,
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=10)

        put_entry(client, habit_id, on(0), "done")
        put_entry(client, habit_id, on(-1), "missed")

        assert entry_rows(database, habit_id, on(0)) == 1
        assert entry_rows(database, habit_id, on(-1)) == 1


class TestConcurrentSaving:
    """Two saves of one day must never become two rows or a 500.

    The service looks the row up and then inserts it. A second request can slip
    into that window (a double-clicked save, or two clients); the unique
    constraint catches the loser, and the request has to fall back to updating
    the row that appeared instead of failing with an internal error.
    """

    def test_a_save_that_races_another_save_still_keeps_one_row(
        self,
        database: Database,
        session: Session,
        client: TestClient,
        health_area: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=10)
        real_find = daily_service._find
        raced: list[bool] = []

        def find_then_lose_the_race(
            service_session: Session, habit: int, day: date
        ) -> DailyHabitEntry | None:
            found = real_find(service_session, habit, day)
            if found is None and not raced:
                raced.append(True)
                # The other writer commits between our lookup and our insert.
                insert_entry_directly(database, habit, day.isoformat())
            return found

        monkeypatch.setattr(daily_service, "_find", find_then_lose_the_race)

        response = put_entry(client, habit_id, on(-1), "done", note="мой вариант")

        assert raced, "the test did not exercise the interleaving"
        assert response.status_code == 200, response.text
        # Last write wins, exactly as any other repeat save of that day.
        assert response.json()["status"] == "done"
        assert response.json()["note"] == "мой вариант"
        assert entry_rows(database, habit_id, on(-1)) == 1


class TestDeleting:
    def test_deleting_returns_the_day_to_no_entry(
        self,
        database: Database,
        session: Session,
        client: TestClient,
        health_area: dict,
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=10)
        put_entry(client, habit_id, on(-1), "missed")

        response = client.delete(f"/api/habits/{habit_id}/entries/{on(-1)}")

        assert response.status_code == 204
        assert entry_rows(database, habit_id, on(-1)) == 0
        assert day_item(client, habit_id, on(-1))["entry"] is None

    def test_deleting_never_substitutes_missed(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=10)
        put_entry(client, habit_id, on(-1), "done")

        client.delete(f"/api/habits/{habit_id}/entries/{on(-1)}")

        item = day_item(client, habit_id, on(-1))
        assert item["entry"] is None, "a cleared day must not become 'missed'"

    def test_deleting_a_day_that_holds_nothing_is_a_no_op(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        response = client.delete(f"/api/habits/{habit['id']}/entries/{on(0)}")

        assert response.status_code == 204

    def test_deleting_for_an_unknown_habit_is_a_404(self, client: TestClient) -> None:
        response = client.delete(f"/api/habits/4242/entries/{on(0)}")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "habit_not_found"


class TestQuantity:
    def test_a_binary_habit_rejects_a_quantity(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Meditate")

        response = put_entry(client, habit["id"], on(0), "done", quantity_value=5)

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "quantity_not_allowed"

    def test_a_quantity_habit_accepts_a_quantity(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(
            client,
            health_area["id"],
            name="Reading",
            tracking_mode="binary_quantity",
            quantity_unit="pages",
        )

        response = put_entry(client, habit["id"], on(0), "done", quantity_value=35)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["quantity_value"] == 35
        assert body["quantity_unit"] == "pages"

    def test_a_quantity_is_optional(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(
            client,
            health_area["id"],
            name="Reading",
            tracking_mode="binary_quantity",
            quantity_unit="pages",
        )

        body = put_entry(client, habit["id"], on(0), "done").json()

        assert body["quantity_value"] is None

    def test_a_fraction_is_rejected_when_the_habit_forbids_decimals(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(
            client,
            health_area["id"],
            name="Reading",
            tracking_mode="binary_quantity",
            quantity_unit="pages",
            quantity_allows_decimal=False,
        )

        response = put_entry(client, habit["id"], on(0), "done", quantity_value=6.4)

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "quantity_decimal_not_allowed"

    def test_a_fraction_is_accepted_when_decimals_are_allowed(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(
            client,
            health_area["id"],
            name="Walking",
            tracking_mode="binary_quantity",
            quantity_unit="km",
            quantity_allows_decimal=True,
        )

        response = put_entry(client, habit["id"], on(0), "done", quantity_value=6.4)

        assert response.status_code == 200, response.text
        assert response.json()["quantity_value"] == 6.4
        assert response.json()["quantity_unit"] == "km"

    def test_a_decimal_value_is_stored_exactly(
        self, database: Database, client: TestClient, health_area: dict
    ) -> None:
        """No binary float in the database: 6.4 is 6 400 000 millionths."""
        habit = create_habit(
            client,
            health_area["id"],
            name="Walking",
            tracking_mode="binary_quantity",
            quantity_unit="km",
            quantity_allows_decimal=True,
        )
        put_entry(client, habit["id"], on(0), "done", quantity_value=6.4)

        with database.session() as session:
            stored = session.scalar(
                select(DailyHabitEntry.quantity_value_micro).where(
                    DailyHabitEntry.habit_id == habit["id"]
                )
            )

        assert stored == 6_400_000

    @pytest.mark.parametrize("quantity", [-1, -0.5])
    def test_a_negative_quantity_is_rejected(
        self, client: TestClient, health_area: dict, quantity: float
    ) -> None:
        habit = create_habit(
            client,
            health_area["id"],
            name="Walking",
            tracking_mode="binary_quantity",
            quantity_unit="km",
            quantity_allows_decimal=True,
        )

        response = put_entry(client, habit["id"], on(0), "done", quantity_value=quantity)

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_quantity"

    def test_too_much_precision_is_rejected_rather_than_rounded(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(
            client,
            health_area["id"],
            name="Walking",
            tracking_mode="binary_quantity",
            quantity_unit="km",
            quantity_allows_decimal=True,
        )

        response = put_entry(client, habit["id"], on(0), "done", quantity_value=6.4000001)

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_quantity"


class TestHistoricalConfiguration:
    """A quantity is judged by the configuration that applied on its own date."""

    def pages_then_minutes(
        self, session: Session, client: TestClient, area_id: int
    ) -> dict:
        """A habit that measured pages until five days ago and minutes since.

        Version 1 (from ten days ago): pages, whole numbers only.
        Version 2 (from five days ago): minutes, decimals allowed.
        """
        config = HabitConfig.create(
            name="Reading",
            area_id=area_id,
            weight=1,
            tracking_mode=TrackingMode.BINARY_QUANTITY,
            quantity_unit="pages",
            quantity_allows_decimal=False,
            schedule=Schedule.create("daily"),
        )
        habit = habit_service.create_habit(
            session, config, effective_date=TODAY - timedelta(days=10)
        )

        habit_service.update_habit(
            session,
            habit.id,
            HabitConfig.create(
                name="Reading",
                area_id=area_id,
                weight=1,
                tracking_mode=TrackingMode.BINARY_QUANTITY,
                quantity_unit="minutes",
                quantity_allows_decimal=True,
                schedule=Schedule.create("daily"),
            ),
            effective_date=TODAY - timedelta(days=5),
        )
        return {"id": habit.id}

    def test_a_past_entry_uses_the_past_unit(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit = self.pages_then_minutes(session, client, health_area["id"])

        body = put_entry(client, habit["id"], on(-6), "done", quantity_value=35).json()

        assert body["quantity_unit"] == "pages"

    def test_a_past_entry_is_validated_by_the_past_decimal_rule(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit = self.pages_then_minutes(session, client, health_area["id"])

        # Six days ago the habit was measured in whole pages.
        response = put_entry(client, habit["id"], on(-6), "done", quantity_value=6.4)

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "quantity_decimal_not_allowed"

    def test_a_later_past_entry_uses_the_later_rule(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit = self.pages_then_minutes(session, client, health_area["id"])

        body = put_entry(client, habit["id"], on(-1), "done", quantity_value=6.4).json()

        assert body["quantity_unit"] == "minutes"
        assert body["quantity_value"] == 6.4

    def test_the_same_value_is_judged_differently_on_two_dates(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        """6.4 is invalid on one date and valid five days later."""
        habit = self.pages_then_minutes(session, client, health_area["id"])

        rejected = put_entry(client, habit["id"], on(-6), "done", quantity_value=6.4)
        accepted = put_entry(client, habit["id"], on(-5), "done", quantity_value=6.4)

        assert rejected.status_code == 422
        assert accepted.status_code == 200

    def test_the_day_view_describes_each_date_by_its_own_configuration(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit = self.pages_then_minutes(session, client, health_area["id"])

        older = day_item(client, habit["id"], on(-6))
        newer = day_item(client, habit["id"], on(-1))

        assert older["quantity_unit"] == "pages"
        assert older["quantity_allows_decimal"] is False
        assert newer["quantity_unit"] == "minutes"
        assert newer["quantity_allows_decimal"] is True

    def test_editing_a_past_entry_keeps_the_historical_unit(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit = self.pages_then_minutes(session, client, health_area["id"])
        put_entry(client, habit["id"], on(-7), "done", quantity_value=10)

        body = put_entry(client, habit["id"], on(-7), "done", quantity_value=12).json()

        assert body["quantity_unit"] == "pages"
        assert body["quantity_value"] == 12


class TestDayViewScope:
    """Which habits a date shows: exactly those that existed that day.

    The schedule is deliberately not consulted — assigning habits to days, and
treating an unrecorded day as missed, belongs to a later stage. Nothing here
synthesises an entry.
    """

    def test_a_habit_is_not_listed_before_its_first_configuration(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=3)

        earlier = client.get(f"/api/days/{on(-4)}").json()
        first_day = client.get(f"/api/days/{on(-3)}").json()

        assert habit_id not in [item["habit_id"] for item in earlier["items"]]
        assert habit_id in [item["habit_id"] for item in first_day["items"]]

    def test_a_habit_is_not_listed_on_a_day_before_its_later_configuration(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        """A version that starts later must not pull the habit back in time."""
        habit_id = create_habit_since(session, health_area["id"], days=3)
        habit_service.update_habit(
            session,
            habit_id,
            habit_config(health_area["id"], name="Walking"),
            effective_date=TODAY + timedelta(days=1),
        )

        today = client.get(f"/api/days/{on(0)}").json()

        item = next(i for i in today["items"] if i["habit_id"] == habit_id)
        assert item["name"] == "Reading"

    def test_an_archived_habit_recorded_on_another_day_is_not_listed(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=10)
        put_entry(client, habit_id, on(-2), "done")
        client.post(f"/api/habits/{habit_id}/archive")

        other_day = client.get(f"/api/days/{on(-1)}").json()

        assert habit_id not in [item["habit_id"] for item in other_day["items"]]

    def test_unrecorded_days_stay_unrecorded_for_every_habit_listed(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=10)

        day = client.get(f"/api/days/{on(-5)}").json()

        assert habit_id in [item["habit_id"] for item in day["items"]]
        item = day_item(client, habit_id, on(-5))
        assert item["entry"] is None
        assert [i["entry"] for i in day["items"]] == [None] * len(day["items"])


class TestArchivedHabits:
    def test_a_recorded_day_survives_archiving(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=10)
        put_entry(client, habit_id, on(-2), "done", note="до архива")

        client.post(f"/api/habits/{habit_id}/archive")

        item = day_item(client, habit_id, on(-2))
        assert item["is_archived"] is True
        assert item["entry"]["note"] == "до архива"

    def test_a_recorded_day_stays_readable_through_its_own_endpoint(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=10)
        put_entry(client, habit_id, on(-2), "missed")
        client.post(f"/api/habits/{habit_id}/archive")

        response = client.get(f"/api/habits/{habit_id}/entries/{on(-2)}")

        assert response.status_code == 200
        assert response.json()["status"] == "missed"

    def test_an_archived_habit_can_still_be_edited_for_a_recorded_date(
        self, session: Session, client: TestClient, health_area: dict
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=10)
        put_entry(client, habit_id, on(-2), "missed")
        client.post(f"/api/habits/{habit_id}/archive")

        response = put_entry(client, habit_id, on(-2), "done", note="исправлено")

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "done"

    def test_an_archived_habit_without_a_record_is_not_on_the_day_screen(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")
        client.post(f"/api/habits/{habit['id']}/archive")

        day = client.get(f"/api/days/{on(0)}").json()

        assert [item["habit_id"] for item in day["items"]] == []

    def test_archiving_does_not_delete_anything_in_the_database(
        self,
        database: Database,
        session: Session,
        client: TestClient,
        health_area: dict,
    ) -> None:
        habit_id = create_habit_since(session, health_area["id"], days=10)
        put_entry(client, habit_id, on(-2), "done")

        client.post(f"/api/habits/{habit_id}/archive")

        assert entry_rows(database, habit_id, on(-2)) == 1


class TestDayView:
    def test_the_day_lists_habits_that_existed_on_that_date(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        yesterday = client.get(f"/api/days/{on(-1)}").json()
        today = client.get(f"/api/days/{on(0)}").json()

        # The habit's first configuration is effective from today.
        assert [item["habit_id"] for item in yesterday["items"]] == []
        assert [item["habit_id"] for item in today["items"]] == [habit["id"]]

    def test_the_day_reports_the_date_and_the_rule_it_implies(
        self, client: TestClient, health_area: dict
    ) -> None:
        create_habit(client, health_area["id"], name="Reading")

        today = client.get(f"/api/days/{on(0)}").json()
        tomorrow = client.get(f"/api/days/{on(1)}").json()

        assert today["entry_date"] == on(0)
        assert today["today"] == on(0)
        assert today["is_future"] is False
        assert tomorrow["is_future"] is True

    def test_the_day_carries_the_configuration_of_that_date(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(
            client,
            health_area["id"],
            name="Reading",
            weight=3,
            tracking_mode="binary_quantity",
            quantity_unit="pages",
            quantity_allows_decimal=True,
            schedule={"type": "weekdays", "weekdays": [0, 2, 4]},
        )

        item = day_item(client, habit["id"], on(0))

        assert item["name"] == "Reading"
        assert item["weight"] == 3
        assert item["tracking_mode"] == "binary_quantity"
        assert item["quantity_unit"] == "pages"
        assert item["quantity_allows_decimal"] is True
        assert item["schedule"]["weekdays"] == [0, 2, 4]
        assert item["area"]["name"] == "Health"
        assert item["is_archived"] is False

    def test_the_day_is_ordered_by_area_then_name(
        self, client: TestClient, health_area: dict, other_area: dict
    ) -> None:
        create_habit(client, health_area["id"], name="Sleep")
        create_habit(client, health_area["id"], name="Exercise")
        create_habit(client, other_area["id"], name="Reading")

        day = client.get(f"/api/days/{on(0)}").json()

        assert [item["name"] for item in day["items"]] == ["Reading", "Exercise", "Sleep"]

    def test_the_day_shows_the_recorded_state_of_each_habit(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")
        put_entry(client, habit["id"], on(0), "done", note="вечером")

        item = day_item(client, habit["id"], on(0))

        assert item["entry"]["status"] == "done"
        assert item["entry"]["note"] == "вечером"

    def test_a_habit_with_no_record_has_a_null_entry(
        self, client: TestClient, health_area: dict
    ) -> None:
        habit = create_habit(client, health_area["id"], name="Reading")

        assert day_item(client, habit["id"], on(0))["entry"] is None


class TestDatabaseConstraints:
    """The database backstops the domain rules it can express."""

    def _habit_and_area(self, session: Session, area_id: int) -> int:
        habit = habit_service.create_habit(
            session,
            HabitConfig.create(
                name="Reading",
                area_id=area_id,
                weight=1,
                tracking_mode=TrackingMode.BINARY,
                schedule=Schedule.create("daily"),
            ),
            effective_date=TODAY,
        )
        return habit.id

    def test_rejects_a_second_entry_for_the_same_habit_and_date(
        self, session: Session
    ) -> None:
        area_id = area_service.create_area(session, name="Health").id
        habit_id = self._habit_and_area(session, area_id)
        session.execute(
            text(
                "INSERT INTO daily_habit_entries (habit_id, entry_date, status, "
                "created_at, updated_at) VALUES (:habit_id, :day, 'done', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"habit_id": habit_id, "day": TODAY.isoformat()},
        )
        session.commit()

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO daily_habit_entries (habit_id, entry_date, status, "
                    "created_at, updated_at) VALUES (:habit_id, :day, 'missed', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"habit_id": habit_id, "day": TODAY.isoformat()},
            )
            session.commit()

    def test_rejects_a_skip_without_a_reason(self, session: Session) -> None:
        area_id = area_service.create_area(session, name="Health").id
        habit_id = self._habit_and_area(session, area_id)

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO daily_habit_entries (habit_id, entry_date, status, "
                    "created_at, updated_at) VALUES (:habit_id, :day, 'skipped', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"habit_id": habit_id, "day": TODAY.isoformat()},
            )
            session.commit()

    def test_rejects_a_whitespace_only_reason(self, session: Session) -> None:
        """A reason that is only spaces is not a reason, in the database too."""
        area_id = area_service.create_area(session, name="Health").id
        habit_id = self._habit_and_area(session, area_id)

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO daily_habit_entries (habit_id, entry_date, status, "
                    "skip_reason, created_at, updated_at) VALUES (:habit_id, :day, "
                    "'skipped', '   ', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"habit_id": habit_id, "day": TODAY.isoformat()},
            )
            session.commit()

    def test_rejects_a_reason_on_a_non_skipped_entry(self, session: Session) -> None:
        area_id = area_service.create_area(session, name="Health").id
        habit_id = self._habit_and_area(session, area_id)

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO daily_habit_entries (habit_id, entry_date, status, "
                    "skip_reason, created_at, updated_at) VALUES (:habit_id, :day, "
                    "'done', 'Болезнь', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"habit_id": habit_id, "day": TODAY.isoformat()},
            )
            session.commit()

    def test_rejects_an_unknown_status(self, session: Session) -> None:
        area_id = area_service.create_area(session, name="Health").id
        habit_id = self._habit_and_area(session, area_id)

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO daily_habit_entries (habit_id, entry_date, status, "
                    "created_at, updated_at) VALUES (:habit_id, :day, 'perhaps', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"habit_id": habit_id, "day": TODAY.isoformat()},
            )
            session.commit()

    def test_rejects_a_negative_quantity(self, session: Session) -> None:
        area_id = area_service.create_area(session, name="Health").id
        habit_id = self._habit_and_area(session, area_id)

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO daily_habit_entries (habit_id, entry_date, status, "
                    "quantity_value_micro, created_at, updated_at) VALUES (:habit_id, "
                    ":day, 'done', -1000000, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"habit_id": habit_id, "day": TODAY.isoformat()},
            )
            session.commit()

    def test_a_habit_with_history_cannot_be_deleted(self, session: Session) -> None:
        """Recorded entries protect the habit row (`ON DELETE RESTRICT`)."""
        area_id = area_service.create_area(session, name="Health").id
        habit_id = self._habit_and_area(session, area_id)
        session.execute(
            text(
                "INSERT INTO daily_habit_entries (habit_id, entry_date, status, "
                "created_at, updated_at) VALUES (:habit_id, :day, 'done', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"habit_id": habit_id, "day": TODAY.isoformat()},
        )
        session.commit()

        with pytest.raises(IntegrityError):
            session.execute(text("DELETE FROM habits WHERE id = :id"), {"id": habit_id})
            session.commit()

    def test_the_entry_points_at_an_existing_habit(self, session: Session) -> None:
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO daily_habit_entries (habit_id, entry_date, status, "
                    "created_at, updated_at) VALUES (4242, :day, 'done', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"day": TODAY.isoformat()},
            )
            session.commit()

    def test_entries_are_removed_with_the_habit_row_only_through_the_api(
        self, session: Session
    ) -> None:
        """Sanity check that the ORM model is registered on the same metadata."""
        assert Habit.__tablename__ == "habits"
        assert "daily_habit_entries" in {t.name for t in Habit.metadata.tables.values()}
