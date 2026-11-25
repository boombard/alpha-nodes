"""price_behaviour lens: scoring, claims, data-quality flag and run-time overrides."""

from datetime import date
from typing import Any

import pytest
from alpha_nodes.lenses.price_behaviour import PriceBehaviour
from alpha_nodes.metrics import DrawdownResult, MomentumResult, TrendResult, VolatilityResult
from lensgraph.charts import LineChart
from lensgraph.deterministic import LinearScorer
from lensgraph.node import NodeContext
from lensgraph.types import Absent
from lensgraph.verdict import LensVerdict

START, END = date(2025, 1, 2), date(2026, 1, 2)


def _window(suspect: int = 0) -> dict[str, Any]:
    return {"bars": 300, "start": START, "end": END, "suspect_bars": suspect}


def make_inputs(
    momentum: float | None = 0.1,
    pct: float | None = 0.0,
    slope: float | None = 0.0,
    vol: float | None = 0.30,
    dd: float | None = -0.375,
    suspect: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Result models for the four calc inputs; `suspect` maps input name -> suspect bars."""
    s = suspect or {}
    return {
        "momentum": MomentumResult(total_return=momentum, **_window(s.get("momentum", 0))),
        "trend": TrendResult(
            close=None, ma=None, pct_above_ma=pct, ma_slope=slope, **_window(s.get("trend", 0))
        ),
        "volatility": VolatilityResult(annualised=vol, **_window(s.get("volatility", 0))),
        "drawdown": DrawdownResult(
            max_drawdown=dd, peak_date=None, trough_date=None, **_window(s.get("drawdown", 0))
        ),
    }


@pytest.fixture
def chart() -> LineChart:
    return LineChart(title="Price", x=[START, END], series={"close": [1.0, 2.0]})


async def run_lens(lens: PriceBehaviour | None = None, **inputs: Any) -> LensVerdict:
    inputs.setdefault("price_chart", Absent(reason="not built"))
    return await (lens or PriceBehaviour()).run(NodeContext(run_id="r", candidate=None), **inputs)


async def test_strong_uptrend_is_strongly_bullish():
    v = await run_lens(**make_inputs(0.5, 0.15, 0.3, 0.15, -0.10))
    assert v.stance == 2
    assert set(v.components) == {"momentum", "trend", "trend_slope", "volatility", "drawdown"}


async def test_crash_is_strongly_bearish():
    v = await run_lens(**make_inputs(-0.4, -0.2, -0.4, 0.6, -0.7))
    assert v.stance == -2


async def test_middling_stock_is_neutral():
    v = await run_lens(**make_inputs(0.1, 0.0, 0.0, 0.30, -0.375))
    assert v.score == pytest.approx(0.0)
    assert v.stance == 0


async def test_missing_component_is_skipped():
    v = await run_lens(**make_inputs(momentum=None))
    assert v.status == "ok"
    assert set(v.components) == {"trend", "trend_slope", "volatility", "drawdown"}


async def test_all_values_none_abstains():
    v = await run_lens(**make_inputs(None, None, None, None, None))
    assert v.status == "abstained"


async def test_suspect_bars_raise_data_quality_flag():
    v = await run_lens(**make_inputs(suspect={"momentum": 2, "drawdown": 1}))
    (flag,) = v.flags
    assert (flag.severity, flag.code) == ("warn", "data_quality")
    assert flag.cites == ["momentum.suspect_bars", "drawdown.suspect_bars"]
    assert "momentum" in flag.text and "2" in flag.text


async def test_no_flag_without_suspect_bars():
    assert (await run_lens(**make_inputs())).flags == []


async def test_claims_cite_price_chart_when_present(chart):
    v = await run_lens(price_chart=chart, **make_inputs())
    cites = {c.text.split()[0]: c.cites for c in v.claims}
    assert cites["12-1"] == ["momentum.total_return", "price_chart"]
    assert cites["Close"] == ["trend.pct_above_ma", "price_chart"]
    assert cites["200-day"] == ["trend.ma_slope"]


async def test_claims_without_price_chart():
    v = await run_lens(**make_inputs())
    assert all("price_chart" not in c.cites for c in v.claims)
    assert v.coverage == pytest.approx(1.0)


async def test_chart_does_not_change_coverage(chart):
    with_chart = await run_lens(price_chart=chart, **make_inputs())
    assert with_chart.coverage == pytest.approx(1.0)


async def test_overrides_change_the_verdict():
    inputs = make_inputs(0.5, -0.2, -0.4, 0.6, -0.7)  # momentum +1, the rest -1
    base = await run_lens(**inputs)
    assert base.stance == -1
    shifted = await run_lens(PriceBehaviour(thresholds=(-0.2, -0.1, 0.0, 0.1)), **inputs)
    assert shifted.stance == -2
    weighted = await run_lens(PriceBehaviour(weight_overrides={"momentum": 10.0}), **inputs)
    assert weighted.stance == 2
    scorer = {"momentum": LinearScorer(lo=0.6, hi=1.0)}
    rescored = await run_lens(PriceBehaviour(scorer_overrides=scorer), **inputs)
    assert rescored.components["momentum"] == -1.0
    assert rescored.stance == -2


def test_lens_reads_only_calc_nodes():
    assert set(PriceBehaviour.all_inputs().values()) == {
        "momentum",
        "trend",
        "volatility",
        "drawdown",
        "price_chart",
    }


async def test_claim_texts_render():
    v = await run_lens(**make_inputs(momentum=0.25))
    assert "12-1 month total return +25.0%" in {c.text for c in v.claims}
