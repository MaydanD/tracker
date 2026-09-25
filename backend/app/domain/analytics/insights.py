"""Stage 8 Insight Engine: admissible evidence turned into a human-readable insight.

Pure and deterministic. The engine never computes a coefficient, a lag alignment,
a coverage number, an FDR correction, a weekday control or a confidence verdict.
Stage 7A supplies the canonical dataset, Stage 7C the associations, Stage 7D the
lag alignment, the Stage 7D guardrails the admissibility verdict and Stage 7E the
evidence maturity. The engine only decides

1. which hypotheses a discovery sweep inspects at all;
2. which admissible hypotheses become user-facing insights;
3. what deterministic Russian sentence represents each one;
4. which lag represents a relationship family and how the feed is ordered;
5. how every limitation is translated into a short Russian warning.

Nothing here proves causation, recommends behaviour, predicts anything or calls a
language model. Wording comes from typed templates keyed by variable type,
direction, lag and confidence; identity comes from stable variable keys.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date
from hashlib import sha256
from itertools import combinations
from typing import Literal

from app.domain.analytics.builder import slice_dataset
from app.domain.analytics.confidence import (
    CAVEATS as CONFIDENCE_CAVEATS, analyze as analyze_confidence, classify_confidence,
    evaluate_methods, not_evaluable_reason,
)
from app.domain.analytics.confidence_types import (
    POLICY as CONFIDENCE_POLICY, Caveat, ConfidenceAnalytics, ConfidenceLevel,
    GuardrailSummary, NotEvaluableReason,
)
from app.domain.analytics.descriptive import make_series, rolling
from app.domain.analytics.guardrails import paired_observations
from app.domain.analytics.guardrail_types import (
    BLOCKING_REASONS, WARNINGS, GuardrailAnalytics, GuardrailHypothesis, GuardrailVerdict,
)
from app.domain.analytics.insight_types import (
    AVAILABILITY_MESSAGES, DISCOVERY_POLICY, POLICY, CaveatSeverity, DiscoveryPolicy,
    InsightAlternative, InsightCandidate, InsightCaveat, InsightChart, InsightChartPoint,
    InsightChartSummary, InsightConfidence, InsightCounts, InsightEvidence, InsightFeedMode,
    InsightGuardrail, InsightOrientation, InsightPairPoint, InsightRelationship,
    InsightRollingPoint, InsightSegment, InsightSeries, InsightStatus, InsightSummary,
    InsightText,
)
from app.domain.analytics.lags import normalize_lags
from app.domain.analytics.relationship_types import Direction
from app.domain.analytics.types import (
    AnalyticsDataset, Availability as A, Grain, Variable, VariableType as T,
)
from app.domain.analytics.variables import habit_key

Hypothesis = tuple[str, str, int]

FINGERPRINT_VERSION = "1"
KIND = "association"

VERDICT_RANK: dict[GuardrailVerdict, int] = {
    "pass": 0, "pass_with_warnings": 1, "blocked": 2, "not_evaluable": 3,
}
CONFIDENCE_RANK: dict[ConfidenceLevel | None, int] = {
    "well_supported": 0, "stable": 1, "preliminary": 2, None: 3,
}

# --------------------------------------------------------------------------- #
# Short presentation caveats. Reused backend codes are never renamed; only the
# one-line label the card shows is authored here, because the Stage 7 label is
# written for a technical reader.
# --------------------------------------------------------------------------- #

CAVEAT_PRESENTATION: dict[str, tuple[str, str, CaveatSeverity]] = {
    # Stage 7E confidence caveats.
    "small_sample": ("Мало наблюдений",
                     "Связь рассчитана по небольшому числу совместных дней.", "warning"),
    "limited_history": ("Короткая история",
                        "Период слишком короткий, чтобы разделить историю на отрезки.",
                        "warning"),
    "low_coverage": ("Низкое покрытие",
                     "Оба показателя заполнены не на всех подходящих днях.", "warning"),
    "systematic_missingness_possible": ("Данных заполнено неравномерно",
                                        "Пропуски могут быть неслучайными.", "warning"),
    "segment_inconsistency": ("Связь повторяется не везде",
                              "Не все отрезки истории поддерживают связь.", "warning"),
    "direction_reversal": ("Где-то направление противоположное",
                           "Хотя бы на одном отрезке знак связи обратный.", "warning"),
    "magnitude_instability": ("Величина связи непостоянна",
                              "Сила связи заметно различается между отрезками истории.",
                              "warning"),
    "partial_period": ("Неполный период",
                       "Часть недель периода неполные и исключена из расчёта.", "info"),
    "method_disagreement": ("Методы расходятся",
                            "Разные способы расчёта дают разную силу связи.", "warning"),
    "constant_series": ("Нет вариации",
                        "Один из показателей не менялся на выбранном периоде.", "blocking"),
    "incompatible_units": ("Несовместимые единицы",
                           "За период встречаются разные единицы измерения.", "blocking"),
    "unsupported_variable_types": ("Неподдерживаемые типы",
                                   "Для такого сочетания показателей расчёт не предусмотрен.",
                                   "blocking"),
    "ordinal_distance_limitation": ("Шкала порядка",
                                    "Для порядковых оценок предполагается сопоставимость "
                                    "расстояний между уровнями.", "info"),
    "autocorrelation_possible": ("Соседние дни могут быть статистически зависимы",
                                 "Объём независимой информации может быть меньше числа дней.",
                                 "info"),
    "association_not_causation": ("Связь не означает причинность",
                                  "Наблюдаемая связь не доказывает, что один показатель "
                                  "вызывает другой.", "info"),
    # Stage 7D warning codes.
    "moderate_coverage": ("Умеренное покрытие",
                          "Часть подходящих дней не имеет обоих показателей.", "warning"),
    "weekday_attenuation": ("Часть связи может объясняться днём недели",
                            "После контроля дня недели величина связи снижается.", "warning"),
    "weekday_control_unavailable": ("День недели не проверен",
                                    "Для этой пары или периода контроль дня недели не "
                                    "применяется.", "info"),
    "insufficient_temporal_evidence": ("Мало отрезков истории",
                                       "Недостаточно отрезков для проверки устойчивости.",
                                       "info"),
    # Stage 7D blocking codes.
    "insufficient_sample": ("Мало наблюдений",
                            "Совместных наблюдений меньше минимума для выводов.", "blocking"),
    "insufficient_coverage": ("Недостаточное покрытие",
                              "Доля совместных наблюдений слишком низкая.", "blocking"),
    "below_effect_threshold": ("Связь слабее порога",
                               "Величина связи ниже минимального значимого уровня.",
                               "blocking"),
    "insufficient_group_balance": ("Несбалансированные группы",
                                   "В одной из групп слишком мало наблюдений.", "blocking"),
    "sparse_contingency_cell": ("Разреженная таблица",
                                "В таблице сопряжённости есть ячейки с малым числом "
                                "наблюдений.", "blocking"),
    "false_discovery_risk": ("Риск ложного открытия",
                             "Связь не проходит контроль доли ложных открытий в этой "
                             "серии проверок.", "blocking"),
    "weekday_explained": ("Полностью объясняется днём недели",
                          "После контроля дня недели вариация связи исчезает.", "blocking"),
    "weekday_reversal": ("Смена знака после контроля дня недели",
                         "После контроля дня недели направление связи меняется.", "blocking"),
    "temporal_direction_inconsistency": ("Нестабильное направление",
                                         "Большинство отрезков истории не поддерживают "
                                         "направление связи.", "blocking"),
    "temporal_reversal": ("Разворот во времени",
                          "На одном из отрезков связь уверенно противоположна.", "blocking"),
    # Presentation-only codes, specific to this layer.
    "negative_lag_reversed_order": ("Обратный порядок во времени",
                                    "Второй показатель измеряется раньше первого, поэтому "
                                    "формулировка читается от более раннего к более позднему.",
                                    "info"),
    "representative_lag_only": ("Показана одна задержка",
                                "Для этой пары проверялись несколько задержек; остальные "
                                "видны в подробностях.", "info"),
    "guardrail_not_evaluable": ("Проверки не выполнены",
                                "Результат не удалось проверить статистическими правилами.",
                                "warning"),
}

CAVEAT_SEVERITY_ORDER: dict[CaveatSeverity, int] = {"blocking": 0, "warning": 1, "info": 2}

# Statistics names that must never appear in generated wording, and the causal or
# advisory phrases the language policy forbids outright.
FORBIDDEN_WORDING: tuple[str, ...] = (
    "влияет", "влияние", "влияют", "улучшает", "улучша", "ухудшает", "ухудша",
    "приводит", "приведёт", "приведет", "из-за", "вам следует", "вам нужно",
    "следует ", "лучше делать", "избегайте", "причина", "причиной", "эффект ",
)


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #


def canonical_keys(x_key: str, y_key: str, lag: int) -> tuple[str, str]:
    """Canonical X/Y order for a hypothesis.

    A same-period association is symmetric, so ``X ↔ Y`` and ``Y ↔ X`` at lag 0
    are one identity and one card. A lagged association is *not* symmetric — the
    pairing itself differs — so both directions are separate hypotheses with
    separate fingerprints.
    """

    return tuple(sorted((x_key, y_key))) if lag == 0 else (x_key, y_key)  # type: ignore[return-value]


def insight_fingerprint(x_key: str, y_key: str, grain: Grain | None, lag: int,
                        kind: str = KIND) -> str:
    """Stable identity of one analytical hypothesis.

    Deliberately independent of mutable labels, coefficient, confidence, policy
    versions and the current date: the same hypothesis keeps one identity while
    its evidence evolves. A habit rename therefore never creates a second insight.
    """

    x, y = canonical_keys(x_key, y_key, lag)
    payload = "|".join((
        "insight", FINGERPRINT_VERSION, kind, x, y,
        grain.value if grain is not None else "none", str(lag),
    ))
    return sha256(payload.encode("utf-8")).hexdigest()


def orientation_of(lag: int) -> InsightOrientation:
    if lag == 0:
        return "same_period"
    return "x_earlier" if lag > 0 else "x_later"


def group_identity(x_key: str, y_key: str) -> tuple[str, str]:
    """Display group of a relationship family: the pair, ignoring the lag."""

    return tuple(sorted((x_key, y_key)))  # type: ignore[return-value]


def known_fingerprints(dataset: AnalyticsDataset, lag: int) -> frozenset[str]:
    """Every identity this dataset could mint for one lag.

    Lets the detail endpoint separate a *stale* identity (a digest we could have
    produced for one of these variables) from an *unknown* one (a digest that is
    not ours at all). Only hashes are computed here; no statistic is touched.
    """

    return frozenset(
        insight_fingerprint(first.key, second.key,
                            first.grain if first.grain == second.grain else None, lag)
        for pair in combinations(dataset.variables, 2)
        for first, second in (pair, tuple(reversed(pair))))


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


def _allocate(budget: int, weights: Sequence[tuple[str, int]]) -> dict[str, int]:
    """Deterministic largest-remainder allocation of ``budget`` seats."""

    total = sum(weight for _name, weight in weights)
    if budget <= 0 or total <= 0:
        return {name: 0 for name, _weight in weights}
    exact = {name: budget * weight / total for name, weight in weights}
    seats = {name: int(value) for name, value in exact.items()}
    left = budget - sum(seats.values())
    order = sorted(weights, key=lambda item: (-(exact[item[0]] - seats[item[0]]), -item[1], item[0]))
    for name, _weight in order[:left]:
        seats[name] += 1
    return seats


def discover_variables(dataset: AnalyticsDataset, *, habit_ids: Sequence[int],
                       budget: int | None = None,
                       policy: DiscoveryPolicy = DISCOVERY_POLICY) -> tuple[str, ...]:
    """The bounded default sweep: daily score, Daily State, active habits.

    Fixed priority order inside each group, a fixed variable budget and a fixed
    lag range, so a discovery run is deterministic and can never degrade into an
    unbounded combination matrix. Everything outside the sweep is still reachable
    through the explorer.
    """

    budget = policy.default_variable_budget if budget is None else budget
    available = {variable.key for variable in dataset.variables
                 if variable.grain == policy.discovery_grain}
    seats = _allocate(budget, (("score", 1), ("state", 3), ("habit", 2)))

    selected: list[str] = []
    if seats["score"] > 0 and policy.score_variable in available:
        selected.append(policy.score_variable)
    states = [key for key in policy.state_priority if key in available][:seats["state"]]
    habits = [habit_key(habit_id, policy.discovery_grain, policy.habit_feature)
              for habit_id in habit_ids]
    habits = [key for key in habits if key in available][:seats["habit"]]
    selected.extend(states)
    selected.extend(habits)
    # Deduplicate while preserving the documented priority order.
    return tuple(dict.fromkeys(selected))


def build_hypotheses(keys: Sequence[str], lags: Sequence[int],
                     policy: DiscoveryPolicy = DISCOVERY_POLICY) -> tuple[Hypothesis, ...]:
    """Every hypothesis of one discovery sweep: pairs x lags x both directions.

    Same-period pairs are generated once (the association is symmetric). Lagged
    pairs are generated in both temporal directions, because ``X earlier → Y`` and
    ``Y earlier → X`` are genuinely different pairings. Both directions share one
    display group, so a user never sees two near-identical cards for one pair.
    """

    ordered = tuple(sorted(dict.fromkeys(keys)))
    lags = normalize_lags(tuple(lags)) if lags else ()
    result: list[Hypothesis] = []
    for first, second in combinations(ordered, 2):
        for lag in lags:
            result.append((first, second, lag))
            if lag != 0:
                result.append((second, first, lag))
    if len(result) > policy.maximum_hypotheses:
        raise ValueError(
            f"Слишком много гипотез для одного запуска ({len(result)}). "
            f"Уменьшите число переменных или набор сдвигов: не более "
            f"{policy.maximum_hypotheses} гипотез.")
    return tuple(result)


def sweep_lags(lags: Sequence[int] | None,
               policy: DiscoveryPolicy = DISCOVERY_POLICY) -> tuple[int, ...]:
    """Requested discovery lags, defaulting to the documented daily range."""

    return normalize_lags(tuple(lags)) if lags else tuple(policy.default_lags)


# --------------------------------------------------------------------------- #
# Human-readable wording (typed templates, Russian, no language model)
# --------------------------------------------------------------------------- #

DAY_PHRASES: dict[int, str] = {
    1: "на следующий день", 2: "через два дня", 3: "через три дня",
    4: "через четыре дня", 5: "через пять дней", 6: "через шесть дней",
    7: "через неделю",
}
WEEK_PHRASES: dict[int, str] = {1: "на следующей неделе", 2: "через две недели",
                                3: "через три недели"}

PREFIXES: dict[ConfidenceLevel, str] = {
    "preliminary": "Пока есть предварительный сигнал: ",
    "stable": "В вашей истории наблюдается связь: ",
    "well_supported": "Эта связь устойчиво повторяется в вашей истории: ",
}
HIDDEN_PREFIX = "Результат не прошёл статистические проверки: "


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def lag_phrase(forward: int, unit: Literal["day", "week"] | None) -> str:
    """Natural wording of a forward distance, never \"7 days\" for weekly grain."""

    if forward <= 0:
        return ""
    if unit == "week":
        return WEEK_PHRASES.get(forward, f"через {forward} {'недели' if 2 <= forward <= 4 else 'недель'}")
    return DAY_PHRASES.get(forward, f"через {forward} {'дня' if 2 <= forward <= 4 else 'дней'}")


