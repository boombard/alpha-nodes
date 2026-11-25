"""Return kernels: simple, log, total-return index and the skip-month return.

Pure numpy; conventions pinned in documentation/design/finance.md (price_behaviour,
Pinned conventions).
"""

import numpy as np

from alpha_nodes.conventions import BARS_PER_MONTH, BARS_PER_YEAR
from alpha_nodes.kernels._validate import as_series, check_same_length, check_window


def simple_returns(x: np.ndarray) -> np.ndarray:
    """Simple returns `x[1:] / x[:-1] - 1` (length n-1). `x` must be positive."""
    x = as_series(x, "x", positive=True)
    return x[1:] / x[:-1] - 1.0


def log_returns(x: np.ndarray) -> np.ndarray:
    """Log returns `diff(log x)` (length n-1). `x` must be positive."""
    x = as_series(x, "x", positive=True)
    return np.diff(np.log(x))


def total_return_index(close: np.ndarray, dividends: np.ndarray) -> np.ndarray:
    """Total-return index: `TR[0] = 1`, `TR[t] = TR[t-1] * (close[t] + dividends[t]) / close[t-1]`.

    Dividends sit on their ex-date row; splits are not applied (closes are assumed already
    split-adjusted). `close` > 0, `dividends` >= 0, equal lengths. Length n.
    """
    close = as_series(close, "close", positive=True)
    dividends = as_series(dividends, "dividends")
    check_same_length(close, dividends, "dividends")
    if (dividends < 0).any():
        raise ValueError("dividends must be >= 0")
    if close.size == 0:
        return close.copy()
    factors = (close[1:] + dividends[1:]) / close[:-1]
    return np.concatenate(([1.0], np.cumprod(factors)))


def skip_return(x: np.ndarray, lookback: int = BARS_PER_YEAR, skip: int = BARS_PER_MONTH) -> float:
    """Momentum with a skipped recent window: `x[-1-skip] / x[-1-lookback] - 1`.

    `nan` if `len(x) < lookback + 1`. Requires `0 <= skip < lookback`; `x` positive.
    """
    x = as_series(x, "x", positive=True)
    lookback = check_window(lookback, "lookback")
    if skip < 0 or skip >= lookback:
        raise ValueError(f"skip must satisfy 0 <= skip < lookback, got {skip}")
    if x.size < lookback + 1:
        return float("nan")
    return float(x[-1 - skip] / x[-1 - lookback] - 1.0)
