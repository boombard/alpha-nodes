"""Risk kernels: realised volatility and drawdown measures.

Pure numpy; see documentation/design/finance.md (price_behaviour, Pinned conventions).
"""

import numpy as np

from alpha_nodes.conventions import BARS_PER_YEAR
from alpha_nodes.kernels._validate import as_series, check_window


def realised_volatility(
    returns: np.ndarray, periods_per_year: int = BARS_PER_YEAR, ddof: int = 1
) -> float:
    """Annualised volatility: `std(returns, ddof) * sqrt(periods_per_year)`.

    `nan` if `len(returns) <= ddof`.
    """
    r = as_series(returns, "returns")
    periods_per_year = check_window(periods_per_year, "periods_per_year")
    if ddof < 0:
        raise ValueError(f"ddof must be >= 0, got {ddof}")
    if r.size <= ddof:
        return float("nan")
    return float(r.std(ddof=ddof) * np.sqrt(periods_per_year))


def drawdown(x: np.ndarray) -> np.ndarray:
    """Drawdown from the running peak: `x / running_max(x) - 1`, all <= 0. `x` positive."""
    x = as_series(x, "x", positive=True)
    if x.size == 0:
        return x.copy()
    return x / np.maximum.accumulate(x) - 1.0


def max_drawdown(x: np.ndarray) -> float:
    """Worst drawdown `min(drawdown(x))`; 0.0 if never below a prior peak, `nan` if empty."""
    dd = drawdown(x)
    return float(dd.min()) if dd.size else float("nan")


def drawdown_extent(x: np.ndarray) -> tuple[int, int]:
    """`(peak index, trough index)` of the maximum drawdown; earliest trough on ties.

    With no drawdown returns `(i, i)` for the last running-max index. Raises on empty `x`.
    """
    x = as_series(x, "x", positive=True)
    if x.size == 0:
        raise ValueError("x must not be empty")
    dd = x / np.maximum.accumulate(x) - 1.0
    trough = int(np.argmin(dd))  # argmin returns the first minimum
    if dd[trough] == 0.0:
        peak = int(np.flatnonzero(x == x.max())[-1])
        return peak, peak
    peak = int(np.flatnonzero(x[: trough + 1] == x[: trough + 1].max())[-1])
    return peak, trough
