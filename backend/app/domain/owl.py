"""Stage 9 Owl: a deterministic, context-aware mascot state.

The Owl never computes a statistic. It reads meaning that already exists —
Stage 4 progress/streaks or the Stage 8 availability, confidence and guardrail
verdicts — and returns **exactly one** state with a short Russian caption and a
factual explanation.

Purity is deliberate. The module has no database, no wall clock and no random
source:

* the "after 18:00" rule is driven by the explicit ``after_hours`` flag the
  caller derives from the injected application clock;
* the day's mood/wellbeing are passed in as values (``None`` means *not
  recorded*, which is never treated as a failure);
* nothing is persisted — the Owl has no history table.

Absence of data is a state, not a failure. Sarcasm is allowed only after a real
recorded action, and is suppressed by low mood/wellbeing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from typing import Literal

OwlTone = Literal["celebratory", "supportive", "neutral", "cautionary", "sarcastic"]
OwlContext = Literal["dashboard", "insights"]

# Asset keys are the stems of the canonical PNGs kept in ``owl/`` at the repo
# root. No other asset exists; every analysis-quality state reuses ``insight``.
ASSET_PENDING = "owl_pending"
ASSET_FAILED = "owl_failed"
ASSET_ALL_DONE = "owl_all_done"
ASSET_INSIGHT = "owl_insight"
ASSET_MANY_MISSES = "owl_many_misses"
ASSET_RECORD = "owl_record"

# Named product thresholds. They are policy, not statistical truth.
PENDING_HOUR = 18
IMPORTANT_WEIGHT = 2
MISS_WINDOW_DAYS = 3
MISS_MIN = 3
MIN_COVERAGE = 0.60
RECORD_MIN_STREAK = 5
BROKEN_STREAK_MIN = 7
BROKEN_STREAK_RECENT_DAYS = 14
WEEKLY_POSITIVE_MIN_SCORE = 85.0
WEEKLY_DRAWDOWN_MIN_DROP = 20.0
WEEKLY_MIN_DAYS = 5
LOW_MOOD_WELLBEING = 2
INSUFFICIENT_SAMPLE_N = 10

# Lower number = shown first. Dashboard execution failures outrank confirmed
# negative trends, which outrank achievements.
DASHBOARD_PRIORITY: dict[str, int] = {
    "failed": 10,
    "pending": 20,
    "many_misses": 30,
    "streak_broken": 40,
    "weekly_drawdown": 50,
    "new_record": 60,
    "all_completed": 70,
    "weekly_positive": 80,
}

# Insights quality states outrank a confirmed finding, which outranks a
# preliminary signal.
INSIGHTS_PRIORITY: dict[str, int] = {
    "no_data": 10,
    "insufficient_data": 20,
    "guardrails_blocked": 30,
    "stable_insight": 40,
    "lag_insight": 40,
    "preliminary_only": 50,
}

_UNIT_WORD: dict[str, str] = {"days": "дней", "weeks": "недель"}


@dataclass(frozen=True)
class OwlState:
    """The single banner the UI shows. ``fingerprint`` is stable per data change."""

    owl_id: str
    asset_key: str
    tone: OwlTone
    priority: int
    caption_line1: str
    caption_line2: str
    dismissible: bool
    fingerprint: str
    context: OwlContext
    # Non-sarcastic replacement used by the client-side sarcasm cooldown. ``None``
    # for messages that are not sarcastic in the first place.
    fallback_line1: str | None = None


@dataclass(frozen=True)
class StreakFact:
    """One habit's streak state, from the Stage 4 streak engine."""

    habit_id: int
    name: str
    current_streak: int
    previous_best_streak: int
    previous_best_end: date | None
    unit: Literal["days", "weeks"]
    active: bool


@dataclass(frozen=True)
class DashboardContext:
    """Everything the dashboard selector may use, all pre-computed upstream."""

    today: date
    after_hours: bool
    required_weight: int
    completed_weight: int
    unmarked_obligations: int
    obligation_count: int
    failed_important: tuple[str, ...]
    mood: int | None
    wellbeing: int | None
    misses_last_window: int
    coverage_last_window: float | None
    streaks: tuple[StreakFact, ...]
    last_week_score: float | None
    last_week_days: int
    last_week_coverage: float | None
    previous_week_score: float | None
    previous_week_days: int
    previous_week_coverage: float | None


