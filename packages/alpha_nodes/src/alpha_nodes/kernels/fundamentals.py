"""Fundamentals kernels: ratios, growth, CAGR, dispersion, owner earnings, invested capital, incremental return, capitalised value.

Pure numpy on 1-D float64 arrays and plain floats; non-finite input raises `ValueError`
and scalars that cannot be computed return `nan`. Pandas adapters and calc nodes build on
these; see documentation/design/finance.md, Calculation layers and Fundamentals: pinned
conventions.
"""

import math

import numpy as np

from alpha_nodes.kernels._validate import as_series, check_same_length


def _pair(num: np.ndarray, den: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Validate two equal-length finite arrays."""
    num = as_series(num, "num")
    den = as_series(den, "den")
    check_same_length(num, den, "den")
    return num, den


def safe_ratio(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    """Elementwise `num / den`; `nan` where `den <= 0`. Equal lengths required."""
    num, den = _pair(num, den)
    out = np.full(num.shape, np.nan)
    ok = den > 0
    out[ok] = num[ok] / den[ok]
    return out


def growth(prev: float, cur: float) -> float:
    """Relative change `(cur - prev) / |prev|`; `nan` when `prev == 0`.

    The absolute base keeps the sign meaningful when growing out of a loss.
    """
    if prev == 0:
        return float("nan")
    return float((cur - prev) / abs(prev))


def cagr(first: float, last: float, years: float) -> float:
    """Compound annual growth `(last / first) ** (1 / years) - 1`.

    `nan` unless `first > 0`, `last > 0` and `years > 0`.
    """
    if first <= 0 or last <= 0 or years <= 0:
        return float("nan")
    return float((last / first) ** (1.0 / years) - 1.0)


def mean_std(x: np.ndarray, min_n: int = 3) -> tuple[float, float]:
    """Sample mean and standard deviation (ddof=1).

    The mean is `nan` if `x` is empty; the std is `nan` if `len(x) < min_n` (or < 2).
    """
    x = as_series(x, "x")
    if x.size == 0:
        return float("nan"), float("nan")
    mean = float(x.mean())
    if x.size < max(min_n, 2):
        return mean, float("nan")
    return mean, float(x.std(ddof=1))


def coefficient_of_variation(x: np.ndarray, min_n: int = 3) -> float:
    """`std / mean` (ddof=1); `nan` when `mean <= 0` or `len(x) < min_n`."""
    mean, std = mean_std(x, min_n)
    if math.isnan(mean) or math.isnan(std) or mean <= 0:
        return float("nan")
    return std / mean


def owner_earnings(net_income: np.ndarray, dep_amort: np.ndarray, capex: np.ndarray) -> np.ndarray:
    """Owner earnings `net_income + dep_amort - minimum(capex, dep_amort)`.

    Maintenance capex is approximated by D&A, capped at actual capex. Equal lengths.
    """
    net_income, dep_amort = _pair(net_income, dep_amort)
    capex = as_series(capex, "capex")
    check_same_length(net_income, capex, "capex")
    return net_income + dep_amort - np.minimum(capex, dep_amort)


def sum_ratio(num: np.ndarray, den: np.ndarray) -> float:
    """`sum(num) / sum(den)`; `nan` when empty or `sum(den) <= 0`. Equal lengths."""
    num, den = _pair(num, den)
    if num.size == 0:
        return float("nan")
    total = float(den.sum())
    if total <= 0:
        return float("nan")
    return float(num.sum()) / total


def capitalised_value(earnings: float, rate: float) -> float:
    """Capitalised value `earnings / rate`; `nan` when `earnings <= 0`.

    Raises `ValueError` when `rate <= 0`.
    """
    if rate <= 0:
        raise ValueError(f"rate must be > 0, got {rate}")
    if earnings <= 0:
        return float("nan")
    return float(earnings / rate)


def invested_capital(
    total_debt: np.ndarray, total_equity: np.ndarray, cash: np.ndarray
) -> np.ndarray:
    """Invested capital per period, `total_debt + total_equity - cash`. Equal lengths.

    May be zero or negative; callers (`safe_ratio`) treat those periods as having no return.
    """
    total_debt, total_equity = _pair(total_debt, total_equity)
    cash = as_series(cash, "cash")
    check_same_length(total_debt, cash, "cash")
    return total_debt + total_equity - cash


def incremental_return(
    op_income_start: float, op_income_end: float, capital_start: float, capital_end: float
) -> float:
    """Return on new capital `(op_end - op_start) / (cap_end - cap_start)`.

    `nan` when the capital did not grow (change <= 0). Raises `ValueError` on non-finite input.
    """
    args = (op_income_start, op_income_end, capital_start, capital_end)
    if not all(math.isfinite(a) for a in args):
        raise ValueError(f"inputs must be finite, got {args}")
    change = capital_end - capital_start
    if change <= 0:
        return float("nan")
    return float((op_income_end - op_income_start) / change)
