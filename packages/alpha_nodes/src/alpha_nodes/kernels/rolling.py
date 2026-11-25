"""Rolling-statistic kernels (SMA, standard deviation, regression slope).

Each returns an array of the input's length with a leading-NaN warm-up (TA-Lib's lookback
convention); input shorter than the window gives all NaN. See
documentation/design/finance.md, Calculation layers.
"""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from alpha_nodes.kernels._validate import as_series, check_window


def _windows(x: np.ndarray, window: int) -> np.ndarray | None:
    """Trailing windows as a (n-window+1, window) view, or None if `x` is too short."""
    if x.size < window:
        return None
    return sliding_window_view(x, window)


def _pad(values: np.ndarray, n: int) -> np.ndarray:
    """Left-pad `values` with NaN to length `n`."""
    out = np.full(n, np.nan)
    if values.size:
        out[n - values.size :] = values
    return out


def sma(x: np.ndarray, window: int) -> np.ndarray:
    """Simple moving average: mean of the trailing `window` values. First `window-1` are NaN."""
    x = as_series(x)
    window = check_window(window)
    w = _windows(x, window)
    return _pad(np.array([]) if w is None else w.mean(axis=1), x.size)


def rolling_std(x: np.ndarray, window: int, ddof: int = 1) -> np.ndarray:
    """Rolling standard deviation over the trailing `window` values with `ddof`.

    Requires `window > ddof`. `ddof=0` is the population std (TA-Lib `STDDEV`).
    """
    x = as_series(x)
    window = check_window(window)
    if ddof < 0 or window <= ddof:
        raise ValueError(f"window must be greater than ddof ({ddof}), got {window}")
    w = _windows(x, window)
    return _pad(np.array([]) if w is None else w.std(axis=1, ddof=ddof), x.size)


def linreg_slope(x: np.ndarray, window: int) -> np.ndarray:
    """OLS slope of each trailing window regressed on `0..window-1` (units of x per bar).

    Requires `window >= 2`. Matches TA-Lib `LINEARREG_SLOPE`.
    """
    x = as_series(x)
    window = check_window(window, minimum=2)
    w = _windows(x, window)
    if w is None:
        return _pad(np.array([]), x.size)
    t = np.arange(window, dtype=np.float64)
    t -= t.mean()
    slopes = (w - w.mean(axis=1, keepdims=True)) @ t / (t @ t)
    return _pad(slopes, x.size)
