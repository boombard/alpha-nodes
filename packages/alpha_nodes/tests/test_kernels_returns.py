"""Tests for the returns kernels, plus the input-validation rules shared by every kernel."""

from collections.abc import Callable

import numpy as np
import pytest
from alpha_nodes.kernels import (
    drawdown,
    drawdown_extent,
    linreg_slope,
    log_returns,
    max_drawdown,
    realised_volatility,
    rolling_std,
    simple_returns,
    skip_return,
    sma,
    total_return_index,
)

# Every kernel as a one-array callable, for the cross-kernel validation tests below.
ALL_KERNELS: dict[str, Callable[[np.ndarray], object]] = {
    "simple_returns": simple_returns,
    "log_returns": log_returns,
    "total_return_index": lambda x: total_return_index(x, np.zeros_like(x)),
    "skip_return": lambda x: skip_return(x, 5, 2),
    "sma": lambda x: sma(x, 3),
    "rolling_std": lambda x: rolling_std(x, 3),
    "linreg_slope": lambda x: linreg_slope(x, 3),
    "realised_volatility": realised_volatility,
    "drawdown": drawdown,
    "max_drawdown": max_drawdown,
    "drawdown_extent": drawdown_extent,
}
# Kernels that take returns (any sign), so non-positive values are legal for them.
SIGNED_INPUT = {"realised_volatility", "sma", "rolling_std", "linreg_slope"}


def test_total_return_index_hand_value() -> None:
    tr = total_return_index(np.array([100.0, 101.0, 99.0]), np.array([0.0, 0.0, 2.0]))
    np.testing.assert_allclose(tr, [1.0, 1.01, 1.01])


def test_skip_return_hand_value() -> None:
    x = np.arange(1, 300.0)
    assert skip_return(x) == pytest.approx(x[-22] / x[-253] - 1)


def test_simple_returns_hand_value() -> None:
    np.testing.assert_allclose(simple_returns(np.array([100.0, 110.0, 99.0])), [0.1, -0.1])


def test_skip_return_nan_when_short() -> None:
    assert np.isnan(skip_return(np.arange(1, 253.0)))


def test_skip_return_rejects_bad_skip() -> None:
    with pytest.raises(ValueError, match="skip"):
        skip_return(np.arange(1, 300.0), lookback=10, skip=10)


def test_total_return_index_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError, match="dividends"):
        total_return_index(np.array([1.0, 2.0]), np.array([0.0]))


def test_total_return_index_rejects_negative_dividends() -> None:
    with pytest.raises(ValueError, match="dividends"):
        total_return_index(np.array([1.0, 2.0]), np.array([0.0, -1.0]))


@pytest.mark.parametrize("seed", range(3))
def test_log_and_simple_returns_agree(random_walk, seed: int) -> None:
    x = random_walk(200, seed)
    np.testing.assert_allclose(np.exp(log_returns(x)) - 1, simple_returns(x), rtol=1e-9, atol=1e-14)


@pytest.mark.parametrize("name", list(ALL_KERNELS))
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_kernels_reject_non_finite(name: str, bad: float) -> None:
    x = np.array([1.0, 2.0, bad, 4.0, 5.0, 6.0, 7.0])
    with pytest.raises(ValueError, match="finite"):
        ALL_KERNELS[name](x)


@pytest.mark.parametrize("name", [n for n in ALL_KERNELS if n not in SIGNED_INPUT])
@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_kernels_reject_non_positive_prices(name: str, bad: float) -> None:
    x = np.array([1.0, 2.0, bad, 4.0, 5.0, 6.0, 7.0])
    with pytest.raises(ValueError, match="positive"):
        ALL_KERNELS[name](x)


@pytest.mark.parametrize("name", list(ALL_KERNELS))
def test_kernels_reject_2d_input(name: str) -> None:
    with pytest.raises(ValueError, match="1-D"):
        ALL_KERNELS[name](np.ones((3, 3)))
