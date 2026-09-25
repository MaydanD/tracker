"""Stage 8 Insight Engine: wording, identity, status gating and caveats.

The engine is a representation layer. It must never invent a statistic, a
causality or a recommendation, and its identity must survive renames, policy
changes and new data. These tests pin the templates, the status mapping, the
fingerprint and the presentation caveats.
"""

from datetime import date, timedelta

import pytest

from app.domain.analytics.confidence import CAVEATS
from app.domain.analytics.guardrail_types import BLOCKING_REASONS, WARNINGS
from app.domain.analytics.insight_types import POLICY
from app.domain.analytics.insights import (
    build_caveats, build_text, canonical_keys, distance_phrase, insight_fingerprint,
    lag_phrase, orientation_of, presentation_status, timing_phrase, variable_group,
)
from app.domain.analytics.types import Grain, Variable, VariableType as T


def var(key, label, kind, grain=Grain.DAILY):
    return Variable(key, label, kind, grain, "test", "test")


MOOD = var("state.mood", "Настроение", T.ORDINAL)
ENERGY = var("state.energy", "Энергия", T.ORDINAL)
SLEEP = var("state.sleep_minutes", "Сон, минуты", T.NUMERIC)
TRAINING = var("habit.7.daily.completion", "Тренировка", T.BOOLEAN)
ALCOHOL = var("state.alcohol", "Алкоголь", T.BOOLEAN)


def text(x, y, lag=0, direction="positive", status="stable", level="stable", *,
         unit=None, grain=None, reason=None):
    resolved = grain or (Grain.WEEKLY if unit == "week" else Grain.DAILY)
    return build_text(x, y, lag, unit, direction, resolved, status=status, level=level,
                      reason=reason)


# --- identity -----------------------------------------------------------------------

def test_fingerprint_is_stable_and_ignores_presentation():
    first = insight_fingerprint("state.mood", "state.sleep_minutes", Grain.DAILY, 0)
    second = insight_fingerprint("state.mood", "state.sleep_minutes", Grain.DAILY, 0)
    assert first == second
    assert len(first) == 64 and first.isascii()


def test_same_period_pair_is_symmetric_but_lagged_pairs_are_directional():
    """X ↔ Y at lag 0 is one identity; X earlier → Y and Y earlier → X are two."""
    forward = insight_fingerprint("state.mood", "state.energy", Grain.DAILY, 0)
    reverse = insight_fingerprint("state.energy", "state.mood", Grain.DAILY, 0)
    assert forward == reverse
    assert canonical_keys("state.mood", "state.energy", 0) == ("state.energy", "state.mood")
    assert canonical_keys("state.mood", "state.energy", 1) == ("state.mood", "state.energy")

    x_earlier = insight_fingerprint("state.mood", "state.energy", Grain.DAILY, 1)
    y_earlier = insight_fingerprint("state.energy", "state.mood", Grain.DAILY, 1)
    assert x_earlier != y_earlier


@pytest.mark.parametrize("lag", [-7, -1, 1, 2, 7])
def test_lag_changes_the_fingerprint(lag):
    assert insight_fingerprint("state.mood", "state.energy", Grain.DAILY, lag) != \
        insight_fingerprint("state.mood", "state.energy", Grain.DAILY, 0)


def test_fingerprint_does_not_depend_on_labels_or_grain_only_keys():
    """A rename is presentation metadata and can never mint a second identity."""
    renamed = var("state.mood", "Самочувствие (переименовано)", T.ORDINAL)
    assert insight_fingerprint(renamed.key, "state.energy", Grain.DAILY, 0) == \
        insight_fingerprint(MOOD.key, "state.energy", Grain.DAILY, 0)
    assert insight_fingerprint("state.mood", "state.energy", Grain.DAILY, 0) != \
        insight_fingerprint("state.mood", "state.energy", Grain.WEEKLY, 0)


