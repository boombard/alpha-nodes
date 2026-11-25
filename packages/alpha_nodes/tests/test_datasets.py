from datetime import timedelta
from typing import get_args

import pandas as pd
import pandera.pandas as pa
import pytest
from alpha_nodes.datasets import DATASETS, FX, PRICES, PROFILE, FxSchema, PriceSchema, ProfileSchema
from alpha_nodes.units import FieldKind

SCHEMAS = [PriceSchema, ProfileSchema, FxSchema]


@pytest.mark.parametrize("schema", SCHEMAS)
def test_every_column_declares_a_kind(schema: type[pa.DataFrameModel]) -> None:
    columns = schema.to_schema().columns
    assert columns
    for name, col in columns.items():
        assert (col.metadata or {}).get("kind") in get_args(FieldKind), name


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
    assert set(DATASETS) == {"prices", "profile", "fx"}
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