@dataclass(frozen=True)
class InsightFact:
    """The wording of one already-computed insight candidate."""

    x_label: str
    y_label: str
    statement: str
    timing: str
    lag: int


@dataclass(frozen=True)
class InsightsContext:
    """Everything the insights selector may use, all from the Stage 8 payload."""

    availability: str
    availability_message: str
    hypothesis_count: int
    max_sample_n: int
    preliminary_count: int
    blocked_reason: str | None
    stable: InsightFact | None


def _fingerprint(context: OwlContext, owl_id: str, *parts: object) -> str:
    payload = "|".join([context, owl_id, *("" if p is None else str(p) for p in parts)])
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


def _sarcasm_suppressed(mood: int | None, wellbeing: int | None) -> bool:
    """True when a recorded bad state forbids sarcasm. Missing data never does."""

    return (mood is not None and mood <= LOW_MOOD_WELLBEING) or (
        wellbeing is not None and wellbeing <= LOW_MOOD_WELLBEING
    )


def _percent(value: float) -> str:
    return f"{value:.0f}%"


def select_dashboard(context: DashboardContext) -> OwlState | None:
    """Pick the one dashboard state that matters most, or ``None``."""

    candidates: list[OwlState] = []
    today = context.today
    suppressed = _sarcasm_suppressed(context.mood, context.wellbeing)

    if context.failed_important:
        name = context.failed_important[0]
        candidates.append(OwlState(
            owl_id="failed",
            asset_key=ASSET_FAILED,
            tone="cautionary" if suppressed else "sarcastic",
            priority=DASHBOARD_PRIORITY["failed"],
            caption_line1="Отмечен провал привычки." if suppressed else "У тебя есть порох или как?",
            caption_line2=f"«{name}» отмечена невыполненной сегодня.",
            # A recorded failure is a fact worth looking at; it is not dismissible.
            dismissible=False,
            fingerprint=_fingerprint("dashboard", "failed", today, name),
            context="dashboard",
            fallback_line1=None if suppressed else "Отмечен провал привычки.",
        ))

    if context.after_hours and context.unmarked_obligations > 0:
        candidates.append(OwlState(
            owl_id="pending",
            asset_key=ASSET_PENDING,
            tone="cautionary",
            priority=DASHBOARD_PRIORITY["pending"],
            caption_line1="Эй, отметь привычку!",
            caption_line2=(
                f"Осталось неотмеченными: {context.unmarked_obligations} "
                f"из {context.obligation_count}."),
            dismissible=True,
            fingerprint=_fingerprint(
                "dashboard", "pending", today, context.unmarked_obligations,
                context.obligation_count),
            context="dashboard",
        ))

    coverage = context.coverage_last_window
    if (
        context.misses_last_window >= MISS_MIN
        and coverage is not None
        and coverage >= MIN_COVERAGE
    ):
        candidates.append(OwlState(
            owl_id="many_misses",
            asset_key=ASSET_MANY_MISSES,
            tone="cautionary" if suppressed else "sarcastic",
            priority=DASHBOARD_PRIORITY["many_misses"],
            caption_line1="Не пропускай так много." if suppressed else "Ну ты серьёзно?",
            caption_line2=(
                f"За последние {MISS_WINDOW_DAYS} дня пропусков: "
                f"{context.misses_last_window}."),
            dismissible=True,
            fingerprint=_fingerprint(
                "dashboard", "many_misses", today, context.misses_last_window, today),
            context="dashboard",
            fallback_line1=None if suppressed else "Не пропускай так много.",
        ))

    broken = next(
        (s for s in context.streaks
         if s.active and s.current_streak == 0 and s.previous_best_streak >= BROKEN_STREAK_MIN
         and s.previous_best_end is not None
         and (today - s.previous_best_end).days <= BROKEN_STREAK_RECENT_DAYS),
        None)
    if broken is not None:
        word = _UNIT_WORD[broken.unit]
        candidates.append(OwlState(
            owl_id="streak_broken",
            asset_key=ASSET_FAILED,
            tone="cautionary",
            priority=DASHBOARD_PRIORITY["streak_broken"],
            caption_line1="Серия прервалась.",
            caption_line2=(
                f"«{broken.name}»: серия из {broken.previous_best_streak} "
                f"{word} оборвалась."),
            dismissible=True,
            fingerprint=_fingerprint(
                "dashboard", "streak_broken", broken.habit_id,
                broken.previous_best_streak, broken.previous_best_end),
            context="dashboard",
        ))

    last = context.last_week_score
    previous = context.previous_week_score
    comparable = (
        last is not None and previous is not None
        and context.last_week_days >= WEEKLY_MIN_DAYS
        and context.previous_week_days >= WEEKLY_MIN_DAYS
        and (context.last_week_coverage or 0.0) >= MIN_COVERAGE
        and (context.previous_week_coverage or 0.0) >= MIN_COVERAGE
    )
    if comparable and previous - last > WEEKLY_DRAWDOWN_MIN_DROP:
        drop = previous - last
        candidates.append(OwlState(
            owl_id="weekly_drawdown",
            asset_key=ASSET_MANY_MISSES,
            tone="cautionary",
            priority=DASHBOARD_PRIORITY["weekly_drawdown"],
            caption_line1="Неделя просела.",
            caption_line2=(
                f"Раньше — {_percent(previous)}, за прошлую неделю — {_percent(last)}: "
                f"падение примерно {_percent(drop)}."),
            dismissible=True,
            fingerprint=_fingerprint("dashboard", "weekly_drawdown", context.today, last, previous),
            context="dashboard",
        ))

    record = max(
        (s for s in context.streaks
         if s.active and s.current_streak >= RECORD_MIN_STREAK
         and s.current_streak > s.previous_best_streak),
        key=lambda s: (s.current_streak, s.habit_id),
        default=None)
    if record is not None:
        word = _UNIT_WORD[record.unit]
        candidates.append(OwlState(
            owl_id="new_record",
            asset_key=ASSET_RECORD,
            tone="celebratory",
            priority=DASHBOARD_PRIORITY["new_record"],
            caption_line1="Новый рекорд!",
            caption_line2=(
                f"«{record.name}»: {record.current_streak} {word} подряд — "
                f"это личный рекорд."),
            dismissible=True,
            fingerprint=_fingerprint(
                "dashboard", "new_record", record.habit_id, record.current_streak),
            context="dashboard",
        ))

    if (
        context.required_weight > 0
        and context.completed_weight >= context.required_weight
    ):
        candidates.append(OwlState(
            owl_id="all_completed",
            asset_key=ASSET_ALL_DONE,
            tone="celebratory",
            priority=DASHBOARD_PRIORITY["all_completed"],
            caption_line1="Ну вот. Можешь жить.",
            caption_line2="Все обязательные привычки на сегодня выполнены — 100%.",
            dismissible=True,
            fingerprint=_fingerprint("dashboard", "all_completed", today),
            context="dashboard",
        ))

    if (
        last is not None
        and last >= WEEKLY_POSITIVE_MIN_SCORE
        and context.last_week_days >= WEEKLY_MIN_DAYS
        and (context.last_week_coverage or 0.0) >= MIN_COVERAGE
    ):
        candidates.append(OwlState(
            owl_id="weekly_positive",
            asset_key=ASSET_ALL_DONE,
            tone="celebratory",
            priority=DASHBOARD_PRIORITY["weekly_positive"],
            caption_line1="Хорошая неделя.",
            caption_line2=f"За прошлую неделю — {_percent(last)}.",
            dismissible=True,
            fingerprint=_fingerprint("dashboard", "weekly_positive", context.today, last),
            context="dashboard",
        ))

    return _winner(candidates)


