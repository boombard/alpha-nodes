"""Frame adapters: the middle calculation layer between numpy kernels and calc nodes.

Thin pandas glue. They turn the `prices` fetch frame into a total-return frame, choose
trailing windows in bars and describe a window. All maths lives in `alpha_nodes.kernels`.
See documentation/design/finance.md, Calculation layers and Pinned conventions.
"""

from datetime import date
from typing import cast

import pandas as pd
import pandera.pandas as pa
from pandera.typing.pandas import DateTime, Series

from alpha_nodes.kernels import total_return_index
from alpha_nodes.metrics import PriceWindow


class TotalReturnSchema(pa.DataFrameModel):
    """One row per bar with ascending unique dates: closes, dividends and the total-return index.

    Output of the `total_return` node and input of every price calc node.
    """

    date: Series[DateTime]
    close: Series[float] = pa.Field(gt=0)
    dividends: Series[float] = pa.Field(ge=0)
    tr_index: Series[float] = pa.Field(gt=0)  # 1.0 on the first bar; see `total_return_index`
    suspect: Series[bool]  # the source bar was labelled `suspect`
    currency: Series[str]  # trading currency of the bars (major unit), carried into every price window


def total_return(prices: pd.DataFrame) -> pd.DataFrame:
    """Build the `TotalReturnSchema` frame from a `prices` frame.

    Sorts by date and raises `ValueError` on duplicate dates. `suspect` is
    `quality == "suspect"` (False when the frame carries no quality column).
    """
    frame = prices.sort_values("date", kind="stable").reset_index(drop=True)
    if frame["date"].duplicated().any():
        raise ValueError("prices has duplicate dates")
    quality = frame["quality"] if "quality" in frame else pd.Series("ok", index=frame.index)
    index = total_return_index(frame["close"].to_numpy(float), frame["dividends"].to_numpy(float))
    return pd.DataFrame(
        {
            "date": frame["date"],
            "close": frame["close"].astype(float),
            "dividends": frame["dividends"].astype(float),
            "tr_index": index,
            "suspect": (quality == "suspect").astype(bool),
            "currency": frame["currency"].astype(str),
        }
    )


def trailing(frame: pd.DataFrame, bars: int) -> pd.DataFrame:
    """The last `bars` rows of `frame` (all of them if it has fewer)."""
    return frame.iloc[max(len(frame) - bars, 0) :]


def window_info(frame: pd.DataFrame) -> PriceWindow:
    """Describe `frame` as a price window: bar count, first and last date, suspect bar count, trading currency."""
    empty = frame.empty
    return PriceWindow(
        bars=len(frame),
        start=None if empty else frame["date"].iloc[0].date(),
        end=None if empty else frame["date"].iloc[-1].date(),
        suspect_bars=int(frame["suspect"].to_numpy().sum()),
        currency=None if empty else str(frame["currency"].iloc[-1]),
    )


def close_on(prices: pd.DataFrame, day: date) -> tuple[date, float, str] | None:
    """The last bar on or before `day` as `(date, close, currency)`; None when there is none.

    Level-based: the price a valuation on `day` uses (finance.md, Prices and point-in-time).
    """
    rows = cast(pd.DataFrame, prices[prices["date"] <= pd.Timestamp(day)])
    if rows.empty:
        return None
    last = rows.loc[rows["date"].idxmax()]
    return cast(date, pd.Timestamp(last["date"]).date()), float(last["close"]), str(last["currency"])


def bars_back(prices: pd.DataFrame, day: date, bars: int) -> date | None:
    """The date of the bar `bars` sessions before the last bar on or before `day`.

    None when there is no bar on or before `day` or fewer than `bars` earlier bars. Counts bars,
    not calendar days (finance.md, Pinned conventions).
    """
    dates = sorted(d for d in prices["date"] if d <= pd.Timestamp(day))
    position = len(dates) - 1 - bars
    return None if position < 0 else cast(date, pd.Timestamp(dates[position]).date())