def distance_phrase(amount: int, unit: Literal["day", "week"] | None) -> str:
    if unit == "week":
        if amount == 1:
            return "1 неделю"
        return f"{amount} недели" if 2 <= amount <= 4 else f"{amount} недель"
    if amount == 1:
        return "1 день"
    return f"{amount} дня" if 2 <= amount <= 4 else f"{amount} дней"


def timing_phrase(lag: int, unit: Literal["day", "week"] | None,
                  grain: Grain | None) -> str:
    """Short lag chip. A negative lag is never dressed up as X preceding Y."""

    if lag == 0:
        return "На той же неделе" if grain == Grain.WEEKLY else "В те же дни"
    if lag < 0:
        return f"Обратный порядок: {distance_phrase(-lag, unit)}"
    return _capitalize(lag_phrase(lag, unit))


def _period_nominative(grain: Grain | None) -> str:
    """``дни`` / ``недели`` — for \"в дни, когда…\" and \"в одни и те же дни\"."""

    return "недели" if grain == Grain.WEEKLY else "дни"


def _period_genitive(grain: Grain | None) -> str:
    """``дней`` / ``недель`` — for the lagged frame \"После дней…\"."""

    return "недель" if grain == Grain.WEEKLY else "дней"


def _roles(x: Variable, y: Variable, lag: int) -> tuple[Variable, Variable, int]:
    """Readable temporal roles: the exposure is always the *earlier* measurement.

    For a negative lag the requested X is measured after Y, so the sentence is
    built from Y towards X and the timing chip plus a caveat say so explicitly.
    """

    if lag < 0:
        return y, x, -lag
    return x, y, lag


