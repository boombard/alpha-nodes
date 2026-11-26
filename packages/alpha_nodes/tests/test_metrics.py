from datetime import UTC, date, datetime
from typing import Any

import pytest
from alpha_nodes.metrics import (
    BalanceSheetResult,
    CashGenerationResult,
    DrawdownResult,
    FundamentalTrendResult,
    MomentumResult,
    NewsItem,
    PeriodWindow,
    PriceWindow,
    ProfitabilityResult,
    TrendResult,
    ValuationChangeResult,
    ValuationResult,
    VolatilityResult,
)
from lensgraph import citable_ids
from pydantic import ValidationError


def test_suspect_bars_cannot_exceed_bars():
    with pytest.raises(ValidationError, match="suspect_bars"):
        PriceWindow(bars=2, start=date(2024, 1, 1), end=date(2024, 1, 2), suspect_bars=3)


def test_results_are_frozen():
    result = MomentumResult(bars=0, start=None, end=None, suspect_bars=0, total_return=None)
    with pytest.raises(ValidationError):
        result.bars = 1  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(ValidationError):
        MomentumResult(bars=0, start=None, end=None, suspect_bars=0, total_return=None, junk=1)  # pyright: ignore[reportCallIssue]


def test_none_fields_allowed_for_short_history():
    empty = {"bars": 0, "start": None, "end": None, "suspect_bars": 0}
    assert TrendResult(**empty, close=None, ma=None, pct_above_ma=None, ma_slope=None).ma is None
    assert VolatilityResult(**empty, annualised=None).annualised is None
    dd = DrawdownResult(**empty, max_drawdown=None, peak_date=None, trough_date=None)
    assert dd.trough_date is None


NO_PERIODS = {"periods": 0, "first_period_end": None, "last_period_end": None, "suspect_periods": 0, "currency": None}


def test_suspect_periods_cannot_exceed_periods():
    with pytest.raises(ValidationError, match="suspect_periods"):
        PeriodWindow(
            periods=2,
            first_period_end=date(2023, 12, 31),
            last_period_end=date(2024, 12, 31),
            suspect_periods=3,
            currency="USD",
        )


def test_fundamentals_results_allow_none_fields():
    def none_of(model: type) -> object:
        return model(**NO_PERIODS, **{f: None for f in model.model_fields if f not in {*NO_PERIODS, "field_periods"}})

    for model in (
        ProfitabilityResult,
        BalanceSheetResult,
        CashGenerationResult,
        FundamentalTrendResult,
        ValuationResult,
        ValuationChangeResult,
    ):
        result = none_of(model)
        assert isinstance(result, PeriodWindow)
        with pytest.raises(ValidationError):
            result.periods = 1  # pyright: ignore[reportAttributeAccessIssue]
        with pytest.raises(ValidationError):
            model(**NO_PERIODS, junk=1)  # pyright: ignore[reportCallIssue]


def test_news_item_is_citable_by_id():
    item = NewsItem(
        id="a1", published_at=datetime(2026, 1, 5, tzinfo=UTC), headline="h", source=None, url=None, summary=None
    )
    assert "news[a1]" in citable_ids({"news": [item]})


def test_field_periods_default_empty():
    result = BalanceSheetResult(**NO_PERIODS, debt_to_equity=None, interest_cover=None, net_debt=None)
    assert result.field_periods == {}


def test_field_periods_rejects_unknown_field_and_non_older_date():
    window: dict[str, Any] = {
        "periods": 2, "first_period_end": date(2023, 12, 31), "last_period_end": date(2024, 12, 31),
        "suspect_periods": 0, "currency": "USD",
    }
    fields: dict[str, Any] = {"debt_to_equity": None, "interest_cover": None, "net_debt": None}
    ok = BalanceSheetResult(**window, **fields, field_periods={"interest_cover": date(2023, 12, 31)})
    assert ok.field_periods == {"interest_cover": date(2023, 12, 31)}
    with pytest.raises(ValidationError, match="bogus"):
        BalanceSheetResult(**window, **fields, field_periods={"bogus": date(2023, 12, 31)})
    with pytest.raises(ValidationError, match="older"):
        BalanceSheetResult(**window, **fields, field_periods={"net_debt": date(2024, 12, 31)})
