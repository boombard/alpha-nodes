"""Canonical, provider-neutral finance datasets: prices, profile and fx.

Providers map their raw payloads onto these schemas; nodes rely on nothing else.
See documentation/design/finance.md, Datasets and Prices and point-in-time.
"""

from datetime import timedelta

import pandas as pd
import pandera.pandas as pa
from lensgraph import Dataset
from pandera.typing.pandas import DateTime, Series

from alpha_nodes.units import FieldKind, is_major_iso


def _kind(kind: FieldKind) -> dict[str, str]:
    return {"kind": kind}


def _major_iso(series: Series[str]) -> Series[bool]:
    return Series[bool](series.map(is_major_iso).astype(bool))


class PriceSchema(pa.DataFrameModel):
    """Daily OHLCV for one instrument, one row per trading day, in major currency units.

    Close is as the provider gives it; there is no adjusted close (the total-return
    adjustment is our own calc). `date` is the tz-naive exchange-local trading date.
    """

    date: Series[DateTime] = pa.Field(metadata=_kind("date"))
    open: Series[float] = pa.Field(gt=0, metadata=_kind("money"))
    high: Series[float] = pa.Field(gt=0, metadata=_kind("money"))
    low: Series[float] = pa.Field(gt=0, metadata=_kind("money"))
    close: Series[float] = pa.Field(gt=0, metadata=_kind("money"))
    volume: Series[pd.Int64Dtype] = pa.Field(ge=0, nullable=True, metadata=_kind("count"))
    dividends: Series[float] = pa.Field(ge=0, metadata=_kind("per_share"))  # 0.0 when none
    split_ratio: Series[float] = pa.Field(gt=0, metadata=_kind("ratio"))  # 1.0 when none
    currency: Series[str] = pa.Field(metadata=_kind("code"))

    @pa.check("currency", name="is_major_iso")
    @classmethod
    def _currency_is_major(cls, series: Series[str]) -> Series[bool]:
        return _major_iso(series)


class ProfileSchema(pa.DataFrameModel):
    """Snapshot of one entity: identity, listing, currencies and descriptive text.

    Holds shares outstanding, not market cap; market cap is computed as price x shares.
    """

    name: Series[str] = pa.Field(metadata=_kind("text"))
    isin: Series[str] = pa.Field(nullable=True, metadata=_kind("code"))
    exchange: Series[str] = pa.Field(metadata=_kind("code"))  # MIC, e.g. "XLON"
    country: Series[str] = pa.Field(nullable=True, metadata=_kind("code"))
    trading_currency: Series[str] = pa.Field(metadata=_kind("code"))
    reporting_currency: Series[str] = pa.Field(nullable=True, metadata=_kind("code"))
    sector: Series[str] = pa.Field(nullable=True, metadata=_kind("text"))
    industry: Series[str] = pa.Field(nullable=True, metadata=_kind("text"))
    shares_outstanding: Series[float] = pa.Field(gt=0, nullable=True, metadata=_kind("shares"))
    listing_date: Series[DateTime] = pa.Field(nullable=True, metadata=_kind("date"))
    business_summary: Series[str] = pa.Field(nullable=True, metadata=_kind("text"))

    @pa.check("trading_currency", name="is_major_iso")
    @classmethod
    def _trading_is_major(cls, series: Series[str]) -> Series[bool]:
        return _major_iso(series)

    @pa.check("reporting_currency", name="is_major_iso")
    @classmethod
    def _reporting_is_major(cls, series: Series[str]) -> Series[bool]:
        return Series[bool](series.isna() | _major_iso(series.fillna("USD")))


class FxSchema(pa.DataFrameModel):
    """Daily FX rate to USD; the entity is the currency code (e.g. "GBP")."""

    date: Series[DateTime] = pa.Field(metadata=_kind("date"))
    usd_per_unit: Series[float] = pa.Field(gt=0, metadata=_kind("ratio"))


_DAY = timedelta(days=1)
_WEEK = timedelta(days=7)

PRICES = Dataset(
    name="prices",
    frame_schema=PriceSchema,
    key_columns=("date",),
    axis="date",
    axis_column="date",
    ttl=_DAY,
    empty_ttl=_WEEK,
)
PROFILE = Dataset(
    name="profile",
    frame_schema=ProfileSchema,
    key_columns=(),
    axis="none",
    ttl=timedelta(days=90),
    empty_ttl=_WEEK,
)
FX = Dataset(
    name="fx",
    frame_schema=FxSchema,
    key_columns=("date",),
    axis="date",
    axis_column="date",
    ttl=_DAY,
    empty_ttl=_WEEK,
)

DATASETS: dict[str, Dataset] = {d.name: d for d in (PRICES, PROFILE, FX)}
"""All canonical datasets by name; the finance domain registers these with the source store."""
