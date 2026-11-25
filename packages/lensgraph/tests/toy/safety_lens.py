"""Toy AI lens over the strain domain: the test-suite's stand-in for an LLM judgement."""

from pathlib import Path
from typing import ClassVar

from lensgraph.ai import AINode
from lensgraph.lens import DepthRequirement

_PROMPTS = Path(__file__).parent / "prompts"


class SafetyLens(AINode):
    """Judges strain safety from its growth rate and toxicity notes; abstains without the notes."""

    name: ClassVar[str] = "safety_lens"
    lens_name: ClassVar[str] = "safety"
    prompt: ClassVar[Path] = _PROMPTS / "safety.md.j2"
    variants: ClassVar[dict[str, Path]] = {"strict": _PROMPTS / "safety_strict.md.j2"}
    inputs: ClassVar[dict[str, str]] = {"growth_rate": "growth_rate"}
    optional_inputs: ClassVar[dict[str, str]] = {"tox_notes": "tox_notes"}
    depth: ClassVar[dict[str, DepthRequirement]] = {
        "tox_notes": DepthRequirement(desired=3, minimum=1)
    }
    critical_inputs: frozenset[str] = frozenset({"tox_notes"})
    flag_codes: ClassVar[frozenset[str] | None] = frozenset({"tox_signal"})