def test_fingerprint_has_no_policy_or_date_dependency():
    """The signature deliberately has no coefficient, confidence or date input."""
    import inspect

    parameters = set(inspect.signature(insight_fingerprint).parameters)
    assert parameters == {"x_key", "y_key", "grain", "lag", "kind"}


@pytest.mark.parametrize("lag,expected", [(0, "same_period"), (1, "x_earlier"),
                                          (-1, "x_later"), (7, "x_earlier")])
def test_orientation_reflects_the_sign(lag, expected):
    assert orientation_of(lag) == expected


# --- lag and period wording ---------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (1, "на следующий день"), (2, "через два дня"), (3, "через три дня"),
    (4, "через четыре дня"), (5, "через пять дней"), (6, "через шесть дней"),
    (7, "через неделю"),
])
def test_daily_lag_wording(value, expected):
    assert lag_phrase(value, "day") == expected
    assert timing_phrase(value, "day", Grain.DAILY) == expected[:1].upper() + expected[1:]


@pytest.mark.parametrize("value,expected", [
    (1, "на следующей неделе"), (2, "через две недели"), (3, "через три недели"),
    (4, "через 4 недели"), (5, "через 5 недель"), (7, "через 7 недель"),
])
def test_weekly_lag_wording_never_says_days(value, expected):
    phrase = lag_phrase(value, "week")
    assert phrase == expected
    assert "дн" not in phrase


def test_same_period_timing_depends_on_grain():
    assert timing_phrase(0, "day", Grain.DAILY) == "В те же дни"
    assert timing_phrase(0, "week", Grain.WEEKLY) == "На той же неделе"


def test_negative_lag_is_labelled_as_reversed_order():
    assert timing_phrase(-1, "day", Grain.DAILY) == "Обратный порядок: 1 день"
    assert timing_phrase(-2, "day", Grain.DAILY) == "Обратный порядок: 2 дня"
    assert timing_phrase(-1, "week", Grain.WEEKLY) == "Обратный порядок: 1 неделю"
    assert distance_phrase(5, "day") == "5 дней"


# --- sentence templates --------------------------------------------------------------

@pytest.mark.parametrize("x,y,lag,unit,direction,expected", [
    # boolean exposure, same period
    (TRAINING, MOOD, 0, None, "positive",
     "В дни, когда было отмечено «Тренировка», значение «Настроение» обычно было выше."),
    (TRAINING, MOOD, 0, None, "negative",
     "В дни, когда было отмечено «Тренировка», значение «Настроение» обычно было ниже."),
    # numeric exposure, same period
    (SLEEP, ENERGY, 0, None, "positive",
     "Чем выше был показатель «Сон, минуты», тем обычно выше было значение «Энергия»."),
    (SLEEP, ENERGY, 0, None, "negative",
     "Чем выше был показатель «Сон, минуты», тем обычно ниже было значение «Энергия»."),
    # numeric exposure, boolean outcome
    (SLEEP, TRAINING, 0, None, "positive",
     "Чем выше был показатель «Сон, минуты», тем чаще отмечалось «Тренировка»."),
    (SLEEP, TRAINING, 0, None, "negative",
     "Чем выше был показатель «Сон, минуты», тем реже отмечалось «Тренировка»."),
    # boolean and boolean, same period
    (TRAINING, ALCOHOL, 0, None, "positive",
     "«Тренировка» и «Алкоголь» чаще отмечались в одни и те же дни."),
    (TRAINING, ALCOHOL, 0, None, "negative",
     "«Тренировка» и «Алкоголь» реже отмечались в одни и те же дни."),
    # lagged
    (TRAINING, MOOD, 1, "day", "positive",
     "После дней, когда было отмечено «Тренировка», на следующий день значение "
     "«Настроение» обычно было выше."),
    (TRAINING, MOOD, 2, "day", "negative",
     "После дней, когда было отмечено «Тренировка», через два дня значение "
     "«Настроение» обычно было ниже."),
    (SLEEP, ENERGY, 7, "day", "positive",
     "После дней с более высоким показателем «Сон, минуты», через неделю значение "
     "«Энергия» обычно было выше."),
    (SLEEP, TRAINING, 1, "day", "positive",
     "После дней с более высоким показателем «Сон, минуты», на следующий день "
     "«Тренировка» отмечалось чаще."),
    (TRAINING, ALCOHOL, 1, "day", "negative",
     "После дней, когда было отмечено «Тренировка», на следующий день «Алкоголь» "
     "отмечалось реже."),
    # weekly grain
    (TRAINING, MOOD, 1, "week", "positive",
     "После недель, когда было отмечено «Тренировка», на следующей неделе значение "
     "«Настроение» обычно было выше."),
])
def test_association_sentences_are_typed_and_morphology_safe(x, y, lag, unit, direction,
                                                             expected):
    assert text(x, y, lag, direction, unit=unit).statement == expected


