---
id: TASK-47
title: >-
  M5.5 Run view: chart kind for cited LineCharts and field tables for cited
  models
status: In Review
assignee: []
created_date: '2026-11-25T06:37:27Z'
updated_date: '2026-11-25T07:02:13Z'
labels:
  - core
  - ui
milestone: m-4
dependencies:
  - TASK-43
references:
  - documentation/design/core.md
type: feature
ordinal: 47000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Show cited charts and metrics in the run view. A cited `LineChart` becomes a new `CitedView` kind, `chart`, drawn as a line chart, and a cited flat model (such as a price metric result) is drawn as a two-column field/value table instead of raw JSON. Both are generic core and UI features with no finance code: the finance domain only outputs `LineChart`s and models. After TASK-43 (M5.1), in parallel with M5.3/M5.4. Spec: `documentation/design/core.md`, Reporting: run view (Domain renderers, Data sources, Python users never need Node).

## Files
- Modify (Python):
  - `packages/lensgraph/src/lensgraph/lineage.py`: `CitedValue.kind` gains `"chart"` (a resolved `LineChart` value, whole input or field)
  - `packages/lensgraph/src/lensgraph/view/models.py`: `CitedView.kind` gains `"chart"`; new field `chart: LineChart | None = None`
  - `packages/lensgraph/src/lensgraph/view/build.py`: `cited_view` fills `chart` (dates as ISO strings, None kept) for the chart kind
  - `packages/lensgraph/src/lensgraph/view/app/index.html`, `packages/lensgraph/src/lensgraph/view/app/BUILD_INFO.json` (rebuilt bundle)
  - `documentation/design/core.md`: Reporting (chart kind, the model field table; replace "domains add renderers by kind in the app (e.g. a price chart) in later milestones" with what now exists)
- Modify (UI, `packages/lensgraph-ui`):
  - `package.json`, `pnpm-lock.yaml`: add `@mui/x-charts` (community edition, MIT, the same major as `@mui/x-data-grid`)
  - `src/types/run-view.ts` (regenerated), `src/components/CitedValue.tsx` (register `chart`; `model` kind with only scalar fields → field/value table, else JSON as today)
  - Create `src/components/LineChartView.tsx`
  - Tests: `tests/unit/components/lineChart.test.tsx`, `tests/unit/components/citedValue.test.tsx` (new), `tests/unit/helpers/fixture.ts` if a chart fixture helps
- Test (Python): `packages/lensgraph/tests/test_view.py`, `packages/lensgraph/tests/test_lineage.py`, `packages/lensgraph/tests/test_view_schema.py` (regenerated fixture via `LENSGRAPH_REGEN_FIXTURES=1` if the schema hash changes)

## Interfaces
Consumes: `LineChart` (TASK-43 (M5.1)); `CitedValue`, `resolve_citation`, `CitedView`, `cited_view`, `build_run_view`, schema/type generation, `renderers` hook (M3).

Produces:
```python
# lineage.py
CitedValue.kind: Literal["frame", "model", "field", "item", "value", "chart"]   # "chart" whenever the resolved value is a LineChart
# view/models.py
class CitedView:  kind: Literal[..., "chart"];  chart: LineChart | None = None    # set iff kind == "chart"
```
```ts
// UI
export function LineChartView(props: { chart: LineChart }): JSX.Element   // one line per series, date x-axis, theme palette, legend, light/dark
renderers.chart = (cited) => <LineChartView chart={cited.chart!} />
```

## Steps
- [ ] Write the failing tests:
  - Python: `test_lineage.py::test_line_chart_cite_has_chart_kind` (whole input and model field); `test_view.py::test_cited_chart_in_run_view` (kind "chart", `chart` set, `json_value` None, None y values kept as null, x ISO dates); `test_view.py::test_cited_model_unchanged` (other models are still kind "model" with `json_value`).
  - UI: `lineChart.test.tsx` renders one series per key, with the legend names; `citedValue.test.tsx` covers chart kind → chart, flat model → field/value table, nested model → JSON block.
- [ ] Run them. Expected: FAIL.
- [ ] Implement. Regenerate the TS types (`scripts/gen-types.mjs`), then `pnpm -C packages/lensgraph-ui install`, `test`, `typecheck` and `bundle`.
- [ ] Run `uv run pytest -q`, `uv run ruff check`, `uv run pyright`, plus the pnpm `test` and `typecheck`. Expected: PASS (including the bundle up-to-date check).
- [ ] Commit: `feat(lensgraph,ui): chart kind for cited LineCharts and field tables for cited models`.

Out of scope: finance chart content (M5.3 `price_chart`); new pages; interactive chart features beyond tooltip and legend; Playwright e2e changes unless the existing ones break.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A cited LineChart resolves to kind chart with CitedView.chart set; TS types regenerated and schema test green
- [ ] #2 The UI draws chart-kind cites as a line chart (MUI X Charts community) and flat models as a field/value table
- [ ] #3 pnpm test, typecheck and bundle pass; committed bundle up to date (pytest check)
- [ ] #4 core.md Reporting updated
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
Worker: dispatch ctx_2cf2685fd968, worktree task-47 (run run_3fc22c1f4db5)
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker: CitedValue/CitedView kind 'chart' for any resolved LineChart (whole input or model field), CitedView.chart (ISO dates, null y kept); TS types and toy-run.json fixture regenerated; LineChartView (MUI X Charts 9.18.1, theme palette, legend, tooltip, gaps break lines); flat models (kind model, json_value with only scalars) drawn as a field/value table, nested models stay JSON; bundle rebuilt; core.md Reporting updated. pytest 770 passed, ruff/pyright clean, pnpm test 53/53, typecheck clean.
Coordinator review: matches ACs 1-4 and Interfaces. One fix round (6c73df9): candidate.test.tsx was already failing on main (TASK-43's fixture regeneration removed the hardcoded lens_version id); I authorised editing it, and it now derives the id from the loaded fixture. Function-local test imports moved to module top.
Open points: 2 commits, squash on landing. Out-of-Files edits: charts.py module docstring (doc only) and candidate.test.tsx (authorised). Rulings: field table only for kind 'model' with all-scalar json_value (field cites of a flat model still show JSON); numbers shown via String() at full precision; ChartHolder test model is module-level so it round-trips the blob store.
<!-- SECTION:FINAL_SUMMARY:END -->
