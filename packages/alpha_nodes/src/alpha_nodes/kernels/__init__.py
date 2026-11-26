"""Atomic numpy kernels for finance calculations (bottom calculation layer).

Pure functions on 1-D float64 arrays: no pandas, dates or nodes. Frame adapters and calc
nodes build on them; see documentation/design/finance.md, Calculation layers.
"""

from alpha_nodes.kernels.fundamentals import (
    cagr,
    capitalised_value,
    coefficient_of_variation,
    growth,
    incremental_return,
    invested_capital,
    mean_std,
    owner_earnings,
    safe_ratio,
    sum_ratio,
)
from alpha_nodes.kernels.returns import log_returns, simple_returns, skip_return, total_return_index
from alpha_nodes.kernels.risk import drawdown, drawdown_extent, max_drawdown, realised_volatility
from alpha_nodes.kernels.rolling import linreg_slope, rolling_std, sma

__all__ = [
    "cagr",
    "capitalised_value",
    "coefficient_of_variation",
    "drawdown",
    "drawdown_extent",
    "growth",
    "incremental_return",
    "invested_capital",
    "linreg_slope",
    "log_returns",
    "max_drawdown",
    "mean_std",
    "owner_earnings",
    "realised_volatility",
    "rolling_std",
    "safe_ratio",
    "simple_returns",
    "skip_return",
    "sma",
    "sum_ratio",
    "total_return_index",
]
