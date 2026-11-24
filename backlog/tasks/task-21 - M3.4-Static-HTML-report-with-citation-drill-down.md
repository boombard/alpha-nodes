---
id: TASK-21
title: M3.4 RunView contract, run.json export and generated TS types
status: In Review
assignee: []
created_date: '2026-11-23T23:51:15Z'
updated_date: '2026-11-24T01:45:06Z'
labels:
  - core
milestone: m-2
dependencies:
  - TASK-19
  - TASK-20
references:
  - documentation/design/core.md
type: feature
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Python side of the run view. Decided 2026-11-24 (human): the end-of-run report and the future live view are **one React app** reading **one data contract**. `run.json` is the source of truth now; a DB/API serves the same shape later. This task builds the contract and the data export; TASK-24 builds the app. Spec: `documentation/design/core.md`, Reporting, and "Run view: one app, one contract".

## Files
- Create: `packages/lensgraph/src/lensgraph/view/{__init__,models,build,schema}.py`, `packages/lensgraph-ui/src/types/run-view.ts` (generated), `packages/lensgraph-ui/fixtures/toy-run.json` (generated)
- Modify: `packages/lensgraph/src/lensgraph/plangraph.py` (map `DossierReviewer` to kind "reviewer"), `packages/lensgraph/src/lensgraph/__init__.py` (exports), `documentation/design/core.md` (Reporting)
- Test: `packages/lensgraph/tests/{test_view,test_view_schema}.py`

## Interfaces
Consumes: `DossierRecord`, `DossierReview`, `LLMCall`, `PlanGraph`, `RunIndex` (`run_config`, `node_results`, `node_result`, `llm_calls`, `plan_graph`), `BlobStore`, `resolve_all`/`CitedValue`/`UnresolvedCitation`.

Produces:
```python
# view/models.py  (frozen, extra="forbid"; the contract the UI is typed against)
class TableData(BaseModel): columns: list[str]; rows: list[list[Any]]; total_rows: int; truncated: bool
class CitedView(BaseModel):
    id: str                                   # stable: f"{source_hash[:16]}:{cite}"
    cite: str; source_hash: str
    kind: Literal["frame", "model", "field", "item", "value"]
    table: TableData | None = None            # frames, lists of models
    json_value: Any = None                    # models, fields, items, scalars (JSON-safe)
class ClaimRef(BaseModel): lens: str; claim_index: int; cites: dict[str, str | None]   # cite -> CitedView.id, None if unresolved
class CandidateView(BaseModel):
    id: str; record: DossierRecord; claims: list[ClaimRef]
    node_status: dict[str, NodeStatus]        # node name -> status for this candidate (and shared nodes)
class RunSummary(BaseModel):
    run_id: str; status: str; started_at: datetime | None; finished_at: datetime | None
    config: dict[str, Any]; node_counts: dict[NodeStatus, int]; cache_hits: int
    llm_input_tokens: int; llm_output_tokens: int; llm_cost_usd: float | None   # None if any call's cost is unknown
class RunView(BaseModel):
    schema_version: Literal[1] = 1
    summary: RunSummary; plan: PlanGraph; candidates: list[CandidateView]
    cited: dict[str, CitedView]               # by CitedView.id, deduplicated
    llm_calls: list[LLMCall]
# view/build.py
def build_run_view(run_id: str, index: RunIndex, blobs: BlobStore, *, max_rows: int = 200) -> RunView
def write_run_view(view: RunView, out_dir: Path) -> Path
    # writes out_dir/run.json (the contract) and out_dir/data/run.js ("window.__RUN__ = <same JSON>;"), returns run.json
# view/schema.py
def run_view_schema() -> dict[str, Any]       # RunView.model_json_schema()
```
Semantics:
- **Data comes only from the index and blobs:** the panel and aggregator from `run_config`, dossiers and reviews via `node_result` and then blobs, citations via `resolve_all` per verdict. An `UnresolvedCitation` maps the cite to None; it never raises.
- **JSON-safe:** frames become `TableData` (the last `max_rows` rows, `truncated` set); non-finite floats become null; datetimes become ISO strings.
- **Deterministic:** the same run gives byte-identical `run.json` (sorted keys, stable ordering), so the file can be diffed and snapshotted.
- **TypeScript types are generated, not hand-written:** `packages/lensgraph-ui/src/types/run-view.ts` comes from `run_view_schema()` via `json-schema-to-typescript`, run through `pnpm dlx` from a small script, `packages/lensgraph-ui/scripts/gen-types.mjs`. Allowed extra file: that script, plus a minimal `packages/lensgraph-ui/package.json` if it doesn't exist yet; TASK-24 owns the rest of the UI package.
- **Drift test:** `test_view_schema.py` regenerates the schema and fails if the committed `run-view.ts` header hash differs. Embed the schema hash in a comment on the generated file's first line, so the test needs no Node.
- **Fixture for the UI:** `fixtures/toy-run.json` is the toy panel run (with reviewer) through `build_run_view`, written by a test helper. The test asserts the committed fixture is up to date, and a `--regen` style env var (`LENSGRAPH_REGEN_FIXTURES=1`) rewrites it.

