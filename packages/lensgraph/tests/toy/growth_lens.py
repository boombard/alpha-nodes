"""Toy deterministic lens over the toy `growth_rate` calc (the strain domain's scored number)."""

from typing import ClassVar

from lensgraph.deterministic import Component, DeterministicLens, LinearScorer


class GrowthLens(DeterministicLens):
    """Scores a strain's growth rate: -0.1 /h scores -1, 0.1 /h is neutral, 0.3 /h or more scores +1."""

    name: ClassVar[str] = "growth_lens"
    lens_name: ClassVar[str] = "growth"
    inputs: ClassVar[dict[str, str]] = {"growth_rate": "growth_rate"}
    components: ClassVar[list[Component]] = [
        Component(name="growth", source="growth_rate", scorer=LinearScorer(lo=-0.1, hi=0.3))
    ]
