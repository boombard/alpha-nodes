"""price_vs_fundamentals AI lens: guard rails, framework-owned flag severity, abstention, prompt."""

from datetime import date
from typing import Any

import pandas as pd
import pytest
from alpha_nodes.lenses.price_vs_fundamentals import FLAG_SEVERITY, PriceVsFundamentals
from alpha_nodes.metrics import (
    FundamentalTrendResult,
    MomentumResult,
    TrendResult,
    ValuationChangeResult,
)
from lensgraph.node import NodeContext
from lensgraph.verdict import LensVerdict
from pydantic_ai.messages import SystemPromptPart, UserPromptPart

from .ai_lens_helpers import Scripted, fundamentals, parts, registry_for, window

pytestmark = pytest.mark.usefixtures("forbid_real_model_requests")

GOOD: dict[str, Any] = {
    "status": "ok",
    "stance": -1,
    "conviction": "medium",
    "claims": [
        {
            "text": "Price rose while revenue growth turned negative",
            "direction": -1,
            "cites": ["momentum.total_return", "fundamental_trend.revenue_growth_1y"],
        }
    ],
    "flags": [],
}


def flag(code: str, severity: str) -> dict[str, Any]:
    return {"severity": severity, "code": code, "text": "t", "cites": []}


def _pricewindow() -> dict[str, Any]:
    return {
        "bars": 250,
        "start": date(2025, 6, 30),
        "end": date(2026, 6, 30),
        "suspect_bars": 0,
    }


def falling_fundamentals(periods: int) -> pd.DataFrame:
    """Annual fundamentals with falling revenue, matching the scenario's negative growth."""
    return fundamentals(periods, revenue_step=-1.0)


def make_inputs(periods: int = 4, **overrides: Any) -> dict[str, Any]:
    inputs: dict[str, Any] = {
        "momentum": MomentumResult(total_return=0.4, **_pricewindow()),
        "trend": TrendResult(close=50.0, ma=40.0, pct_above_ma=0.25, ma_slope=0.01, **_pricewindow()),
        "fundamental_trend": FundamentalTrendResult(
            revenue_growth_1y=-0.05, revenue_cagr_3y=-0.02, op_margin_change_1y=-0.01,
            eps_growth_1y=-0.1, fcf_growth_1y=-0.2, **window(periods),
        ),
        "valuation_change": ValuationChangeResult(
            date_now=date(2026, 6, 30), date_then=date(2025, 6, 30), pe_now=25.0, pe_then=15.0,
            pe_change=10.0, earnings_yield_now=0.04, earnings_yield_then=0.067, **window(periods),
        ),
        "annual_fundamentals": falling_fundamentals(periods),
    }
    inputs.update(overrides)
    return inputs


async def run_lens(model: Scripted, **overrides: Any) -> LensVerdict:
    lens = PriceVsFundamentals(profile="test")
    ctx = NodeContext(run_id="r", candidate=None, services={"profiles": registry_for(model)})
    return await lens.run(ctx, **make_inputs(**overrides))


async def test_ok_verdict_with_valid_cites(make_model):
    v = await run_lens(make_model(GOOD))
    assert v.status == "ok" and v.stance == -1
    assert v.claims[0].cites == ["momentum.total_return", "fundamental_trend.revenue_growth_1y"]


async def test_flag_severity_overridden_from_code(make_model):
    said = {**GOOD, "flags": [flag("price_up_fundamentals_down", "info")]}
    v = await run_lens(make_model(said))
    assert [(f.code, f.severity) for f in v.flags] == [("price_up_fundamentals_down", "warn")]


def test_flag_severity_table_matches_spec():
    assert FLAG_SEVERITY == {
        "price_up_fundamentals_down": "warn",
        "rerating_despite_deterioration": "warn",
        "price_down_fundamentals_up": "info",
        "derating_despite_improvement": "info",
    }
    assert PriceVsFundamentals.flag_codes == frozenset(FLAG_SEVERITY)


async def test_unknown_flag_code_rejected(make_model):
    bad = {**GOOD, "flags": [flag("bogus", "warn")]}
    v = await run_lens(make_model(bad, GOOD))
    assert v.provenance.attempts == 2


async def test_abstains_with_one_period_and_no_model_call(make_model):
    model = make_model(GOOD)
    v = await run_lens(model, annual_fundamentals=falling_fundamentals(1))
    assert v.status == "abstained"
    assert model.calls == []


async def test_depth_note_rendered(make_model):
    model = make_model(GOOD)
    v = await run_lens(model, annual_fundamentals=falling_fundamentals(2))
    assert v.status == "ok"
    assert "2 of 4" in parts(model, UserPromptPart)


async def test_prompt_states_divergence_framing(make_model):
    model = make_model(GOOD)
    await run_lens(model)
    system = parts(model, SystemPromptPart)
    assert "divergence" in system
    assert "+2" in system and "-2" in system
    assert "not a reason to be bullish" in system
    for code in FLAG_SEVERITY:
        assert code in system


async def test_prompt_mentions_field_periods(make_model):
    model = make_model(GOOD)
    await run_lens(model)
    system = parts(model, SystemPromptPart)
    assert "field_periods" in system and "last_period_end" in system and "stale" in system


def test_docstring_records_no_analyst_inputs():
    doc = PriceVsFundamentals.__doc__ or ""
    assert "analyst" in doc and "herding" in doc
