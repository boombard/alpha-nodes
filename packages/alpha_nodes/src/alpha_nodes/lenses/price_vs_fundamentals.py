"""The `price_vs_fundamentals` AI lens: does the price action agree with the fundamentals?

See documentation/design/finance.md, v1 lenses (3. price_vs_fundamentals) and Fundamentals: lens
inputs and abstention; the guard rails are in documentation/design/core.md, AI nodes.
"""

from pathlib import Path
from typing import Any, ClassVar, Literal

from lensgraph.ai import AINode
from lensgraph.lens import DepthRequirement, LensAssessment
from lensgraph.node import NodeContext
from pydantic import Field

from alpha_nodes.glossary import FINANCE_GLOSSARY_DIR

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"

FLAG_SEVERITY: dict[str, Literal["info", "warn"]] = {
    "price_up_fundamentals_down": "warn",
    "rerating_despite_deterioration": "warn",
    "price_down_fundamentals_up": "info",
    "derating_despite_improvement": "info",
}
"""The closed list of flag codes `price_vs_fundamentals` may raise, with their severities.

Severity is framework-owned (like status): it is set from this table after the model answers,
whatever severity the model gave.
"""


class PriceVsFundamentals(AINode):
    """Divergence check: do the price action and the change in valuation agree with the fundamental trend?

    Framed as a divergence check, not a second momentum lens, so momentum is not double-counted:
    the momentum and trend numbers are context for the comparison, never a reason to be bullish
    by themselves. Abstains, with no model call, when `annual_fundamentals` is missing or has
    fewer than 2 periods (critical input).

    Deliberate choice: no analyst consensus, ratings or price targets reach the context, to avoid
    LLM herding (the TASK-13 note); the inputs are only calc results and the annual fundamentals frame.
    """

    name: ClassVar[str] = "price_vs_fundamentals"
    lens_name: ClassVar[str] = "price_vs_fundamentals"
    require_units: ClassVar[bool] = False  # TASK-69
    glossary: ClassVar[Path | None] = FINANCE_GLOSSARY_DIR
    prompt: ClassVar[Path] = PROMPTS / "price_vs_fundamentals.md.j2"
    inputs: ClassVar[dict[str, str]] = {
        "momentum": "momentum",
        "trend": "trend",
        "fundamental_trend": "fundamental_trend",
        "valuation_change": "valuation_change",
        "annual_fundamentals": "annual_fundamentals",
    }
    depth: ClassVar[dict[str, DepthRequirement]] = {
        "annual_fundamentals": DepthRequirement(desired=4, minimum=2)
    }
    flag_codes: ClassVar[frozenset[str] | None] = frozenset(FLAG_SEVERITY)

    critical_inputs: frozenset[str] = Field(default=frozenset({"annual_fundamentals"}))

    async def assess(  # type: ignore[override]
        self, ctx: NodeContext, citables: frozenset[str], **inputs: Any
    ) -> LensAssessment:
        """Run the guard-railed model call, then set each flag's severity from `FLAG_SEVERITY`."""
        assessment = await super().assess(ctx, citables, **inputs)
        assessment.flags = [
            f.model_copy(update={"severity": FLAG_SEVERITY[f.code]}) for f in assessment.flags
        ]
        return assessment
