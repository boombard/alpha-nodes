"""The `price_behaviour` deterministic lens.

Scores momentum, trend, volatility and drawdown from the M5 price metric models.
See documentation/design/finance.md, v1 lenses (price_behaviour and Pinned conventions)
and documentation/design/core.md, Deterministic lenses.
"""

from typing import Any, ClassVar

from lensgraph.deterministic import Component, DeterministicLens, LinearScorer
from lensgraph.lens import LensAssessment
from lensgraph.node import NodeContext
from lensgraph.verdict import Flag

_CALC_INPUTS = ("momentum", "trend", "volatility", "drawdown")


class PriceBehaviour(DeterministicLens):
    """Absolute, price-only lens: momentum, trend, volatility and drawdown.

    Reads the calc nodes' result models (finance.md, Calculation layers); the optional
    `price_chart` is cited as evidence but carries no coverage weight. Defaults are a starting
    point for the M8 backtest to calibrate; `thresholds`, `weight_overrides` and
    `scorer_overrides` tune them per run. Raises a `data_quality` warn flag when any input's
    window contained suspect bars.
    """

    name: ClassVar[str] = "price_behaviour"
    lens_name: ClassVar[str] = "price_behaviour"
    inputs: ClassVar[dict[str, str]] = {n: n for n in _CALC_INPUTS}
    optional_inputs: ClassVar[dict[str, str]] = {"price_chart": "price_chart"}
    input_weights: ClassVar[dict[str, float]] = {"price_chart": 0.0}  # evidence only
    components: ClassVar[list[Component]] = [
        Component(
            name="momentum",
            source="momentum.total_return",
            scorer=LinearScorer(lo=-0.20, hi=0.40),
            weight=1.0,
            claim_template="12-1 month total return {value:+.1%}",
            evidence=("price_chart",),
        ),
        Component(
            name="trend",
            source="trend.pct_above_ma",
            scorer=LinearScorer(lo=-0.10, hi=0.10),
            weight=0.5,
            claim_template="Close {value:+.1%} vs its 200-day average",
            evidence=("price_chart",),
        ),
        Component(
            name="trend_slope",
            source="trend.ma_slope",
            scorer=LinearScorer(lo=-0.20, hi=0.20),
            weight=0.5,
            claim_template="200-day average rising {value:+.1%} a year",
        ),
        Component(
            name="volatility",
            source="volatility.annualised",
            scorer=LinearScorer(lo=0.15, hi=0.45, higher_is_better=False),
            weight=0.5,
            claim_template="Realised volatility {value:.0%} a year",
        ),
        Component(
            name="drawdown",
            source="drawdown.max_drawdown",
            scorer=LinearScorer(lo=-0.60, hi=-0.15),
            weight=0.5,
            claim_template="Max drawdown {value:.0%} over the window",
        ),
    ]

    def assess(self, ctx: NodeContext, citables: frozenset[str], **inputs: Any) -> LensAssessment:
        """Score the components, then add the `data_quality` flag if suspect bars were used."""
        assessment = super().assess(ctx, citables, **inputs)
        suspect = {
            n: count
            for n in _CALC_INPUTS
            if (count := getattr(inputs.get(n), "suspect_bars", 0)) > 0
        }
        if suspect:
            detail = ", ".join(f"{n} ({c} suspect bars)" for n, c in suspect.items())
            assessment.flags.append(
                Flag(
                    severity="warn",
                    code="data_quality",
                    text=f"Suspect price bars used in: {detail}",
                    cites=[f"{n}.suspect_bars" for n in suspect],
                )
            )
        return assessment
