"""The configuration Tracker starts every user with.

Twenty-four ordinary daily habits in four ordinary areas: the same rows the user
could have created by hand in the Сферы / Привычки screens, with the same
configuration fields — a value scale, its labels, a direction and an importance.

The one thing that sets a shipped habit apart is its ``key``: a stable machine
identifier (``body.walk``) that never changes, is never displayed and is never
renamed. Reconciliation uses it to recognise the rows it owns, so starting the
app never duplicates them, and renaming a habit in the UI never breaks the
recognition.

Everything else is deliberately *not* special: names, labels, direction,
importance, area assignment and archival are all editable through the ordinary
habit interface, and the manifest is only the starting point.

Ordering is data too: the areas and habits carry the order the user should see
them in, so the check-in screen does not have to sort them itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.tracking import Direction, ValueType


@dataclass(frozen=True, slots=True)
class CanonicalArea:
    """One shipped sphere: a machine key, its Russian name and its colour."""

    key: str
    name: str
    color: str
    sort_order: int


@dataclass(frozen=True, slots=True)
class CanonicalHabit:
    """One shipped habit definition.

    ``labels`` are the words of the habit's own scale — deliberately per habit,
    because Настроение (``ужас/плохо/норм/хорошо``) and Симптомы
    (``нет/слабые/заметные/сильные``) share the ``ordinal_4`` type but not a
    single word of it.
    """

    key: str
    area_key: str
    name: str
    value_type: ValueType
    labels: tuple[str, ...]
    direction: Direction
    sort_order: int


CANONICAL_AREAS: tuple[CanonicalArea, ...] = (
    CanonicalArea("body", "Тело", "#2f9e5f", 1),
    CanonicalArea("development", "Развитие", "#4a7cc7", 2),
    CanonicalArea("leisure", "Досуг", "#b5891b", 3),
    CanonicalArea("nutrition", "Питание и вещества", "#c2540a", 4),
)

#: Reused label sets. ``ordinal_4`` is not one global scale, so every habit
#: states its own words; these are just the common spellings.
_ZERO_MUCH = ("0", "мало", "нормально", "много")
_NO_YES = ("нет", "да")
_BINARY = ValueType.BINARY
_ORDINAL = ValueType.ORDINAL_4

CANONICAL_HABITS: tuple[CanonicalHabit, ...] = (
    # ── Тело ──────────────────────────────────────────────────────────────
    CanonicalHabit(
        "body.exercise", "body", "Зарядка", _BINARY, _NO_YES,
        Direction.POSITIVE, 1,
    ),
    CanonicalHabit(
        "body.workout", "body", "Тренировка", _BINARY, _NO_YES,
        Direction.POSITIVE, 2,
    ),
    CanonicalHabit(
        "body.walk", "body", "Прогулка", _ORDINAL, _ZERO_MUCH,
        Direction.POSITIVE, 3,
    ),
    CanonicalHabit(
        "body.bicycle", "body", "Велосипед", _ORDINAL, _ZERO_MUCH,
        Direction.POSITIVE, 4,
    ),
    CanonicalHabit(
        "body.mood", "body", "Настроение", _ORDINAL,
        ("ужас", "плохо", "норм", "хорошо"), Direction.POSITIVE, 5,
    ),
    CanonicalHabit(
        "body.energy", "body", "Энергия", _ORDINAL,
        ("нет сил", "мало", "норм", "много"), Direction.POSITIVE, 6,
    ),
    CanonicalHabit(
        "body.sleep_quality", "body", "Качество сна", _ORDINAL,
        ("ужас", "плохо", "норм", "хорошо"), Direction.POSITIVE, 7,
    ),
    CanonicalHabit(
        "body.symptoms", "body", "Симптомы заболевания", _ORDINAL,
        ("нет", "слабые", "заметные", "сильные"), Direction.NEGATIVE, 8,
    ),
    CanonicalHabit(
        "body.sex", "body", "Секс", _BINARY, _NO_YES, Direction.NEUTRAL, 9,
    ),
    CanonicalHabit(
        "body.masturbation", "body", "Мастурбация", _BINARY, _NO_YES,
        Direction.NEUTRAL, 10,
    ),
    # ── Развитие ──────────────────────────────────────────────────────────
    CanonicalHabit(
        "development.reading", "development", "Чтение", _ORDINAL, _ZERO_MUCH,
        Direction.POSITIVE, 11,
    ),
    CanonicalHabit(
        "development.study", "development", "Учёба", _ORDINAL, _ZERO_MUCH,
        Direction.POSITIVE, 12,
    ),
    CanonicalHabit(
        "development.projects", "development", "Вайбкодинг / свои проекты",
        _ORDINAL, _ZERO_MUCH, Direction.POSITIVE, 13,
    ),
    CanonicalHabit(
        "development.work", "development", "Работа", _ORDINAL, _ZERO_MUCH,
        Direction.NEUTRAL, 14,
    ),
    CanonicalHabit(
        "development.tasks", "development", "Дела", _ORDINAL, _ZERO_MUCH,
        Direction.POSITIVE, 15,
    ),
    # ── Досуг ─────────────────────────────────────────────────────────────
    CanonicalHabit(
        "leisure.friends", "leisure", "Общение с друзьями", _ORDINAL,
        _ZERO_MUCH, Direction.POSITIVE, 16,
    ),
    CanonicalHabit(
        "leisure.games", "leisure", "Игры", _ORDINAL, _ZERO_MUCH,
        Direction.NEGATIVE, 17,
    ),
    CanonicalHabit(
        "leisure.movies", "leisure", "Кино / сериалы", _ORDINAL, _ZERO_MUCH,
        Direction.NEUTRAL, 18,
    ),
    CanonicalHabit(
        "leisure.computer", "leisure", "Просто сидел за компом", _ORDINAL,
        _ZERO_MUCH, Direction.NEUTRAL, 19,
    ),
    # ── Питание и вещества ────────────────────────────────────────────────
    CanonicalHabit(
        "nutrition.normal_food", "nutrition", "Нормальное питание", _ORDINAL,
        ("0", "мало", "нормально", "хорошо"), Direction.POSITIVE, 20,
    ),
    CanonicalHabit(
        "nutrition.junk_food", "nutrition", "Вредная еда", _ORDINAL,
        ("0", "немного", "нормально", "много"), Direction.NEGATIVE, 21,
    ),
    CanonicalHabit(
        "nutrition.overeating", "nutrition", "Переедание", _ORDINAL,
        ("0", "немного", "заметно", "сильно"), Direction.NEGATIVE, 22,
    ),
    CanonicalHabit(
        "nutrition.coffee", "nutrition", "Кофе", _ORDINAL,
        ("0", "1 кофе", "2 кофе", "3+ кофе"), Direction.NEUTRAL, 23,
    ),
    CanonicalHabit(
        "nutrition.alcohol", "nutrition", "Алкоголь", _ORDINAL,
        ("0", "немного", "нормально", "много"), Direction.NEGATIVE, 24,
    ),
)

CANONICAL_AREAS_BY_KEY: dict[str, CanonicalArea] = {
    area.key: area for area in CANONICAL_AREAS
}

assert len(CANONICAL_HABITS) == 24, "The canonical set must stay at 24 habits."
assert len(CANONICAL_AREAS) == 4, "The canonical set must stay at 4 areas."
assert {h.sort_order for h in CANONICAL_HABITS} == set(range(1, 25)), (
    "Canonical sort_order must be exactly 1..24."
)
assert all(h.area_key in CANONICAL_AREAS_BY_KEY for h in CANONICAL_HABITS), (
    "Every canonical habit belongs to a canonical area."
)
