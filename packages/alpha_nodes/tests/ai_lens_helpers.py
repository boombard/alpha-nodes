"""Test-only helpers shared by the AI-lens test modules (quality_value, price_vs_fundamentals).

A scripted `FunctionModel` standing in for the LLM, a profile registry that routes to it, and
small builders for the window facts and annual-fundamentals frame every lens input carries.
Tests never reach a real model; see CLAUDE.md, Hard rules.
"""

import json
from datetime import date
from typing import Any

import pandas as pd
from lensgraph.llm import LLMProfile, ProfileRegistry
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel


class Scripted(FunctionModel):
    """Replays canned answers (last repeats) and records each request's messages."""

    def __init__(self, *payloads: dict[str, Any]) -> None:
        self.calls: list[list[ModelMessage]] = []
        self._payloads = payloads
        super().__init__(self._answer)

    def _answer(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        payload = self._payloads[min(len(self.calls), len(self._payloads) - 1)]
        self.calls.append(messages)
        if info.output_tools:
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, payload)])
        return ModelResponse(parts=[TextPart(json.dumps(payload))])


def registry_for(model: Scripted) -> ProfileRegistry:
    """A registry whose profile "test" is answered by `model`."""
    return ProfileRegistry(
        {"test": LLMProfile(name="test", model="test")}, model_overrides={"test": model}
    )


def window(periods: int) -> dict[str, Any]:
    """Keyword args for a `PeriodWindow` result covering `periods` annual periods."""
    return {
        "periods": periods,
        "first_period_end": date(2018, 12, 31),
        "last_period_end": date(2025, 12, 31),
        "suspect_periods": 0,
        "currency": "USD",
    }


def fundamentals(periods: int, *, revenue_step: float = 1.0) -> pd.DataFrame:
    """A minimal annual-fundamentals frame with `periods` rows.

    Revenue starts at 100 and changes by `revenue_step` per period (negative for falling revenue).
    """
    return pd.DataFrame(
        {
            "period_end": pd.date_range("2018-12-31", periods=periods, freq="YE"),
            "revenue": [100.0 + revenue_step * i for i in range(periods)],
        }
    )


def parts(model: Scripted, part_type: type, call: int = 0) -> str:
    """The text of all `part_type` parts (system or user prompt) in request number `call`."""
    return "\n".join(
        str(p.content)  # pyright: ignore[reportAttributeAccessIssue]
        for m in model.calls[call]
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, part_type)
    )


def lens_input_contracts(lens: Any) -> dict[str, Any]:
    """Output contract of every input (required and optional) of an AI lens, by input name.

    Each contract is `contract()` of the node that produces the input (a fetch node's is its dataset's frame schema): the registry's
    node where registered, else the node class in `fundamental_calcs` / `valuation_calcs` / `news`
    (not registered yet).
    """
    from alpha_nodes.nodes import fundamental_calcs, news, valuation_calcs
    from alpha_nodes.registry import build_registry

    registry = build_registry()
    producers: dict[str, Any] = {name: registry.get(name) for name in registry.names()}
    for cls in (
        fundamental_calcs.AnnualFundamentals, fundamental_calcs.Profitability,
        fundamental_calcs.BalanceSheet, fundamental_calcs.CashGeneration,
        fundamental_calcs.FundamentalTrend, valuation_calcs.Valuation,
        valuation_calcs.ValuationChange, news.RecentNews,
    ):  # fmt: skip
        producers.setdefault(cls.name, cls)
    contracts = {name: node.contract() for name, node in producers.items()}
    inputs = {**lens.inputs, **lens.optional_inputs}
    return {name: contracts[source] for name, source in inputs.items()}


def bound[L](lens: L) -> L:
    """`lens` after the plan-build binding step (`bind_upstream`), so its data dictionary is rendered."""
    lens.bind_upstream(lens_input_contracts(lens))  # type: ignore[attr-defined]
    return lens
