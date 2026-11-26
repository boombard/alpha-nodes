"""Tests for the price calc nodes (`alpha_nodes.nodes.price_calcs`)."""

import math
from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest
from alpha_nodes import series
from alpha_nodes.kernels import (
    drawdown_extent,
    linreg_slope,
    log_returns,
    max_drawdown,
    realised_volatility,
    skip_return,
    sma,
    total_return_index,
)
from alpha_nodes.metrics import TrendResult
from alpha_nodes.nodes.price_calcs import (
    Drawdown,
    Momentum,
    PriceChart,
    TotalReturn,
    Trend,
    Volatility,
    opt,
)
from lensgraph.node import NodeContext
from lensgraph.types import CandidateRef
from lensgraph.units import format_value, unit_of

G = 1.001
Prices = Callable[..., pd.DataFrame]


@pytest.fixture
def ctx() -> NodeContext:
    return NodeContext(run_id="r", candidate=CandidateRef(id="BP.L"))


@pytest.fixture
def prices() -> Prices:
    """Factory: `prices(n)` is `close = 100 * g**t` on business days; override columns via kwargs."""

    def make(n: int, g: float = G, **columns: list) -> pd.DataFrame:
        frame = pd.DataFrame(
            {
                "date": pd.bdate_range("2024-01-01", periods=n),
                "close": 100.0 * g ** np.arange(n),
                "dividends": 0.0,
                "quality": "ok",
                "currency": "GBP",
            }
        )
        for name, values in columns.items():
            frame[name] = values
        return frame

    return make


@pytest.fixture
def tr(prices: Prices) -> Callable[..., pd.DataFrame]:
    """Factory: the total-return frame for a synthetic geometric series."""
    return lambda n, **kw: series.total_return(prices(n, **kw))


def test_momentum_hand_value(tr, ctx) -> None:
    result = Momentum().run(ctx, tr=tr(400))
    assert result.total_return == pytest.approx(G**231 - 1)
    assert result.bars == 253


def test_momentum_none_when_252_bars(tr, ctx) -> None:
    result = Momentum().run(ctx, tr=tr(252))
    assert result.total_return is None
    assert result.bars == 252
    assert result.start is not None and result.end is not None


def test_trend_pct_above_ma_hand_value(tr, ctx) -> None:
    frame = tr(300)
    closes = frame["close"].to_numpy()
    result = Trend().run(ctx, tr=frame)
    ma = closes[-200:].mean()
    assert result.ma == pytest.approx(ma)
    assert result.close == pytest.approx(closes[-1])
    assert result.pct_above_ma == pytest.approx(closes[-1] / ma - 1)


def test_trend_slope_of_geometric_series(tr, ctx) -> None:
    result = Trend().run(ctx, tr=tr(400))
    assert result.ma_slope == pytest.approx(252 * math.log(G))
    assert result.bars == 219


def test_trend_none_when_short(tr, ctx) -> None:
    result = Trend().run(ctx, tr=tr(218))
    assert (result.close, result.ma, result.pct_above_ma, result.ma_slope) == (None,) * 4
    assert result.bars == 218


def test_volatility_matches_kernel(prices, ctx) -> None:
    rng = np.random.default_rng(1)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 400)))
    frame = series.total_return(prices(400, close=close))
    expected = realised_volatility(log_returns(frame["tr_index"].to_numpy()[-253:]), 252)
    assert Volatility().run(ctx, tr=frame).annualised == pytest.approx(expected)


def test_volatility_none_below_min_returns(tr, ctx) -> None:
    assert Volatility().run(ctx, tr=tr(64)).annualised is not None  # 63 returns
    result = Volatility().run(ctx, tr=tr(63))
    assert result.annualised is None
    assert result.bars == 63


def test_drawdown_uses_available_bars(tr, ctx) -> None:
    result = Drawdown().run(ctx, tr=tr(400))
    assert result.bars == 400
    assert result.max_drawdown == 0.0
    assert (result.peak_date, result.trough_date) == (None, None)


def test_drawdown_none_below_min_bars(tr, ctx) -> None:
    result = Drawdown().run(ctx, tr=tr(251))
    assert (result.max_drawdown, result.peak_date, result.trough_date) == (None, None, None)
    assert result.bars == 251


