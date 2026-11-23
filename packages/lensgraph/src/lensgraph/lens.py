"""LensNode: template for lenses, with framework-computed coverage and citation checks.

See documentation/design/core.md, Verdicts and dossiers.
"""

import asyncio
import inspect
from typing import Any, ClassVar, Literal

from pydantic import BaseModel

from .citations import citable_ids
from .node import Node, NodeContext
from .types import Absent, ContractViolation, Failed
from .verdict import Claim, Conviction, Flag, LensVerdict, Provenance, Stance


class DepthRequirement(BaseModel):
    """How much of an input a lens wants, measured as `len(value)`."""

    desired: int  # at or above this, the input is fully sufficient
    minimum: int = 1  # below this, the input counts as absent


class LensAssessment(BaseModel):
    """What `LensNode.assess` returns: the judgement only; the template adds the rest."""

    status: Literal["ok", "abstained"]
    stance: Stance | None = None
    conviction: Conviction | None = None
    stance_mean: float | None = None  # finer stance if the lens has one; defaults to `stance`
    stance_spread: float | None = None  # instability of the stance, if measured
    score: float | None = None
    components: dict[str, float] = {}
    claims: list[Claim] = []
    flags: list[Flag] = []
    abstain_reason: str | None = None  # becomes the verdict's `error`
    provenance_extra: dict[str, Any] = {}  # merged into Provenance (model, tokens, ...)


def input_sufficiency(value: Any, req: DepthRequirement | None) -> float:
    """Sufficiency in [0, 1] of one input: 0 if missing/empty/below minimum, else depth ratio.

    Values without a length (e.g. a float) count as 1.0 when present.
    """
    if value is None or isinstance(value, Absent):
        return 0.0
    size = len(value) if hasattr(value, "__len__") else None
    if size == 0:
        return 0.0
    if req is None or size is None:
        return 1.0
    if size < req.minimum:
        return 0.0
    return min(1.0, size / req.desired)


class LensNode(Node):
    """Base of every lens. Subclasses implement `assess`; `run` is a template method.

    `run` computes coverage and citable ids, calls `assess`, enforces citations and builds the
    `LensVerdict` (see documentation/design/core.md, Verdicts and dossiers).
    """

    lens_name: ClassVar[str]
    output = LensVerdict
    depth: ClassVar[dict[str, DepthRequirement]] = {}  # input name -> depth requirement
    input_weights: ClassVar[dict[str, float]] = {}  # input name -> coverage weight (default 1)

    def assess(self, ctx: NodeContext, citables: frozenset[str], **inputs: Any) -> LensAssessment:
        """Judge the candidate from `inputs`; may be `async`. Cite only ids in `citables`."""
        raise NotImplementedError

    async def run(self, ctx: NodeContext, **inputs: Any) -> LensVerdict:  # type: ignore[override]
        """Template method; do not override. Implement `assess` instead."""
        suff = {n: input_sufficiency(inputs.get(n), self.depth.get(n)) for n in self.all_inputs()}
        weights = {n: self.input_weights.get(n, 1.0) for n in suff}
        total = sum(weights.values())
        coverage = sum(suff[n] * weights[n] for n in suff) / total if total else 0.0
        citables = citable_ids({n: v for n, v in inputs.items() if not isinstance(v, Absent)})
        if inspect.iscoroutinefunction(self.assess):
            assessment = await self.assess(ctx, citables, **inputs)
        else:  # keep sync (e.g. pandas-heavy) lenses off the event loop
            assessment = await asyncio.to_thread(self.assess, ctx, citables, **inputs)
        owned = sorted({"lens_version", "input_hashes"} & set(assessment.provenance_extra))
        if owned:
            raise ContractViolation(
                f"{self.name}: provenance_extra may not set template-owned key {owned[0]!r}"
            )
        stance_mean, stance_spread = assessment.stance_mean, assessment.stance_spread
        if assessment.status == "ok":
            if stance_mean is None and assessment.stance is not None:
                stance_mean = float(assessment.stance)
        elif stance_mean is not None or stance_spread is not None:
            raise ContractViolation(
                f"{self.name}: a {assessment.status!r} assessment must not set "
                "stance_mean or stance_spread"
            )
        for cite in [c for claim in assessment.claims for c in claim.cites] + [
            c for flag in assessment.flags for c in flag.cites
        ]:
            if cite not in citables:
                raise ContractViolation(f"{self.name}: cites unknown id {cite!r}")
        return LensVerdict(
            lens=self.lens_name,
            status=assessment.status,
            stance=assessment.stance,
            conviction=assessment.conviction,
            stance_mean=stance_mean,
            stance_spread=stance_spread,
            coverage=coverage,
            input_sufficiency=suff,
            score=assessment.score,
            components=assessment.components,
            claims=assessment.claims,
            flags=assessment.flags,
            error=assessment.abstain_reason,
            provenance=Provenance(
                lens_version=self.code_version(),
                input_hashes=ctx.input_hashes,
                **assessment.provenance_extra,
            ),
        )

    def on_upstream_failure(self, ctx: NodeContext, failure: Failed) -> LensVerdict:
        """A required input failed: record a `failed` verdict (coverage 0) instead of skipping."""
        return LensVerdict(
            lens=self.lens_name,
            status="failed",
            coverage=0.0,
            error=f"upstream '{failure.origin}' failed: {failure.error}",
            provenance=Provenance(lens_version=self.code_version()),
        )
