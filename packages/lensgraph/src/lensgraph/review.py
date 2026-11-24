"""Post-panel dossier reviewer: a guard-railed narrative read of a finished dossier.

See documentation/design/core.md, Assessment brief and post-panel review. The reviewer is a
separate tier from the panel: it reads the dossier (and the brief, which lenses never see),
produces a `DossierReview` with no stance and no score, and its output never feeds the
aggregator, so it can flag or demote a candidate but never promote one.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel
from pydantic_ai import ModelRetry

from .ai import _JINJA, _registry, call_structured
from .hashing import content_hash
from .node import Node, NodeContext
from .verdict import AssessmentBrief, Dossier, DossierReview, Flag, Provenance, ReviewPoint


class ReviewOut(BaseModel):
    """The LLM-facing answer schema of the reviewer: a `DossierReview` minus provenance."""

    summary: str
    fit: list[ReviewPoint] = []
    gaps: list[ReviewPoint] = []
    flags: list[Flag] = []


def review_citables(dossier: Dossier) -> frozenset[str]:
    """Ids a review may cite: `verdict.<lens>`, `verdict.<lens>.claim[<i>]`, `flag.<lens>.<code>`.

    Failed and abstained verdicts are citable too (their error explains the gap).
    """
    ids: set[str] = set()
    for verdict in dossier.verdicts:
        ids.add(f"verdict.{verdict.lens}")
        ids.update(f"verdict.{verdict.lens}.claim[{i}]" for i in range(len(verdict.claims)))
        ids.update(f"flag.{verdict.lens}.{flag.code}" for flag in verdict.flags)
    return frozenset(ids)


def _block(cid: str, body: dict[str, Any]) -> str:
    return f"### [{cid}]\n{json.dumps(body, default=str)}"


def render_review_context(dossier: Dossier, *, show_stances: bool = True) -> str:
    """Render the dossier as the reviewer's user message, one `### [<id>]` block per citable id.

    With `show_stances=False` every stance-derived value (stance, stance_mean, direction,
    overall_stance, agreement) is omitted, leaving claims, flags, coverage and status: the
    anchoring guard from core.md, for a fit judgement that should not echo the lenses.
    """
    overall: dict[str, Any] = {
        "candidate": dossier.candidate.id,
        "confidence": dossier.confidence,
        "coverage": dossier.coverage,
    }
    if show_stances:
        overall |= {
            "overall_stance": dossier.overall_stance,
            "direction": dossier.direction,
            "agreement": dossier.agreement,
        }
    blocks = ["### Dossier\n" + json.dumps(overall, default=str)]
    for verdict in dossier.verdicts:
        body: dict[str, Any] = {
            "status": verdict.status,
            "coverage": verdict.coverage,
            "error": verdict.error,
        }
        if show_stances:
            body |= {
                "stance": verdict.stance,
                "stance_mean": verdict.stance_mean,
                "conviction": verdict.conviction,
            }
        blocks.append(_block(f"verdict.{verdict.lens}", body))
        for i, claim in enumerate(verdict.claims):
            effect = "supports" if claim.direction == 1 else "undermines"
            blocks.append(
                _block(f"verdict.{verdict.lens}.claim[{i}]", {"text": claim.text, "effect": effect})
            )
        for flag in verdict.flags:
            blocks.append(
                _block(
                    f"flag.{verdict.lens}.{flag.code}",
                    {"severity": flag.severity, "text": flag.text},
                )
            )
    return "\n\n".join(blocks)


class DossierReviewer(Node):
    """Reads a finished dossier against the brief and returns a cited `DossierReview`.

    Not a lens and never in a panel: `panel_registry` registers the class named by
    `Panel.reviewer` as node `review`, fed by the panel's aggregator. Subclasses set `prompt`
    (a Jinja2 template rendered with `brief` and `flag_codes` as the static system prompt).
    The brief is a node param, so it is part of the memo key and a new brief reruns only the
    review. Guard rails (`ModelRetry`): unknown cites, flag codes outside `flag_codes`,
    priorities outside the brief's, and `fit` points when there is no brief.
    """

    name: ClassVar[str] = "review"
    output = DossierReview
    consumes_verdicts: ClassVar[bool] = True
    resource = "llm"
    inputs: ClassVar[dict[str, str]] = {"dossier": "dossier"}
    prompt: ClassVar[Path]
    flag_codes: ClassVar[frozenset[str]] = frozenset({"brief_conflict", "evidence_gap"})

    brief: AssessmentBrief | None = None
    profile: str = "dev"  # model profile name; see llm.py
    show_stances: bool = True  # False: hide stances from the model (anchoring guard)

    def _prompt_hash(self) -> str:
        return content_hash(self.prompt.read_text())

    def memo_salt(self, services: Mapping[str, Any]) -> str:
        """Profile fingerprint plus prompt-template hash; see core.md, Memoization (AI nodes)."""
        return content_hash([_registry(services).fingerprint(self.profile), self._prompt_hash()])

    def _system_prompt(self) -> str:
        template = _JINJA.from_string(self.prompt.read_text())
        return template.render(brief=self.brief, flag_codes=sorted(self.flag_codes))

    def _guard_rail(self, out: ReviewOut, citables: frozenset[str]) -> ReviewOut:
        """Raise `ModelRetry` with a precise message when the answer is unusable."""
        points = [*out.fit, *out.gaps]
        cites = [c for p in points for c in p.cites] + [c for f in out.flags for c in f.cites]
        unknown = sorted({c for c in cites if c not in citables})
        if unknown:
            raise ModelRetry(f"Unknown citation ids: {unknown}. Valid ids: {sorted(citables)}")
        bad_codes = sorted({f.code for f in out.flags if f.code not in self.flag_codes})
        if bad_codes:
            raise ModelRetry(
                f"Unknown flag codes: {bad_codes}. Valid codes: {sorted(self.flag_codes)}"
            )
        if self.brief is None and out.fit:
            raise ModelRetry("There is no brief, so `fit` must be empty.")
        allowed = self.brief.priorities if self.brief else []
        bad_priorities = sorted({p.priority for p in points if p.priority and p.priority not in allowed})
        if bad_priorities:
            raise ModelRetry(f"Unknown priority: {bad_priorities}. Valid priorities: {allowed}")
        return out

    async def run(self, ctx: NodeContext, dossier: Dossier) -> DossierReview:  # type: ignore[override]
        """One guard-railed model call; exhausted retries fail the node (no fallback)."""
        citables = review_citables(dossier)
        out, extra = await call_structured(
            registry=_registry(ctx.services),
            profile_name=self.profile,
            output_type=ReviewOut,
            system_prompt=self._system_prompt(),
            user_message=render_review_context(dossier, show_stances=self.show_stances),
            validate=lambda o: self._guard_rail(o, citables),
        )
        return DossierReview(
            summary=out.summary,
            fit=out.fit,
            gaps=out.gaps,
            flags=out.flags,
            provenance=Provenance(
                lens_version=self.code_version(),
                input_hashes=ctx.input_hashes,
                prompt_hash=self._prompt_hash(),
                **extra,
            ),
        )
