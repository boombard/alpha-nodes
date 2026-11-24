---
id: TASK-20
title: M3.3 Post-panel dossier reviewer
status: Done
assignee: []
created_date: '2026-11-23T23:51:14Z'
updated_date: '2026-11-24T01:29:57Z'
labels:
  - core
milestone: m-2
dependencies:
  - TASK-18
references:
  - documentation/design/core.md
type: feature
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Post-panel reviewer. Runs in parallel with M3.2. Spec: `documentation/design/core.md`, Assessment brief and post-panel review (demote-only, no stance or score, lenses never see the brief).

## Files
- Create: `packages/lensgraph/src/lensgraph/review.py`, `packages/lensgraph/tests/toy/reviewer.py` (toy `DossierReviewer` subclass named `toy_reviewer`), `packages/lensgraph/tests/toy/prompts/reviewer.md.j2`
- Modify:
  - `packages/lensgraph/src/lensgraph/ai.py`: extract the single structured model call (agent build, usage limits, guard-rail wiring, retries-exhausted error, provenance_extra) into a reusable helper used by both `AINode` and the reviewer. `AINode` behaviour is unchanged.
  - `packages/lensgraph/src/lensgraph/verdict.py`: remove `Dossier.summary` (superseded by `DossierReview`).
  - `packages/lensgraph/src/lensgraph/panel.py`: `Panel.reviewer` wiring.
  - `packages/lensgraph/src/lensgraph/__init__.py`: exports.
  - `packages/lensgraph/tests/toy/registry.py`: register `toy_reviewer`; `build_services`' scripted model also answers the reviewer's output schema (choose the answer by the output tool's schema in `AgentInfo`).
  - `packages/lensgraph/tests/toy/toy_run.yaml`: `panel.reviewer: toy_reviewer`, `nodes.review.profile: test`.
  - `documentation/design/core.md`: drop `summary` from the Dossier block; note the reviewer node name and citable ids.
- Test: `packages/lensgraph/tests/test_review.py`

## Interfaces
Consumes (M3.1): `AssessmentBrief`, `ReviewPoint`, `DossierReview`. Earlier: `Dossier`, `LensVerdict`, `Flag`, `Provenance`, `ProfileRegistry`, `LLMProfile`, `guard_rail` machinery, `ModelRetry`, `Panel`, `panel_registry`, `scripted_model` fixture.

Produces:
```python
# ai.py
async def call_structured(*, registry: ProfileRegistry, profile_name: str, output_type: type[BaseModel],
                          system_prompt: str, user_message: str,
                          validate: Callable[[BaseModel], BaseModel]) -> tuple[BaseModel, dict[str, Any]]
    # returns (validated output, provenance_extra without prompt_hash/variant)
# review.py
class ReviewOut(BaseModel): summary: str; fit: list[ReviewPoint] = []; gaps: list[ReviewPoint] = []; flags: list[Flag] = []
def review_citables(dossier: Dossier) -> frozenset[str]
    # "verdict.<lens>" per verdict, "verdict.<lens>.claim[<i>]" per claim (0-based), "flag.<lens>.<code>" per flag
def render_review_context(dossier: Dossier, *, show_stances: bool = True) -> str
class DossierReviewer(Node):
    name: ClassVar[str] = "review"; output = DossierReview; consumes_verdicts = True
    resource = "llm"; inputs = {"dossier": "dossier"}           # panel_registry rebinds to the panel's aggregator
    prompt: ClassVar[Path]; flag_codes: ClassVar[frozenset[str]] = frozenset({"brief_conflict", "evidence_gap"})
    brief: AssessmentBrief | None = None                          # a node param, so it is in the memo key automatically
    profile: str = "dev"; show_stances: bool = True
    async def run(self, ctx: NodeContext, dossier: Dossier) -> DossierReview
    def memo_salt(self, services) -> str                         # profile fingerprint + prompt hash
# panel.py
class Panel(BaseModel): ... reviewer: str | None = None        # registered reviewer class name, or None
    def targets(self) -> list[str]
```
Semantics:
- **No brief, no review:** with `brief=None` the reviewer still summarises, and `fit` must be empty (guard rail).
- **Guard rail** (raise `ModelRetry`): a cite not in `review_citables`; a flag code not in `flag_codes`; a `priority` not in `brief.priorities`; a `fit` point when there is no brief.
- **Brief rendering:** the brief goes in the system prompt (static first), the dossier in the user message. `show_stances=False` omits stance, stance_mean, direction and overall_stance from the rendered dossier, leaving claims, flags, coverage and status (the anchoring guard in core.md).
- **Failed reviews:** retries exhausted fails the node (no fallback). A dossier with no ok verdicts still gets a review (summary of failures; gaps allowed).
- **Wiring:** `panel_registry` registers the reviewer class (looked up by `Panel.reviewer` in the source registry) under name `review` with `inputs = {"dossier": panel.aggregator}`. `Panel.targets() -> list[str]` returns `[aggregator]` plus `"review"` when a reviewer is set. `arun` adopts it in M3.5 (run.py belongs to M3.2 in this wave), so tests here pass `targets` explicitly.
- **Demote-only by construction:** the reviewer's output never feeds the aggregator; acceptance rules that read review flags arrive with campaigns (M7).
- **`DossierReview.provenance`:** `lens_version` = the reviewer's `code_version()`, `input_hashes` = ctx.input_hashes, plus the call's provenance_extra.

## Steps
- [ ] Write the failing tests (`scripted_model` answers; no network):
  - `test_review_citables_from_dossier`
  - `test_review_ok_becomes_dossier_review_with_provenance`
  - `test_unknown_cite_retried_then_ok`
  - `test_unknown_priority_retried`
  - `test_fit_without_brief_rejected`
  - `test_show_stances_false_hides_stances`: rendered context contains no "stance" values, but still contains claims.
  - `test_brief_change_invalidates_review_only`: rerun the toy panel with a different brief; the lens and dossier nodes are cache hits and the review reruns.
  - `test_reviewer_wired_by_panel`: `Panel(lenses=[...], reviewer="toy_reviewer")` produces a review per candidate, including S3 (all lenses failed).
  - `test_ai_lens_unchanged_after_refactor`: the existing test_ai_lens suite passes untouched (no test edits there).
- [ ] Run `uv run pytest packages/lensgraph/tests/test_review.py -q`. Expected: FAIL.
- [ ] Implement (refactor ai.py first, keeping test_ai_lens green).
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): post-panel dossier reviewer`.

**Note from the TASK-18 review:** fix `ReviewPoint`'s docstring in verdict.py. It says the model can't check `priority` "since it doesn't know the brief", but the reviewer's model does see the brief in its system prompt. The real reason is that the output schema can't validate against run data, so the node checks it.

Out of scope: acceptance rules using review flags (M7), macro context inputs (later), repeated sampling (TASK-17).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 DossierReviewer produces a guard-railed DossierReview (no stance or score; cites, flags and priorities validated)
- [x] #2 A brief change reruns only the review; lens and dossier nodes are cache hits
- [x] #3 show_stances=False hides stances from the reviewer's context
- [x] #4 AINode behaviour unchanged after extracting call_structured; Dossier.summary removed
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
Worker: dispatch ctx_2a72d8e780c6, worktree task-20
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker (Sonnet, dispatch ctx_2a72d8e780c6, branch boom/task-20, 2 commits a2571f0..e548ad1): review.py (ReviewOut, review_citables, render_review_context with show_stances, DossierReviewer: brief as a node param, guard rail on cites, flag codes, priorities and fit-without-brief), call_structured extracted in ai.py and shared with AINode, Panel.reviewer and Panel.targets(), panel_registry registers the reviewer as node 'review' fed by the aggregator, Dossier.summary removed, ReviewPoint docstring corrected, toy reviewer and prompt, toy registry and toy_run.yaml updated, core.md updated. ACs 1-4 met (test_review_ok_becomes_dossier_review_with_provenance, test_unknown_cite_retried_then_ok, test_unknown_priority_retried, test_unknown_flag_code_rejected, test_fit_without_brief_rejected; test_brief_change_invalidates_review_only; test_show_stances_false_hides_stances; test_ai_lens.py untouched and green, summary removed; also test_reviewer_wired_by_panel covering all-failed S3). Coordinator re-ran checks: pytest 270 passed, ruff clean, pyright 0 errors; merges cleanly with boom/task-19.
Coordinator review, one fix round: panel_registry raises GraphError when Panel.reviewer isn't a DossierReviewer subclass.
Rulings: the toy reviewer is registered as 'toy_reviewer' and re-registered as 'review'; call_structured's validate is typed Callable[[Any], Any]; show_stances=False also hides agreement and conviction, and renders claim direction as supports/undermines; review.py imports the private _JINJA/_registry helpers from ai.py; the review sets prompt_hash and leaves variant None.
Open points: plangraph.node_kind (TASK-19) labels the reviewer 'other' until TASK-21 maps it to 'reviewer' (noted in TASK-21).
Landed f0cda8f..f0cda8f on main (worker commits squashed into one).
<!-- SECTION:FINAL_SUMMARY:END -->
