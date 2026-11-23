---
id: TASK-6
title: M2.1 Verdict models, LensNode template, coverage and citations
status: Done
assignee: []
created_date: '2026-11-23T08:02:58Z'
updated_date: '2026-11-23T09:51:32Z'
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
- [x] #1 Claim, Flag, Provenance, LensVerdict, Dossier match Interfaces with validators
- [x] #2 LensNode computes depth-aware coverage and citable ids; assess() is the only extension point
- [x] #3 Upstream failure yields a failed verdict naming the origin
- [x] #4 Lens-on-lens dependencies rejected at graph build unless consumes_verdicts
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 `uv run pytest` passes (whole workspace)
- [x] #2 `uv run ruff check` and `uv run pyright` are clean
- [x] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [x] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Worker: dispatch ctx_4946200e3cf6, worktree task-6

Back to In Progress (human approved 2026-11-23): add stance_mean, stance_spread and Provenance.stance_samples before landing, so AI sampling (TASK-8) and interpolated thresholds (TASK-7) have somewhere to record them, and the aggregator uses stance_mean. Sent to the worker.

Old session stopped after an API 529 and a cleared context; fresh worker dispatch ctx_521bd60ed2fe in worktree task-6 for the stance fields.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker (Sonnet, dispatch ctx_4946200e3cf6, branch boom/task-6, 4 commits 677f6c9..ef3b2b1): verdict.py (Claim, Flag, Provenance, LensVerdict with the status/stance validator, Dossier), lens.py (DepthRequirement, LensAssessment, input_sufficiency, the LensNode template), citations.py (citable_ids), and lens_dependency_rule plus LensDependencyError appended to GRAPH_RULES; public exports added. ACs 1-4 met (test_verdict_*, test_claim_requires_a_cite; test_lens_coverage_weighted, test_citable_ids_*; test_lens_upstream_failure_verdict; test_lens_on_lens_rejected, test_consumes_verdicts_allowed; the toy e2e shows S3 recovered). Coordinator re-ran checks: pytest 150 passed, ruff clean, pyright 0 errors.
Coordinator review, one fix round: (1) a sync assess now runs via asyncio.to_thread (LensNode.run is async, so a sync assess used to block the event loop and serialize everything); a timing test proves two sync lenses run concurrently. (2) provenance_extra setting lens_version or input_hashes now raises ContractViolation, instead of a raw TypeError or a silent audit override.
Round 2 (asked for by the human after the aggregation research): LensVerdict gains stance_mean (in [-2, 2]; what aggregators use; framework-computed; the template defaults it to float(stance)) and stance_spread (>= 0; None = not measured). Provenance gains stance_samples. An ok verdict requires stance_mean; non-ok verdicts and assessments carry neither (ContractViolation in the template). core.md LensVerdict block updated. Two worker sessions stopped on API 529 Overloaded before changing anything, so the coordinator implemented this round directly (TDD, commit ef3b2b1, at the human's request). It merges cleanly with main.
Rulings: (1) The worker edited core.md (outside the Files list) to match the task interface: Dossier has no run_id, and confidence is float (0.0 if no ok lens). The run index can carry run_id alongside each dossier; re-add the field if dossiers travel alone (reports, API). Decide before TASK-9. (2) input_sufficiency treats values without a length (e.g. float) as 1.0 when present, ignoring any depth requirement. (3) Str inputs measure depth in characters. (4) Verdict models are frozen with extra=forbid via a private _Model base. (5) lens_dependency_rule imports LensNode lazily (import cycle). (6) Only the first colliding provenance key is named in the error.
Open points: commit 677f6c9 is not pyright-clean on its own (squash when landing).
Landed 6f25b46..6f25b46 on main (4 commits squashed into one at the human's request).
<!-- SECTION:FINAL_SUMMARY:END -->
