"""Verdict and dossier models: the auditable output contract of every lens.

See documentation/design/core.md, Verdicts and dossiers.
"""

from datetime import date
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .types import CandidateRef
from .units import Unit

Stance = Literal[-2, -1, 0, 1, 2]
"""Ordinal stance; the domain layer supplies the labels (e.g. bearish..bullish)."""
Conviction = Literal["low", "medium", "high"]
"""Three-level conviction; never a 0-100 number from an LLM."""
LensStatus = Literal["ok", "abstained", "failed"]
"""A lens ran and judged (ok), declined to judge (abstained), or errored (failed)."""


class _Model(BaseModel):
    """Base for verdict models: immutable and strict about unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Claim(_Model):
    """A statement a lens makes, with the citable ids (see citations.py) that support it."""

    text: str
    direction: Literal[1, -1]  # supports (1) or undermines (-1) a positive stance
    cites: list[str] = Field(min_length=1)


class Flag(_Model):
    """A machine-readable warning raised by a lens; `veto` flags are acted on by aggregators."""

    severity: Literal["info", "warn", "veto"]
    code: str
    text: str
    cites: list[str] = []


class Provenance(_Model):
    """How a verdict was produced, for audit and backtesting."""

    lens_version: str  # the lens class's `code_version()`
    input_hashes: dict[str, str] = {}
    model: str | None = None  # AI lenses only
    model_settings: dict[str, Any] = {}
    prompt_hash: str | None = None
    variant: str | None = None
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    as_of: date | None = None
    backtest_valid: bool = True  # False if inputs may leak information from after `as_of`
    stance_samples: list[Stance] = []  # AI lenses: the stance of each sampled run, in order
    # Cited field path (`input.field`; for a cited frame `input.column`) -> its unit, so the run
    # view formats cited values from the index alone (core.md, Units).
    cite_units: dict[str, Unit] = {}
    glossary_terms: list[str] = []  # AI lenses: glossary entry ids injected into the prompt, sorted; empty when use_glossary is off


class LensVerdict(_Model):
    """One lens's assessment of one candidate. Output contract of `LensNode`."""

    lens: str
    status: LensStatus
    stance: Stance | None = None  # the label shown to humans
    conviction: Conviction | None = None
    # Continuous stance that aggregators use, computed by the framework, never stated by an
    # LLM: the mean of an AI lens's sampled stances, or a deterministic lens's interpolated
    # score; `float(stance)` when the lens supplies nothing finer.
    stance_mean: float | None = Field(default=None, ge=-2, le=2)
    # How unstable the stance is (e.g. std dev of the samples); None means not measured.
    stance_spread: float | None = Field(default=None, ge=0)
    coverage: float = Field(ge=0, le=1)  # computed by the framework, never by an LLM
    input_sufficiency: dict[str, float] = {}  # per-input sufficiency behind `coverage`
    score: float | None = None  # deterministic lenses only
    components: dict[str, float] = {}
    claims: list[Claim] = []
    flags: list[Flag] = []
    error: str | None = None  # failure message, or the abstain reason
    provenance: Provenance

    @model_validator(mode="after")
    def _check_status(self) -> Self:
        """`ok` requires stance, conviction and stance_mean; other statuses carry no stance."""
        if self.status == "ok":
            if self.stance is None or self.conviction is None or self.stance_mean is None:
                raise ValueError("status 'ok' requires stance, conviction and stance_mean")
        elif (self.stance, self.stance_mean, self.stance_spread) != (None, None, None):
            raise ValueError(
                f"status {self.status!r} must not have a stance, stance_mean or stance_spread"
            )
        return self


class Dossier(_Model):
    """All lens verdicts for one candidate plus the aggregator's combined view."""

    candidate: CandidateRef
    verdicts: list[LensVerdict]
    overall_stance: float | None
    confidence: float  # computed, never LLM-reported; equals `evidence_share`
    weights: dict[str, float]  # lens -> effective weight used
    agreement: float | None
    # Plain weighted average of the ok stances (None if no ok verdict): which way the panel
    # leans, regardless of how much evidence arrived.
    direction: float | None = None
    # Share of the panel's possible evidence weight that arrived, in [0, 1]; overall_stance
    # is `direction * evidence_share` under the default aggregator.
    evidence_share: float = 0.0
    coverage: dict[str, LensStatus]  # lens -> status
    flags: list[Flag]


class AssessmentBrief(_Model):
    """What the human wants from an assessment, passed to the post-panel reviewer.

    See documentation/design/core.md, Assessment brief and post-panel review.

    Args:
        purpose: why the candidates are being assessed.
        horizon: the time frame the assessment should hold for, if any.
        priorities: what matters most; `ReviewPoint.priority` must be one of these.
        out_of_scope: topics the review must not weigh.
        extra: domain-specific facts (e.g. constraints) as plain strings.
    """

    purpose: str
    horizon: str | None = None
    priorities: list[str] = []
    out_of_scope: list[str] = []
    extra: dict[str, str] = {}


class ReviewPoint(_Model):
    """One cited observation in a `DossierReview`.

    `priority`, when set, must be one of the brief's priorities; the reviewer node checks
    that: the output schema cannot validate against run data.
    """

    text: str
    cites: list[str] = Field(min_length=1)
    priority: str | None = None


class DossierReview(_Model):
    """The reviewer's read of a dossier against the brief (never a number used in scoring).

    See documentation/design/core.md, Assessment brief and post-panel review.

    Args:
        fit: how the dossier fits the brief.
        gaps: what additional evidence would change the view.
        flags: warnings, restricted by the reviewer node to a closed list of codes.
    """

    summary: str
    fit: list[ReviewPoint] = []
    gaps: list[ReviewPoint] = []
    flags: list[Flag] = []
    provenance: Provenance
