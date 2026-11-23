---
id: TASK-7
title: M2.2 Deterministic lens with scored components
status: To Do
assignee: []
created_date: '2026-11-23T08:02:58Z'
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
6. **Claims:** one per scored component, with text from `claim_template.format(name=..., value=<raw value>)`, direction +1 if the scored value is at least 0 (else -1), and `cites=[source]`.

## Steps
- [ ] Write the failing tests:
  - `test_linear_scorer`, parametrized over `LinearScorer(lo=0, hi=1)`: 0 gives -1, 0.5 gives 0, 1 gives 1, 2 gives 1 (clipped), -1 gives -1. With `higher_is_better=False`, 0 gives 1.
  - `test_stance_thresholds`, parametrized: -0.7 gives -2, -0.3 gives -1, 0.0 gives 0, 0.3 gives 1, 0.7 gives 2.
  - `test_conviction_from_margin`: 0.25 gives low, 0.45 gives medium, 0.95 gives high.
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
- [ ] #1 LinearScorer, Component and DeterministicLens behave per thresholds and conviction margins
- [ ] #2 Missing components skipped with renormalised weights; none available abstains
- [ ] #3 Toy GrowthLens produces ok verdicts citing growth_rate and a failed verdict for S3
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
