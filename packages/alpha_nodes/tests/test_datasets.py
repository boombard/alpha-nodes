from datetime import timedelta

import pandas as pd
import pandera.pandas as pa
import pytest
from alpha_nodes.datasets import (
    DATASETS,
    FUNDAMENTALS,
    FX,
    NEWS,
    PRICES,
    PROFILE,
    FundamentalsSchema,
    FxSchema,
    NewsSchema,
    PriceSchema,
    ProfileSchema,
)
from alpha_nodes.statements import AnnualFundamentalsSchema
from alpha_nodes.units import MONEY, MONEY_PER_SHARE, SHARES
from lensgraph.units import COUNT, Unit, is_numeric_field, unit_of

SCHEMAS = [PriceSchema, ProfileSchema, FxSchema, FundamentalsSchema, NewsSchema]


@pytest.mark.parametrize("schema", [*SCHEMAS, AnnualFundamentalsSchema])
def test_every_numeric_dataset_column_has_a_unit(schema: type[pa.DataFrameModel]) -> None:
    for name in schema.to_schema().columns:
        unit = unit_of(schema, name)
        if is_numeric_field(schema, name):
            assert isinstance(unit, Unit), f"{schema.__name__}.{name}"
        else:
            assert unit is None, f"{schema.__name__}.{name}"
        assert "kind" not in (schema.to_schema().columns[name].metadata or {})


def test_prices_valid(prices_frame: pd.DataFrame) -> None:
    PriceSchema.validate(prices_frame)


def test_prices_reject_minor_unit_currency(prices_frame: pd.DataFrame) -> None:
    prices_frame["currency"] = "GBp"
    with pytest.raises(pa.errors.SchemaError):
        PriceSchema.validate(prices_frame)


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_prices_reject_non_positive_close(prices_frame: pd.DataFrame, bad: float) -> None:
    prices_frame.loc[0, "close"] = bad
    with pytest.raises(pa.errors.SchemaError):
        PriceSchema.validate(prices_frame)


def test_profile_allows_missing_optionals(profile_frame: pd.DataFrame) -> None:
    ProfileSchema.validate(profile_frame)


def test_profile_rejects_minor_unit_currency(profile_frame: pd.DataFrame) -> None:
    profile_frame["trading_currency"] = "GBp"
    with pytest.raises(pa.errors.SchemaError):
        ProfileSchema.validate(profile_frame)


def test_fx_valid_and_rejects_non_positive(fx_frame: pd.DataFrame) -> None:
    FxSchema.validate(fx_frame)
    fx_frame["usd_per_unit"] = 0.0
    with pytest.raises(pa.errors.SchemaError):
        FxSchema.validate(fx_frame)


def test_datasets_registry_names_match() -> None:
    assert set(DATASETS) == {"prices", "profile", "fx", "fundamentals", "news"}
    for name, ds in DATASETS.items():
        assert ds.name == name
    assert DATASETS["prices"] is PRICES and DATASETS["profile"] is PROFILE
    assert DATASETS["fx"] is FX


def test_dataset_shapes() -> None:
    day, week = timedelta(days=1), timedelta(days=7)
    for ds in (PRICES, FX):
        assert (ds.axis, ds.axis_column, ds.key_columns) == ("date", "date", ("date",))
        assert (ds.ttl, ds.empty_ttl) == (day, week)
    assert (PROFILE.axis, PROFILE.key_columns) == ("none", ())
    assert (PROFILE.ttl, PROFILE.empty_ttl) == (timedelta(days=90), week)


def test_datasets_registry_has_fundamentals_and_news() -> None:
    assert DATASETS["fundamentals"] is FUNDAMENTALS and DATASETS["news"] is NEWS
    assert (FUNDAMENTALS.axis, FUNDAMENTALS.key_columns) == ("none", ("period_type", "period_end", "filed_at"))
    assert (FUNDAMENTALS.ttl, FUNDAMENTALS.empty_ttl) == (timedelta(days=7), timedelta(days=7))
    assert (NEWS.axis, NEWS.key_columns) == ("none", ("id",))
    assert (NEWS.ttl, NEWS.empty_ttl) == (timedelta(days=1), timedelta(days=7))


def test_fundamentals_money_and_shares_units() -> None:
    assert unit_of(FundamentalsSchema, "capex") == MONEY
    assert unit_of(FundamentalsSchema, "shares_diluted") == SHARES
    assert unit_of(PriceSchema, "close") == MONEY_PER_SHARE
    assert unit_of(PriceSchema, "volume") == COUNT


def test_fundamentals_schema_accepts_canonical_frame(fundamentals_frame: pd.DataFrame) -> None:
    assert list(fundamentals_frame["filed_at"].isna()) == [True, False]
    FundamentalsSchema.validate(fundamentals_frame)


def test_fundamentals_rejects_negative_capex(fundamentals_frame: pd.DataFrame) -> None:
    fundamentals_frame.loc[0, "capex"] = -1.0
    with pytest.raises(pa.errors.SchemaError):
        FundamentalsSchema.validate(fundamentals_frame)


def test_fundamentals_rejects_minor_unit_currency(fundamentals_frame: pd.DataFrame) -> None:
    fundamentals_frame["currency"] = "GBp"
    with pytest.raises(pa.errors.SchemaError):
        FundamentalsSchema.validate(fundamentals_frame)


def test_fundamentals_rejects_non_positive_shares(fundamentals_frame: pd.DataFrame) -> None:
    fundamentals_frame.loc[0, "shares_diluted"] = 0.0
    with pytest.raises(pa.errors.SchemaError):
        FundamentalsSchema.validate(fundamentals_frame)


def test_fundamentals_rejects_unknown_period_type(fundamentals_frame: pd.DataFrame) -> None:
    fundamentals_frame["period_type"] = "quarterly"
    with pytest.raises(pa.errors.SchemaError):
        FundamentalsSchema.validate(fundamentals_frame)


def test_news_schema_accepts_canonical_frame(news_frame: pd.DataFrame) -> None:
    NewsSchema.validate(news_frame)


def test_news_schema_requires_tz_aware_published_at(news_frame: pd.DataFrame) -> None:
    news_frame["published_at"] = news_frame["published_at"].dt.tz_localize(None)
    with pytest.raises(pa.errors.SchemaError):
        NewsSchema.validate(news_frame)