def _not_evaluable_statement(x: Variable, y: Variable, reason: NotEvaluableReason | None) -> str:
    pair = f"«{x.label}» и «{y.label}»"
    return {
        "insufficient_data": f"Для показателей {pair} пока недостаточно совместных наблюдений.",
        "constant_series": f"Связь между показателями {pair} не рассчитана: один из них не "
                           f"менялся за период.",
        "incompatible_units": f"Связь между показателями {pair} не рассчитана: за период "
                              f"менялись единицы измерения.",
        "unsupported_types": f"Связь между показателями {pair} не рассчитана: для такого "
                             f"сочетания типов расчёт не предусмотрен.",
        "grain_mismatch": f"Связь между показателями {pair} не рассчитана: один измеряется по "
                          f"дням, другой по неделям.",
        "invalid_values": f"Связь между показателями {pair} не рассчитана: в данных есть "
                          f"некорректные значения.",
        "numerical_error": f"Связь между показателями {pair} не рассчитана: расчёт оказался "
                           f"численно неустойчивым.",
    }.get(reason or "unsupported", f"Связь между показателями {pair} не рассчитана.")


def association_statement(exposure: Variable, outcome: Variable, forward: int,
                          unit: Literal["day", "week"] | None, grain: Grain | None,
                          direction: Direction) -> str:
    """Deterministic sentence, chosen by variable type, direction and lag."""

    upward = direction == "positive"
    up, down = ("выше", "ниже") if upward else ("ниже", "выше")
    more, less = ("чаще", "реже") if upward else ("реже", "чаще")
    periods = _period_nominative(grain)
    if forward == 0:
        if exposure.type == T.BOOLEAN and outcome.type == T.BOOLEAN:
            return (f"«{exposure.label}» и «{outcome.label}» {more} отмечались "
                    f"в одни и те же {periods}.")
        if exposure.type == T.BOOLEAN:
            return (f"В {periods}, когда было отмечено «{exposure.label}», значение "
                    f"«{outcome.label}» обычно было {up}.")
        if outcome.type == T.BOOLEAN:
            return (f"Чем выше был показатель «{exposure.label}», тем {more} "
                    f"отмечалось «{outcome.label}».")
        return (f"Чем выше был показатель «{exposure.label}», тем обычно {up} было "
                f"значение «{outcome.label}».")
    phrase = lag_phrase(forward, unit)
    after = _period_genitive(grain)
    if exposure.type == T.BOOLEAN:
        subject = f"После {after}, когда было отмечено «{exposure.label}»,"
    else:
        subject = f"После {after} с более высоким показателем «{exposure.label}»,"
    if outcome.type == T.BOOLEAN:
        body = f"«{outcome.label}» отмечалось {more}"
    else:
        body = f"значение «{outcome.label}» обычно было {up}"
    return f"{subject} {phrase} {body}."


