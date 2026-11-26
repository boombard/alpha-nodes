---
id: TASK-67
title: 'Units: declared on fields, formatted in AI evidence and claims'
status: In Progress
assignee: []
created_date: '2026-11-26T04:34:59Z'
updated_date: '2026-11-26T04:44:29Z'
labels:
  - core
milestone: m-5
dependencies:
  - TASK-64
references:
  - documentation/design/core.md
ordinal: 67000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Core unit mechanism (core.md "Units", written by the coordinator: implement it as written). A number's unit is declared once on the field's output contract, and the AI evidence and deterministic claim text format numbers from it. Values stay plain floats everywhere else. Domain-free: no money or currency names in lensgraph (a domain unit is a plain `Unit` with `prefix_field`).

## Files
- Create: `packages/lensgraph/src/lensgraph/units.py` (`Unit`, generic constants, `format_value`, `unit_of`, `UnitError`)
- Modify: `packages/lensgraph/src/lensgraph/lens.py` (`LensNode.bind_upstream` records the unit map and checks it; memo salt covers it plus the renderer source; `cite_units` in provenance), `ai.py` (`bind_upstream` calls super; salt combines), `deterministic.py` (claim formatting with `value`/`signed`/`raw`; component sources checked), `context.py` (`render_context` formats unit fields and frame cells), `verdict.py` (`Provenance.cite_units`), `__init__.py` (exports)
- Modify (one line each): `packages/alpha_nodes/src/alpha_nodes/lenses/{price_behaviour,quality_value,price_vs_fundamentals}.py`: `require_units: ClassVar[bool] = False  # TASK-69`
- Modify (test data): `packages/lensgraph/tests/toy/` (annotate the toy result models and frames; convert toy claim templates)
- Test: `packages/lensgraph/tests/test_units.py` (new), `test_context.py`, `test_deterministic.py`, `test_ai_lens.py`, `test_lens.py`
- Regenerate only if a hash check needs it: `packages/lensgraph-ui/fixtures/toy-run.json`, run-view types (say so in the summary; the run view itself is TASK-68)
- Docs: core.md is done; fix it only if implementation shows a wording error

## Interfaces

```python
class Unit(BaseModel):            # frozen, extra="forbid"
    id: str
    style: Literal["percent", "multiple", "number", "integer", "compact"]
    suffix: str = ""
    prefix_field: str | None = None

FRACTION, FRACTION_PER_YEAR, MULTIPLE, NUMBER, COUNT, BARS, DAYS, YEARS: Unit
def format_value(value: float | int | None, unit: Unit, row: Mapping[str, Any] | None = None, *, signed: bool = False) -> str | None
def unit_of(model: type, field: str) -> Unit | None
class UnitError(GraphError): ...
class LensNode: require_units: ClassVar[bool] = True   # False skips the plan-build unit check (temporary, until a domain annotates)
class Provenance: cite_units: dict[str, Unit] = {}
```

## Steps
- [ ] Failing tests (units): `test_percent_three_sig_figs`, `test_small_nonzero_never_prints_zero`, `test_no_scientific_notation`, `test_compact_suffixes`, `test_integer_exact`, `test_prefix_field_from_row`, `test_signed`, `test_none_stays_none`, `test_unit_of_pydantic_annotated`, `test_unit_of_pandera_metadata`, `test_unit_of_walks_mro`, `test_unit_round_trips_json`.
- [ ] Failing tests (lenses/context): `test_numeric_field_without_unit_fails_plan` (names lens, input, field), `test_bool_and_date_fields_need_no_unit`, `test_deterministic_component_source_needs_unit`, `test_evidence_formats_unit_fields`, `test_frame_cells_formatted_headers_unchanged`, `test_claim_template_value_signed_raw`, `test_provenance_records_cite_units`, `test_unit_change_changes_memo_salt`, `test_unrelated_unit_change_keeps_memo_salt`.
- [ ] Run. Expected: FAIL.
- [ ] Implement; annotate the toy models.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS. Do not annotate finance fields (TASK-69). Instead set `require_units = False` on the finance lenses, with a `# TASK-69` comment on each, so main stays green.
- [ ] Commit: `feat(lensgraph): units declared on fields, formatted in AI evidence and claims`.

Out of scope: the run view and UI (TASK-68); finance annotations (TASK-69); unit-aware run-config thresholds ("10%").
Expected side effect: every lens's memo salt changes, so lens verdicts miss the cache once.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Unit is pure data; format_value is the only formatter (3 s.f., no scientific notation, non-zero never prints zero)
- [ ] #2 A numeric field reaching a lens (AI input or deterministic component) without a unit fails the plan with UnitError naming lens, input and field
- [ ] #3 AI evidence shows unit fields formatted; frame headers unchanged
- [ ] #4 Claim templates get value, signed and raw; provenance records cite_units
- [ ] #5 Changing a used unit or the renderer changes that lens's memo salt only
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
Worker: dispatch ctx_5e2b5f6545e1, worktree task-67
<!-- SECTION:NOTES:END -->