def test_drawdown_dates(prices, ctx) -> None:
    close = 100.0 * G ** np.arange(300)
    close[200:230] = close[199] * np.linspace(0.99, 0.6, 30)  # dip, trough at index 229
    frame = series.total_return(prices(300, close=close))
    result = Drawdown().run(ctx, tr=frame)
    assert result.peak_date == frame["date"].iloc[199].date()
    assert result.trough_date == frame["date"].iloc[229].date()
    assert result.max_drawdown == pytest.approx(0.6 - 1)


def test_suspect_bars_counted_in_window(prices, ctx) -> None:
    quality = ["ok"] * 400
    quality[10] = "suspect"  # outside every window
    quality[390] = "suspect"
    frame = series.total_return(prices(400, quality=quality))
    assert Momentum().run(ctx, tr=frame).suspect_bars == 1
    assert Volatility().run(ctx, tr=frame).suspect_bars == 1
    assert Drawdown().run(ctx, tr=frame).suspect_bars == 2
    assert Trend().run(ctx, tr=frame).suspect_bars == 1


def test_price_chart_weekly_points(tr, ctx) -> None:
    frame = tr(400)
    chart = PriceChart(weeks=20).run(ctx, tr=frame)
    assert chart.title == "BP.L: close vs 200-day average"
    assert len(chart.x) == 20
    assert chart.x[-1] == frame["date"].iloc[-1].date()  # last session of the last week
    assert all(d.weekday() == 4 for d in chart.x[:-1])  # earlier weeks end on a Friday
    assert set(chart.series) == {"close", "ma200"}
    assert all(v is not None for v in chart.series["ma200"])  # 400 bars: warm-up long past
    short = PriceChart(weeks=156).run(ctx, tr=tr(300))
    assert short.series["ma200"][0] is None  # warm-up
    assert short.series["ma200"][-1] is not None
    assert short.series["close"][-1] == pytest.approx(100 * G**299)


def test_empty_prices_give_none_results(prices, ctx) -> None:
    empty = pd.DataFrame(
        {
            "date": pd.to_datetime([]),
            "close": pd.Series([], dtype=float),
            "dividends": pd.Series([], dtype=float),
            "quality": pd.Series([], dtype=str),
            "currency": pd.Series([], dtype=str),
        }
    )
    frame = TotalReturn().run(ctx, prices=empty)
    assert frame.empty
    for node, field in [
        (Momentum(), "total_return"),
        (Trend(), "pct_above_ma"),
        (Volatility(), "annualised"),
        (Drawdown(), "max_drawdown"),
    ]:
        result = node.run(ctx, tr=frame)
        assert (result.bars, result.start, result.end, result.suspect_bars) == (0, None, None, 0)
        assert getattr(result, field) is None
    chart = PriceChart().run(ctx, tr=frame)
    assert chart.x == [] and chart.series == {"close": [], "ma200": []}


def test_calc_nodes_declare_their_kernels() -> None:
    assert skip_return in Momentum.code_deps
    assert {sma, linreg_slope} <= set(Trend.code_deps)
    assert {log_returns, realised_volatility} <= set(Volatility.code_deps)
    assert {max_drawdown, drawdown_extent} <= set(Drawdown.code_deps)
    assert {sma, opt} <= set(PriceChart.code_deps)
    assert {total_return_index, series.total_return} <= set(TotalReturn.code_deps)
    for node in (Momentum, Trend, Volatility, Drawdown):
        assert {series.trailing, series.window_info} <= set(node.code_deps)


def test_price_calc_nodes_are_not_memoized() -> None:
    nodes = (TotalReturn, Momentum, Trend, Volatility, Drawdown, PriceChart)
    assert [n.memoize for n in nodes] == [False] * 6


def test_trend_close_renders_with_its_trading_currency(prices, ctx) -> None:
    result = Trend().run(ctx, tr=TotalReturn().run(ctx, prices=prices(300, g=1.0, close=[189.2] * 300)))
    assert result.currency == "GBP"
    unit = unit_of(TrendResult, "close")
    assert unit is not None
    assert format_value(result.close, unit, result.model_dump()) == "GBP 189.20"
