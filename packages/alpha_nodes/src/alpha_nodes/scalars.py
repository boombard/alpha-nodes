"""Scalar glue between numpy kernels and the optional-float fields of result models.

Kernels signal "cannot be computed" with `nan`; result models say it with `None`. These two
helpers are the only place that translation lives, shared by the calc nodes and the valuation
adapter. See documentation/design/finance.md, Calculation layers.
"""

import numpy as np

from alpha_nodes.kernels import safe_ratio


def opt(value: float) -> float | None:
    """A kernel's `nan` ("cannot be computed") as None, else a plain float."""
    return None if np.isnan(value) else float(value)


def ratio(num: float | None, den: float | None) -> float | None:
    """`num / den` via `safe_ratio`; None when an input is None or `den <= 0`."""
    if num is None or den is None:
        return None
    return opt(float(safe_ratio(np.array([num]), np.array([den]))[0]))
