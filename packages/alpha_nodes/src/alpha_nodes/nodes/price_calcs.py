"""Price calc nodes behind the `price_behaviour` lens (top calculation layer).

Each node exposes its windows as params, calls frame adapters from `alpha_nodes.series` and
kernels from `alpha_nodes.kernels`, and returns a result model. They hold no maths of their
own, and declare what they call in `code_deps`. Conventions are pinned in
documentation/design/finance.md (Pinned conventions); the bar counts are in
`alpha_nodes.conventions`.

None of these nodes is memoized (`memoize = False`). They cost milliseconds and their outputs
are stored for lineage anyway, so caching saves almost nothing. It would risk stale results
from things outside the memo key (module constants such as `BARS_PER_YEAR`, library upgrades),
which would persist indefinitely in fixed as-of runs.
"""

from typing import ClassVar

import numpy as np
import pandas as pd
from lensgraph.charts import LineChart
from lensgraph.node import CalcNode, NodeContext, TransformNode

from alpha_nodes.conventions import BARS_PER_MONTH, BARS_PER_YEAR
from alpha_nodes.kernels import (
    drawdown_extent,
    linreg_slope,
    log_returns,
    max_drawdown,
    realised_volatility,
    skip_return,
    sma,
    total_return_index,
)
from alpha_nodes.metrics import (
    DrawdownResult,
    MomentumResult,
    TrendResult,
    VolatilityResult,
)
from alpha_nodes.series import TotalReturnSchema, total_return, trailing, window_info

_WINDOW_DEPS = (trailing, window_info)


def _opt(value: float) -> float | None:
    """A kernel's `nan` ("not enough history") as None; the field is then skipped by the lens."""
    return None if np.isnan(value) else float(value)


class TotalReturn(TransformNode):
    """Adds the total-return index to the `prices` frame (dividends reinvested on the ex-date)."""

    name: ClassVar[str] = "total_return"
    memoize: ClassVar[bool] = False  # see module docstring
    inputs: ClassVar[dict[str, str]] = {"prices": "prices"}
    output: ClassVar = TotalReturnSchema
    code_deps: ClassVar = (total_return, total_return_index)

    def run(self, ctx: NodeContext, prices: pd.DataFrame) -> pd.DataFrame:
        """Return the `TotalReturnSchema` frame for `prices`."""
        return total_return(prices)


class Momentum(CalcNode):
    """12-1 momentum: total return from `lookback` bars ago to `skip` bars ago.

    Attributes:
        lookback: bars back to the start of the return (252 = 12 months).
        skip: recent bars skipped (21 = 1 month).
    """

    name: ClassVar[str] = "momentum"
    memoize: ClassVar[bool] = False  # see module docstring
    inputs: ClassVar[dict[str, str]] = {"tr": "total_return"}
    output: ClassVar = MomentumResult
    code_deps: ClassVar = (skip_return, _opt, *_WINDOW_DEPS)
    lookback: int = BARS_PER_YEAR
    skip: int = BARS_PER_MONTH

    def run(self, ctx: NodeContext, tr: pd.DataFrame) -> MomentumResult:
        """Compute the skip-return of the TR index over the last `lookback + 1` bars."""
        window = trailing(tr, self.lookback + 1)
        value = (
            skip_return(window["tr_index"].to_numpy(), self.lookback, self.skip)
            if len(window) > self.lookback
            else float("nan")
        )
        return MomentumResult(**window_info(window).model_dump(), total_return=_opt(value))


class Trend(CalcNode):
    """Close vs its simple moving average, and the annualised log slope of that average.

    Attributes:
        ma_window: bars in the moving average.
        slope_window: bars over which the MA's log slope is fitted.
    """

    name: ClassVar[str] = "trend"
    memoize: ClassVar[bool] = False  # see module docstring
    inputs: ClassVar[dict[str, str]] = {"tr": "total_return"}
    output: ClassVar = TrendResult
    code_deps: ClassVar = (sma, linreg_slope, _opt, *_WINDOW_DEPS)
    ma_window: int = 200
    slope_window: int = 20

    def run(self, ctx: NodeContext, tr: pd.DataFrame) -> TrendResult:
        """Compute the trend fields over the last `ma_window + slope_window - 1` bars."""
        needed = self.ma_window + self.slope_window - 1
        window = trailing(tr, needed)
        info = window_info(window).model_dump()
        if len(window) < needed:
            return TrendResult(**info, close=None, ma=None, pct_above_ma=None, ma_slope=None)
        close = window["close"].to_numpy()
        ma = sma(close, self.ma_window)
        log_ma = np.log(ma[self.ma_window - 1 :])  # drop the warm-up NaNs
        slope = linreg_slope(log_ma, self.slope_window)[-1] * BARS_PER_YEAR
        return TrendResult(
            **info,
            close=float(close[-1]),
            ma=float(ma[-1]),
            pct_above_ma=float(close[-1] / ma[-1] - 1.0),
            ma_slope=_opt(slope),
        )


