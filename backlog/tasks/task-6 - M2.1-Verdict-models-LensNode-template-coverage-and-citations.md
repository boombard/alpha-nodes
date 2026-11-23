---
id: TASK-6
title: M2.1 Verdict models, LensNode template, coverage and citations
status: To Do
assignee: []
created_date: '2026-11-23T08:02:58Z'
labels:
  - core
  - contracts
milestone: m-1
dependencies:
  - TASK-5
references:
  - documentation/design/core.md
priority: high
type: feature
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Contracts task for M2. Sequential: task-7, task-8 and task-9 build on these names. Spec: `documentation/design/core.md`, sections Verdicts and dossiers and AI nodes (citable ids).

## Files
- Create: `packages/lensgraph/src/lensgraph/{verdict,lens,citations}.py`
- Modify:
  - `packages/lensgraph/src/lensgraph/graph.py`: append `lens_dependency_rule` to `GRAPH_RULES`.
  - `packages/lensgraph/src/lensgraph/__init__.py`: exports.
- Test: `packages/lensgraph/tests/{test_verdict,test_lens,test_citations}.py`

## Interfaces
Consumes (M1): `Node`, `NodeContext`, `Failed`, `Absent`, `ContractViolation`, `GraphError`, `GRAPH_RULES`, `run`, and `RunSpec` (for one integration test).

Produces:
```python
# verdict.py  (frozen, extra="forbid")
Stance = Literal[-2, -1, 0, 1, 2]; Conviction = Literal["low", "medium", "high"]
LensStatus = Literal["ok", "abstained", "failed"]
class Claim(BaseModel): text: str; direction: Literal[1, -1]; cites: list[str] = Field(min_length=1)
class Flag(BaseModel): severity: Literal["info", "warn", "veto"]; code: str; text: str; cites: list[str] = []
class Provenance(BaseModel):
    lens_version: str; input_hashes: dict[str, str] = {}; model: str | None = None
    model_settings: dict[str, Any] = {}; prompt_hash: str | None = None; variant: str | None = None
    attempts: int = 0; input_tokens: int = 0; output_tokens: int = 0
    as_of: date | None = None; backtest_valid: bool = True
class LensVerdict(BaseModel):
    lens: str; status: LensStatus; stance: Stance | None = None; conviction: Conviction | None = None
    coverage: float = Field(ge=0, le=1); input_sufficiency: dict[str, float] = {}
    score: float | None = None; components: dict[str, float] = {}
    claims: list[Claim] = []; flags: list[Flag] = []; error: str | None = None; provenance: Provenance
    # model_validator: status=="ok" requires stance and conviction; otherwise stance is None
class Dossier(BaseModel):
    candidate: CandidateRef; verdicts: list[LensVerdict]; overall_stance: float | None
    confidence: float; weights: dict[str, float]; agreement: float | None
    coverage: dict[str, LensStatus]; flags: list[Flag]; summary: str | None = None

# lens.py
class DepthRequirement(BaseModel): desired: int; minimum: int = 1        # measured as len(value)
class LensAssessment(BaseModel):
    status: Literal["ok", "abstained"]; stance: Stance | None = None; conviction: Conviction | None = None
    score: float | None = None; components: dict[str, float] = {}; claims: list[Claim] = []
    flags: list[Flag] = []; abstain_reason: str | None = None; provenance_extra: dict[str, Any] = {}
def input_sufficiency(value: Any, req: DepthRequirement | None) -> float
class LensNode(Node):
    lens_name: ClassVar[str]; output = LensVerdict
    depth: ClassVar[dict[str, DepthRequirement]] = {}; input_weights: ClassVar[dict[str, float]] = {}
    def assess(self, ctx: NodeContext, citables: frozenset[str], **inputs: Any) -> LensAssessment: ...  # may be async
    async def run(self, ctx, **inputs) -> LensVerdict      # template method: do not override
    def on_upstream_failure(self, ctx, failure) -> LensVerdict   # status="failed", coverage=0.0

# citations.py
def citable_ids(inputs: Mapping[str, Any]) -> frozenset[str]

# graph.py
class LensDependencyError(GraphError): ...
def lens_dependency_rule(classes: Mapping[str, type[Node]]) -> None
```
Semantics:
- **`input_sufficiency`:**
  - `None`, `Absent`, or an empty value (frame/list/dict) gives 0.0.
  - With no requirement, the value gives 1.0.
  - A length below `minimum` gives 0.0. Otherwise the result is `min(1.0, len/desired)`.
- **`LensNode.run`:**
  1. Compute per-input sufficiency over `all_inputs()`. Coverage is the mean weighted by `input_weights` (default weight 1).
  2. Compute `citables = citable_ids(non-Absent inputs)`.
  3. Await or call `assess`.
  4. Any claim or flag citation outside `citables` raises `ContractViolation`. That is a programming error in a deterministic lens; AI lenses check citations earlier.
  5. Build a `LensVerdict` with `lens=lens_name` and `Provenance(lens_version=code_version(), input_hashes=ctx.input_hashes, **assessment.provenance_extra)`. An abstained assessment's `abstain_reason` goes into `error`.
- **`on_upstream_failure`:** `error=f"upstream '{failure.origin}' failed: {failure.error}"` and empty provenance hashes.
- **`citable_ids`:** produces:
  - the input name `n` for every input
  - `n.<field>` for each scalar (non-container) field of a BaseModel value
  - `n[<id>]` for each item of a list of models that have an `id` attribute

  DataFrames contribute only `n`.
- **`lens_dependency_rule`:** raises `LensDependencyError` if any class whose `all_inputs()` includes a `LensNode` subclass has `consumes_verdicts` False.

## Steps
- [ ] Write the failing tests:
  - `test_verdict_ok_requires_stance_and_conviction`
  - `test_verdict_failed_has_no_stance`
  - `test_claim_requires_a_cite`
  - `test_input_sufficiency`, parametrized with `DepthRequirement(desired=8, minimum=3)`: a list of length 4 gives 0.5; length 2 gives 0.0; length 10 gives 1.0; `Absent` gives 0.0; `[]` gives 0.0; no requirement with `[1]` gives 1.0.
  - `test_lens_coverage_weighted`: inputs a (sufficiency 1.0, weight 3) and b (0.0, weight 1) give coverage 0.75.
  - `test_lens_upstream_failure_verdict`: `status="failed"`, error names the origin, coverage 0.
  - `test_claim_citing_unknown_id_raises_contract_violation`
  - `test_abstained_assessment_maps_reason_to_error`
  - `test_citable_ids_model_fields_list_items_frames`
  - `test_lens_on_lens_rejected`
  - `test_consumes_verdicts_allowed`
  - `test_toy_lens_runs_end_to_end`: a minimal test-local lens over `growth_rate` produces an ok verdict for S1 and a failed verdict (status `recovered` in `NodeResult`) for S3, via `run(RunSpec(...))`.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_verdict.py packages/lensgraph/tests/test_lens.py packages/lensgraph/tests/test_citations.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): verdict models, LensNode template, coverage and citations`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Claim, Flag, Provenance, LensVerdict, Dossier match Interfaces with validators
- [ ] #2 LensNode computes depth-aware coverage and citable ids; assess() is the only extension point
- [ ] #3 Upstream failure yields a failed verdict naming the origin
- [ ] #4 Lens-on-lens dependencies rejected at graph build unless consumes_verdicts
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