def test_negative_lag_is_phrased_from_the_earlier_variable():
    """X is measured *after* Y, so the sentence must start from Y, not from X."""
    result = text(MOOD, TRAINING, -1, "positive")
    assert result.statement == (
        "После дней, когда было отмечено «Тренировка», на следующий день значение "
        "«Настроение» обычно было выше.")
    assert result.timing == "Обратный порядок: 1 день"
    assert "Тренировка» обычно было" not in result.statement


def test_near_zero_direction_is_not_dressed_up_as_an_association():
    result = text(SLEEP, ENERGY, 0, "near_zero")
    assert result.statement == ("Показатели «Сон, минуты» и «Энергия» были слабо связаны "
                               "в данных за период.")


@pytest.mark.parametrize("status,level,prefix", [
    ("preliminary", "preliminary", "Пока есть предварительный сигнал: "),
    ("stable", "stable", "В вашей истории наблюдается связь: "),
    ("well_supported", "well_supported",
     "Эта связь устойчиво повторяется в вашей истории: "),
    ("warning", "stable", "В вашей истории наблюдается связь: "),
    ("hidden", "stable", "Результат не прошёл статистические проверки: "),
])
def test_confidence_prefixes_match_the_status(status, level, prefix):
    result = text(SLEEP, ENERGY, 0, "positive", status=status, level=level)
    assert result.prefix == prefix
    assert result.full.startswith(prefix)
    # The sentence itself is lower-cased inside the prefix and keeps its full stop.
    assert result.full.endswith(".")
    assert result.full == prefix + result.statement[:1].lower() + result.statement[1:]


@pytest.mark.parametrize("reason,fragment", [
    ("insufficient_data", "недостаточно совместных наблюдений"),
    ("constant_series", "не менялся за период"),
    ("incompatible_units", "менялись единицы измерения"),
    ("unsupported_types", "сочетания типов"),
    ("grain_mismatch", "по дням, другой по неделям"),
    ("invalid_values", "некорректные значения"),
    ("numerical_error", "численно неустойчивым"),
])
def test_not_evaluable_statements_explain_the_reason(reason, fragment):
    result = text(SLEEP, ENERGY, 0, None, status="not_evaluable", level=None, reason=reason)
    assert fragment in result.statement
    assert result.prefix == "" and result.full == result.statement
    assert result.timing == "Не рассчитано"


# --- causal and recommendation language guard ----------------------------------------

def all_generated_text():
    """Every string the templates themselves produce, across the whole matrix."""
    directions = ("positive", "negative", "near_zero", None)
    statuses = ("preliminary", "stable", "well_supported", "warning", "hidden",
                "not_evaluable")
    pairs = ((TRAINING, MOOD), (MOOD, ENERGY), (SLEEP, ENERGY), (TRAINING, ALCOHOL),
             (SLEEP, TRAINING), (MOOD, TRAINING))
    for x, y in pairs:
        for lag in (-2, -1, 0, 1, 2, 7):
            unit = "week" if lag and x.grain == Grain.WEEKLY else "day"
            for direction in directions:
                for status in statuses:
                    level = None if status == "not_evaluable" else (
                        status if status in ("preliminary", "stable", "well_supported")
                        else "stable")
                    result = build_text(x, y, lag, unit if lag else None, direction,
                                        Grain.WEEKLY if unit == "week" else Grain.DAILY,
                                        status=status, level=level,
                                        reason="insufficient_data")
                    yield result.statement
                    yield result.timing
                    yield result.prefix
                    yield result.full


