"""Tests for the valuation adapter (`alpha_nodes.valuation`); values are hand-computed."""

from collections.abc import Callable
from datetime import date

import pandas as pd
import pytest
from alpha_nodes.valuation import valuation_on

Rows = Callable[..., pd.DataFrame]
DAY = date(2030, 1, 1)
OK = {"net_income": 10.0, "depreciation_amortization": 4.0, "capex": 6.0, "shares_outstanding": 5.0}
# owner earnings: 10 + 4 - min(6, 4) = 10


def prices_on(close: float = 20.0, currency: str = "USD") -> pd.DataFrame:
    return pd.DataFrame(
        {"date": pd.to_datetime(["2029-12-28", "2029-12-31"]), "close": [close - 1, close], "currency": currency}
    )


def fx_rows(*rows: tuple[str, str, float]) -> pd.DataFrame:
    """`fx` frame from (entity, date, usd_per_unit) triples."""
    return pd.DataFrame(
        {
            "entity": [r[0] for r in rows],
            "date": pd.to_datetime([r[1] for r in rows]),
            "usd_per_unit": [r[2] for r in rows],
        }
    )


@pytest.fixture
def fundamentals(fundamentals_rows: Rows) -> Callable[..., pd.DataFrame]:
    """Factory: rows are the year-ends of 2020 + i, in USD unless overridden."""

    def make(*rows: dict) -> pd.DataFrame:
        return fundamentals_rows(
            *({"period_end": f"{2020 + i}-12-31", "currency": "USD", **r} for i, r in enumerate(rows))
        )

    return make


def test_same_currency_hand_values(fundamentals: Callable[..., pd.DataFrame]) -> None:
    out = valuation_on(prices_on(20.0), fundamentals(OK), fx_rows(), DAY)
    assert (out.price_date, out.close, out.trading_currency, out.fx_rate) == (date(2029, 12, 31), 20.0, "USD", 1.0)
    assert out.currency == "USD"
    assert out.market_cap == pytest.approx(100.0)  # 20 * 5
    assert out.earnings_yield == pytest.approx(0.1)
    assert out.pe == pytest.approx(10.0)
    assert out.owner_earnings_yield == pytest.approx(0.1)
    assert out.value_low == pytest.approx(10 / 0.12)
    assert out.value_high == pytest.approx(10 / 0.08)
    assert out.price_to_value == pytest.approx(100 / ((10 / 0.12 + 10 / 0.08) / 2))
    assert out.field_periods == {}


def test_hurdles_are_parameters(fundamentals: Callable[..., pd.DataFrame]) -> None:
    out = valuation_on(prices_on(), fundamentals(OK), fx_rows(), DAY, hurdle_low=0.05, hurdle_high=0.10)
    assert (out.value_low, out.value_high) == (pytest.approx(100.0), pytest.approx(200.0))


def test_cross_currency_uses_fx(fundamentals: Callable[..., pd.DataFrame]) -> None:
    fx = fx_rows(("GBP", "2029-12-31", 1.25))
    out = valuation_on(prices_on(20.0, "GBP"), fundamentals(OK), fx, DAY)
    assert out.fx_rate == pytest.approx(1.25)  # USD per GBP; reporting currency is USD
    assert out.market_cap == pytest.approx(125.0)  # 20 GBP * 5 shares * 1.25
    assert out.pe == pytest.approx(12.5)


def test_missing_fx_rate_gives_none_not_one(fundamentals: Callable[..., pd.DataFrame]) -> None:
    out = valuation_on(prices_on(20.0, "GBP"), fundamentals(OK), fx_rows(), DAY)
    assert out.fx_rate is None
    for name in ("market_cap", "earnings_yield", "pe", "owner_earnings_yield", "price_to_value"):
        assert getattr(out, name) is None
    assert out.close == 20.0 and out.price_date == date(2029, 12, 31)
    assert out.value_low == pytest.approx(10 / 0.12)  # reporting-currency only: needs no fx


def test_negative_earnings_pe_none_yield_negative(fundamentals: Callable[..., pd.DataFrame]) -> None:
    row = {**OK, "net_income": -5.0}  # owner earnings: -5 + 4 - 4 = -5
    out = valuation_on(prices_on(20.0), fundamentals(row), fx_rows(), DAY)
    assert out.pe is None
    assert out.earnings_yield == pytest.approx(-0.05)


def test_negative_owner_earnings_band_none(fundamentals: Callable[..., pd.DataFrame]) -> None:
    row = {**OK, "net_income": -5.0}
    out = valuation_on(prices_on(20.0), fundamentals(row), fx_rows(), DAY)
    assert (out.value_low, out.value_high, out.price_to_value) == (None, None, None)
    assert out.owner_earnings_yield == pytest.approx(-0.05)


def test_no_known_periods_gives_zero_period_result(fundamentals: Callable[..., pd.DataFrame]) -> None:
    out = valuation_on(prices_on(20.0), fundamentals(), fx_rows(), DAY)
    assert out.periods == 0 and out.currency is None
    assert out.market_cap is None and out.pe is None and out.value_low is None
    assert out.close == 20.0  # the price side is still reported


def test_no_price_gives_none_price_fields(fundamentals: Callable[..., pd.DataFrame]) -> None:
    out = valuation_on(prices_on().iloc[0:0], fundamentals(OK), fx_rows(), DAY)
    assert out.price_date is None and out.close is None and out.market_cap is None
    assert out.value_low == pytest.approx(10 / 0.12)


def test_valuation_records_stale_shares_in_field_periods(fundamentals: Callable[..., pd.DataFrame]) -> None:
    latest = {k: v for k, v in OK.items() if k != "shares_outstanding"}
    out = valuation_on(prices_on(20.0), fundamentals(OK, latest), fx_rows(), DAY)
    assert out.last_period_end == date(2021, 12, 31)
    stale = date(2020, 12, 31)  # every field built on the shares count carries the caveat
    assert out.field_periods == dict.fromkeys(
        ("market_cap", "earnings_yield", "pe", "owner_earnings_yield", "price_to_value"), stale
    )
    assert out.market_cap == pytest.approx(100.0)
    assert out.pe == pytest.approx(10.0)  # net income from the latest period, shares from the year before
