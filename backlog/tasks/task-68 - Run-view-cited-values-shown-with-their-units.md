---
id: TASK-68
title: 'Run view: cited values shown with their units'
status: In Review
assignee: []
created_date: '2026-11-26T04:35:00Z'
updated_date: '2026-11-26T05:23:47Z'
labels:
  - core
  - ui
milestone: m-5
dependencies:
  - TASK-67
references:
  - documentation/design/core.md
ordinal: 68000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The run view formats cited values by unit (core.md "Units" and "Reporting: run view"). The builder reads each verdict's `Provenance.cite_units`, so it needs no domain import. The UI shows Python's formatted strings and keeps the raw values for sorting, so there is no second formatter in TypeScript.

## Files
- Modify: `packages/lensgraph/src/lensgraph/view/models.py` (`CitedView.display: dict[str, str] | None`, field -> formatted, for model/field cites; `TableData.units: dict[str, str]` column -> unit id, and `TableData.display_rows: list[list[str | None]] | None`), `view/build.py` (fill them from `cite_units` with `format_value`, rows giving `prefix_field` context)
- Modify (UI): `packages/lensgraph-ui/src/` (field/value table shows `display`; DataGrid uses `display_rows` in a valueFormatter, sorts on raw, and adds unit ids to the column headers), regenerated `src/types/run-view.ts`, `fixtures/toy-run.json`, bundle and `BUILD_INFO.json`
- Test: `packages/lensgraph/tests/test_view.py`, `test_view_schema.py`; `packages/lensgraph-ui/tests/unit/` (the matching component tests)
- Docs: core.md "Reporting: run view": one bullet on display strings

## Steps
- [ ] Failing tests: `test_cited_field_has_display`, `test_cited_frame_display_rows_and_units`, `test_money_display_uses_row_prefix`, `test_cite_without_units_has_no_display` (old runs still render); UI: the display text is shown, and sorting stays numeric.
- [ ] Run. Expected: FAIL.
- [ ] Implement; regenerate the types and fixture; `pnpm -C packages/lensgraph-ui test`, `typecheck`, `bundle`.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`. Expected: PASS. Open a toy report in the browser and look at a cited table and a cited model.
- [ ] Commit: `feat(lensgraph): run view shows cited values with their units`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Cited fields and frames carry display strings formatted from cite_units, with no domain import
- [ ] #2 UI shows the display strings, sorts on raw values, and shows units in table headers
- [ ] #3 Runs without cite_units still render
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
Worker: dispatch ctx_598585b7319a, worktree task-68 (Orca run run_3877057d3c69)
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker (ctx_598585b7319a, follow-up ctx_c8d6a59de21a): CitedView.display and TableData.units/display_rows, filled by view/build.py from Provenance.cite_units via format_value (no domain import). UI shows the display strings, sorts on raw values (columns now sortable), adds unit ids to headers, tolerates old run.json without units. Types, toy fixture, bundle, core.md "Reporting: run view" bullet updated. Branch boom/task-68: a8600d5 + a000984 (squash on landing). Checks: pytest 1198 passed, ruff and pyright clean, pnpm test 60 passed, typecheck and bundle clean.

Review: 1 round, 3 findings, all resolved. (1) Tests added: single-field money cite takes its prefix from the parent row, item cite display, list-of-models table units and per-row display. (2) DRY: new lensgraph.units.units_for_cite shared by LensNode._cite_units and the view builder (lens.py, units.py, test_units.py approved outside Files). Behaviour is unchanged, checked by hand, including item ids with dots. (3) Removed a redundant field filter.

Verdict: approve.

Rulings and open points:
- A single-field cite renders as a one-row field table (field -> display).
- Editing units.py changes _renderer_fingerprint (whole-module source hash), so every lens's lens_version changes. That means a one-time cache miss for all lenses, AI included, and a regenerated toy-run.json.
- Not checked in a browser: the toy run has no units, so the new display strings need a unit-bearing run (finance, after TASK-69) to see.
<!-- SECTION:FINAL_SUMMARY:END -->
