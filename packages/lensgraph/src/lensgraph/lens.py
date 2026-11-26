"""LensNode: template for lenses, with framework-computed coverage and citation checks.

See documentation/design/core.md, Verdicts and dossiers.
"""

import asyncio
import functools
import inspect
from collections.abc import Mapping
from typing import Any, ClassVar, Literal, Self

from pydantic import BaseModel, Field, PrivateAttr, model_validator

from . import context, units
from .citations import citable_ids
from .glossary import contract_model, model_fields
from .hashing import content_hash
from .node import Node, NodeContext
from .types import Absent, ContractViolation, Failed
from .units import Unit, UnitError, is_numeric_field, unit_of
from .verdict import Claim, Conviction, Flag, LensVerdict, Provenance, Stance


@functools.cache
def _renderer_fingerprint() -> str:
    """Hash of the formatter and evidence renderer source, computed once per process."""
    return content_hash([inspect.getsource(units), inspect.getsource(context)])


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

    Two params let a lens refuse to judge on thin evidence: `critical_inputs` and `min_coverage`.
    If either is unmet, `run` returns an `abstained` verdict before `assess` (so an AI lens makes
    no model call); see core.md, Verdicts and dossiers, "critical inputs and minimum coverage".
    """

    critical_inputs: frozenset[str] = frozenset()  # input names the lens can't judge without
    min_coverage: float = Field(default=0.0, ge=0.0, le=1.0)  # abstain below this coverage

    # False skips the plan-build unit check (temporary, until a domain annotates its fields).
    require_units: ClassVar[bool] = True

    _units: dict[str, Unit] = PrivateAttr(default_factory=dict)  # "input.field" -> unit, set by bind_upstream

    def _unit_scope(self) -> set[str] | None:
        """Paths (`input.field`) that must carry a unit if numeric; None means every field of every input."""
        return None

    def bind_upstream(self, outputs: Mapping[str, Any]) -> None:
        """Record the unit of every input field and, if `require_units`, check the numeric ones.

        A numeric field (int or float, not bool) in scope without a unit raises `UnitError` naming
        this lens, the input and the field. The map feeds claim and evidence formatting, the memo
        salt and the verdict's `cite_units`. See core.md, Units.
        """
        bound: dict[str, Unit] = {}
        missing: dict[str, str] = {}  # path -> message
        for input_name, output in outputs.items():
            model = contract_model(output)
            if model is None:
                continue
            for field in model_fields(model):
                path = f"{input_name}.{field}"
                unit = unit_of(model, field)
                if unit is not None:
                    bound[path] = unit
                elif is_numeric_field(model, field):
                    missing[path] = (
                        f"{self.name}: input {input_name!r} field {field!r} ({model.__name__}) "
                        "is numeric but declares no unit"
                    )
        self._units = bound
        if self.require_units:
            scope = self._unit_scope()
            errors = [m for p, m in sorted(missing.items()) if scope is None or p in scope]
            if errors:
                raise UnitError(errors[0] + (f" (+{len(errors) - 1} more)" if len(errors) > 1 else ""))

    def memo_salt(self, services: Mapping[str, Any]) -> str:
        """Presentation fingerprint: the bound unit map and the renderer source (core.md, Units).

        Changing a unit this lens sees, or `units`/`context`, reruns it; other lenses keep their cache.
        """
        return content_hash(
            [
                {path: unit.model_dump() for path, unit in sorted(self._units.items())},
                _renderer_fingerprint(),
            ]
        )

    def _cite_units(self, cites: list[str]) -> dict[str, Unit]:
        """Units of the cited fields; a cited whole input (or list item) brings all its fields' units."""
        out: dict[str, Unit] = {}
        for cite in cites:
            head = cite.split("[")[0].split(".")[0]
            for path, unit in self._units.items():
                if path == cite or ((cite == head or "[" in cite) and path.startswith(f"{head}.")):
                    out[path] = unit
        return dict(sorted(out.items()))

    @model_validator(mode="after")
    def _check_critical_inputs(self) -> Self:
        """Reject critical input names that match no input (typos) at plan time."""
        known = sorted(type(self).all_inputs())
        unknown = sorted(self.critical_inputs - set(known))
        if unknown:
            raise ValueError(f"critical_inputs names unknown inputs {unknown}; known: {known}")
        return self

    def _abstain_reason(self, suff: dict[str, float], coverage: float) -> str | None:
        """Why the lens must not judge (unmet critical input, then low coverage), else None."""
        missing = sorted(n for n in self.critical_inputs if suff[n] == 0.0)
        if missing:
            extra = f" (+{len(missing) - 1} more)" if len(missing) > 1 else ""
            return f"critical input '{missing[0]}' unavailable{extra}"
        if coverage < self.min_coverage:
            return f"coverage {coverage:.2f} below minimum {self.min_coverage:.2f}"
        return None

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
        reason = self._abstain_reason(suff, coverage)
        if reason is not None:  # no assess() call, hence no model call for AI lenses
            return LensVerdict(
                lens=self.lens_name,
                status="abstained",
                coverage=coverage,
                input_sufficiency=suff,
                error=reason,
                provenance=Provenance(
                    lens_version=self.code_version(), input_hashes=ctx.input_hashes
                ),
            )
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
        cited = [c for claim in assessment.claims for c in claim.cites] + [
            c for flag in assessment.flags for c in flag.cites
        ]
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
                cite_units=self._cite_units(cited),
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