def _prefix(status: InsightStatus, level: ConfidenceLevel | None) -> str:
    if status == "not_evaluable":
        return ""
    if status == "hidden":
        return HIDDEN_PREFIX
    return PREFIXES.get(level, "") if level is not None else ""


def build_text(x: Variable, y: Variable, lag: int,
               unit: Literal["day", "week"] | None, direction: Direction | None,
               grain: Grain | None, *, status: InsightStatus, level: ConfidenceLevel | None,
               reason: NotEvaluableReason | None = None) -> InsightText:
    """The one place that turns evidence into Russian prose."""

    timing = timing_phrase(lag, unit, grain)
    if status == "not_evaluable":
        statement = _not_evaluable_statement(x, y, reason)
        return InsightText(statement=statement, timing="Не рассчитано", prefix="",
                           full=statement, template_version=POLICY.template_version)
    if direction is None or direction == "near_zero":
        statement = (f"Показатели «{x.label}» и «{y.label}» были слабо связаны "
                     f"в данных за период.")
    else:
        exposure, outcome, forward = _roles(x, y, lag)
        statement = association_statement(exposure, outcome, forward, unit, grain, direction)
    prefix = _prefix(status, level)
    return InsightText(statement=statement, timing=timing, prefix=prefix,
                       full=prefix + _lower_first(statement) if prefix else statement,
                       template_version=POLICY.template_version)


# --------------------------------------------------------------------------- #
# Status, confidence view and caveats
# --------------------------------------------------------------------------- #