class Volatility(CalcNode):
    """Annualised realised volatility of daily log total returns.

    Attributes:
        window: returns in the window.
        min_returns: fewer returns than this gives None.
    """

    name: ClassVar[str] = "volatility"
    memoize: ClassVar[bool] = False  # see module docstring
    inputs: ClassVar[dict[str, str]] = {"tr": "total_return"}
    output: ClassVar = VolatilityResult
    code_deps: ClassVar = (log_returns, realised_volatility, _opt, *_WINDOW_DEPS)
    window: int = BARS_PER_YEAR
    min_returns: int = 63

    def run(self, ctx: NodeContext, tr: pd.DataFrame) -> VolatilityResult:
        """Compute volatility over the last `window` returns (`window + 1` bars)."""
        bars = trailing(tr, self.window + 1)
        value = float("nan")
        if len(bars) - 1 >= self.min_returns:
            returns = log_returns(bars["tr_index"].to_numpy())
            value = realised_volatility(returns, BARS_PER_YEAR)
        return VolatilityResult(**window_info(bars).model_dump(), annualised=_opt(value))


class Drawdown(CalcNode):
    """Maximum peak-to-trough fall of the total-return index, with the peak and trough dates.

    Attributes:
        window: most bars used.
        min_bars: fewer bars than this gives None.
    """

    name: ClassVar[str] = "drawdown"
    memoize: ClassVar[bool] = False  # see module docstring
    inputs: ClassVar[dict[str, str]] = {"tr": "total_return"}
    output: ClassVar = DrawdownResult
    code_deps: ClassVar = (max_drawdown, drawdown_extent, _opt, *_WINDOW_DEPS)
    window: int = 3 * BARS_PER_YEAR
    min_bars: int = BARS_PER_YEAR

    def run(self, ctx: NodeContext, tr: pd.DataFrame) -> DrawdownResult:
        """Compute the drawdown over the last `window` bars."""
        bars = trailing(tr, self.window)
        info = window_info(bars).model_dump()
        if len(bars) < max(self.min_bars, 1):
            return DrawdownResult(**info, max_drawdown=None, peak_date=None, trough_date=None)
        index = bars["tr_index"].to_numpy()
        worst = _opt(max_drawdown(index))
        if not worst:  # None or 0.0: the series never fell, so there is no peak-to-trough
            return DrawdownResult(**info, max_drawdown=worst, peak_date=None, trough_date=None)
        peak, trough = drawdown_extent(index)
        return DrawdownResult(
            **info,
            max_drawdown=worst,
            peak_date=bars["date"].iloc[peak].date(),
            trough_date=bars["date"].iloc[trough].date(),
        )


class PriceChart(CalcNode):
    """Weekly close and moving average for the dossier chart (last session of each week).

    Attributes:
        weeks: most weekly points shown.
        ma_window: bars in the moving average, computed on the daily closes.
    """

    name: ClassVar[str] = "price_chart"
    memoize: ClassVar[bool] = False  # see module docstring
    inputs: ClassVar[dict[str, str]] = {"tr": "total_return"}
    output: ClassVar = LineChart
    code_deps: ClassVar = (sma, _opt)
    weeks: int = 156
    ma_window: int = 200

    def run(self, ctx: NodeContext, tr: pd.DataFrame) -> LineChart:
        """Sample the daily close and its MA at the last session of each W-FRI week."""
        if ctx.candidate is None:
            raise ValueError("price_chart needs a candidate")
        ma = sma(tr["close"].to_numpy(), self.ma_window) if len(tr) else np.array([])
        daily = tr.assign(ma=ma)
        week = daily["date"].dt.to_period("W-FRI")
        weekly = daily.groupby(week, sort=True).tail(1).tail(self.weeks)
        return LineChart(
            title=f"{ctx.candidate.id}: close vs {self.ma_window}-day average",
            x=[d.date() for d in weekly["date"]],
            series={
                "close": [float(v) for v in weekly["close"]],
                f"ma{self.ma_window}": [_opt(v) for v in weekly["ma"]],
            },
        )
