import inspect

import pytest
from alpha_nodes import metrics
from alpha_nodes.datasets import DATASETS
from alpha_nodes.lenses.price_behaviour import PriceBehaviour
from alpha_nodes.lenses.price_vs_fundamentals import PriceVsFundamentals
from alpha_nodes.lenses.quality_value import QualityValue
from alpha_nodes.metrics import ValuationResult
from alpha_nodes.statements import AnnualFundamentalsSchema
from alpha_nodes.units import (
    MONEY,
    MONEY_PER_SHARE,
    TRADING_MONEY_PER_SHARE,
    is_major_iso,
    to_major,
)
from lensgraph.units import PERCENTAGE_POINTS, format_value, is_numeric_field, unit_of
from pydantic import BaseModel

from .ai_lens_helpers import lens_input_contracts

DATASET_SCHEMAS = [d.frame_schema for d in DATASETS.values()] + [AnnualFundamentalsSchema]


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("GBp", ("GBP", 100)),
        ("GBX", ("GBP", 100)),
        ("ZAc", ("ZAR", 100)),
        ("ILA", ("ILS", 100)),
        ("EUR", ("EUR", 1)),
    ],
)
def test_to_major_minor_units(code: str, expected: tuple[str, int]) -> None:
    assert to_major(code) == expected


@pytest.mark.parametrize("junk", ["", "gbp", "EURO", "E1R", "US"])
def test_to_major_rejects_junk(junk: str) -> None:
    with pytest.raises(ValueError):
        to_major(junk)


@pytest.mark.parametrize(
    ("code", "ok"),
    [
        ("GBP", True),
        ("EUR", True),
        ("GBp", False),
        ("GBX", False),
        ("ILA", False),
        ("gbp", False),
        ("EU", False),
        ("", False),
    ],
)
def test_is_major_iso(code: str, ok: bool) -> None:
    assert is_major_iso(code) is ok


def _result_models() -> list[type[BaseModel]]:
    return [
        m for _, m in inspect.getmembers(metrics, inspect.isclass)
        if issubclass(m, BaseModel) and m.__module__ == metrics.__name__
    ]


def test_every_numeric_result_field_has_a_unit() -> None:
    missing = [
        f"{m.__name__}.{f}"
        for m in _result_models()
        for f in m.model_fields
        if is_numeric_field(m, f) and unit_of(m, f) is None
    ]
    assert missing == []


def test_money_fields_prefix_an_existing_currency_field() -> None:
    checked = 0
    models: list[type] = [*_result_models(), *DATASET_SCHEMAS]
    for m in models:
        fields = set(m.model_fields) if issubclass(m, BaseModel) else set(m.to_schema().columns)  # type: ignore[attr-defined]
        for f in fields:
            unit = unit_of(m, f)
            if unit is not None and unit.prefix_field is not None:
                checked += 1
                assert unit.prefix_field in fields, f"{m.__name__}.{f} -> {unit.prefix_field}"
    assert checked > 20


def test_trading_and_reporting_currency_are_not_mixed() -> None:
    assert unit_of(ValuationResult, "close").prefix_field == "trading_currency"  # type: ignore[union-attr]
    for f in ("market_cap", "value_low", "value_high"):
        assert unit_of(ValuationResult, f).prefix_field == "currency"  # type: ignore[union-attr]


@pytest.mark.parametrize("lens_cls", [QualityValue, PriceVsFundamentals])
def test_ai_lens_plans_build_with_units(lens_cls) -> None:
    assert lens_cls.require_units is True
    lens = lens_cls()
    lens.bind_upstream(lens_input_contracts(lens_cls))  # raises UnitError for any unitless numeric field
    assert lens._units["valuation.market_cap" if lens_cls is QualityValue else "momentum.total_return"]


def test_price_behaviour_plan_builds_with_units() -> None:
    lens = PriceBehaviour()
    assert lens.require_units is True
    lens.bind_upstream(lens_input_contracts(lens))


def test_money_renders_with_its_currency() -> None:
    assert format_value(12.3e9, MONEY, {"currency": "USD"}) == "USD 12.3bn"


def test_per_share_money_shows_two_decimals() -> None:
    assert format_value(189.2, MONEY_PER_SHARE, {"currency": "GBP"}) == "GBP 189.20"
    assert format_value(189.2, TRADING_MONEY_PER_SHARE, {"trading_currency": "GBP"}) == "GBP 189.20"


def test_margin_change_is_in_percentage_points() -> None:
    unit = unit_of(metrics.FundamentalTrendResult, "op_margin_change_1y")
    assert unit == PERCENTAGE_POINTS
    assert unit is not None
    assert format_value(0.02, unit, signed=True) == "+2 pp"
