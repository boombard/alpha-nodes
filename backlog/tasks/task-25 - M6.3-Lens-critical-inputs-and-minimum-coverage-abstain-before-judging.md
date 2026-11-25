---
id: TASK-25
title: 'M6.3 Lens critical inputs and minimum coverage: abstain before judging'
status: Done
assignee: []
created_date: '2026-11-24T08:05:27Z'
updated_date: '2026-11-25T23:09:38Z'
labels:
  - core
  - ui
milestone: m-5
dependencies:
  - TASK-22
references:
  - documentation/design/core.md
type: feature
ordinal: 49500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A framework-enforced "don't judge without this": a lens may name inputs it cannot judge without, and a minimum coverage. When either isn't met, the lens returns an `abstained` verdict naming the reason **before** `assess` runs, so an AI lens spends no LLM call. Origin (2026-11-24): the toy AI safety lens said "high conviction" while its key evidence was missing. M6's AI lenses declare `annual_fundamentals` critical. No dependencies; runs alongside M6.1 and M6.2. Spec: `documentation/design/core.md` (Verdicts and dossiers: the "Planned (TASK-25)" bullet and the coverage principles).

## Files
- Modify:
  - `packages/lensgraph/src/lensgraph/lens.py`: `critical_inputs`, `min_coverage`, the pre-assess abstain in `LensNode.run`
  - `packages/lensgraph/tests/toy/safety_lens.py`: `critical_inputs = frozenset({"tox_notes"})`
  - `packages/lensgraph/tests/test_e2e_toy.py`, `packages/lensgraph/tests/test_panel_e2e.py` and other toy expectations that change because S2's safety lens now abstains (only expectations; no behaviour changes elsewhere)
  - `packages/lensgraph-ui/src/pages/Candidate.tsx`: an abstained verdict's `error` shows as an info alert `Abstained: <reason>`, not a red `Error:`; plus its unit test, the regenerated `fixtures/toy-run.json` if the toy run changes, and the committed bundle (`pnpm -C packages/lensgraph-ui bundle`)
  - `documentation/design/core.md`: replace the "Planned (TASK-25)" bullet with the rule as built (Verdicts and dossiers)
- Test: `packages/lensgraph/tests/test_lens.py`, `packages/lensgraph/tests/test_ai_lens.py`

## Interfaces
Consumes: `LensNode`, `AINode`, `input_sufficiency`, `LensVerdict` (M2); `build_plan` / `ParamsError` handling of node param validation (M1/M3).

Produces:
```python
class LensNode(Node):
    critical_inputs: frozenset[str] = frozenset()   # a param (pydantic field); subclasses override the default
    min_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    # model_validator: a name not in all_inputs() -> ValueError naming it and the known inputs,
    #   so a typo is a ParamsError at plan time (same path as weight_overrides)
    # run(): after coverage and input_sufficiency, before assess():
    #   - any critical input with sufficiency 0 -> abstained, error "critical input '<name>' unavailable"
    #     (several: the first in sorted order, the rest counted: "... (+1 more)")
    #   - else coverage < min_coverage -> abstained, error "coverage 0.40 below minimum 0.60"
    #   the verdict keeps the computed coverage and input_sufficiency; stance, conviction, claims None/empty;
    #   provenance has lens_version and input_hashes only (no model call happened)
```
Abstained, not failed: missing data is a legitimate outcome and the aggregator already gives abstentions weight 0.

## Steps
- [ ] Write the failing tests:
  - `test_lens.py::test_critical_input_absent_abstains_without_assess` (an `assess` that raises if called), `test_critical_input_below_depth_minimum_abstains`, `test_min_coverage_abstains_with_reason`, `test_above_thresholds_judges_as_before`, `test_unknown_critical_input_rejected` (`ValidationError` naming the known inputs), `test_critical_inputs_settable_per_run` (a param: changes the memo key).
  - `test_ai_lens.py::test_ai_lens_abstains_without_model_call` (a `FunctionModel` that fails the test if invoked; `SafetyLens` with `tox_notes` `Absent`).
  - Toy: S2's safety verdict is `abstained` with error `critical input 'tox_notes' unavailable`; its dossier rests on the growth lens alone (update the expected evidence share).
  - UI unit test: an abstained verdict renders `Abstained:` in an info alert; a failed one still renders `Error:`.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_lens.py packages/lensgraph/tests/test_ai_lens.py -q`. Expected: FAIL.
- [ ] Implement; update the toy expectations, the UI and core.md.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`, `pnpm -C packages/lensgraph-ui test`, `pnpm -C packages/lensgraph-ui typecheck`. Expected: PASS.
- [ ] Commit: `feat(lensgraph): lens critical inputs and minimum coverage abstain before judging`.

Out of scope: suspect rows lowering sufficiency (core.md mentions it; not built); treating a result model with all-None fields as insufficient (a later refinement; M6 lenses use the `annual_fundamentals` frame, whose length is its depth).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 LensNode.critical_inputs and min_coverage are params; unknown critical input names are rejected at plan time
- [x] #2 An unmet critical input or coverage below the minimum gives an abstained verdict naming the reason, before assess (no LLM call)
- [x] #3 Toy SafetyLens declares tox_notes critical; S2 abstains and toy expectations are updated
- [x] #4 The run view shows an abstain reason as an info alert, not an error; bundle rebuilt
- [x] #5 core.md documents the rule as built
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
Worker: dispatch ctx_13d3c5d47f07, worktree task-25 (Orca run run_743fda9ec0e6)
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker: LensNode.critical_inputs (frozenset param, validated against all_inputs at plan time) and min_coverage (0..1); LensNode.run abstains before assess (no LLM call) with 'critical input <name> unavailable' (+N more) or 'coverage X below minimum Y', keeping coverage/input_sufficiency, provenance lens_version + input_hashes only. Toy SafetyLens declares tox_notes critical; S2 safety abstains, dossier rests on growth (evidence_share 0.25). Run view shows abstained reason as info alert 'Abstained:'; fixture and bundle regenerated; core.md updated. Commits dffc6ef + 7b08656 (review fix) - squash on landing. Evidence: pytest 860 passed, ruff/pyright clean, pnpm test 55 passed, typecheck clean. Coordinator verdict: approve; one review round (removed a dead test-helper branch). Rulings: critical input reason wins over min_coverage; test_absent_optional_input_rendered_not_available_and_not_citable passes critical_inputs=[] to keep exercising the optional-absent path; test_panel_e2e/test_ai_lens/fixture/bundle touched beyond listed toy files (expectations/regen only). Open: none.
Landed 35b51ae (squashed) on main
<!-- SECTION:FINAL_SUMMARY:END -->
