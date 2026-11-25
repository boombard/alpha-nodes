"""Shared input checks for the numpy kernels.

Every kernel validates through these helpers so errors are uniform: `ValueError` naming
the offending argument. Gaps (NaN/inf) are rejected here and handled in the frame
adapters, never inside a kernel; see documentation/design/finance.md, Calculation layers.
"""

import numpy as np


def as_series(x: np.ndarray, name: str = "x", *, positive: bool = False) -> np.ndarray:
    """Return `x` as a 1-D float64 array, raising `ValueError` if it is not finite.

    With `positive=True` every value must also be > 0 (prices).
    """
    arr = np.asarray(x, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D, got {arr.ndim}-D")
    if not np.isfinite(arr).all():
        raise ValueError(f"{name} must be finite (no NaN or inf)")
    if positive and (arr <= 0).any():
        raise ValueError(f"{name} must be positive")
    return arr


def check_window(window: int, name: str = "window", *, minimum: int = 1) -> int:
    """Require an integer `window >= minimum`."""
    if int(window) != window or window < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}, got {window}")
    return int(window)


def check_same_length(a: np.ndarray, b: np.ndarray, name: str) -> None:
    """Require `a` and `b` to have equal length; `name` is the argument reported."""
    if a.shape != b.shape:
        raise ValueError(f"{name} must have the same length as the prices ({a.size}), got {b.size}")
