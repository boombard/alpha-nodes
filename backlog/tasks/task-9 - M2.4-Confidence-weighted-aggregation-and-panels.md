---
id: TASK-9
title: M2.4 Confidence-weighted aggregation and panels
status: Done
assignee: []
created_date: '2026-11-23T08:02:59Z'
updated_date: '2026-11-23T23:47:04Z'
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
**Formula changed 2026-11-24 (human decision): evidence share replaces the k-shrink**, because a fixed k over-shrank small panels and made results depend on panel size. `overall = direction × evidence_share`, with `evidence_share = Σw / W_max`. See core.md, Verdicts and dossiers. The k version below is kept for history; TASK-16 may offer it as an alternative policy.

Original formula, applied to ok verdicts only:
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
- [x] #1 ShrunkMeanAggregator matches the worked example exactly (evidence-share formula, decided 2026-11-24: direction 1.181818, evidence_share 0.6875, overall 0.8125)
- [x] #2 All-failed/abstained candidates give overall None, confidence 0 without error
- [x] #3 Thin coverage lowers confidence; VetoAggregator forces -2 on veto flags
- [x] #4 Toy panel e2e (growth + safety lens) produces correct dossiers and caches on rerun
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
Worker: dispatch ctx_e5b1bf3221d6, worktree task-9

Back to In Progress (human decision, 2026-11-24): default aggregation switched to evidence share (overall = direction x evidence_share); Dossier gains direction and evidence_share; k removed. Sent to the worker.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker (Sonnet, dispatch ctx_e5b1bf3221d6, branch boom/task-9, 3 commits 730590e..2955ded): Aggregator (consumes_verdicts; Absent lens becomes a failed verdict), ShrunkMeanAggregator (default formula using stance_mean; evidence share since round 2), VetoAggregator (forces -2 on qualifying veto flags), Panel, panel_registry, dossiers(), RunSpec.panel. ACs 1-4 met (test_combine_worked_example; test_all_failed_or_abstained, which is Review Focus 5, and test_single_ok_verdict_agreement_none; test_thin_coverage_lowers_confidence, test_veto_forces_minus_two; test_panel_e2e_toy, test_panel_rerun_cached, test_profile_switch_reruns_only_ai_and_dossier). Coordinator re-ran checks: pytest 245 passed, ruff clean, pyright 0 errors; S1's dossier checked by hand against the formula.
Coordinator review, one fix round: (1) Node.code_version now hashes the source of every Node class in the MRO. Before, editing a base class (aggregation formula, DeterministicLens, AINode) left subclasses' cached outputs silently stale; this was a latent TASK-1 bug, and core.md Memoization is updated. (2) A failed lens uses its lens_name key, consistent across candidates. (3) arun auto-wraps the registry when RunSpec.panel is set. (4) Empty targets without a panel raise ParamsError.
Round 2 (human decision after the shrinkage discussion): evidence-share formula. direction = Σw·s/Σw; evidence_share = Σw/W_max (W_max = Σ panel lens_weight × max conviction factor); overall = direction × evidence_share; confidence = evidence_share; k removed. Dossier gains direction and evidence_share; core.md updated. Tests: worked example (direction 1.181818, share 0.6875, overall 0.8125), perfect small panel not shrunk, panel-size independence. Coordinator verified.
Rulings: RunSpec.targets defaults to []; dossiers() returns candidate (plan) order; lens_names falls back to the node name for a lens without lens_name.

M2 DEMO GATE (evidence-share formula; toy panel: growth = deterministic, safety = AI on a scripted test model that always answers stance +1, high conviction)
S1: overall 0.410, confidence (evidence share) 0.583, direction 0.703. growth ok (stance 0, stance_mean 0.306, low, coverage 1.0, weight 0.5); safety ok (stance 1, high, coverage 0.667 = tox_notes 1 of 3, weight 0.667).
S2: overall 0.355, confidence 0.500, direction 0.709. growth ok (stance_mean 0.418); safety ok but coverage 0.5 (no tox notes), weight 0.5.
S3: overall null, confidence 0.0, direction null. growth and safety both failed: upstream 'assay_clean' failed: ContractViolation: raw is missing columns ['od600'].
Full indented JSON: the worker's demo.txt (printed by test_panel_e2e_toy -s).
Landed ea148d8..ea148d8 on main (worker commits squashed into one).
<!-- SECTION:FINAL_SUMMARY:END -->
