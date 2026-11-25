"""Result models of the price-behaviour calc nodes.

See documentation/design/finance.md, Calculation layers and price_behaviour.
"""

from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PriceWindow(BaseModel):
    """The bars a price metric was computed from; base of every price metric result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bars: int = Field(ge=0)  # bars actually used
    start: date | None  # first bar date of the window; None when bars == 0
    end: date | None  # last bar date of the window; None when bars == 0
    suspect_bars: int = Field(ge=0)  # bars in the window labelled `suspect`

    @model_validator(mode="after")
    def _check_suspect(self) -> Self:
        """Suspect bars are a subset of the window's bars."""
        if self.suspect_bars > self.bars:
            raise ValueError("suspect_bars must not exceed bars")
        return self


class MomentumResult(PriceWindow):
    """12-1 momentum."""

    total_return: float | None  # None if history is too short


class TrendResult(PriceWindow):
    """Position of the close relative to its moving average."""

    close: float | None
    ma: float | None
    pct_above_ma: float | None
    ma_slope: float | None


class VolatilityResult(PriceWindow):
    """Annualised realised volatility."""

    annualised: float | None


class DrawdownResult(PriceWindow):
    """Maximum peak-to-trough drawdown within the window."""

    max_drawdown: float | None
    peak_date: date | None
    trough_date: date | None