def presentation_status(verdict: GuardrailVerdict,
                        level: ConfidenceLevel | None) -> InsightStatus:
    """Single display label derived from both axes; never a third verdict.

    Precedence: not computable -> ``not_evaluable``; inadmissible evidence ->
    ``hidden``; admissible with limitations -> ``warning``; otherwise the Stage 7E
    confidence level. ``confidence`` and ``guardrail`` remain separate fields and
    are both shown, so this label replaces neither of them.
    """

    if level is None:
        return "not_evaluable"
    if verdict in ("blocked", "not_evaluable"):
        return "hidden"
    if verdict == "pass_with_warnings":
        return "warning"
    return level


def confidence_view(hypothesis: GuardrailHypothesis) -> tuple[ConfidenceLevel | None,
                                                             NotEvaluableReason | None]:
    """Stage 7E maturity for one evaluated hypothesis, with the guardrail cap."""

    relationship = hypothesis.relationship
    if relationship.status != "ok" or relationship.coefficient is None:
        return None, not_evaluable_reason(relationship)
    methods = evaluate_methods(relationship)
    level = classify_confidence(hypothesis.sample, hypothesis.coverage,
                               hypothesis.stability, methods, CONFIDENCE_POLICY)
    if hypothesis.verdict == "blocked" and level == "well_supported":
        level = "stable"
    return level, None


def _stage7_detail(code: str) -> str:
    """Long technical explanation, reused verbatim from Stage 7 where one exists."""

    for table in (BLOCKING_REASONS, WARNINGS):
        if code in table:
            label, message = table[code]
            return f"{label}. {message}"
    entry = CONFIDENCE_CAVEATS.get(code)
    if entry is not None:
        label, message = entry
        return f"{label}. {message}"
    return CAVEAT_PRESENTATION.get(code, ("", "", "info"))[1]


def build_caveats(hypothesis: GuardrailHypothesis,
                  caveats: Sequence[Caveat], *,
                  negative_lag: bool,
                  representative_of_family: bool) -> tuple[InsightCaveat, ...]:
    """Translate backend codes into short Russian warnings, in canonical order.

    No caveat is invented here beyond three presentation-only codes (a negative
    lag, a representative lag out of several, and an unevaluable guardrail); every
    other entry keeps its backend code and its Stage 7 explanation.
    """

    ordered: list[tuple[str, CaveatSeverity]] = []
    ordered.extend((reason.code, "blocking") for reason in hypothesis.blocking_reasons)
    ordered.extend((reason.code, "warning") for reason in hypothesis.warnings)
    ordered.extend((caveat.code, CAVEAT_PRESENTATION.get(caveat.code, ("", "", "warning"))[2])
                   for caveat in caveats)
    if hypothesis.verdict == "not_evaluable":
        ordered.append(("guardrail_not_evaluable", "warning"))
    if negative_lag:
        ordered.append((POLICY.negative_lag_caveat, "info"))
    if representative_of_family:
        ordered.append(("representative_lag_only", "info"))

    seen: set[str] = set()
    unique: list[tuple[str, CaveatSeverity]] = []
    for code, severity in ordered:
        if code not in seen:
            seen.add(code)
            unique.append((code, severity))
    unique.sort(key=lambda item: (CAVEAT_SEVERITY_ORDER[item[1]],))

    result = []
    for code, severity in unique:
        label, message, _default = CAVEAT_PRESENTATION.get(
            code, ("Ограничение данных", "Есть ограничение по этому результату.", severity))
        result.append(InsightCaveat(code=code, label=label, message=message,
                                    detail=_stage7_detail(code), severity=severity))
    return tuple(result)


# --------------------------------------------------------------------------- #
# Candidate views
# --------------------------------------------------------------------------- #


def _relationship_view(hypothesis: GuardrailHypothesis) -> InsightRelationship:
    relationship = hypothesis.relationship
    methods = evaluate_methods(relationship)
    return InsightRelationship(
        method=relationship.method, coefficient=relationship.coefficient,
        absolute_coefficient=hypothesis.effect.absolute_coefficient,
        direction=relationship.direction, strength=relationship.strength,
        n=relationship.n, status=relationship.status,
        reason=relationship.reason, limitations=relationship.limitations,
        method_agreement=methods.agreement)


def _guardrail_view(hypothesis: GuardrailHypothesis, result: GuardrailAnalytics,
                    *, capped: bool) -> InsightGuardrail:
    comparison = hypothesis.multiple_comparisons
    return InsightGuardrail(
        verdict=hypothesis.verdict, policy_version=result.guardrail_policy_version,
        family_mode=result.family.mode, family_size=result.family.requested_size,
        tested_size=result.family.tested_size, family_rank=comparison.family_rank,
        threshold=comparison.threshold, raw_p_value=comparison.raw_p_value,
        adjusted_q_value=comparison.adjusted_q_value,
        blocking_reasons=hypothesis.blocking_reasons, warnings=hypothesis.warnings,
        confidence_capped=capped)


def _confidence_field(confidence: ConfidenceAnalytics) -> InsightConfidence:
    return InsightConfidence(status="evaluated" if confidence.confidence is not None
                             else "not_evaluable", level=confidence.confidence,
                             policy_version=confidence.confidence_policy_version,
                             reason=confidence.reason)


def _segments(confidence: ConfidenceAnalytics) -> tuple[InsightSegment, ...]:
    return tuple(InsightSegment(index=segment.index, name=segment.name,
                                period=segment.period,
                                coefficient=segment.relationship.coefficient,
                                direction=segment.direction, strength=segment.strength,
                                relation_to_full=segment.relation_to_full)
                 for segment in confidence.segments)


