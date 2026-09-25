"""Deterministic registry. Identity never depends on a mutable habit name."""

from app.domain.analytics.types import Grain, Variable, VariableType as T


# Explicit field list: adding a source text field cannot silently add a feature.
STATE_FIELDS = (
    ("mood", "Настроение", T.ORDINAL),
    ("energy", "Энергия", T.ORDINAL),
    ("wellbeing", "Самочувствие", T.ORDINAL),
    ("alcohol", "Алкоголь", T.BOOLEAN),
    ("gaming", "Видеоигры", T.BOOLEAN),
    ("gaming_minutes", "Видеоигры, минуты", T.NUMERIC),
    ("computer_overuse", "Избыточное использование компьютера", T.BOOLEAN),
    ("computer_minutes", "Компьютер, минуты", T.NUMERIC),
    ("sleep_status", "Оценка сна", T.CATEGORICAL),
    ("sleep_minutes", "Сон, минуты", T.NUMERIC),
)

DAILY_HABIT_FIELDS = (
    ("status", "Отметка", T.CATEGORICAL),
    ("quantity", "Количество", T.NUMERIC),
    ("weight", "Вес", T.NUMERIC),
    ("required_weight", "Обязательный дневной вес", T.NUMERIC),
)
WEEKLY_HABIT_FIELDS = (
    ("quota", "Недельная квота", T.NUMERIC),
    ("completed_count", "Выполнения недельной квоты", T.NUMERIC),
    ("required_weight", "Обязательный вес за неделю", T.NUMERIC),
    ("completed_weight", "Выполненный вес за неделю", T.NUMERIC),
    ("daily_required_count", "Дневных обязательств за неделю", T.NUMERIC),
    ("daily_completed_count", "Дневных выполнений за неделю", T.NUMERIC),
)


def habit_key(habit_id: int, grain: Grain, feature: str) -> str:
    return f"habit.{habit_id}.{grain.value}.{feature}"


def registry(habit_ids: tuple[int, ...]) -> tuple[Variable, ...]:
    result: list[Variable] = []

    def add(key, label, kind, grain, source, missing, **kwargs):
        result.append(Variable(key, label, kind, grain, source, missing, **kwargs))

    for grain in Grain:
        for name, label, kind in (
            ("iso_year", "Год ISO", T.NUMERIC),
            ("iso_week", "Неделя ISO", T.CATEGORICAL),
        ):
            add(f"{grain.value}.{name}", label, kind, grain, "calendar", "Всегда задано.")
        for name, label in (("score", "Процент выполнения"),
                            ("completed_weight", "Выполненный вес"),
                            ("required_weight", "Обязательный вес")):
            add(f"{grain.value}.{name}", label, T.NUMERIC, grain,
                f"stage4.{'day_progress' if grain == Grain.DAILY else 'week_progress'}",
                "score: no_obligations при отсутствии обязательств; score и выполненный вес: "
                "future для будущего периода. Обязательный вес — известный план, включая 0.")
    for name, label, kind in (
        ("weekday", "День недели (0 — понедельник)", T.CATEGORICAL),
        ("month", "Месяц", T.CATEGORICAL),
        ("year", "Год", T.NUMERIC),
        ("weekend", "Выходной", T.BOOLEAN),
        ("date_relation", "Дата относительно сегодня", T.CATEGORICAL),
    ):
        categories = {
            "date_relation": ("historical", "today", "future"),
            "weekday": tuple(str(n) for n in range(7)),
            "month": tuple(str(n) for n in range(1, 13)),
        }.get(name, ())
        add(f"daily.{name}", label, kind, Grain.DAILY, "calendar", "Всегда задано.",
            categories=categories)

    for name, label, kind in STATE_FIELDS:
        add(f"state.{name}", label, kind, Grain.DAILY, f"daily_states.{name}",
            "source_missing: нет записи; field_missing: поле не заполнено; future: будущая дата. "
            "false и 0 сохраняются. Связанные поля не выводятся друг из друга.",
            categories=("underslept", "normal", "overslept") if name == "sleep_status" else (),
            minimum=1 if kind == T.ORDINAL else (0 if kind == T.NUMERIC else None),
            maximum=5 if kind == T.ORDINAL else (1440 if kind == T.NUMERIC else None))
        add(f"weekly.state.{name}.observed_count", f"{label}: наблюдений", T.NUMERIC,
            Grain.WEEKLY, f"requested_elapsed_dates:state.{name}",
            "Число непустых наблюдений; 0 допустим. future, если все запрошенные даты будущие.")
        if kind in (T.NUMERIC, T.ORDINAL):
            add(f"weekly.state.{name}.mean", f"{label}: среднее", T.NUMERIC, Grain.WEEKLY,
                f"observed_mean:state.{name}",
                "Только наблюдения в запрошенных прошедших датах и сегодня; "
                "no_observations при нуле наблюдений, future для полностью будущей части.")
        if kind == T.BOOLEAN:
            for suffix, suffix_label in (("true_count", "Да"), ("false_count", "Нет")):
                add(f"weekly.state.{name}.{suffix}", f"{label}: {suffix_label}", T.NUMERIC,
                    Grain.WEEKLY, f"observed_count:state.{name}",
                    "Только явные ответы; null исключён. future для полностью будущей части.")

    for habit_id in sorted(habit_ids):
        for grain, fields in ((Grain.DAILY, DAILY_HABIT_FIELDS), (Grain.WEEKLY, WEEKLY_HABIT_FIELDS)):
            for name, label, kind in fields:
                add(habit_key(habit_id, grain, name), f"Привычка №{habit_id}: {label}", kind,
                    grain, "daily_habit_entries + effective habit_versions" if grain == Grain.DAILY
                    else "stage4.week_progress (полная календарная неделя)",
                    "not_applicable: вне активности или неприменимое поле; source_missing: нет отметки; "
                    "field_missing: количество не задано; future: будущее наблюдение. "
                    "Вес и квота — план. Единица количества берётся из конфигурации даты.",
                    habit_id=habit_id,
                    categories=("done", "missed", "skipped") if name == "status" else ())
    return tuple(result)
