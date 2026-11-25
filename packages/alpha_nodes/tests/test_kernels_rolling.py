"""Tests for the rolling-statistics kernels; TA-Lib is the oracle (tests only)."""

import numpy as np
import pytest
import talib
from alpha_nodes.kernels import linreg_slope, rolling_std, sma


def test_sma_hand_value() -> None:
    np.testing.assert_allclose(
        sma(np.array([1.0, 2.0, 3.0, 4.0]), 2), [np.nan, 1.5, 2.5, 3.5], equal_nan=True
    )


def test_rolling_std_hand_value() -> None:
    out = rolling_std(np.array([1.0, 2.0, 4.0]), 3)
    assert out[2] == pytest.approx(np.std([1.0, 2.0, 4.0], ddof=1))
    assert np.isnan(out[:2]).all()


@pytest.mark.parametrize("kernel", [sma, rolling_std, linreg_slope])
def test_rolling_kernels_all_nan_when_short(kernel) -> None:
    out = kernel(np.array([1.0, 2.0, 3.0]), 5)
    assert out.shape == (3,)
    assert np.isnan(out).all()


@pytest.mark.parametrize("kernel", [sma, rolling_std, linreg_slope])
@pytest.mark.parametrize("window", [0, -1])
def test_bad_window_rejected(kernel, window: int) -> None:
    with pytest.raises(ValueError, match="window"):
        kernel(np.ones(10), window)


def test_linreg_slope_needs_window_two() -> None:
    with pytest.raises(ValueError, match="window"):
        linreg_slope(np.ones(10), 1)


def test_rolling_std_needs_window_above_ddof() -> None:
    with pytest.raises(ValueError, match="window"):
        rolling_std(np.ones(10), 1, ddof=1)


@pytest.mark.parametrize("window", [1, 5, 20])
def test_sma_of_constant_is_constant(window: int) -> None:
    out = sma(np.full(50, 7.5), window)
    np.testing.assert_allclose(out[window - 1 :], 7.5)


@pytest.mark.parametrize("slope", [-2.0, 0.0, 0.5, 3.0])
def test_linreg_slope_of_line_is_its_slope(slope: float) -> None:
    out = linreg_slope(10.0 + slope * np.arange(60.0), 20)
    np.testing.assert_allclose(out[19:], slope, atol=1e-9)
    assert np.isnan(out[:19]).all()


@pytest.mark.parametrize("window", [20, 200])
def test_sma_matches_talib(random_walk, window: int) -> None:
    x = random_walk(500, 1)
    np.testing.assert_allclose(sma(x, window), talib.SMA(x, window), rtol=1e-10, equal_nan=True)


def test_linreg_slope_matches_talib(random_walk) -> None:
    x = random_walk(500, 2)
    np.testing.assert_allclose(
        linreg_slope(x, 20),
        talib.LINEARREG_SLOPE(x, 20),
        rtol=1e-10,
        atol=1e-12,  # TA-Lib accumulates running sums; ~3e-13 abs drift on near-zero slopes
        equal_nan=True,
    )


def test_rolling_std_matches_talib_population(random_walk) -> None:
    x = random_walk(500, 3)
    np.testing.assert_allclose(
        rolling_std(x, 20, ddof=0),
        talib.STDDEV(x, timeperiod=20, nbdev=1),
        rtol=1e-10,
        equal_nan=True,
    )