def _evidence(confidence: ConfidenceAnalytics,
              hypothesis: GuardrailHypothesis) -> InsightEvidence:
    evidence = confidence.evidence
    return InsightEvidence(sample=evidence.sample, coverage=evidence.coverage,
                           stability=evidence.stability, methods=evidence.methods,
                           effect=hypothesis.effect, weekday=hypothesis.weekday,
                           checks=hypothesis.checks, segments=_segments(confidence))


def _alternative(hypothesis: GuardrailHypothesis,
                 representative_fingerprint: str, labels: Mapping[str, str]) -> InsightAlternative:
    level, _reason = confidence_view(hypothesis)
    fingerprint = insight_fingerprint(hypothesis.x.key, hypothesis.y.key,
                                      hypothesis.grain, hypothesis.lag)
    return InsightAlternative(
        fingerprint=fingerprint, lag=hypothesis.lag,
        timing=(f"{labels.get(hypothesis.x.key, hypothesis.x.label)} — "
                f"{labels.get(hypothesis.y.key, hypothesis.y.label)}: "
                f"{timing_phrase(hypothesis.lag, hypothesis.lag_unit, hypothesis.grain)}"),
        is_representative=fingerprint == representative_fingerprint,
        orientation=orientation_of(hypothesis.lag), guardrail=hypothesis.verdict,
        status=presentation_status(hypothesis.verdict, level), confidence=level,
        coefficient=hypothesis.relationship.coefficient,
        absolute_coefficient=hypothesis.effect.absolute_coefficient,
        direction=hypothesis.relationship.direction, n=hypothesis.sample.n,
        pair_coverage=hypothesis.coverage.pair_coverage,
        blocking_reasons=tuple(reason.code for reason in hypothesis.blocking_reasons),
        warnings=tuple(reason.code for reason in hypothesis.warnings))


def _labelled(variable: Variable, labels: Mapping[str, str]) -> Variable:
    label = labels.get(variable.key)
    return replace(variable, label=label) if label else variable


def _candidate(hypothesis: GuardrailHypothesis, confidence: ConfidenceAnalytics,
               group: Sequence[GuardrailHypothesis], result: GuardrailAnalytics,
               labels: Mapping[str, str], first_seen: Mapping[str, date],
               mode: InsightFeedMode) -> InsightCandidate:
    level = confidence.confidence
    status = presentation_status(hypothesis.verdict, level)
    x = _labelled(hypothesis.x, labels)
    y = _labelled(hypothesis.y, labels)
    fingerprint = insight_fingerprint(hypothesis.x.key, hypothesis.y.key,
                                      hypothesis.grain, hypothesis.lag)
    representative = select_representative(group)
    representative_fingerprint = insight_fingerprint(
        representative.x.key, representative.y.key, representative.grain, representative.lag)
    alternatives = tuple(_alternative(item, representative_fingerprint, labels)
                         for item in sorted(group, key=lambda item: (item.lag, item.x.key)))
    representative_only = len({(item.x.key, item.y.key, item.lag) for item in group}) > 1
    caveats = build_caveats(hypothesis, confidence.caveats,
                            negative_lag=hypothesis.lag < 0,
                            representative_of_family=representative_only and mode == "discovery")
    return InsightCandidate(
        fingerprint=fingerprint, kind=KIND, status=status,
        orientation=orientation_of(hypothesis.lag),
        x=x, y=y, grain=hypothesis.grain, lag=hypothesis.lag,
        lag_unit=hypothesis.lag_unit, target_period=hypothesis.target_period,
        text=build_text(x, y, hypothesis.lag, hypothesis.lag_unit,
                        hypothesis.relationship.direction, hypothesis.grain,
                        status=status, level=level, reason=confidence.reason),
        relationship=_relationship_view(hypothesis),
        guardrail=_guardrail_view(
            hypothesis, result,
            capped=bool(confidence.guardrail.confidence_capped
                        if confidence.guardrail is not None else False)),
        confidence=_confidence_field(confidence),
        evidence=_evidence(confidence, hypothesis),
        caveats=caveats, alternatives=alternatives,
        in_default_feed=(hypothesis.verdict in ("pass", "pass_with_warnings")
                         and hypothesis.lag >= 0),
        first_seen=first_seen.get(fingerprint))


# --------------------------------------------------------------------------- #
# Grouping, representative selection and ordering
# --------------------------------------------------------------------------- #


def representative_sort_key(item: tuple[GuardrailHypothesis, ConfidenceLevel | None]) -> tuple:
    """Order used to pick the representative lag *after* family guardrails.

    Only hypotheses whose verdict already includes the FDR correction compete
    here, so a strong lag can never be promoted before the correction is applied.
    """

    hypothesis, level = item
    return (
        VERDICT_RANK[hypothesis.verdict],
        CONFIDENCE_RANK[level],
        -(hypothesis.effect.absolute_coefficient or 0.0),
        -hypothesis.sample.n,
        abs(hypothesis.lag),
        hypothesis.lag,
        hypothesis.x.key,
        hypothesis.y.key,
    )


def select_representative(group: Sequence[GuardrailHypothesis]) -> GuardrailHypothesis:
    """Deterministic representative lag. Never called \"the optimal lag\"."""

    return sorted(group, key=lambda item: representative_sort_key(
        (item, confidence_view(item)[0])))[0]


def feed_sort_key(candidate: InsightCandidate) -> tuple:
    """Display order only, never a claim about importance."""

    return (
        VERDICT_RANK[candidate.guardrail.verdict],
        CONFIDENCE_RANK[candidate.confidence.level],
        -candidate.target_period.end.toordinal(),
        -candidate.evidence.sample.n,
        -(candidate.relationship.absolute_coefficient or 0.0),
        candidate.fingerprint,
    )


