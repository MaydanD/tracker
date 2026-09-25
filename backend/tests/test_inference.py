"""Reference values, monotonicity and edge cases for inference math."""

from math import inf, nan

import pytest

from app.domain.analytics.inference import (
    benjamini_hochberg, cohens_d, correlation_p_value, median, method_p_value,
    phi_p_value, regularized_incomplete_beta,
)


@pytest.mark.parametrize("coefficient,n,expected", [
    (0.632, 10, 0.0498),      # df = 8, classic two-sided t table
    (0.576, 10, 0.0818),
    (0.444, 10, 0.1985),
    (0.304, 10, 0.3928),
    (0.25, 30, 0.1824),       # df = 28
    (0.5, 10, 0.1408),
])
def test_correlation_p_value_matches_t_tables(coefficient, n, expected):
    assert correlation_p_value(coefficient, n) == pytest.approx(expected, abs=0.002)


def test_correlation_p_value_boundaries():
    assert correlation_p_value(0.0, 30) == 1.0
    assert correlation_p_value(1.0, 30) == 0.0
    assert correlation_p_value(-1.0, 30) == 0.0
    assert correlation_p_value(0.4, 2) is None       # df would be zero
    assert correlation_p_value(None, 30) is None
    assert correlation_p_value(0.4, 3) is not None
    for coefficient in (nan, inf, -inf):
        assert correlation_p_value(coefficient, 30) is None


def test_phi_p_value_is_exact_chi_square_with_one_degree_of_freedom():
    assert phi_p_value(0.2, 100) == pytest.approx(0.0455, abs=0.0001)
    assert phi_p_value(0.1, 100) == pytest.approx(0.3173, abs=0.0001)
    assert phi_p_value(0.0, 50) == 1.0
    assert phi_p_value(1.0, 50) == pytest.approx(0.0, abs=1e-10)
    assert phi_p_value(None, 50) is None
    assert phi_p_value(0.2, 1) is None
    assert phi_p_value(nan, 50) is None


@pytest.mark.parametrize("method", ["pearson", "spearman", "point_biserial"])
def test_method_dispatch_reuses_the_correlation_test(method):
    assert method_p_value(method, 0.632, 10) == correlation_p_value(0.632, 10)


def test_method_dispatch_never_fabricates_a_p_value():
    assert method_p_value("phi", 0.2, 100) == phi_p_value(0.2, 100)
    assert method_p_value("unknown_method", 0.2, 100) is None


def test_regularized_incomplete_beta_is_bounded_and_monotone():
    assert regularized_incomplete_beta(1, 1, 0.3) == pytest.approx(0.3)
    assert regularized_incomplete_beta(0.5, 0.5, 0.5) == pytest.approx(0.5)
    assert regularized_incomplete_beta(2, 3, 0.0) == 0.0
    assert regularized_incomplete_beta(2, 3, 1.0) == 1.0
    values = [regularized_incomplete_beta(2.5, 4.0, step / 20) for step in range(21)]
    assert values == sorted(values)
    assert all(0.0 <= value <= 1.0 for value in values)
    with pytest.raises(ValueError):
        regularized_incomplete_beta(0, 1, 0.5)


def test_benjamini_hochberg_matches_a_hand_computed_example():
    p_values = (0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216,
                0.222, 0.251, 0.269, 0.275, 0.34)
    expected = (0.015, 0.06, 0.126, 0.126, 0.126, 0.15, 0.15857142857142856,
                0.29464285714285715, 0.29464285714285715, 0.29464285714285715,
                0.29464285714285715, 0.29464285714285715, 0.29464285714285715,
                0.29464285714285715, 0.34)
    adjusted = benjamini_hochberg(p_values)
    assert adjusted == pytest.approx(expected)


def test_benjamini_hochberg_preserves_identity_and_is_monotone():
    p_values = (0.5, 0.01, 0.2, 0.01)
    adjusted = benjamini_hochberg(p_values)
    assert adjusted == pytest.approx((0.5, 0.02, 0.26666666666666666, 0.02))
    ordered = [value for _, value in sorted(zip(p_values, adjusted))]
    assert ordered == sorted(ordered)


@pytest.mark.parametrize("p_values,expected", [
    ((), ()),
    ((0.03,), (0.03,)),
    ((0.0,), (0.0,)),
    ((1.0,), (1.0,)),
    ((0.01, 0.01, 0.01), (0.01, 0.01, 0.01)),
])
def test_benjamini_hochberg_edge_cases(p_values, expected):
    assert benjamini_hochberg(p_values) == pytest.approx(expected)


def test_benjamini_hochberg_ties_and_clamping():
    adjusted = benjamini_hochberg((0.6, 0.6, 0.9))
    assert adjusted[0] == adjusted[1]
    assert all(0.0 <= value <= 1.0 for value in adjusted)
    assert all(value >= p for p, value in zip((0.6, 0.6, 0.9), adjusted))
    assert benjamini_hochberg((0.9, 0.95))[0] <= 1.0


@pytest.mark.parametrize("p_values", [(nan,), (-0.01,), (1.01,), (inf,)])
def test_benjamini_hochberg_rejects_invalid_probabilities(p_values):
    with pytest.raises(ValueError):
        benjamini_hochberg(p_values)


def test_family_size_changes_the_verdict_for_one_hypothesis():
    assert benjamini_hochberg((0.03,))[0] == pytest.approx(0.03)
    assert benjamini_hochberg((0.03,) + (0.9,) * 19)[0] == pytest.approx(0.6)


@pytest.mark.parametrize("group,other,expected", [
    ([3, 4, 5], [1, 2, 3], 2.0),
    ([1, 2, 3], [3, 4, 5], -2.0),
    ([5, 5, 5], [5, 5, 5], None),          # zero pooled variance
    ([1], [2, 3, 4], None),                # group too small
])
def test_cohens_d(group, other, expected):
    assert cohens_d(group, other) == pytest.approx(expected) if expected is not None \
        else cohens_d(group, other) is None


def test_median_handles_even_and_odd_and_empty():
    assert median([1, 2, 3]) == 2.0
    assert median([1, 2, 3, 4]) == 2.5
    assert median([]) is None
