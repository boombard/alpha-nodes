---
id: TASK-19
title: M3.2 Citation lineage and LLM call cost
status: In Progress
assignee: []
created_date: '2026-11-23T23:51:14Z'
updated_date: '2026-11-24T01:19:39Z'
labels:
  - core
milestone: m-2
dependencies:
  - TASK-18
references:
  - documentation/design/core.md
type: feature
ordinal: 19000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Lineage and LLM cost. Runs in parallel with M3.3. Spec: `documentation/design/core.md`, Artifact store and run index ("any citable id resolves to a stored output"). Also see the TASK-10 note on cost per LLM call.

## Files
- Create: `packages/lensgraph/src/lensgraph/lineage.py`, `packages/lensgraph/src/lensgraph/cost.py`
- Modify:
  - `packages/lensgraph/src/lensgraph/store/duckdb_index.py`: implement `record_llm_call`, `llm_calls`, `run_config`, `node_result` (new table `llm_calls`).
  - `packages/lensgraph/src/lensgraph/run.py`: after a successful or aborted execute, record LLM calls (`cost.llm_calls_from_result`).
- Test: `packages/lensgraph/tests/{test_lineage,test_cost}.py`, plus DuckDB cases added to `packages/lensgraph/tests/test_duckdb_index.py`

## Interfaces
Consumes (M3.1): `LLMCall`, `RunIndex` (new methods), `DossierReview`. Earlier: `LensVerdict`, `Provenance`, `BlobStore`, `RunResult`, `content_hash`, `citable_ids`.

Produces:
```python
# lineage.py
class CitedValue(BaseModel):                         # arbitrary_types_allowed
    cite: str; source_hash: str; value: Any          # value: frame, model, scalar, list item...
    kind: Literal["frame", "model", "field", "item", "value"]
class UnresolvedCitation(LookupError): ...
def resolve_citation(verdict: LensVerdict, cite: str, blobs: BlobStore) -> CitedValue
def resolve_all(verdict: LensVerdict, blobs: BlobStore) -> dict[str, CitedValue]   # every cite in claims and flags
# cost.py
def price_usd(model: str, input_tokens: int, output_tokens: int) -> float | None
def llm_calls_from_result(run_id: str, result: RunResult) -> list[LLMCall]
```
Semantics:
- **Resolution uses the verdict's provenance, so it needs no extra table.** For cite `n`, `n.field` or `n[id]`, `h = verdict.provenance.input_hashes[n]`; load `blobs.get(h)`, then take the field (`getattr`) or the list item whose `id == id`. A missing input hash, a missing blob, field or item raises `UnresolvedCitation` naming the cite. Cache hits resolve the same way, because input hashes are content hashes.
- **`price_usd`:** a model string `"provider:name"` is split for genai-prices (`calc_price(usage, model_ref=name, provider_id=provider)`, with a genai-prices `Usage(input_tokens=..., output_tokens=...)`). Unknown model or provider gives None, never 0. Use the bundled price snapshot; never call `update_prices` (no network).
- **`llm_calls_from_result`:** one `LLMCall` per value in `result.values` that has `provenance.model` set (AI lens verdicts and, from M3.3, `DossierReview`s), **skipping cache hits** (`result.results[key].cache_hit`), because no call was made this run. Tokens and attempts come from provenance.
- **`arun`:** after execute, `index.record_llm_call` for each call. On `RunAborted`, record from `exc.result` before re-raising.

## Steps
- [ ] Write the failing tests:
  - `test_lineage.py` (run the toy panel with `InMemoryBlobStore` through the executor, or build verdicts by hand with a stored blob):
    - `test_resolve_node_level_frame`: the growth lens's `growth_rate` cite resolves to the stored float (kind "value").
    - `test_resolve_list_item_by_id`: the safety lens citing `tox_notes[S1-n1]` resolves to that `ToxNote` (kind "item").
    - `test_resolve_model_field`: a model input's `n.field` resolves to the field value.
    - `test_unresolved_citation_names_cite`: unknown input, missing item id and missing blob each raise `UnresolvedCitation` containing the cite.
    - `test_resolve_after_cache_hit`: rerun and resolve from the second run's verdict.
  - `test_cost.py`:
    - `test_price_known_model`: a model present in the bundled genai-prices snapshot gives a positive price (pick one and assert > 0, not an exact figure).
    - `test_price_unknown_model_is_none`
    - `test_llm_calls_skip_cache_hits`: first toy panel run records one call per candidate with a safety verdict; an identical rerun records none.
    - `test_llm_calls_recorded_in_index`: after `run`, `DuckDBRunIndex.llm_calls(run_id)` matches.
  - `test_duckdb_index.py`: `test_llm_calls_roundtrip`, `test_run_config_roundtrip`, `test_node_result_lookup`.
- [ ] Run `uv run pytest packages/lensgraph/tests/test_lineage.py packages/lensgraph/tests/test_cost.py packages/lensgraph/tests/test_duckdb_index.py -q`. Expected: FAIL.
- [ ] Implement.
- [ ] Run `uv run pytest -q`, then the DoD checks. Expected: PASS.
- [ ] Commit: `feat(lensgraph): citation lineage and LLM call cost`.

**Added 2026-11-24 (for reports now and a live run view later):** persist the plan graph at run start.
- `RunIndex` gains `record_plan(run_id: str, plan: ExecutionPlan) -> None` and `plan_graph(run_id: str) -> PlanGraph`, where `PlanGraph(BaseModel)` has `nodes: list[PlanNode]` (`key: NodeKey`, `scope`, `kind`: the node's base kind fetch/transform/calc/lens/aggregator/reviewer/other) and `edges: list[PlanEdge]` (`source: NodeKey`, `target: NodeKey`, `kwarg: str`, `optional: bool`). Put the models in plan.py and the protocol methods in store/base.py; implement both in memory.py and duckdb_index.py (tables `plan_nodes`, `plan_edges`).
- `arun` calls `record_plan` right after `start_run`, before executing.
- Allowed extra files: `plan.py`, `store/base.py`, `store/memory.py`.
- Tests: `test_plan_graph_roundtrip` (memory and DuckDB): node and edge counts match the plan, optional edges flagged, shared nodes once.

Out of scope: rendering (M3.4); verdicts/dossiers tables (derivable from node_results + blobs; add when campaigns need queries).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every cite in a verdict resolves via provenance input hashes to a stored value, or raises UnresolvedCitation naming it
- [ ] #2 LLM calls are recorded per run with tokens and genai-prices cost (None when unknown); cache hits record no call
- [ ] #3 DuckDB implements llm_calls, run_config and node_result
- [ ] #4 The plan graph (nodes, edges, kinds) is recorded at run start and readable from both index implementations
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
Worker: dispatch ctx_cfc637929a54, worktree task-19
<!-- SECTION:NOTES:END -->