def select_insights(context: InsightsContext) -> OwlState | None:
    """Pick the one insights state that reflects the analytics engine, or ``None``."""

    if context.availability == "no_data":
        return OwlState(
            owl_id="no_data",
            asset_key=ASSET_INSIGHT,
            tone="neutral",
            priority=INSIGHTS_PRIORITY["no_data"],
            caption_line1="Тут пока пусто.",
            caption_line2=context.availability_message,
            dismissible=True,
            fingerprint=_fingerprint("insights", "no_data"),
            context="insights",
        )

    if context.availability == "insufficient_data":
        sample = (
            f" Совместных наблюдений пока: {context.max_sample_n}."
            if context.max_sample_n > 0 else "")
        return OwlState(
            owl_id="insufficient_data",
            asset_key=ASSET_INSIGHT,
            tone="supportive",
            priority=INSIGHTS_PRIORITY["insufficient_data"],
            caption_line1="Мало данных — это не провал.",
            caption_line2=f"{context.availability_message}{sample}",
            dismissible=True,
            fingerprint=_fingerprint("insights", "insufficient_data", context.hypothesis_count,
                                     context.max_sample_n),
            context="insights",
        )

    if context.availability == "no_guardrails_passed":
        reason = context.blocked_reason or "связь не прошла статистические проверки."
        return OwlState(
            owl_id="guardrails_blocked",
            asset_key=ASSET_INSIGHT,
            tone="neutral",
            priority=INSIGHTS_PRIORITY["guardrails_blocked"],
            caption_line1="Так. Но выводов пока нет.",
            caption_line2=f"Связь не прошла статистическую проверку: {reason}",
            dismissible=True,
            fingerprint=_fingerprint("insights", "guardrails_blocked", context.blocked_reason),
            context="insights",
        )

    if context.stable is not None:
        fact = context.stable
        if fact.lag != 0:
            return OwlState(
                owl_id="lag_insight",
                asset_key=ASSET_INSIGHT,
                tone="neutral",
                priority=INSIGHTS_PRIORITY["lag_insight"],
                caption_line1="Так. А вот это уже интересно.",
                caption_line2=(
                    f"Связь «{fact.x_label}» — «{fact.y_label}» сильнее всего "
                    f"наблюдается со сдвигом: {_lower_first(fact.timing)}."),
                dismissible=True,
                fingerprint=_fingerprint(
                    "insights", "lag_insight", fact.x_label, fact.y_label, fact.lag),
                context="insights",
            )
        return OwlState(
            owl_id="stable_insight",
            asset_key=ASSET_INSIGHT,
            tone="neutral",
            priority=INSIGHTS_PRIORITY["stable_insight"],
            caption_line1="Так. А вот это уже интересно.",
            caption_line2=fact.statement,
            dismissible=True,
            fingerprint=_fingerprint(
                "insights", "stable_insight", fact.x_label, fact.y_label, fact.lag),
            context="insights",
        )

    if context.availability == "preliminary_only" or context.preliminary_count > 0:
        return OwlState(
            owl_id="preliminary_only",
            asset_key=ASSET_INSIGHT,
            tone="neutral",
            priority=INSIGHTS_PRIORITY["preliminary_only"],
            caption_line1="Есть первый сигнал.",
            caption_line2="Но делать выводы пока рано.",
            dismissible=True,
            fingerprint=_fingerprint("insights", "preliminary_only", context.preliminary_count),
            context="insights",
        )

    return None


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def _winner(candidates: list[OwlState]) -> OwlState | None:
    """Exactly one winner: highest priority, deterministic tie-break by id."""

    if not candidates:
        return None
    return sorted(candidates, key=lambda state: (state.priority, state.owl_id))[0]


__all__ = [
    "ASSET_ALL_DONE",
    "ASSET_FAILED",
    "ASSET_INSIGHT",
    "ASSET_MANY_MISSES",
    "ASSET_PENDING",
    "ASSET_RECORD",
    "DashboardContext",
    "InsightFact",
    "InsightsContext",
    "OwlState",
    "StreakFact",
    "select_dashboard",
    "select_insights",
]
