"""Tests for the valuation calc nodes (`alpha_nodes.nodes.valuation_calcs`); values are hand-computed."""

from collections.abc import Callable
from datetime import date

import pandas as pd
import pytest
from alpha_nodes import series, statements, valuation
from alpha_nodes.conventions import BARS_PER_YEAR
from alpha_nodes.kernels import capitalised_value, owner_earnings, safe_ratio
from alpha_nodes.nodes.valuation_calcs import Valuation, ValuationChange
from lensgraph.node import NodeContext
from lensgraph.types import CandidateRef
from pydantic import ValidationError

Rows = Callable[..., pd.DataFrame]
NOW = date(2030, 1, 1)
EMPTY_FX = pd.DataFrame({"entity": [], "date": pd.to_datetime([]), "usd_per_unit": []})


def ctx_on(day: date = NOW) -> NodeContext:
    return NodeContext(run_id="r", candidate=CandidateRef(id="X"), as_of=day)


def prices_frame(closes: list[float], end: str = "2029-12-31") -> pd.DataFrame:
    """Business-day USD prices ending on `end`."""
    dates = pd.bdate_range(end=end, periods=len(closes))
    return pd.DataFrame({"date": dates, "close": closes, "currency": "USD"})


def _first_bar(n: int) -> date:
    """Date of the first of `n` business-day bars ending 2029-12-31."""
    return pd.bdate_range(end="2029-12-31", periods=n).to_pydatetime()[0].date()


def period(year: int, net_income: float, filed: str | None = None) -> dict:
    """A USD annual row: owner earnings == net_income (D&A == capex), 10 shares."""
    return {
        "period_end": f"{year}-12-31",
        "filed_at": filed,
        "currency": "USD",
        "net_income": net_income,
        "depreciation_amortization": 1.0,
        "capex": 1.0,
        "shares_outstanding": 10.0,
    }


def test_valuation_change_pe_change_hand_value(fundamentals_rows: Rows) -> None:
    n = BARS_PER_YEAR + 1
    closes = [10.0] * (n - 1) + [20.0]  # then = 10, now = 20
    out = ValuationChange().run(
        ctx_on(),
        prices=prices_frame(closes),
        fundamentals=fundamentals_rows(period(2027, 10.0, "2028-03-01"), period(2028, 10.0, "2029-03-01")),
        fx=EMPTY_FX,
    )
    assert out.pe_then == pytest.approx(10.0)  # 10 * 10 / 10
    assert out.pe_now == pytest.approx(20.0)
    assert out.pe_change == pytest.approx(1.0)  # 20 / 10 - 1
    assert out.earnings_yield_then == pytest.approx(0.1) and out.earnings_yield_now == pytest.approx(0.05)
    assert out.date_now == date(2029, 12, 31)
    assert out.date_then == _first_bar(n)


def test_valuation_change_uses_periods_known_then(fundamentals_rows: Rows) -> None:
    n = BARS_PER_YEAR + 1
    then = _first_bar(n)  # mid-Jan 2029
    frame = fundamentals_rows(
        period(2027, 10.0, filed="2028-03-01"),
        period(2028, 40.0, filed=f"{then.year}-06-01"),  # filed after `then`, before now
    )
    out = ValuationChange().run(
        ctx_on(), prices=prices_frame([10.0] * n), fundamentals=frame, fx=EMPTY_FX
    )
    assert out.pe_then == pytest.approx(10.0)  # net income 10 (2027), not the later 40
    assert out.pe_now == pytest.approx(2.5)  # net income 40 known now
    assert out.last_period_end == date(2028, 12, 31)  # the window is the "now" side's


def test_short_price_history_then_none(fundamentals_rows: Rows) -> None:
    out = ValuationChange().run(
        ctx_on(),
        prices=prices_frame([10.0] * 50),
        fundamentals=fundamentals_rows(period(2028, 10.0, "2029-03-01")),
        fx=EMPTY_FX,
    )
    assert out.date_then is None
    assert (out.pe_then, out.pe_change, out.earnings_yield_then) == (None, None, None)
    assert out.pe_now == pytest.approx(10.0)


def test_valuation_node_matches_adapter(fundamentals_rows: Rows) -> None:
    frame, prices = fundamentals_rows(period(2028, 10.0, "2029-03-01")), prices_frame([10.0] * 5)
    node_out = Valuation(hurdle_low=0.05, hurdle_high=0.10).run(
        ctx_on(), prices=prices, fundamentals=frame, fx=EMPTY_FX
    )
    assert node_out == valuation.valuation_on(prices, frame, EMPTY_FX, NOW, 0.05, 0.10)


@pytest.mark.parametrize("low, high", [(0.0, 0.1), (-0.1, 0.1), (0.12, 0.08), (0.1, 0.1)])
def test_hurdles_validated(low: float, high: float) -> None:
    with pytest.raises(ValidationError):
        Valuation(hurdle_low=low, hurdle_high=high)


def test_valuation_nodes_are_not_memoized_and_declare_code_deps() -> None:
    for node in (Valuation, ValuationChange):
        assert node.memoize is False
        assert {valuation.valuation_on, series.close_on} & set(node.code_deps)
    assert {valuation.valuation_on, capitalised_value, owner_earnings, safe_ratio} <= set(Valuation.code_deps)
    assert {series.bars_back, statements.annual_periods} <= set(ValuationChange.code_deps)