def _hypothesis_summary(hypothesis: GuardrailHypothesis,
                        result: GuardrailAnalytics) -> GuardrailSummary:
    return GuardrailSummary(
        policy_version=result.guardrail_policy_version, status=hypothesis.verdict,
        family_size=result.family.tested_size,
        blocking_reasons=tuple(reason.code for reason in hypothesis.blocking_reasons),
        warnings=tuple(reason.code for reason in hypothesis.warnings))


def build_feed(dataset: AnalyticsDataset, start: date, end: date,
               result: GuardrailAnalytics, *, mode: InsightFeedMode,
               labels: Mapping[str, str], first_seen: Mapping[str, date],
               include_hidden: bool = False,
               confidence_filter: Sequence[ConfidenceLevel] | None = None,
               verdict_filter: Sequence[str] | None = None,
               variable_filter: Sequence[str] | None = None
               ) -> tuple[InsightSummary, tuple[InsightCandidate, ...]]:
    """Gate, group, format and order the candidates of one already-evaluated family."""

    groups: dict[tuple[str, str], list[GuardrailHypothesis]] = {}
    for hypothesis in result.hypotheses:
        groups.setdefault(group_identity(hypothesis.x.key, hypothesis.y.key), []).append(hypothesis)

    by_status = {name: 0 for name in ("preliminary", "stable", "well_supported", "warning",
                                      "hidden", "not_evaluable")}
    by_reason: dict[str, int] = {}
    evaluated = admissible = blocked = unevaluable = observed = 0
    for hypothesis in result.hypotheses:
        level, _reason = confidence_view(hypothesis)
        if level is not None:
            evaluated += 1
        if hypothesis.verdict in ("pass", "pass_with_warnings"):
            admissible += 1
        elif hypothesis.verdict == "blocked":
            blocked += 1
        else:
            unevaluable += 1
        # An *observed* pair, not a merely eligible day: a period with no data at
        # all must read as "no data", never as "not enough observations yet".
        if hypothesis.sample.n > 0:
            observed += 1
        for reason in hypothesis.blocking_reasons:
            by_reason[reason.code] = by_reason.get(reason.code, 0) + 1

    candidates = []
    for group in groups.values():
        representative = select_representative(group)
        confidence = analyze_confidence(
            dataset, start, end, (representative.x.key, representative.y.key),
            representative.lag, guardrail=_hypothesis_summary(representative, result))
        candidate = _candidate(representative, confidence, group, result, labels,
                               first_seen, mode)
        by_status[candidate.status] += 1
        candidates.append(candidate)

    default_feed = [candidate for candidate in candidates if candidate.in_default_feed]
    visible = sorted(candidates, key=feed_sort_key)
    if mode == "discovery" and not include_hidden:
        visible = [candidate for candidate in visible if candidate.in_default_feed]
    if confidence_filter:
        visible = [candidate for candidate in visible
                   if candidate.confidence.level in confidence_filter]
    if verdict_filter:
        visible = [candidate for candidate in visible
                   if candidate.guardrail.verdict in verdict_filter]
    if variable_filter:
        allowed = set(variable_filter)
        visible = [candidate for candidate in visible
                   if candidate.x.key in allowed or candidate.y.key in allowed]

    total = len(result.hypotheses)
    if total == 0 or observed == 0:
        availability = "no_data"
    elif evaluated == 0:
        availability = "insufficient_data"
    elif admissible == 0:
        availability = "no_guardrails_passed"
    elif default_feed and all(candidate.confidence.level == "preliminary"
                              for candidate in default_feed):
        availability = "preliminary_only"
    else:
        availability = "ok"

    counts = InsightCounts(
        hypotheses=total, evaluated_hypotheses=evaluated, admissible_hypotheses=admissible,
        blocked_hypotheses=blocked, unevaluable_hypotheses=unevaluable, groups=len(groups),
        shown=len(visible), in_default_feed=len(default_feed), by_status=by_status,
        by_blocking_reason={code: by_reason[code] for code in
                            sorted(by_reason, key=lambda code: (-by_reason[code], code))})
    summary = InsightSummary(availability=availability,
                            message=AVAILABILITY_MESSAGES[availability], counts=counts)
    return summary, tuple(visible)


# --------------------------------------------------------------------------- #
# Detail charts: existing Stage 7B/7D evidence, reshaped for drawing only
# --------------------------------------------------------------------------- #


def _series(dataset: AnalyticsDataset, variable: Variable, start: date, end: date
            ) -> tuple[InsightSeries, tuple[InsightChartPoint, ...]]:
    sliced = slice_dataset(dataset, start, end)
    by_week: dict[date, list] = {}
    for row in sliced.daily:
        by_week.setdefault(row.week_start, []).append(row)
    raw = make_series(sliced, variable, by_week)
    plottable = variable.type in (T.NUMERIC, T.ORDINAL, T.BOOLEAN)
    points = []
    for point in raw:
        observed = plottable and point.availability == A.PRESENT
        value = None
        if observed:
            value = float(point.value is True) if variable.type == T.BOOLEAN else float(point.value)
        points.append(InsightChartPoint(date=point.date, value=value, missing=not observed,
                                        incomplete=point.incomplete))
    averages = ()
    if variable.type in (T.NUMERIC, T.ORDINAL):
        averages = tuple(InsightRollingPoint(date=item.date, window=item.window_size,
                                            mean=item.mean, status=item.status)
                         for item in rolling(variable, raw))
    return InsightSeries(variable=variable, points=tuple(points), rolling=averages), tuple(points)


