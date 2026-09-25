"""Pure coefficients over already paired finite observations; never impute.

Scaling before centering avoids overflowing sums/squares; rescaling deviations
also avoids underflow for almost constant series. Spearman uses average ranks.
"""

from math import fsum, isfinite, sqrt
from collections.abc import Sequence

from app.domain.analytics.relationship_types import POLICY, Method, Metric


def _validate(x: Sequence, y: Sequence, method: Method) -> Metric | None:
    if len(x) != len(y) or any(type(v) not in (int, float) or not finite_number(v) for v in (*x, *y)):
        return Metric(method, "invalid_values", None, "nonfinite_or_invalid_values")
    if len(x) < POLICY.calculation_minimum:
        return Metric(method, "insufficient_data", None, "too_few_pairs")
    if min(x) == max(x) or min(y) == max(y):
        return Metric(method, "constant_series", None, "zero_variance")
    return None


def finite_number(value: int | float) -> bool:
    try:
        return isfinite(value)
    except OverflowError:
        return False


def _center(values: Sequence[float]) -> list[float]:
    # Translation first preserves small representable differences at large offsets.
    shifted = [value - values[0] for value in values]
    if not all(finite_number(value) for value in shifted):
        scale = max(abs(value) for value in values)
        shifted = [value / scale for value in values]
    scale = max(abs(value) for value in shifted)
    normalized = [value / scale for value in shifted]
    average = fsum(normalized) / len(normalized)
    centered = [value - average for value in normalized]
    scale = max(abs(value) for value in centered)
    return [value / scale for value in centered]


def pearson(x: Sequence[float], y: Sequence[float], *, method: Method = "pearson") -> Metric:
    invalid = _validate(x, y, method)
    if invalid is not None:
        return invalid
    try:
        a, b = _center(x), _center(y)
        r = fsum(u * v for u, v in zip(a, b)) / sqrt(fsum(v * v for v in a)) / sqrt(fsum(v * v for v in b))
        if not isfinite(r):
            raise ValueError("Nonfinite coefficient")
        return Metric(method, "ok", max(-1.0, min(1.0, r)))
    except (OverflowError, ValueError, ZeroDivisionError):
        return Metric(method, "numerical_error", None, "unstable_calculation")


def average_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + 1 + end) / 2
        for index in order[start:end]:
            ranks[index] = rank
        start = end
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> Metric:
    invalid = _validate(x, y, "spearman")
    return invalid if invalid is not None else pearson(average_ranks(x), average_ranks(y), method="spearman")


def point_biserial(binary: Sequence[bool], numeric: Sequence[float]) -> Metric:
    """Encode observed booleans only; null is rejected, never encoded as 0."""
    if any(type(v) is not bool for v in binary):
        return Metric("point_biserial", "invalid_values", None, "nonfinite_or_invalid_values")
    return pearson([int(v) for v in binary], numeric, method="point_biserial")


def phi(x: Sequence[bool], y: Sequence[bool]) -> Metric:
    """Binary Pearson equals Phi; constant margins are explicitly undefined."""
    if any(type(v) is not bool for v in (*x, *y)):
        return Metric("phi", "invalid_values", None, "nonfinite_or_invalid_values")
    return pearson([int(v) for v in x], [int(v) for v in y], method="phi")
