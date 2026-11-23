"""Aggregators: combine per-lens verdicts into a `Dossier` (a node that consumes verdicts).

See documentation/design/core.md, Verdicts and dossiers (aggregation formula). The default
policy is an evidence-share-scaled weighted mean; `combine` is pure so policies are pluggable.
"""

import math
from typing import Any, ClassVar

from pydantic import Field

from .node import Node, NodeContext
from .types import Absent, CandidateRef
from .verdict import Conviction, Dossier, LensVerdict, Provenance


class Aggregator(Node):
    """Base aggregator node. Subclasses implement `combine`; `panel_registry` wires its inputs.

    Params: `lens_weights` (per-lens multiplier, default 1), `conviction_factors` (weight factor per conviction level).
    """

    name: ClassVar[str] = "dossier"
    output: ClassVar[Any] = Dossier
    consumes_verdicts: ClassVar[bool] = True
    # input kwarg (lens node name) -> the lens's `lens_name`; set by `panel_registry` so a
    # lens whose node failed gets the same key as its real verdicts would have.
    lens_names: ClassVar[dict[str, str]] = {}

    lens_weights: dict[str, float] = Field(default_factory=dict)
    conviction_factors: dict[Conviction, float] = Field(
        default_factory=lambda: {"low": 0.5, "medium": 0.75, "high": 1.0}
    )

    def run(self, ctx: NodeContext, **verdicts: LensVerdict | Absent) -> Dossier:
        """Combine the panel's verdicts; an `Absent` lens (its node failed) counts as failed."""
        assert ctx.candidate is not None
        resolved = [
            v
            if isinstance(v, LensVerdict)
            else LensVerdict(
                lens=self.lens_names.get(kwarg, kwarg), status="failed", coverage=0.0, error=v.reason,
                provenance=Provenance(lens_version=""),
            )
            for kwarg, v in verdicts.items()
        ]
        return self.combine(ctx.candidate, resolved)

    def combine(self, candidate: CandidateRef, verdicts: list[LensVerdict]) -> Dossier:
        """Pure policy: verdicts in, dossier out. Subclasses implement it."""
        raise NotImplementedError


class ShrunkMeanAggregator(Aggregator):
    """Default policy ("evidence share"): direction scaled by how much evidence arrived.

    w_i = lens_weight x coverage x conviction_factor (ok verdicts only);
    W_max = sum over every panel verdict of lens_weight x max conviction factor.
    direction = sum(w*s) / sum(w); evidence_share = sum(w) / W_max;
    overall_stance = direction x evidence_share; confidence = evidence_share.
    Agreement is the weighted std dev of ok stances (None below two ok verdicts).
    Unlike a fixed-k shrink this does not depend on panel size.
    See documentation/design/core.md, Verdicts and dossiers.
    """

    def combine(self, candidate: CandidateRef, verdicts: list[LensVerdict]) -> Dossier:
        """Apply the evidence-share formula; see the class docstring."""
        weights = {
            v.lens: self.lens_weights.get(v.lens, 1.0)
            * v.coverage
            * self.conviction_factors[v.conviction]
            if v.status == "ok" and v.conviction is not None
            else 0.0
            for v in verdicts
        }
        pairs = [
            (weights[v.lens], v.stance_mean)
            for v in verdicts
            if v.status == "ok" and v.stance_mean is not None
        ]
        total = sum(w for w, _ in pairs)
        max_conviction = max(self.conviction_factors.values())
        w_max = sum(self.lens_weights.get(v.lens, 1.0) * max_conviction for v in verdicts)
        direction = sum(w * s for w, s in pairs) / total if total > 0 else None
        share = total / w_max if w_max > 0 else 0.0
        overall = direction * share if direction is not None else None
        agreement: float | None = None
        if len(pairs) >= 2 and total > 0:
            mean = sum(w * s for w, s in pairs) / total
            agreement = math.sqrt(sum(w * (s - mean) ** 2 for w, s in pairs) / total)
        return Dossier(
            candidate=candidate,
            verdicts=verdicts,
            overall_stance=overall,
            confidence=share,
            direction=direction,
            evidence_share=share,
            weights=weights,
            agreement=agreement,
            coverage={v.lens: v.status for v in verdicts},
            flags=[f for v in verdicts for f in v.flags],
        )


class VetoAggregator(ShrunkMeanAggregator):
    """Shrunk mean, but a qualifying veto flag forces `overall_stance = -2.0`.

    `veto_codes=None` means any flag with severity "veto" qualifies; otherwise only veto
    flags whose code is listed.
    """

    veto_codes: list[str] | None = None

    def combine(self, candidate: CandidateRef, verdicts: list[LensVerdict]) -> Dossier:
        """Shrunk-mean dossier, with overall stance overridden to -2.0 on a qualifying veto."""
        dossier = super().combine(candidate, verdicts)
        vetoed = any(
            f.severity == "veto" and (self.veto_codes is None or f.code in self.veto_codes)
            for f in dossier.flags
        )
        return dossier.model_copy(update={"overall_stance": -2.0}) if vetoed else dossier
