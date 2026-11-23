---
id: TASK-9
title: M2.4 Confidence-weighted aggregation and panels
status: To Do
assignee: []
created_date: '2026-11-23T08:02:59Z'
labels:
  - core
milestone: m-1
dependencies:
  - TASK-7
  - TASK-8
references:
  - documentation/design/core.md
type: feature
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Integration task closing M2. Spec: `documentation/design/core.md`, section Verdicts and dossiers (aggregation formula, D18).

**Scope kept simple on purpose (human decision, 2026-11-23).** Implement only the baseline below. Overlap discounts between lenses that share data, configurable veto caps, a subjective-logic aggregator and calibration are deferred to TASK-16. Keep `Aggregator.combine` pure and the aggregator pluggable (`panel_registry(..., aggregator_cls=...)`), so TASK-16 can add policies without changing this interface.

## Files
- Create: `packages/lensgraph/src/lensgraph/{aggregate,panel}.py`
- Modify: `packages/lensgraph/src/lensgraph/run.py` (`RunSpec.panel`), `packages/lensgraph/src/lensgraph/__init__.py`
- Test: `packages/lensgraph/tests/test_aggregate.py`, `packages/lensgraph/tests/test_panel_e2e.py`

## Interfaces
Consumes:
- `LensVerdict`, `Dossier`, `Flag`, `Conviction` (task-6)
- `GrowthLens` (task-7)
- `SafetyLens`, `ProfileRegistry`, `scripted_model` fixture (task-8)
- `run`, `RunSpec`, `NodeRegistry` (M1)

Produces:
```python
class Aggregator(Node):
    name = "dossier"; output = Dossier; consumes_verdicts = True
    lens_weights: dict[str, float] = {}; k: float = 1.0
    conviction_factors: dict[str, float] = {"low": 0.5, "medium": 0.75, "high": 1.0}
    def run(self, ctx, **verdicts: LensVerdict | Absent) -> Dossier   # Absent -> failed LensVerdict(error=reason)
    def combine(self, candidate: CandidateRef, verdicts: list[LensVerdict]) -> Dossier   # pure
class ShrunkMeanAggregator(Aggregator): ...          # the default formula
class VetoAggregator(ShrunkMeanAggregator):
    veto_codes: list[str] | None = None              # None = any flag with severity "veto"
class Panel(BaseModel): lenses: list[str]; aggregator: str = "dossier"
def panel_registry(panel: Panel, registry: NodeRegistry,
                   aggregator_cls: type[Aggregator] = ShrunkMeanAggregator) -> NodeRegistry
    # copy of registry + an aggregator subclass named panel.aggregator with optional_inputs={l: l for l in lenses}
def dossiers(result: RunResult) -> list[Dossier]     # in candidate order
# run.py: RunSpec.panel: Panel | None = None; when set and targets empty -> targets = [panel.aggregator]
```
Formula, applied to ok verdicts only:
- weight: `w_i = lens_weights.get(lens, 1) * coverage_i * conviction_factors[conviction_i]`
- overall stance: `overall = Σ w_i·s_i / (Σ w_i + k)`, or `None` if there are no ok verdicts
- `s_i` is the verdict's `stance_mean` (added by TASK-6's follow-up; the LensNode template sets it to `float(stance)` when a lens doesn't supply one, so the worked example below is unchanged).
- confidence: `Σ w_i / (Σ w_i + k)`, or `0.0` if there are no ok verdicts
- agreement: the weighted std dev `sqrt(Σ w_i (s_i − m)² / Σ w_i)`, where `m = Σ w_i s_i / Σ w_i`. It is `None` if there are fewer than 2 ok verdicts.
- **Other fields:**
  - `weights`: holds `w_i`, with 0.0 for non-ok verdicts.
  - `coverage`: maps each lens to its status.
  - `flags`: the union of all verdicts' flags.
- `VetoAggregator`: when a qualifying flag is present, `overall_stance = -2.0`.

## Steps
- [ ] Write the failing tests:
  - `test_combine_worked_example`: lens a has stance 2, coverage 1.0, conviction high; lens b has stance -1, coverage 0.5, conviction medium; k=1. Expect `weights == {"a": 1.0, "b": 0.375}`, `overall_stance ≈ 0.684211`, `confidence ≈ 0.578947`, `agreement ≈ 1.336085` (`pytest.approx(rel=1e-5)`).
  - `test_all_failed_or_abstained`: `overall_stance is None`, `confidence == 0.0`, `agreement is None`, and no exception.
  - `test_single_ok_verdict_agreement_none`
  - `test_lens_weight_param_changes_result`
  - `test_veto_forces_minus_two`
  - `test_absent_lens_input_becomes_failed_verdict`
  - `test_thin_coverage_lowers_confidence`: identical stances, with coverage 1.0 vs 0.5, give lower confidence and a lower |overall| for the thin one.
  - `test_panel_e2e_toy`: `Panel(lenses=["growth_lens", "safety_lens"])` with a scripted model that always gives stance 1. Expected:
    - S1: dossier with 2 ok verdicts.
    - S2: `safety` coverage < 1 and confidence < S1's.
    - S3: both verdicts failed and `overall_stance is None`.
  - `test_panel_rerun_cached`: every memoizable node is a cache hit.
  - `test_profile_switch_reruns_only_ai_and_dossier`
- [ ] Run `uv run pytest packages/lensgraph/tests/test_aggregate.py packages/lensgraph/tests/test_panel_e2e.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): confidence-weighted aggregation and panels`.

**M2 demo gate (for the human):** put a printed dossier for each of S1, S2 and S3 (JSON, indented) into the task's final summary.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ShrunkMeanAggregator matches the worked example exactly
- [ ] #2 All-failed/abstained candidates give overall None, confidence 0 without error
- [ ] #3 Thin coverage lowers confidence; VetoAggregator forces -2 on veto flags
- [ ] #4 Toy panel e2e (growth + safety lens) produces correct dossiers and caches on rerun
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
