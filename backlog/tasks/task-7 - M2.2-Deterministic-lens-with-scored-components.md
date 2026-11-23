---
id: TASK-7
title: M2.2 Deterministic lens with scored components
status: Done
assignee: []
created_date: '2026-11-23T08:02:58Z'
updated_date: '2026-11-23T23:24:15Z'
labels:
  - core
milestone: m-1
dependencies:
  - TASK-6
references:
  - documentation/design/core.md
type: feature
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec: `documentation/design/core.md`, section Deterministic lenses. Runs in parallel with task-8, which touches disjoint files.

## Files
- Create: `packages/lensgraph/src/lensgraph/deterministic.py`, `packages/lensgraph/tests/toy/growth_lens.py`
- Test: `packages/lensgraph/tests/test_deterministic.py`

## Interfaces
Consumes (task-6): `LensNode`, `LensAssessment`, `Claim`, `Stance`, `Conviction`. M1: `run`, `RunSpec`, `NodeRegistry`, toy nodes.

Produces:
```python
class LinearScorer(BaseModel):          # maps a value to [-1, 1], clipped
    lo: float; hi: float; higher_is_better: bool = True
    def __call__(self, value: float) -> float      # lo -> -1, hi -> +1 (reversed if not higher_is_better)
class Component(BaseModel):
    name: str; source: str                          # citable id: "<input>" or "<input>.<field>"
    scorer: LinearScorer; weight: float = 1.0
    claim_template: str = "{name}: {value:.3g}"
class DeterministicLens(LensNode):
    components: ClassVar[list[Component]]
    thresholds: tuple[float, float, float, float] = (-0.6, -0.2, 0.2, 0.6)
    conviction_margins: tuple[float, float] = (0.1, 0.3)
    weight_overrides: dict[str, float] = {}
# tests/toy/growth_lens.py
class GrowthLens(DeterministicLens): name = "growth_lens"; lens_name = "growth"; inputs = {"growth_rate": "growth_rate"}
```
Semantics of `assess`:
1. **Resolve components.** Each component's value comes from its `source`. A missing value, `Absent`, or a non-finite value skips that component.
2. **Abstain** if none remain, with reason `"no components available"`.
3. **Score** = the weighted mean of the scored component values. Weights are `weight_overrides.get(name, component.weight)`, renormalised over the components present. `components` holds the scored values by name.
4. **Stance** from `t = thresholds`: `s < t0` gives -2; `s < t1` gives -1; `s <= t2` gives 0; `s <= t3` gives 1; otherwise 2.
5. **Conviction** from `d`, the distance to the nearest threshold: `d < m0` is low, `d < m1` is medium, otherwise high.
5a. **`stance_mean`** (interpolated thresholds; added 2026-11-23 after the scoring discussion): `stance_mean = float(numpy.interp(s, centres, [-2, -1, 0, 1, 2]))`.
   - Centres: `[t0 - (t1 - t0)/2, (t0 + t1)/2, (t1 + t2)/2, (t2 + t3)/2, t3 + (t3 - t2)/2]`. The defaults give `[-0.8, -0.4, 0, 0.4, 0.8]`. Beyond the outer centres it clamps to ±2.
   - Set it on the `LensAssessment` (`stance_spread` stays None). The integer stance still comes from step 4, so with evenly spaced thresholds `round(stance_mean)` equals the stance.
   - This is plain interpolation: no fuzzy library or vocabulary (see core.md, Deterministic lenses, "Possible future: fuzzy rule bases").
6. **Claims:** one per scored component, with text from `claim_template.format(name=..., value=<raw value>)`, direction +1 if the scored value is at least 0 (else -1), and `cites=[source]`.

## Steps
- [ ] Write the failing tests:
  - `test_linear_scorer`, parametrized over `LinearScorer(lo=0, hi=1)`: 0 gives -1, 0.5 gives 0, 1 gives 1, 2 gives 1 (clipped), -1 gives -1. With `higher_is_better=False`, 0 gives 1.
  - `test_stance_thresholds`, parametrized: -0.7 gives -2, -0.3 gives -1, 0.0 gives 0, 0.3 gives 1, 0.7 gives 2.
  - `test_conviction_from_margin`: 0.25 gives low, 0.45 gives medium, 0.95 gives high.
  - `test_stance_mean_interpolated`, parametrized: 0.19 gives ≈ 0.475 (stance 0), 0.21 gives ≈ 0.525 (stance 1), 0.75 gives ≈ 1.875, 0.95 gives 2.0, 0.0 gives 0.0.
  - `test_stance_mean_monotone`: over 201 evenly spaced scores in [-1, 1], `stance_mean` never decreases, and with the default thresholds `round(stance_mean) == stance`.
  - `test_missing_component_skipped_and_weights_renormalised`
  - `test_all_components_missing_abstains`
  - `test_weight_override_param`: `node_params` set via `build_plan`.
  - `test_claims_cite_component_source`
  - `test_growth_lens_toy_run`: S1 and S2 verdicts ok with claims citing `growth_rate`; S3 verdict `status="failed"`.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_deterministic.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run the tests above, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): deterministic lens with scored components`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 LinearScorer, Component and DeterministicLens behave per thresholds and conviction margins; stance_mean is the monotone interpolation of the score
- [x] #2 Missing components skipped with renormalised weights; none available abstains
- [x] #3 Toy GrowthLens produces ok verdicts citing growth_rate and a failed verdict for S3
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
Worker: dispatch ctx_8b27405c0ca8, worktree task-7
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker (Sonnet, dispatch ctx_8b27405c0ca8, branch boom/task-7, 2 commits ff51744..459fc54): LinearScorer, Component and DeterministicLens (weighted mean of present components with renormalised weights; stance from thresholds; conviction from threshold margins; stance_mean interpolated between threshold centres with numpy.interp), toy GrowthLens, core.md Deterministic lenses updated. ACs 1-3 met (test_linear_scorer, test_stance_thresholds, test_conviction_from_margin, test_stance_mean_interpolated, test_stance_mean_monotone; test_missing_component_skipped_and_weights_renormalised, test_all_components_missing_abstains, test_unusable_values_skipped, test_weight_override_param; test_growth_lens_toy_run, test_claims_cite_component_source). Coordinator re-ran checks: pytest 182 passed, ruff clean, pyright 0 errors.
Coordinator review, one fix round: unknown or negative weight_overrides keys raise ParamsError at build_plan (no silent typos); zero total weight abstains instead of dividing by zero; LinearScorer rejects hi == lo; GrowthLens docstring corrected.
Rulings: (1) round(stance_mean) == stance fails at exact threshold ties (e.g. score -0.6 gives stance -1 and mean -1.5; Python rounds to -2). The coordinator's spec claim was wrong there, so the monotonicity test skips exact half-integer means. (2) Bools and non-numeric values are unusable and skipped; an 'input.field' source resolves only on model inputs. (3) GrowthLens uses LinearScorer(lo=-0.1, hi=0.3). (4) The worker edited core.md (not in the Files list; the DoD requires it). (5) A total weight <= 0 abstains.
Open points: Component.weight itself may still be negative (only overrides are checked); low impact, since components are code, not config.
Landed da62391..da62391 on main (worker commits squashed into one).
<!-- SECTION:FINAL_SUMMARY:END -->
