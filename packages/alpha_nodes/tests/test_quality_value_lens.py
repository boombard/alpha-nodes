"""quality_value AI lens: guard rails, abstention, depth, variants and the static rubric."""

from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
import pytest
from alpha_nodes.lenses.quality_value import QUALITY_VALUE_FLAGS, QualityValue
from alpha_nodes.metrics import (
    BalanceSheetResult,
    CashGenerationResult,
    NewsItem,
    ProfitabilityResult,
    ValuationResult,
)
from lensgraph.node import NodeContext
from lensgraph.types import Absent
from lensgraph.verdict import LensVerdict
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import SystemPromptPart, UserPromptPart

from .ai_lens_helpers import Scripted, fundamentals, parts, registry_for, window

pytestmark = pytest.mark.usefixtures("forbid_real_model_requests")

GOOD: dict[str, Any] = {
    "status": "ok",
    "stance": 1,
    "conviction": "medium",
    "claims": [
        {
            "text": "Returns on equity are high and steady",
            "direction": 1,
            "cites": ["profitability.roe_mean", "recent_news[n1]"],
        }
    ],
    "flags": [],
}


def profile_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name": ["Acme plc"],
            "sector": ["Industrials"],
            "industry": ["Machinery"],
            "country": ["GB"],
            "business_summary": ["Makes widgets."],
            "recommendationKey": ["strong_buy"],
            "targetMeanPrice": [999.0],
            "isin": ["GB0000000001"],
        }
    )


def news_items() -> list[NewsItem]:
    return [
        NewsItem(
            id="n1",
            published_at=datetime(2026, 6, 20, tzinfo=UTC),
            headline="Acme wins contract",
            source=None,
            url=None,
            summary=None,
        )
    ]


def make_inputs(periods: int = 8, **overrides: Any) -> dict[str, Any]:
    inputs: dict[str, Any] = {
        "annual_fundamentals": fundamentals(periods),
        "profitability": ProfitabilityResult(
            roe_mean=0.18, roe_min=0.1, roe_std=0.03, op_margin_mean=0.2, op_margin_std=0.02,
            net_income_cv=0.15, loss_years=0, **window(periods),
        ),
        "balance_sheet": BalanceSheetResult(
            debt_to_equity=0.3, interest_cover=12.0, net_debt=5.0, **window(periods)
        ),
        "cash_generation": CashGenerationResult(
            owner_earnings=10.0, fcf=9.0, fcf_conversion=0.9, share_count_cagr=0.0, **window(periods)
        ),
        "valuation": ValuationResult(
            price_date=date(2026, 6, 30), close=10.0, trading_currency="USD", fx_rate=1.0,
            market_cap=100.0, earnings_yield=0.07, pe=14.0, owner_earnings_yield=0.08,
            value_low=90.0, value_high=140.0, price_to_value=0.9, **window(periods),
        ),
        "profile": profile_frame(),
        "recent_news": news_items(),
    }
    inputs.update(overrides)
    return inputs


async def run_lens(
    model: Scripted, lens: QualityValue | None = None, **overrides: Any
) -> LensVerdict:
    lens = lens or QualityValue(profile="test")
    ctx = NodeContext(run_id="r", candidate=None, services={"profiles": registry_for(model)})
    return await lens.run(ctx, **make_inputs(**overrides))


async def test_ok_verdict_with_valid_cites(make_model):
    v = await run_lens(make_model(GOOD))
    assert v.status == "ok" and v.stance == 1
    assert v.claims[0].cites == ["profitability.roe_mean", "recent_news[n1]"]
    assert v.provenance.variant == "default"


async def test_unknown_cite_retried_then_fails(make_model):
    bad = {**GOOD, "claims": [{"text": "x", "direction": 1, "cites": ["made_up"]}]}
    with pytest.raises(UnexpectedModelBehavior, match="made_up"):
        await run_lens(make_model(bad))


async def test_unknown_flag_code_rejected(make_model):
    bad = {**GOOD, "flags": [{"severity": "warn", "code": "bogus", "text": "t", "cites": []}]}
    model = make_model(bad, GOOD)
    v = await run_lens(model)
    assert v.provenance.attempts == 2
    good_flag = {"severity": "warn", "code": "dilution", "text": "t", "cites": []}
    assert (await run_lens(make_model({**GOOD, "flags": [good_flag]}))).flags[0].code == "dilution"
    assert "dilution" in QUALITY_VALUE_FLAGS and "bogus" not in QUALITY_VALUE_FLAGS


