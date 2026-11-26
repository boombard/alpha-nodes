"""Valuation adapter: prices, fundamentals and fx combined at one day (middle calculation layer).

Thin pandas glue between the fetch frames and the `Valuation` / `ValuationChange` nodes in
`alpha_nodes.nodes.valuation_calcs`: pick the price and the periods known on a day, convert
market cap into the reporting currency through `fx`, and apply the kernels. All maths lives in
`alpha_nodes.kernels`. See documentation/design/finance.md, Fundamentals: pinned conventions
(Market cap, Valuation) and Currency.
"""

from datetime import date
from typing import Any, cast

import pandas as pd

from alpha_nodes.kernels import capitalised_value, owner_earnings
from alpha_nodes.metrics import ValuationResult
from alpha_nodes.money import fx_factor
from alpha_nodes.scalars import opt, ratio
from alpha_nodes.series import close_on
from alpha_nodes.statements import annual_periods, latest_complete, period_window

_OE_COLUMNS = ("net_income", "depreciation_amortization", "capex")
# result fields built on each latest-point input; a stale input is recorded against all of them
_DEPENDENTS = {
    "shares": ("market_cap", "earnings_yield", "pe", "owner_earnings_yield", "price_to_value"),
    "net_income": ("earnings_yield", "pe"),
    "owner_earnings": ("owner_earnings_yield", "value_low", "value_high", "price_to_value"),
}


def valuation_on(
    prices: pd.DataFrame,
    fundamentals: pd.DataFrame,
    fx: pd.DataFrame,
    day: date,
    hurdle_low: float = 0.08,
    hurdle_high: float = 0.12,
) -> ValuationResult:
    """Valuation of one company on `day`, from the price and the periods known on that day.

    Shares outstanding, net income and owner earnings each come from the newest of the last
    `MAX_STALE_PERIODS + 1` known periods holding all their inputs (`latest_complete`); every
    result field built on an older one is listed in `field_periods`. Market cap is
    `close × shares × fx` (trading to reporting currency on the price date). A missing fx rate
    gives `fx_rate = None` and None for every field that needs market cap, never 1.0. The band
    is `owner earnings / hurdle_high` to `owner earnings / hurdle_low`, None for non-positive
    owner earnings; it needs no fx. P/E is None for non-positive net income (the yield is
    negative then). With no known period the result has `periods=0` and no money fields.

    Args:
        hurdle_low: required yield at the optimistic end (gives `value_high`).
        hurdle_high: required yield at the pessimistic end (gives `value_low`).
    """
    annual = annual_periods(fundamentals, day)
    price = close_on(prices, day)
    rows = {
        "shares": latest_complete(annual, "shares_outstanding"),
        "net_income": latest_complete(annual, "net_income"),
        "owner_earnings": latest_complete(annual, *_OE_COLUMNS),
    }
    window = period_window(annual)
    price_date, close, trading_currency = price if price is not None else (None, None, None)

    stale: dict[str, date] = {}
    if len(annual):
        used = [r["period_end"].iloc[0] for r in rows.values() if len(r)]
        window = period_window(
            cast(pd.DataFrame, annual[annual["period_end"] >= min(used, default=annual["period_end"].iloc[-1])])
        )
        for key, row in rows.items():
            if len(row) and row["period_end"].iloc[0] < annual["period_end"].iloc[-1]:
                for name in _DEPENDENTS[key]:
                    stale[name] = min(stale.get(name, date.max), row["period_end"].iloc[0].date())

    fx_rate = None
    if price is not None and window.currency is not None:
        fx_rate = fx_factor(fx, price[2], window.currency, price[0])
    shares = float(rows["shares"]["shares_outstanding"].iloc[0]) if len(rows["shares"]) else None
    net_income = float(rows["net_income"]["net_income"].iloc[0]) if len(rows["net_income"]) else None
    oe_rows = rows["owner_earnings"]
    oe = (
        opt(float(owner_earnings(*(oe_rows[c].to_numpy(float) for c in _OE_COLUMNS))[0]))
        if len(oe_rows)
        else None
    )

    market_cap = None
    if price is not None and shares is not None and fx_rate is not None:
        market_cap = price[1] * shares * fx_rate
    low = None if oe is None else opt(capitalised_value(oe, hurdle_high))
    high = None if oe is None else opt(capitalised_value(oe, hurdle_low))
    fields: dict[str, Any] = {
        "market_cap": market_cap,
        "earnings_yield": ratio(net_income, market_cap),
        "pe": ratio(market_cap, net_income),
        "owner_earnings_yield": ratio(oe, market_cap),
        "value_low": low,
        "value_high": high,
        "price_to_value": None if low is None or high is None else ratio(market_cap, (low + high) / 2),
    }
    return ValuationResult(
        **window.model_dump(exclude={"field_periods"}),
        price_date=price_date,
        close=close,
        trading_currency=trading_currency,
        fx_rate=fx_rate,
        **fields,
        field_periods={n: d for n, d in stale.items() if fields[n] is not None},
    )
