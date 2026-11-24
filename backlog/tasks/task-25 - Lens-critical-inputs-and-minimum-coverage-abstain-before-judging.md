---
id: TASK-25
title: 'Lens critical inputs and minimum coverage: abstain before judging'
status: To Do
assignee: []
created_date: '2026-11-24T08:05:27Z'
labels:
  - core
  - sketch
milestone: m-5
dependencies:
  - TASK-22
references:
  - documentation/design/core.md
type: feature
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sketch (noted 2026-11-24, from reviewing S2's safety verdict in the toy report): the AI safety lens said "high conviction" while its key evidence (toxicity notes) was entirely missing. The framework only softened this through coverage (0.5), and only because the prompt told the model the data was missing. Lenses need a framework-enforced way to say "without this input, don't judge". Detail it when planning M6, where the real AI lenses arrive (TASK-13).

## Scope sketch
- `LensNode` gains two ClassVars, overridable per run as params (so they are in the memo key):
  - `critical_inputs: ClassVar[frozenset[str]] = frozenset()`: input names whose sufficiency must be > 0, i.e. present, non-empty and at least the depth minimum.
  - `min_coverage: ClassVar[float] = 0.0`: the lowest coverage at which the lens judges at all.
- In `LensNode.run`, after coverage is computed and **before** `assess` (so no LLM call is spent), if a critical input has sufficiency 0 or coverage < min_coverage, return an `abstained` verdict with `error` naming the reason (e.g. `"critical input 'tox_notes' unavailable"` / `"coverage 0.40 below minimum 0.60"`) and the computed coverage and input_sufficiency. It is abstained, not failed: missing data is a legitimate outcome, and the aggregator already gives abstentions weight 0.
- The run view shows the abstain reason on the verdict card.
- Validation at plan time: a `critical_inputs` name that isn't one of the lens's inputs is a GraphError (no silent typos).
- Toy: SafetyLens declares `critical_inputs={"tox_notes"}`, so S2 abstains. Update the toy expectations (S2's dossier then rests on the growth lens alone; evidence share drops).
- Tests: critical input empty gives abstain without calling the model (scripted model asserts it is not called); coverage below minimum abstains; above threshold judges as before; unknown critical input name raises at build_plan.
- core.md, Verdicts and dossiers (coverage principles): document critical inputs and minimum coverage as the framework-level guard against confident verdicts on missing evidence.
<!-- SECTION:DESCRIPTION:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->