async def test_abstains_without_fundamentals_and_no_model_call(make_model):
    model = make_model(GOOD)
    v = await run_lens(model, annual_fundamentals=fundamentals(0))
    assert v.status == "abstained" and "annual_fundamentals" in (v.error or "")
    assert model.calls == []


async def test_two_periods_below_minimum_abstains(make_model):
    model = make_model(GOOD)
    v = await run_lens(model, annual_fundamentals=fundamentals(2))
    assert v.status == "abstained"
    assert model.calls == []


async def test_four_periods_gives_half_sufficiency_and_depth_note(make_model):
    model = make_model(GOOD)
    v = await run_lens(model, annual_fundamentals=fundamentals(4))
    assert v.status == "ok"
    assert v.input_sufficiency["annual_fundamentals"] == pytest.approx(0.5)
    assert "4 of 8" in parts(model, UserPromptPart)


async def test_persona_variant_changes_prompt_hash_and_memo_salt(make_model):
    default, persona = QualityValue(profile="test"), QualityValue(profile="test", variant="buffett_persona")
    services = {"profiles": registry_for(make_model(GOOD))}
    assert default.memo_salt(services) != persona.memo_salt(services)
    v = await run_lens(make_model(GOOD), lens=persona)
    d = await run_lens(make_model(GOOD), lens=default)
    assert v.provenance.variant == "buffett_persona"
    assert v.provenance.prompt_hash != d.provenance.prompt_hash


def test_unknown_variant_rejected():
    with pytest.raises(ValueError, match="unknown variant"):
        QualityValue(variant="graham")


PRINCIPLE_HEADINGS = [
    "Consistent earning power",
    "Good returns on equity with little or no debt",
    "Management in place",
    "A simple, understandable business",
    "A durable competitive advantage",
    "Earnings after the reinvestment",
    "Buy only at a clear discount",
]
EVIDENCE_ONLY = "Judge only from the evidence given"


async def test_rubric_is_static_and_names_no_investor(make_model):
    model = make_model(GOOD)
    await run_lens(model)
    system = parts(model, SystemPromptPart)
    for heading in PRINCIPLE_HEADINGS:
        assert heading in system
    for banned in ("Buffett", "Berkshire", "letter", "Graham", "Munger"):
        assert banned not in system
    for code in QUALITY_VALUE_FLAGS:
        assert code in system
    assert EVIDENCE_ONLY in system
    assert "Acme" not in system and "Makes widgets" not in system and "n1" not in system


async def test_persona_prompt_has_guardrails(make_model):
    model = make_model(GOOD)
    await run_lens(model, lens=QualityValue(profile="test", variant="buffett_persona"))
    system = parts(model, SystemPromptPart)
    assert "Warren Buffett" in system and "holdings" in system and "folksy" in system
    assert "The Intelligent Investor" in system  # same rubric underneath
    assert EVIDENCE_ONLY in system


async def test_context_has_no_analyst_fields(make_model):
    model = make_model(GOOD)
    await run_lens(model)
    user = parts(model, UserPromptPart)
    assert "Acme plc" in user and "Makes widgets." in user
    for banned in ("recommendation", "targetMeanPrice", "strong_buy", "999.0", "isin", "GB0000000001"):
        assert banned not in user


async def test_profile_absent_is_tolerated(make_model):
    v = await run_lens(make_model(GOOD), profile=Absent(reason="no profile"))
    assert v.status == "ok"


def test_class_docstring_lists_rubric_sources():
    doc = QualityValue.__doc__ or ""
    assert "Rubric sources" in doc and "deliberately not in the default prompt" in doc
    for source in ("2014 letter", "1996 letter", "2007 letter", "1986 letter", "1992 letter", "Intelligent Investor"):
        assert source in doc


@pytest.mark.parametrize("variant", ["default", "buffett_persona"])
async def test_prompt_mentions_field_periods(make_model, variant):
    model = make_model(GOOD)
    await run_lens(model, lens=QualityValue(profile="test", variant=variant))
    assert "field_periods" in parts(model, SystemPromptPart)


async def test_field_periods_rendered_in_context(make_model):
    model = make_model(GOOD)
    stale = BalanceSheetResult(
        debt_to_equity=0.3, interest_cover=12.0, net_debt=5.0,
        field_periods={"interest_cover": date(2024, 12, 31)}, **window(8),
    )
    await run_lens(model, balance_sheet=stale)
    assert "2024-12-31" in parts(model, UserPromptPart)
