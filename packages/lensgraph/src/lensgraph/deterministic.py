"""Deterministic lenses: weighted scored components mapped to a stance by thresholds.

See documentation/design/core.md, Deterministic lenses.
"""

import math
from typing import Any, ClassVar, Self

import numpy as np
from pydantic import BaseModel, ConfigDict, model_validator

from .lens import LensAssessment, LensNode
from .node import NodeContext
from .types import Absent
from .units import NUMBER, format_value
from .verdict import Claim, Conviction, Stance


class LinearScorer(BaseModel):
    """Maps a raw value to [-1, 1]: `lo` scores -1, `hi` scores +1, clipped outside."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lo: float
    hi: float
    higher_is_better: bool = True  # False reverses the scale: `lo` scores +1

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        """Reject `hi == lo`, which would divide by zero when scoring."""
        if self.hi == self.lo:
            raise ValueError("LinearScorer needs hi != lo")
        return self

    def __call__(self, value: float) -> float:
        """Score `value` linearly between `lo` and `hi`, clipped to [-1, 1]."""
        score = max(-1.0, min(1.0, 2 * (value - self.lo) / (self.hi - self.lo) - 1))
        return score if self.higher_is_better else -score


class Component(BaseModel):
    """One scored ingredient of a deterministic lens: where its value comes from and how it counts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str  # key in the verdict's `components`
    source: str  # citable id of the value: "<input>" or "<input>.<field>"
    scorer: LinearScorer
    weight: float = (
        1.0  # relative weight; overridable per run via `DeterministicLens.weight_overrides`
    )
    evidence: tuple[str, ...] = ()  # extra citable ids added to the claim's cites when citable
    # Formatted with `name`, `value` (formatted by the field's unit), `signed` (the same, with a
    # sign) and `raw` (the float). See core.md, Units.
    claim_template: str = "{name}: {value}"


def _resolve(source: str, inputs: dict[str, Any]) -> float | None:
    """The finite numeric value at `source` (`input` or `input.field`), or None if unusable."""
    name, _, field = source.partition(".")
    value = inputs.get(name)
    if field:
        value = getattr(value, field, None) if isinstance(value, BaseModel) else None
    if isinstance(value, Absent | bool) or not isinstance(value, int | float | np.number):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


class DeterministicLens(LensNode):
    """A lens whose verdict is a weighted mean of scored components; no LLM involved.

    Subclasses declare `components`. The score maps to a stance via `thresholds`, to a
    conviction via its distance from the nearest threshold, and to a continuous `stance_mean`
    by interpolating between threshold centres (see core.md, Deterministic lenses).
    """

    components: ClassVar[list[Component]]

    thresholds: tuple[float, float, float, float] = (-0.6, -0.2, 0.2, 0.6)  # stance cut points
    conviction_margins: tuple[float, float] = (0.1, 0.3)  # distance below which: low, medium
    weight_overrides: dict[str, float] = {}  # noqa: RUF012  # component name -> weight, replacing the default

    scorer_overrides: dict[str, LinearScorer] = {}  # noqa: RUF012  # component name -> scorer, replacing the default

    @model_validator(mode="after")
    def _check_scorer_overrides(self) -> Self:
        """Reject scorer override names that match no component (typos)."""
        known = {c.name for c in type(self).components}
        unknown = sorted(set(self.scorer_overrides) - known)
        if unknown:
            raise ValueError(
                f"scorer_overrides names unknown components {unknown}; known: {sorted(known)}"
            )
        return self

    @model_validator(mode="after")
    def _check_weight_overrides(self) -> Self:
        """Reject override names that match no component (typos) and negative weights."""
        known = {c.name for c in type(self).components}
        unknown = sorted(set(self.weight_overrides) - known)
        if unknown:
            raise ValueError(
                f"weight_overrides names unknown components {unknown}; known: {sorted(known)}"
            )
        negative = sorted(n for n, w in self.weight_overrides.items() if w < 0)
        if negative:
            raise ValueError(f"weight_overrides must not be negative: {negative}")
        return self

    def _unit_scope(self) -> set[str] | None:
        """Only the component sources reach the verdict, so only they need units (core.md, Units)."""
        return {c.source for c in type(self).components if "." in c.source}

    def _claim_text(self, c: Component, value: float, inputs: dict[str, Any]) -> str:
        """The component's claim: its template filled with the value formatted by the source's unit."""
        unit = self._units.get(c.source, NUMBER)
        holder = inputs.get(c.source.partition(".")[0])
        row = holder.model_dump() if isinstance(holder, BaseModel) else None
        return c.claim_template.format(
            name=c.name,
            value=format_value(value, unit, row),
            signed=format_value(value, unit, row, signed=True),
            raw=value,
        )

    def _stance(self, score: float) -> Stance:
        t = self.thresholds
        if score < t[0]:
            return -2
        if score < t[1]:
            return -1
        if score <= t[2]:
            return 0
        return 1 if score <= t[3] else 2

    def _conviction(self, score: float) -> Conviction:
        distance = min(abs(score - t) for t in self.thresholds)
        if distance < self.conviction_margins[0]:
            return "low"
        return "medium" if distance < self.conviction_margins[1] else "high"

    def _stance_mean(self, score: float) -> float:
        t0, t1, t2, t3 = self.thresholds
        centres = [
            t0 - (t1 - t0) / 2,
            (t0 + t1) / 2,
            (t1 + t2) / 2,
            (t2 + t3) / 2,
            t3 + (t3 - t2) / 2,
        ]
        return float(np.interp(score, centres, [-2, -1, 0, 1, 2]))

    def assess(self, ctx: NodeContext, citables: frozenset[str], **inputs: Any) -> LensAssessment:
        """Score the available components; abstain if none can be resolved."""
        raw = {c.name: _resolve(c.source, inputs) for c in self.components}
        present = [(c, v) for c in self.components if (v := raw[c.name]) is not None]
        if not present:
            return LensAssessment(status="abstained", abstain_reason="no components available")
        scored = {c.name: self.scorer_overrides.get(c.name, c.scorer)(v) for c, v in present}
        weights = {c.name: self.weight_overrides.get(c.name, c.weight) for c, _ in present}
        total = sum(weights.values())
        if total <= 0:
            return LensAssessment(
                status="abstained", abstain_reason="all available components have zero weight"
            )
        score = sum(scored[n] * weights[n] for n in scored) / total
        claims = [
            Claim(
                text=self._claim_text(c, v, inputs),
                direction=1 if scored[c.name] >= 0 else -1,
                cites=[c.source, *(e for e in c.evidence if e in citables)],
            )
            for c, v in present
        ]
        return LensAssessment(
            status="ok",
            stance=self._stance(score),
            conviction=self._conviction(score),
            stance_mean=self._stance_mean(score),
            score=score,
            components=scored,
            claims=claims,
        )