def _pair_points(dataset: AnalyticsDataset, x: Variable, y: Variable, start: date, end: date,
                 lag: int) -> tuple[InsightPairPoint, ...]:
    if x.grain != y.grain or x.grain is None:
        return ()
    if x.type not in (T.NUMERIC, T.ORDINAL) or y.type not in (T.NUMERIC, T.ORDINAL):
        return ()
    paired = paired_observations(dataset, start, end, (x.key, y.key), lag)
    if paired is None:
        return ()
    return tuple(InsightPairPoint(x_date=first.date, y_date=second.date,
                                  x=float(first.value), y=float(second.value))
                 for first, second in zip(paired.x, paired.y))


def _chart_summaries(candidate: InsightCandidate, x_points: tuple[InsightChartPoint, ...],
                     y_points: tuple[InsightChartPoint, ...],
                     pairs: tuple[InsightPairPoint, ...],
                     history_count: int) -> tuple[InsightChartSummary, ...]:
    """Accessible Russian text for every chart, so no chart is the only channel."""

    x_observed = sum(1 for point in x_points if not point.missing)
    y_observed = sum(1 for point in y_points if not point.missing)
    summaries = [InsightChartSummary(
        key="series", title="Как менялись показатели",
        summary=f"Показатели «{candidate.x.label}» и «{candidate.y.label}» по датам периода. "
                f"Заполнено точек: {x_observed} и {y_observed}; пропуски оставлены пустыми.")]
    if pairs:
        summaries.append(InsightChartSummary(
            key="relationship", title="Совместные наблюдения",
            summary=f"Точками показаны {len(pairs)} совместных наблюдений. "
                    f"Линия тренда не рассчитывается и на графике не рисуется."))
    group = candidate.evidence.effect.group
    if group is not None:
        exposure = candidate.x if group.boolean_side == "x" else candidate.y
        summaries.append(InsightChartSummary(
            key="groups", title="Сравнение групп",
            summary=f"Показатель «{exposure.label}»: «Да» — {group.true_count} наблюдений, "
                    f"«Нет» — {group.false_count} наблюдений."))
    summaries.append(InsightChartSummary(
        key="lag_profile", title="Профиль задержек",
        summary=f"Проверено задержек: {len(candidate.alternatives)}. Для каждой показана "
                f"величина связи и результат проверок."))
    if candidate.evidence.segments:
        summaries.append(InsightChartSummary(
            key="segments", title="Отрезки истории",
            summary=f"История разделена на {len(candidate.evidence.segments)} "
                    f"последовательных отрезка; показана величина связи на каждом."))
    if history_count:
        summaries.append(InsightChartSummary(
            key="history", title="История оценок",
            summary=f"Сохранённых оценок этой связи: {history_count}."))
    return tuple(summaries)


def candidate_for(dataset: AnalyticsDataset, start: date, end: date,
                  result: GuardrailAnalytics, hypothesis: GuardrailHypothesis,
                  group: Sequence[GuardrailHypothesis], *, labels: Mapping[str, str],
                  first_seen: Mapping[str, date], mode: InsightFeedMode) -> InsightCandidate:
    """One specific hypothesis of an already-evaluated family, for the detail view.

    The verdict is the same family verdict the feed showed, so opening a card can
    never present a differently corrected number.
    """

    confidence = analyze_confidence(
        dataset, start, end, (hypothesis.x.key, hypothesis.y.key), hypothesis.lag,
        guardrail=_hypothesis_summary(hypothesis, result))
    return _candidate(hypothesis, confidence, group, result, labels, first_seen, mode)


def build_chart(dataset: AnalyticsDataset, candidate: InsightCandidate, *,
                history_count: int = 0) -> InsightChart:
    """Chart data for one candidate. No coefficient is recomputed anywhere here."""

    start, end = candidate.target_period.start, candidate.target_period.end
    x_series, x_points = _series(dataset, candidate.x, start, end)
    y_series, y_points = _series(dataset, candidate.y, start, end)
    pairs = _pair_points(dataset, candidate.x, candidate.y, start, end, candidate.lag)
    return InsightChart(
        x=x_series, y=y_series, pairs=pairs, lag_profile=candidate.alternatives,
        segments=candidate.evidence.segments,
        summaries=_chart_summaries(candidate, x_points, y_points, pairs, history_count))


# --------------------------------------------------------------------------- #
# Catalogue metadata
# --------------------------------------------------------------------------- #


def variable_group(variable: Variable) -> str:
    """Coarse grouping used by the filter UI; never a statistical statement."""

    if variable.habit_id is not None:
        return "habit"
    if variable.source.startswith("stage4."):
        return "score"
    if ".state." in variable.key or variable.key.startswith("state."):
        return "state"
    if variable.key.split(".")[0] in ("daily", "weekly"):
        return "calendar"
    return "other"


def supported_variable(variable: Variable) -> bool:
    return variable.type != T.CATEGORICAL


__all__ = [
    "Hypothesis", "association_statement", "build_caveats", "build_chart", "build_feed",
    "build_hypotheses", "build_text", "canonical_keys", "candidate_for", "confidence_view",
    "discover_variables", "distance_phrase",    "feed_sort_key", "group_identity",
    "insight_fingerprint", "known_fingerprints", "lag_phrase", "orientation_of",
    "presentation_status",
    "representative_sort_key", "select_representative", "supported_variable",
    "sweep_lags", "timing_phrase", "variable_group",
]
