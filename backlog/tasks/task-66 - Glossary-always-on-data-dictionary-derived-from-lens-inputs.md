---
id: TASK-66
title: 'Glossary always on: data dictionary derived from lens inputs'
status: In Review
assignee: []
created_date: '2026-11-26T03:30:50Z'
updated_date: '2026-11-26T03:46:05Z'
labels:
  - core
milestone: m-5
dependencies:
  - TASK-63
references:
  - documentation/design/core.md
type: feature
ordinal: 66000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rework TASK-63's opt-in prompt notes into an always-on **data dictionary** (core.md "Glossary", already
rewritten by the coordinator: implement it as written). Almost every number an AI lens sees is our own version
of a metric, so its definition is part of the evidence. The lens's terms are derived from its inputs' output
contracts at plan build (no hand-kept list), the block lists the exact evidence paths each note covers plus the
entry's `kind`, a field with no entry fails the plan, the glossary loads at plan build instead of import, and the
on/off switch leaves the model profile: one `use_glossary` node param, default true, kept for ablation only.
No finance content (TASK-64 seeds and wires the finance glossary on top of this).

## Files
- Modify: `packages/lensgraph/src/lensgraph/glossary.py` (claims resolution `term_for`, whole-model claims,
  `unresolved_claims`, `dictionary_block` replacing `prompt_block`, `by_field` removed),
  `packages/lensgraph/src/lensgraph/node.py` (`Node.bind_upstream`, no-op),
  `packages/lensgraph/src/lensgraph/graph.py` (`build_plan` calls it with the resolved classes' outputs),
  `packages/lensgraph/src/lensgraph/ai.py` (`glossary` becomes a directory path, `glossary_terms` replaced by
  derived terms + `glossary_concepts`, `use_glossary: bool = True`, `__init_subclass__` check removed),
  `packages/lensgraph/src/lensgraph/llm.py` (drop `LLMProfile.glossary`)
- Modify (test data): `packages/lensgraph/tests/toy/glossary/` (claims covering the toy AI lens's input fields)
- Test: `packages/lensgraph/tests/test_glossary.py`, `packages/lensgraph/tests/test_ai_lens.py`
- Docs: core.md is done; fix it only if implementation shows a wording error (say so in the summary)

## Interfaces

```python
class Node:
    def bind_upstream(self, outputs: Mapping[str, Any]) -> None: ...   # input name -> upstream `output`; no-op

class Glossary:
    def term_for(self, model: type, field: str) -> str | None          # MRO walk: Class.field, then Class
    def unresolved_claims(self, models: Iterable[type]) -> list[str]   # claims naming no class/field in models
    def dictionary_block(self, paths: Mapping[str, list[str]], concepts: Iterable[str] = ()) -> str

class AINode(LensNode):
    glossary: ClassVar[Path | None] = None             # glossary directory; loaded in bind_upstream
    glossary_concepts: ClassVar[frozenset[str]] = frozenset()
    use_glossary: bool = True                          # param; ablation only
```

An AINode with a glossary that was never bound (used outside a plan) raises when its prompt is rendered.
Provenance.glossary_terms keeps its meaning: every id in the block, sorted; empty when ablated.

## Steps
- [ ] Failing tests (glossary): `test_term_for_exact_claim`, `test_term_for_walks_mro_to_base_claim`,
  `test_whole_model_claim_covers_its_fields_only`, `test_frame_columns_resolve` (pandera model),
  `test_duplicate_claim_rejected` (field and whole-model), `test_unresolved_claims_lists_stale_ones`,
  `test_dictionary_block_lists_paths_kind_and_note` (compacted `input.{a, b}`, sorted by id, concepts last),
  `test_dictionary_block_unescapes_dollar`.
- [ ] Failing tests (AI node / plan): `test_dictionary_on_by_default_for_every_profile`,
  `test_profile_has_no_glossary_setting`, `test_uncovered_field_fails_plan_build` (message names lens, input,
  field), `test_optional_input_fields_are_covered`, `test_list_of_models_contract_resolves_item_model`,
  `test_bare_contracts_contribute_no_fields`, `test_bind_uses_replacement_output`,
  `test_unknown_concept_fails_plan_build`, `test_broken_entry_fails_only_plans_with_that_ai_lens`
  (a plan without the AI lens builds), `test_use_glossary_false_omits_block_but_still_checks_coverage`,
  `test_block_is_static_when_an_input_is_absent`, `test_used_note_edit_changes_memo_salt`,
  `test_unused_section_edit_keeps_memo_salt`, `test_provenance_records_glossary_terms`,
  `test_unbound_ai_node_with_glossary_raises`. Replace the TASK-63 opt-in tests these supersede.
- [ ] Run. Expected: FAIL.
- [ ] Implement; update the toy glossary so it covers the toy AI lens's inputs.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS. Regenerate run-view types
  and UI fixtures only if a schema hash check requires it (say so in the summary).
- [ ] Commit: `feat(lensgraph): glossary data dictionary always on, derived from lens inputs`.

Out of scope: finance entries and wiring (TASK-64); a run-wide ablation switch (add when needed); the browser (TASK-65).
Expected side effect: every AI lens's rendered prompt changes, so cached AI verdicts miss once.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An AI lens's dictionary terms are derived from its inputs' output contracts at plan build; there is no hand-kept term list
- [ ] #2 The block lists each entry's exact evidence paths and kind; it is static per lens
- [ ] #3 A field reaching an AI lens without a claim, or an unknown concept id, fails the plan before any model call
- [ ] #4 The glossary loads at plan build, not import; a plan without the AI lens is unaffected by a broken entry
- [ ] #5 LLMProfile has no glossary setting; use_glossary defaults to true and only ablates
- [ ] #6 Claims support Model.field and whole-model Model with an MRO walk; unresolved_claims finds stale claims
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `uv run pytest` passes (whole workspace)
- [ ] #2 `uv run ruff check` and `uv run pyright` are clean
- [ ] #3 New tests are pytest functions/fixtures; no network or real LLM calls
- [ ] #4 documentation/design updated in the same change if behaviour differs from it
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Worker: dispatch ctx_75001e45d79b, worktree task-66
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker (Sonnet, worktree task-66, commits 1a9e4e0 + 5f2be49): Glossary.term_for (MRO walk), whole-model claims, unresolved_claims, dictionary_block replacing prompt_block/by_field; Node.bind_upstream called by build_plan with resolved (replacement-aware) contracts; AINode.glossary is a directory loaded at bind, glossary_concepts, use_glossary=True ablation-only; LLMProfile.glossary removed; unbound AI node with glossary raises. Checks: pytest 1125 passed, ruff and pyright clean (worker-reported). core.md needed no changes. UI fixture toy-run.json regenerated (lens_version/dossier hashes only; AINode source is hashed). Review: 2 rounds. Round 1 fixed: pandera frame fields named by attribute (alias-safe, Index excluded) consistently across model_fields/term_for/unresolved_claims; unknown glossary_concepts error names the lens. Verdict: approve. Rulings: claims match on the class that declares the field (subclass claim on an inherited field is reported stale by unresolved_claims); concept lines '- (kind): **Name**: note' with no paths; toy glossary unchanged (toy AI lens inputs are float + bare list, no fields), tests define GrowthResult/list[ToxNote] nodes locally.
<!-- SECTION:FINAL_SUMMARY:END -->
