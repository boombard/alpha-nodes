"""Hand-computed tests for the fundamentals numpy kernels (no TA-Lib oracle exists)."""

import math

import numpy as np
import pytest
from alpha_nodes.kernels.fundamentals import (
    cagr,
    capitalised_value,
    coefficient_of_variation,
    growth,
    incremental_return,
    invested_capital,
    mean_std,
    owner_earnings,
    safe_ratio,
    sum_ratio,
)


def test_safe_ratio_values_and_nonpositive_denominator():
    out = safe_ratio(np.array([1.0, 2.0, 3.0, 4.0]), np.array([2.0, 0.0, -1.0, 8.0]))
    assert out[0] == 0.5
    assert math.isnan(out[1])
    assert math.isnan(out[2])
    assert out[3] == 0.5


def test_safe_ratio_length_mismatch_raises():
    with pytest.raises(ValueError):
        safe_ratio(np.array([1.0, 2.0]), np.array([1.0]))


def test_growth_hand_value():
    assert growth(100.0, 110.0) == pytest.approx(0.1)


def test_growth_from_negative_base():
    assert growth(-50.0, 25.0) == pytest.approx(1.5)


def test_growth_zero_base_is_nan():
    assert math.isnan(growth(0.0, 5.0))


def test_cagr_hand_value():
    assert cagr(100.0, 121.0, 2.0) == pytest.approx(0.10)


@pytest.mark.parametrize(
    "first,last,years",
    [(0.0, 1.0, 1.0), (-1.0, 1.0, 1.0), (1.0, 0.0, 1.0), (1.0, -2.0, 1.0), (1.0, 2.0, 0.0)],
)
def test_cagr_nan_for_nonpositive_ends(first, last, years):
    assert math.isnan(cagr(first, last, years))


def test_mean_std_ddof_1():
    mean, std = mean_std(np.array([1.0, 2.0, 3.0, 4.0]))
    assert mean == 2.5
    assert std == pytest.approx(math.sqrt(5.0 / 3.0))


def test_mean_std_short_gives_nan_std():
    mean, std = mean_std(np.array([1.0, 3.0]))
    assert mean == 2.0
    assert math.isnan(std)


def test_mean_std_empty():
    mean, std = mean_std(np.array([]))
    assert math.isnan(mean) and math.isnan(std)


def test_cv_hand_value():
    assert coefficient_of_variation(np.array([2.0, 4.0, 6.0])) == pytest.approx(0.5)


def test_cv_nan_when_mean_not_positive():
    assert math.isnan(coefficient_of_variation(np.array([-1.0, -2.0, -3.0])))
    assert math.isnan(coefficient_of_variation(np.array([1.0, 2.0])))


def test_owner_earnings_caps_maintenance_at_capex():
    out = owner_earnings(np.array([10.0]), np.array([5.0]), np.array([3.0]))
    assert out[0] == 12.0


def test_owner_earnings_capex_above_da():
    out = owner_earnings(np.array([10.0]), np.array([5.0]), np.array([8.0]))
    assert out[0] == 10.0


def test_sum_ratio_hand_value():
    assert sum_ratio(np.array([1.0, 2.0]), np.array([2.0, 4.0])) == 0.5


def test_sum_ratio_nan_when_denominator_sum_not_positive():
    assert math.isnan(sum_ratio(np.array([1.0]), np.array([0.0])))
    assert math.isnan(sum_ratio(np.array([]), np.array([])))


def test_capitalised_value_hand_value():
    assert capitalised_value(10.0, 0.05) == pytest.approx(200.0)


def test_capitalised_value_negative_earnings_nan():
    assert math.isnan(capitalised_value(-1.0, 0.05))


def test_capitalised_value_rejects_nonpositive_rate():
    with pytest.raises(ValueError):
        capitalised_value(1.0, 0.0)


@pytest.mark.parametrize("bad", [np.nan, np.inf])
@pytest.mark.parametrize(
    "call",
    [
        lambda a: safe_ratio(a, np.ones_like(a)),
        lambda a: safe_ratio(np.ones_like(a), a),
        lambda a: mean_std(a),
        lambda a: coefficient_of_variation(a),
        lambda a: owner_earnings(a, np.ones_like(a), np.ones_like(a)),
        lambda a: owner_earnings(np.ones_like(a), a, np.ones_like(a)),
        lambda a: owner_earnings(np.ones_like(a), np.ones_like(a), a),
        lambda a: sum_ratio(a, np.ones_like(a)),
        lambda a: sum_ratio(np.ones_like(a), a),
    ],
)
def test_non_finite_input_raises(call, bad):
    with pytest.raises(ValueError):
        call(np.array([1.0, bad, 3.0]))


def test_invested_capital():
    out = invested_capital(np.array([50.0, 0.0]), np.array([100.0, 20.0]), np.array([10.0, 30.0]))
    assert out.tolist() == [140.0, -10.0]  # debt + equity - cash, negatives kept for the caller


def test_invested_capital_length_mismatch_raises():
    with pytest.raises(ValueError):
        invested_capital(np.array([1.0, 2.0]), np.array([1.0]), np.array([1.0, 2.0]))


def test_incremental_return_hand_value():
    assert incremental_return(10.0, 20.0, 100.0, 150.0) == pytest.approx(0.2)
    assert incremental_return(20.0, 10.0, 100.0, 150.0) == pytest.approx(-0.2)


@pytest.mark.parametrize("cap_end", [100.0, 90.0])
def test_incremental_return_nan_when_capital_shrinks(cap_end):
    assert math.isnan(incremental_return(10.0, 20.0, 100.0, cap_end))


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_kernels_reject_non_finite(bad):
    ones = np.ones(2)
    for args in ((np.array([1.0, bad]), ones, ones), (ones, np.array([1.0, bad]), ones), (ones, ones, np.array([1.0, bad]))):
        with pytest.raises(ValueError):
            invested_capital(*args)
    for i in range(4):
        vals = [1.0, 2.0, 3.0, 4.0]
        vals[i] = bad
        with pytest.raises(ValueError):
            incremental_return(*vals)
