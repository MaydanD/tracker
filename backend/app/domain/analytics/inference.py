"""Pure statistical inference: correlation p-values and Benjamini-Hochberg FDR.

No dependency is added: the Student-t tail is evaluated through the regularized
incomplete beta function (continued fraction), and the 1-df chi-square tail
through ``erf``. Both are exact for the tests below, deterministic and cheap.

A p-value here is only one guardrail signal. It is never a probability that the
association is true, and it never replaces the coefficient, sample size,
coverage, group balance or temporal evidence.
"""

from math import erfc, exp, isfinite, lgamma, log, log1p, sqrt


# Continued-fraction and convergence guards for the incomplete beta function.
_MAXIMUM_ITERATIONS = 300
_EPSILON = 3e-16
_TINY = 1e-300


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    """Lentz's modified continued fraction for the incomplete beta function."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _TINY:
        d = _TINY
    d = 1.0 / d
    result = d
    for iteration in range(1, _MAXIMUM_ITERATIONS + 1):
        m2 = 2 * iteration
        aa = iteration * (b - iteration) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _TINY:
            d = _TINY
        c = 1.0 + aa / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1.0 / d
        result *= d * c
        aa = -(a + iteration) * (qab + iteration) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _TINY:
            d = _TINY
        c = 1.0 + aa / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < _EPSILON:
            break
    return result


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """I_x(a, b), the CDF of a Beta(a, b) distribution, for a, b > 0."""
    if not (a > 0 and b > 0) or not isfinite(x):
        raise ValueError("Неверные параметры бета-распределения.")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * log(x) + b * log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return max(0.0, min(1.0, front * _beta_continued_fraction(a, b, x) / a))
    return max(0.0, min(1.0, 1.0 - front * _beta_continued_fraction(b, a, 1.0 - x) / b))


def correlation_p_value(coefficient: float | None, n: int) -> float | None:
    """Two-sided p-value for a correlation-like coefficient with df = n - 2.

    Used for Pearson, point-biserial and Spearman. Point-biserial is Pearson on
    the 0/1 encoding, so the pooled two-sample t-test and this value coincide.
    Spearman uses the standard t-approximation on its rank coefficient.
    """
    if coefficient is None or not isfinite(coefficient) or n < 3:
        return None
    if abs(coefficient) >= 1.0:
        return 0.0
    return regularized_incomplete_beta((n - 2) / 2.0, 0.5, 1.0 - coefficient * coefficient)


def phi_p_value(coefficient: float | None, n: int) -> float | None:
    """Exact two-sided p-value for Phi through chi-square with one degree of freedom."""
    if coefficient is None or not isfinite(coefficient) or n < 2:
        return None
    chi_square = n * coefficient * coefficient
    if not isfinite(chi_square):
        return 0.0
    return max(0.0, min(1.0, erfc(sqrt(chi_square / 2.0))))


def method_p_value(method: str, coefficient: float | None, n: int) -> float | None:
    """Primary-method p-value; unsupported methods return None instead of guessing."""
    if method in ("pearson", "spearman", "point_biserial"):
        return correlation_p_value(coefficient, n)
    if method == "phi":
        return phi_p_value(coefficient, n)
    return None


def benjamini_hochberg(p_values: tuple[float, ...]) -> tuple[float, ...]:
    """Benjamini-Hochberg adjusted q-values, aligned with the input order.

    Monotone in p, clamped to [0, 1], deterministic, and identical p-values get
    identical q-values. Callers decide which hypotheses enter the family; the
    denominator is exactly ``len(p_values)``.
    """
    count = len(p_values)
    if count == 0:
        return ()
    for value in p_values:
        if not isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("p-значения должны быть конечными числами от 0 до 1.")
    order = sorted(range(count), key=lambda index: (p_values[index], index))
    adjusted = [0.0] * count
    running = 1.0
    for rank in range(count, 0, -1):
        index = order[rank - 1]
        running = min(running, p_values[index] * count / rank)
        adjusted[index] = max(0.0, min(1.0, running))
    return tuple(adjusted)


def cohens_d(group: list[float], other: list[float]) -> float | None:
    """Pooled-standard-deviation effect size; None when undefined, never imputed."""
    if len(group) < 2 or len(other) < 2:
        return None
    first, second = sum(group) / len(group), sum(other) / len(other)
    variance = (sum((value - first) ** 2 for value in group)
                + sum((value - second) ** 2 for value in other)) / (len(group) + len(other) - 2)
    if variance <= 0:
        return None
    effect = (first - second) / sqrt(variance)
    return effect if isfinite(effect) else None


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    return (float(ordered[middle]) if len(ordered) % 2
            else (ordered[middle - 1] + ordered[middle]) / 2.0)