## Steps
- [ ] Write the failing tests:
  - `test_view.py`:
    - `test_run_view_toy_shape`: 3 candidates; S3 has no overall stance; the plan has every node; the reviewer node's kind is "reviewer".
    - `test_cited_values_resolved_and_deduplicated`: a growth claim's cite maps to a CitedView holding the stored value; the same blob cited twice appears once.
    - `test_unresolved_cite_is_null_not_error`: delete a blob, rebuild, the cite maps to None.
    - `test_frame_truncated_to_max_rows`
    - `test_llm_cost_none_when_any_unknown`
    - `test_run_json_deterministic`: two builds are byte-identical.
    - `test_run_js_matches_run_json`: `data/run.js` wraps exactly the run.json content.
  - `test_view_schema.py`:
    - `test_ts_types_up_to_date` (schema hash comparison)
    - `test_ui_fixture_up_to_date`
- [ ] Run `uv run pytest packages/lensgraph/tests/test_view.py packages/lensgraph/tests/test_view_schema.py -q`. Expected: FAIL.
- [ ] Implement; generate `run-view.ts` and the fixture.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): RunView contract, run.json export and generated TS types`.

Out of scope: the React app (TASK-24), CLI wiring (TASK-22), live events and API (TASK-23).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 RunView (summary, plan, candidates with DossierRecords and claim refs, deduplicated cited values, LLM calls) is built from the index and blobs alone
- [ ] #2 run.json is deterministic and JSON-safe; data/run.js embeds the same content for file:// use
- [ ] #3 Unresolved citations map to null, never raise; frames are truncated with a flag
- [ ] #4 TS types and the UI fixture are generated from the Python models, with drift tests that need no Node
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
Worker: dispatch ctx_2c47f55bf4ee, worktree task-21
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Worker (Sonnet, dispatch ctx_2c47f55bf4ee, branch boom/task-21, 3 commits 74dc726..0cbaf3d): lensgraph.view (models: RunView, RunSummary, CandidateView with ClaimRef and FlagRef, CitedView, TableData; build_run_view and write_run_view writing run.json and data/run.js; json_safe; schema), reviewer node kind in plangraph, RunInfo and RunIndex.run_info (DuckDB and memory, UTC times), packages/lensgraph-ui/{package.json, scripts/gen-types.mjs, src/types/run-view.ts (generated, schema hash on line 1), fixtures/toy-run.json (generated)}, core.md updated. ACs 1-4 met (test_view.py: shape, resolved and deduplicated cites, null cite, truncation, cost None, determinism, run.js equality, flag cites, created_at fallbacks; test_view_schema.py: TS hash and fixture drift, no Node needed). Coordinator re-ran checks: pytest 310 passed, ruff clean, pyright 0 errors; no 1970 placeholder left in the fixture.
Coordinator review, one fix round: no placeholder data in the contract. Run status and times come from the new RunIndex.run_info; DossierRecord.created_at is the run's finish (else start) time, and a run with neither raises. Fixed run id and times live only in the test helper. Flag citations are resolved like claims (FlagRef); review cites stay unresolved, as documented.
Rulings: root pyproject excludes packages/lensgraph-ui from the uv workspace (uv rejects a member without pyproject; TASK-24 relies on it); resolve_citation is called per cite (resolve_all raises on the first failure); candidates are in plan order and LLM calls sorted; test helper tests/toy/toy_view.py; types generated with json-schema-to-typescript@15.0.4 in serialization mode (defaulted fields required); DuckDB times are now UTC (rows in older index files stay local-time naive).
<!-- SECTION:FINAL_SUMMARY:END -->
