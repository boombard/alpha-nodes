"""Tests for units.py: the one formatter and unit lookup (core.md, Units)."""

from typing import Annotated

import pandera.pandas as pa
import pytest
from lensgraph.units import (
    BARS,
    COUNT,
    FRACTION,
    FRACTION_PER_YEAR,
    MULTIPLE,
    NUMBER,
    Unit,
    format_value,
    is_numeric_field,
    unit_of,
)
from lensgraph.verdict import Provenance
from pydantic import BaseModel, ValidationError

MONEY = Unit(id="money", style="compact", prefix_field="currency")


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (0.153, FRACTION, "15.3%"),
        (0.15342, FRACTION, "15.3%"),
        (1.5, FRACTION, "150%"),
        (0.153, FRACTION_PER_YEAR, "15.3%/yr"),
        (2.0, MULTIPLE, "2×"),
        (12.3456, NUMBER, "12.3"),
        (1234.5, NUMBER, "1234"),
        (-0.0512, FRACTION, "-5.12%"),
    ],
)
def test_percent_three_sig_figs(value, unit, expected):
    assert format_value(value, unit) == expected


@pytest.mark.parametrize("value", [0.0004, -0.0004, 1e-9, 4e-12])
def test_small_nonzero_never_prints_zero(value):
    for unit in (FRACTION, NUMBER, MULTIPLE):
        text = format_value(value, unit)
        assert text is not None
        assert float(text.rstrip("%×")) != 0
    assert format_value(0.0004, FRACTION) == "0.04%"


def test_zero_prints_zero():
    assert format_value(0.0, FRACTION) == "0%"


@pytest.mark.parametrize("value", [1e-9, 1e20, 123456789.123, 5e-7])
def test_no_scientific_notation(value):
    text = format_value(value, NUMBER)
    assert text is not None
    assert "e" not in text.lower()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (950, "950"),
        (12_300, "12.3k"),
        (4_560_000, "4.56m"),
        (12_340_000_000, "12.3bn"),
        (7.89e12, "7.89tn"),
        (999_999, "1m"),
        (-2_500_000, "-2.5m"),
    ],
)
def test_compact_suffixes(value, expected):
    assert format_value(value, Unit(id="c", style="compact")) == expected


def test_integer_exact():
    assert format_value(252, COUNT) == "252"
    assert format_value(252.0, BARS) == "252 bars"
    assert format_value(1234567, COUNT) == "1234567"


def test_prefix_field_from_row():
    assert format_value(12_300_000_000, MONEY, {"currency": "USD"}) == "USD 12.3bn"
    assert format_value(12_300_000_000, MONEY, {"currency": None}) == "12.3bn"
    assert format_value(12_300_000_000, MONEY) == "12.3bn"


def test_signed():
    assert format_value(0.05, FRACTION, signed=True) == "+5%"
    assert format_value(-0.05, FRACTION, signed=True) == "-5%"
    assert format_value(0.0, FRACTION, signed=True) == "0%"


def test_none_stays_none():
    assert format_value(None, FRACTION) is None


class Metrics(BaseModel):
    roe: Annotated[float | None, FRACTION] = None
    plain: float = 0.0
    flag: bool = False


class MoreMetrics(Metrics):
    extra: Annotated[int, COUNT] = 0


def test_unit_of_pydantic_annotated():
    assert unit_of(Metrics, "roe") is FRACTION or unit_of(Metrics, "roe") == FRACTION
    assert unit_of(Metrics, "plain") is None


def test_unit_of_pandera_metadata():
    class Frame(pa.DataFrameModel):
        ret: float = pa.Field(metadata={"unit": FRACTION})
        bare: float
        n: int = pa.Field(alias="N", metadata={"unit": COUNT})

    assert unit_of(Frame, "ret") == FRACTION
    assert unit_of(Frame, "n") == COUNT
    assert unit_of(Frame, "bare") is None
    assert is_numeric_field(Frame, "bare")


def test_unit_of_walks_mro():
    assert unit_of(MoreMetrics, "roe") == FRACTION
    assert unit_of(MoreMetrics, "extra") == COUNT

    class Base(pa.DataFrameModel):
        ret: float = pa.Field(metadata={"unit": FRACTION})

    class Child(Base):
        other: float

    assert unit_of(Child, "ret") == FRACTION


def test_is_numeric_field_excludes_bool_and_text():
    assert is_numeric_field(Metrics, "roe")
    assert is_numeric_field(Metrics, "plain")
    assert not is_numeric_field(Metrics, "flag")


def test_unit_round_trips_json():
    assert Unit.model_validate_json(MONEY.model_dump_json()) == MONEY


def test_annotated_unit_field_still_validates_as_float():
    class Holder(BaseModel):
        x: Annotated[float, FRACTION]

    assert Holder(x=0.15).x == 0.15
    with pytest.raises(ValidationError):
        Holder.model_validate({"x": "abc"})
    assert Holder.model_json_schema()["properties"]["x"]["type"] == "number"


def test_unit_as_field_type_round_trips_in_provenance():
    prov = Provenance(lens_version="v", cite_units={"a.x": FRACTION})
    again = Provenance.model_validate_json(prov.model_dump_json())
    assert again.cite_units == {"a.x": FRACTION}


def test_units_for_cite_selects_by_cite_shape():
    from lensgraph.units import COUNT, FRACTION, units_for_cite

    units = {"n.a": FRACTION, "n.b": COUNT, "m.a": FRACTION}
    assert units_for_cite("n.a", units) == {"n.a": FRACTION}  # one field: exact path
    assert units_for_cite("n.zz", units) == {}
    assert units_for_cite("n", units) == {"n.a": FRACTION, "n.b": COUNT}  # whole input
    assert units_for_cite("n[i1]", units) == {"n.a": FRACTION, "n.b": COUNT}  # list item
    assert units_for_cite("other", units) == {}