def test_no_causal_or_recommendation_wording_in_generated_templates():
    forbidden = ("влия", "улучша", "ухудша", "приводи", "из-за", "следует",
                 "нужно", "надо", "избега", "причин", "эффект", "рекоменд",
                 "прогноз", "предсказ", "совет")
    offenders = [(item, word) for item in all_generated_text()
                 for word in forbidden if word in item.lower()]
    assert offenders == []


def test_no_directive_or_imperative_verb_starts_a_sentence():
    for item in all_generated_text():
        assert not item.startswith(("Сделайте", "Попробуйте", "Начните", "Старайтесь"))


# --- status mapping ------------------------------------------------------------------

@pytest.mark.parametrize("verdict,level,expected", [
    ("pass", "well_supported", "well_supported"),
    ("pass", "stable", "stable"),
    ("pass", "preliminary", "preliminary"),
    ("pass_with_warnings", "preliminary", "warning"),
    ("pass_with_warnings", "stable", "warning"),
    ("blocked", "stable", "hidden"),
    ("blocked", "preliminary", "hidden"),
    ("blocked", "well_supported", "hidden"),
    ("not_evaluable", None, "not_evaluable"),
    ("blocked", None, "not_evaluable"),
])
def test_status_never_invents_a_third_verdict(verdict, level, expected):
    assert presentation_status(verdict, level) == expected


# --- caveats -------------------------------------------------------------------------

def test_caveat_presentation_covers_every_backend_code():
    """Every code Stage 7 can emit has a short Russian label, and codes are kept."""
    from app.domain.analytics.insights import CAVEAT_PRESENTATION

    codes = set(CAVEATS) | set(BLOCKING_REASONS) | set(WARNINGS) | {
        "negative_lag_reversed_order", "representative_lag_only", "guardrail_not_evaluable"}
    assert sorted(codes - set(CAVEAT_PRESENTATION)) == []
    for code, (label, message, severity) in CAVEAT_PRESENTATION.items():
        assert label and message and severity in ("info", "warning", "blocking"), code


def test_variable_groups_are_coarse_and_deterministic():
    from app.domain.analytics.variables import registry

    known = {item.key: item for item in registry((3,))}
    assert variable_group(known["daily.score"]) == "score"
    assert variable_group(known["state.mood"]) == "state"
    assert variable_group(known["weekly.state.mood.mean"]) == "state"
    assert variable_group(known["habit.3.daily.completion"]) == "habit"
    assert variable_group(known["daily.weekday"]) == "calendar"


def test_insight_policy_is_reported_with_the_payload():
    assert POLICY.version == "1" and POLICY.template_version == "1"
    assert POLICY.negative_lag_caveat == "negative_lag_reversed_order"


def test_build_caveats_orders_blocking_before_warning_before_info():
    class Reason:
        def __init__(self, code):
            self.code = code

    class Hypothesis:
        verdict = "blocked"
        blocking_reasons = (Reason("insufficient_sample"),)
        warnings = (Reason("small_sample"),)

    caveats = build_caveats(Hypothesis(), (),
                           negative_lag=True, representative_of_family=True)
    severities = [item.severity for item in caveats]
    assert severities == sorted(severities, key=("blocking", "warning", "info").index)
    assert [item.code for item in caveats][-2:] == ["negative_lag_reversed_order",
                                                    "representative_lag_only"]
    assert next(item for item in caveats
                if item.code == "insufficient_sample").detail.startswith("Мало наблюдений")
    assert all(item.label and item.message for item in caveats)
