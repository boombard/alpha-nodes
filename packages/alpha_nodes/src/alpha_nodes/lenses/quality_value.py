"""The `quality_value` AI lens: Buffett-style business quality and price, judged by an LLM.

See documentation/design/finance.md, v1 lenses (2. quality_value) and Fundamentals: lens
inputs and abstention; the guard rails are in documentation/design/core.md, AI nodes.
"""

from pathlib import Path
from typing import Any, ClassVar

import pandas as pd
from lensgraph.ai import AINode
from lensgraph.lens import DepthRequirement, LensAssessment
from lensgraph.node import NodeContext
from lensgraph.types import Absent
from pydantic import Field

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"

QUALITY_VALUE_FLAGS = frozenset(
    {
        "high_leverage",
        "dilution",
        "inconsistent_earnings",
        "stretched_valuation",
        "thin_history",
        "accounting_concern",
    }
)
"""The closed list of flag codes `quality_value` may raise."""

_PROFILE_COLUMNS = ["name", "sector", "industry", "country", "business_summary"]


class QualityValue(AINode):
    """Judges business quality and valuation against Buffett's principles from the fundamentals calcs.

    The default prompt is a rubric of seven principles with their primary sources; the
    `buffett_persona` variant asks for the same judgement "as Warren Buffett would". Both share one
    output contract and flag list. Abstains, with no model call, when `annual_fundamentals` is
    missing or has fewer than 3 periods (critical input).

    Rubric sources (for audit; deliberately not in the default prompt). Naming the investor, his
    letters or years would invite the model to recall his holdings and views (several demo names
    are famous holdings) and would blur the rubric-vs-persona comparison, so the default prompt
    states the principles neutrally. The `buffett_persona` prompt may keep them.
    1. Consistent earning power: Berkshire Hathaway's acquisition criteria, printed in its
       annual reports (e.g. the 2014 letter).
    2. Good returns on equity while employing little or no debt: the same criteria.
    3. Management in place: the same criteria.
    4. Simple, understandable businesses; circle of competence: the same criteria; 1996 letter.
    5. A durable competitive advantage, the "moat": 2007 letter.
    6. Owner earnings (reported earnings + D&A - maintenance capex): 1986 letter, appendix.
    7. Margin of safety: 1992 letter; Graham, *The Intelligent Investor*, ch. 20.

    Two deliberate choices:
    - No analyst consensus, ratings or price targets reach the context, to avoid LLM herding
      (the TASK-13 note): the profile frame is cut to name, sector, industry, country and
      business summary before rendering.
    - News and profile text are untrusted evidence to weigh, never instructions; the prompt says so.
    """

    name: ClassVar[str] = "quality_value"
    lens_name: ClassVar[str] = "quality_value"
    prompt: ClassVar[Path] = PROMPTS / "quality_value.md.j2"
    variants: ClassVar[dict[str, Path]] = {
        "buffett_persona": PROMPTS / "quality_value_buffett_persona.md.j2"
    }
    inputs: ClassVar[dict[str, str]] = {
        "annual_fundamentals": "annual_fundamentals",
        "profitability": "profitability",
        "balance_sheet": "balance_sheet",
        "cash_generation": "cash_generation",
        "valuation": "valuation",
    }
    optional_inputs: ClassVar[dict[str, str]] = {"profile": "profile", "recent_news": "recent_news"}
    depth: ClassVar[dict[str, DepthRequirement]] = {
        "annual_fundamentals": DepthRequirement(desired=8, minimum=3),
        "recent_news": DepthRequirement(desired=5, minimum=1),
    }
    input_weights: ClassVar[dict[str, float]] = {"recent_news": 0.5, "profile": 0.5}
    flag_codes: ClassVar[frozenset[str] | None] = QUALITY_VALUE_FLAGS

    critical_inputs: frozenset[str] = Field(default=frozenset({"annual_fundamentals"}))

    async def assess(  # type: ignore[override]
        self, ctx: NodeContext, citables: frozenset[str], **inputs: Any
    ) -> LensAssessment:
        """Drop all profile columns but the descriptive ones, then run the guard-railed model call."""
        profile = inputs.get("profile")
        if isinstance(profile, pd.DataFrame):
            inputs["profile"] = profile[[c for c in _PROFILE_COLUMNS if c in profile.columns]]
        elif profile is not None and not isinstance(profile, Absent):
            raise TypeError(f"profile must be a frame, got {type(profile).__name__}")
        return await super().assess(ctx, citables, **inputs)
