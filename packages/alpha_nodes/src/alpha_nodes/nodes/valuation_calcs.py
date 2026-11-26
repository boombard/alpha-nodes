"""Valuation calc nodes behind the AI lenses (top calculation layer).

`Valuation` values the company on the run's reference day; `ValuationChange` compares that with
the same valuation one year of bars earlier. Both read the raw `prices`, `fundamentals` and `fx`
frames and call the adapter `alpha_nodes.valuation`, so each side sees only the filings known on its
own day (not later restatements, which `annual_fundamentals` would already include). They hold no
maths of their own and declare what they call in `code_deps`; like the other finance calc nodes
they are not memoized (`memoize = False`; see `alpha_nodes.nodes.price_calcs`). Conventions are
pinned in documentation/design/finance.md (Fundamentals: pinned conventions).
"""

from typing import ClassVar, Self

import pandas as pd
from lensgraph.node import CalcNode, NodeContext
from pydantic import model_validator

from alpha_nodes.conventions import BARS_PER_YEAR
from alpha_nodes.kernels import capitalised_value, owner_earnings, safe_ratio
from alpha_nodes.metrics import PeriodWindow, ValuationChangeResult, ValuationResult
from alpha_nodes.money import fx_factor
from alpha_nodes.reference import reference_day
from alpha_nodes.series import bars_back, close_on
from alpha_nodes.statements import annual_periods, latest_complete, period_window
from alpha_nodes.valuation import _opt, _ratio, valuation_on

_VALUATION_DEPS = (valuation_on, close_on, annual_periods, latest_complete, period_window, fx_factor)
_KERNEL_DEPS = (capitalised_value, owner_earnings, safe_ratio, _opt, _ratio)


class Valuation(CalcNode):
    """Market cap (fx-converted), earnings and owner-earnings yields, P/E and the intrinsic-value band.

    Attributes:
        hurdle_low: yield at the optimistic end of the band (gives `value_high`).
        hurdle_high: yield at the pessimistic end (gives `value_low`); must exceed `hurdle_low`.
    """

    name: ClassVar[str] = "valuation"
    memoize: ClassVar[bool] = False  # see module docstring
    inputs: ClassVar[dict[str, str]] = {"prices": "prices", "fundamentals": "fundamentals", "fx": "fx"}
    output: ClassVar = ValuationResult
    code_deps: ClassVar = (reference_day, *_VALUATION_DEPS, *_KERNEL_DEPS)
    hurdle_low: float = 0.08
    hurdle_high: float = 0.12

    @model_validator(mode="after")
    def _check_hurdles(self) -> Self:
        """`0 < hurdle_low < hurdle_high`."""
        if not 0 < self.hurdle_low < self.hurdle_high:
            raise ValueError("hurdles must satisfy 0 < hurdle_low < hurdle_high")
        return self

    def run(
        self, ctx: NodeContext, prices: pd.DataFrame, fundamentals: pd.DataFrame, fx: pd.DataFrame
    ) -> ValuationResult:
        """Value the company on `reference_day(ctx)`."""
        return valuation_on(
            prices, fundamentals, fx, reference_day(ctx), self.hurdle_low, self.hurdle_high
        )


class ValuationChange(CalcNode):
    """How P/E and earnings yield moved between `lookback_bars` sessions ago and now.

    `now` is the reference day; `then` is the bar `lookback_bars` before the last bar on or
    before it. Each side uses the periods known on its own day. With too little price history
    the `then` fields and `pe_change` are None. The reported window is the "now" side's.

    Attributes:
        lookback_bars: sessions between the two dates (252 = one year).
    """

    name: ClassVar[str] = "valuation_change"
    memoize: ClassVar[bool] = False  # see module docstring
    inputs: ClassVar[dict[str, str]] = {"prices": "prices", "fundamentals": "fundamentals", "fx": "fx"}
    output: ClassVar = ValuationChangeResult
    code_deps: ClassVar = (reference_day, bars_back, *_VALUATION_DEPS, *_KERNEL_DEPS)
    lookback_bars: int = BARS_PER_YEAR

    def run(
        self, ctx: NodeContext, prices: pd.DataFrame, fundamentals: pd.DataFrame, fx: pd.DataFrame
    ) -> ValuationChangeResult:
        """Value the company now and `lookback_bars` earlier and report the change in P/E."""
        today = reference_day(ctx)
        now = valuation_on(prices, fundamentals, fx, today)
        then_day = bars_back(prices, today, self.lookback_bars)
        then = None if then_day is None else valuation_on(prices, fundamentals, fx, then_day)
        pe_now, pe_then = now.pe, None if then is None else then.pe
        change = None if pe_now is None or not pe_then else pe_now / pe_then - 1  # pe_then > 0 when set
        return ValuationChangeResult(
            **now.model_dump(include=set(PeriodWindow.model_fields)),
            date_now=now.price_date,
            date_then=then_day,
            pe_now=pe_now,
            pe_then=pe_then,
            pe_change=change,
            earnings_yield_now=now.earnings_yield,
            earnings_yield_then=None if then is None else then.earnings_yield,
        )
