"""Atomic numpy kernels for finance calculations (bottom calculation layer).

Pure functions on 1-D float64 arrays: no pandas, dates or nodes. Frame adapters and calc
nodes build on them; see documentation/design/finance.md, Calculation layers.
"""

from alpha_nodes.kernels.returns import log_returns, simple_returns, skip_return, total_return_index
from alpha_nodes.kernels.risk import drawdown, drawdown_extent, max_drawdown, realised_volatility
from alpha_nodes.kernels.rolling import linreg_slope, rolling_std, sma

__all__ = [
    "drawdown",
    "drawdown_extent",
    "linreg_slope",
    "log_returns",
    "max_drawdown",
    "realised_volatility",
    "rolling_std",
    "simple_returns",
    "skip_return",
    "sma",
    "total_return_index",
]
