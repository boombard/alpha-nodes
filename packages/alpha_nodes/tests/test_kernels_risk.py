"""Tests for the risk kernels; TA-Lib is the oracle for volatility (tests only)."""

import numpy as np
import pytest
import talib
from alpha_nodes.kernels import drawdown, drawdown_extent, max_drawdown, realised_volatility


def test_realised_volatility_hand_value() -> None:
    r = np.array([0.01, -0.02, 0.03])
    mean = r.mean()
    var = ((r - mean) ** 2).sum() / 2
    assert realised_volatility(r) == pytest.approx(np.sqrt(var) * np.sqrt(252))


def test_realised_volatility_nan_when_too_few() -> None:
    assert np.isnan(realised_volatility(np.array([0.01])))
    assert np.isnan(realised_volatility(np.array([])))


def test_max_drawdown_hand_value() -> None:
    assert max_drawdown(np.array([1.0, 2.0, 1.0, 3.0, 1.5])) == pytest.approx(-0.5)


def test_max_drawdown_nan_when_empty() -> None:
    assert np.isnan(max_drawdown(np.array([])))


def test_drawdown_extent_earliest_trough_on_tie() -> None:
    assert drawdown_extent(np.array([1.0, 2.0, 1.0, 1.0])) == (1, 2)


def test_drawdown_extent_no_drawdown_uses_last_running_max() -> None:
    assert drawdown_extent(np.array([1.0, 2.0, 3.0])) == (2, 2)
    assert drawdown_extent(np.array([1.0, 1.0])) == (1, 1)


def test_drawdown_extent_rejects_empty() -> None:
    with pytest.raises(ValueError, match="x"):
        drawdown_extent(np.array([]))


def test_drawdown_extent_matches_max_drawdown(random_walk) -> None:
    x = random_walk(300, 4)
    peak, trough = drawdown_extent(x)
    assert x[trough] / x[peak] - 1 == pytest.approx(max_drawdown(x))


@pytest.mark.parametrize("seed", range(4))
def test_max_drawdown_scale_invariant(random_walk, seed: int) -> None:
    x = random_walk(300, seed)
    assert max_drawdown(x * 37.5) == pytest.approx(max_drawdown(x), rel=1e-12)


@pytest.mark.parametrize("seed", range(4))
def test_drawdown_never_positive(random_walk, seed: int) -> None:
    assert (drawdown(random_walk(300, seed)) <= 0).all()


def test_monotone_series_has_zero_drawdown() -> None:
    x = np.cumsum(np.ones(20)) + 1
    assert max_drawdown(x) == 0.0
    assert (drawdown(x) == 0.0).all()


def test_constant_growth_has_zero_volatility() -> None:
    assert realised_volatility(np.full(50, 0.001)) == pytest.approx(0.0, abs=1e-12)


def test_realised_volatility_matches_talib_rescaled(random_walk) -> None:
    x = random_walk(500, 5)
    n = 252
    returns = np.diff(np.log(x))[-n:]
    # TA-Lib STDDEV is the population std; rescale to ddof=1, then annualise.
    pop = talib.STDDEV(returns, timeperiod=n, nbdev=1)[-1]
    expected = pop * np.sqrt(n / (n - 1)) * np.sqrt(252)
    np.testing.assert_allclose(realised_volatility(returns), expected, rtol=1e-10)
