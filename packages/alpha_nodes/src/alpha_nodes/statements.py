"""Fundamentals frame adapters: the middle calculation layer for annual statements.

Thin pandas glue between the `fundamentals` fetch frame and the calc nodes in
`alpha_nodes.nodes.fundamental_calcs`: choose the periods known on a day, keep the latest
filing per period, and describe a window of periods. All maths lives in `alpha_nodes.kernels`.
See documentation/design/finance.md, Calculation layers and Fundamentals: pinned conventions.
"""

from datetime import date
from typing import cast

import pandas as pd
import pandera.pandas as pa
from pandera.typing.pandas import Series

from alpha_nodes.conventions import FILING_LAG_DAYS, MAX_ANNUAL_PERIODS, MAX_STALE_PERIODS
from alpha_nodes.datasets import FundamentalsSchema
from alpha_nodes.metrics import PeriodWindow
from alpha_nodes.money import require_same_currency


class AnnualFundamentalsSchema(FundamentalsSchema):
    """One row per annual period, ascending by unique `period_end`: output of `annual_fundamentals`.

    The columns of `FundamentalsSchema` plus `suspect`; input of every fundamentals calc node.
    """

    suspect: Series[bool]  # the source row was labelled `suspect`

    @pa.dataframe_check(name="period_end_unique_ascending")
    @classmethod
    def _period_end_ascending(cls, frame: pd.DataFrame) -> bool:
        """Periods are unique and in ascending order."""
        return bool(frame["period_end"].is_monotonic_increasing and frame["period_end"].is_unique)


def known_on(frame: pd.DataFrame, day: date) -> pd.DataFrame:
    """Rows known on `day`: `filed_at <= day`, or `filed_at` null and `period_end + FILING_LAG_DAYS <= day`."""
    cutoff = pd.Timestamp(day)
    filed = frame["filed_at"].notna()
    lagged = frame["period_end"] + pd.Timedelta(days=FILING_LAG_DAYS)
    mask = (filed & (frame["filed_at"] <= cutoff)) | (~filed & (lagged <= cutoff))
    return cast(pd.DataFrame, frame[mask])


def annual_periods(
    frame: pd.DataFrame, day: date, max_periods: int = MAX_ANNUAL_PERIODS
) -> pd.DataFrame:
    """The `AnnualFundamentalsSchema` frame for `frame` as known on `day`.

    Keeps annual rows known on `day`; per `period_end` the latest `filed_at` wins (a null filing
    date counts as the oldest), then the last `max_periods` periods in ascending order.
    `suspect` is `quality == "suspect"` (False without a quality column). An empty input gives an
    empty frame with the schema's columns.

    Raises:
        CurrencyMismatch: when the kept periods are in different currencies.
    """
    schema_columns = AnnualFundamentalsSchema.to_schema().columns
    columns = list(schema_columns)
    rows = known_on(frame, day)
    if "period_type" in rows:
        rows = rows[rows["period_type"] == "annual"]
    quality = rows["quality"] if "quality" in rows else pd.Series("ok", index=rows.index)
    rows = rows.assign(suspect=(quality == "suspect").astype(bool))
    rows = rows.sort_values(["period_end", "filed_at"], kind="stable", na_position="first")
    rows = rows.groupby("period_end", sort=True).tail(1).tail(max_periods)
    if len(rows):
        require_same_currency(*rows["currency"])
    out = rows.reindex(columns=columns).reset_index(drop=True)
    # an empty frame has no values to infer dtypes from: take the schema's, so the node output still validates
    if out.empty:
        out = out.astype({name: col.dtype.type for name, col in schema_columns.items()})
    return out


def period_window(annual: pd.DataFrame) -> PeriodWindow:
    """Describe `annual` as a window: period count, first and last `period_end`, suspect count, currency."""
    if annual.empty:
        return PeriodWindow(
            periods=0, first_period_end=None, last_period_end=None, suspect_periods=0, currency=None
        )
    return PeriodWindow(
        periods=len(annual),
        first_period_end=annual["period_end"].iloc[0].date(),
        last_period_end=annual["period_end"].iloc[-1].date(),
        suspect_periods=int(annual["suspect"].to_numpy().sum()),
        currency=str(annual["currency"].iloc[-1]),
    )


def values(annual: pd.DataFrame, *columns: str) -> tuple[pd.DataFrame, PeriodWindow]:
    """The rows of `annual` where every named column is non-null (the periods a metric can use), and their window."""
    used = annual.dropna(subset=list(columns))
    return used, period_window(used)


def latest_complete(
    annual: pd.DataFrame, *columns: str, max_stale: int = MAX_STALE_PERIODS
) -> pd.DataFrame:
    """The newest single row of `annual` among the last `max_stale + 1` periods where every named column is non-null.

    Backs the older-period fallback of latest-point fundamentals fields (finance.md, Fundamentals
    pinned conventions); the whole field is computed from this one row, so periods never mix.
    Empty when no row qualifies.
    """
    recent = annual.tail(max_stale + 1)
    complete = recent.dropna(subset=list(columns))
    return complete.tail(1)


def years_between(start: pd.Timestamp, end: pd.Timestamp) -> float:
    """Years from `start` to `end` as `days / 365.25`: the span used for CAGRs and the "1y" step check."""
    return (end - start).days / 365.25
