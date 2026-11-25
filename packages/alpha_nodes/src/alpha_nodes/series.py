"""Frame adapters: the middle calculation layer between numpy kernels and calc nodes.

Thin pandas glue. They turn the `prices` fetch frame into a total-return frame, choose
trailing windows in bars and describe a window. All maths lives in `alpha_nodes.kernels`.
See documentation/design/finance.md, Calculation layers and Pinned conventions.
"""

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
        }
    )


def trailing(frame: pd.DataFrame, bars: int) -> pd.DataFrame:
    """The last `bars` rows of `frame` (all of them if it has fewer)."""
    return frame.iloc[max(len(frame) - bars, 0) :]


def window_info(frame: pd.DataFrame) -> PriceWindow:
    """Describe `frame` as a price window: bar count, first and last date, suspect bar count."""
    empty = frame.empty
    return PriceWindow(
        bars=len(frame),
        start=None if empty else frame["date"].iloc[0].date(),
        end=None if empty else frame["date"].iloc[-1].date(),
        suspect_bars=int(frame["suspect"].to_numpy().sum()),
    )
